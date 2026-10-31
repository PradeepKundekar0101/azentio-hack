"""Processing run: load claims in scope, evaluate rules per policy, then duplicates and alerts; replace earlier results.

Stages are plain functions over loaded data so each can later become a graph node.
"""

import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.build import build_alerts
from app.core.config import Settings
from app.core.enums import RunScope, RunStatus
from app.core.logging import get_logger
from app.db.models import (
    Alert,
    Claim,
    DuplicateMatch,
    LineItem,
    PayableStep,
    Policy,
    PolicyRule,
    ProcessingRun,
    Settlement,
    ValidationResult,
)
from app.db.session import Database
from app.duplicates.detect import detect_duplicates
from app.evidence import service as evidence
from app.graph.service import build_graph
from app.rules.context import ClaimData, Evaluation, LineData, PolicyData, RuleData, SettlementData
from app.rules.payable import RULES_VERSION, evaluate_policy

log = get_logger(__name__)
CHUNK = 5000


async def _policies_in_scope(session: AsyncSession, scope: RunScope, batch_id: int | None) -> list[str]:
    if scope is RunScope.ALL:
        return list(await session.scalars(select(Policy.policy_number)))
    # A batch's claims depend on every earlier claim of the same policies (per-period limits, overall limit).
    return list(await session.scalars(select(Claim.policy_number).where(Claim.import_batch_id == batch_id).distinct()))


async def load_claims(session: AsyncSession, policy_numbers: list[str]) -> dict[str, Any]:
    policies = {
        p.policy_number: PolicyData(
            p.policy_number,
            tuple(p.insured_member_ids),
            p.benefit_period_start,
            p.benefit_period_end,
            p.overall_limit,
            p.deductible_amount,
            p.deductible_basis,
            p.copay_percent,
        )
        for p in await session.scalars(select(Policy).where(Policy.policy_number.in_(policy_numbers)))
    }
    rules: dict[str, list[RuleData]] = defaultdict(list)
    for r in await session.scalars(
        select(PolicyRule).where(PolicyRule.policy_number.in_(policy_numbers)).order_by(PolicyRule.rule_id)
    ):
        rules[r.policy_number].append(
            RuleData(r.rule_id, r.rule_type, r.scope_type, r.scope_value, r.limit_basis, r.limit_amount, r.clause_ref)
        )
    claim_rows = list(await session.scalars(select(Claim).where(Claim.policy_number.in_(policy_numbers))))
    claim_ids = [c.claim_id for c in claim_rows]
    lines: dict[str, list[LineData]] = defaultdict(list)
    line_rows: list[LineItem] = []
    settlements: dict[str, SettlementData] = {}
    for start in range(0, len(claim_ids), CHUNK):
        ids = claim_ids[start : start + CHUNK]
        for ln in await session.scalars(select(LineItem).where(LineItem.claim_id.in_(ids)).order_by(LineItem.line_id)):
            line_rows.append(ln)
            lines[ln.claim_id].append(
                LineData(
                    ln.line_id,
                    ln.service_date,
                    ln.service_code,
                    ln.service_description,
                    ln.category,
                    ln.quantity,
                    ln.unit_price,
                    ln.line_amount,
                )
            )
        for s in await session.scalars(
            select(Settlement).where(Settlement.claim_id.in_(ids)).order_by(Settlement.settlement_date)
        ):
            settlements[s.claim_id] = SettlementData(
                s.settlement_id, s.settlement_date, s.approved_amount, s.paid_amount, s.settlement_status
            )
    claims: dict[str, list[ClaimData]] = defaultdict(list)
    for c in claim_rows:
        claims[c.policy_number].append(
            ClaimData(
                c.claim_id,
                c.claimant_id,
                c.incident_date,
                c.submission_date,
                c.claim_type,
                c.requested_amount,
                c.status,
                tuple(lines[c.claim_id]),
                settlements.get(c.claim_id),
            )
        )
    return {
        "policies": policies,
        "rules": rules,
        "claims": claims,
        "claim_rows": claim_rows,
        "line_rows": line_rows,
    }


def run_rules(loaded: dict[str, Any]) -> tuple[list[Evaluation], list[dict[str, str]]]:
    evaluations: list[Evaluation] = []
    failures: list[dict[str, str]] = []
    for number, policy in loaded["policies"].items():
        claims = loaded["claims"].get(number, [])
        try:
            evaluations.extend(evaluate_policy(policy, tuple(loaded["rules"].get(number, [])), claims))
        except Exception as exc:  # one policy's bad data never stops the run
            log.exception("policy_evaluation_failed", policy_number=number)
            failures.extend({"claim_id": c.claim_id, "error": f"{type(exc).__name__}: {exc}"} for c in claims)
    return evaluations, failures


def _result_rows(run_id: int, evaluations: list[Evaluation]) -> tuple[list[dict], list[dict]]:
    results, steps = [], []
    for evaluation in evaluations:
        for r in evaluation.results:
            results.append(
                {
                    "run_id": run_id,
                    "claim_id": evaluation.claim_id,
                    "line_id": r.line_id,
                    "check_code": r.check_code,
                    "policy_rule_id": r.policy_rule_id,
                    "outcome": r.outcome.value,
                    "expected": r.expected,
                    "actual": r.actual,
                    "amount_impact": r.amount_impact,
                    "inputs": r.inputs,
                    "explanation": r.explanation,
                }
            )
        for number, s in enumerate(evaluation.steps, start=1):
            steps.append(
                {
                    "run_id": run_id,
                    "claim_id": evaluation.claim_id,
                    "step_no": number,
                    "step_code": s.step_code,
                    "amount_before": s.amount_before,
                    "amount_after": s.amount_after,
                    "reduction": s.reduction,
                    "policy_rule_id": s.policy_rule_id,
                    "explanation": s.explanation,
                }
            )
    return results, steps


async def _insert(session: AsyncSession, model: type, rows: list[dict]) -> None:
    for start in range(0, len(rows), CHUNK):
        # Core insert on the table: every row keeps the same columns, so rows go out in large multi-row batches
        # (ORM bulk insert splits batches whenever a row's non-null columns differ, one round trip each).
        await session.execute(insert(model.__table__), rows[start : start + CHUNK])


async def _clear(session: AsyncSession, claim_ids: list[str]) -> None:
    for start in range(0, len(claim_ids), CHUNK):
        ids = claim_ids[start : start + CHUNK]
        for model in (Alert, DuplicateMatch, PayableStep, ValidationResult):
            await session.execute(delete(model).where(model.claim_id.in_(ids)))


async def execute_run(session: AsyncSession, run: ProcessingRun, settings: Settings) -> ProcessingRun:
    timings: dict[str, float] = {}
    clock = time.monotonic()

    def lap(stage: str) -> None:
        nonlocal clock
        now = time.monotonic()
        timings[stage] = round(now - clock, 2)
        clock = now

    policy_numbers = await _policies_in_scope(session, RunScope(run.scope), run.batch_id)
    loaded = await load_claims(session, policy_numbers)
    lap("load")
    evaluations, failures = run_rules(loaded)
    lap("rules")
    matches = await detect_duplicates(session, loaded, run.id, settings.near_duplicate_threshold)
    lap("duplicates")
    alerts = build_alerts(run.id, loaded, evaluations, matches, settings)

    claim_ids = [c.claim_id for c in loaded["claim_rows"]]
    await _clear(session, claim_ids)
    lap("clear")
    results, steps = _result_rows(run.id, evaluations)
    await _insert(session, ValidationResult, results)
    await _insert(session, PayableStep, steps)
    await _insert(session, DuplicateMatch, matches)
    await _insert(session, Alert, alerts)
    lap("insert")
    # Cross-claim correlation over every claim (links cross policies), in the same transaction.
    await build_graph(session, settings, run_id=run.id)
    lap("graph")
    await evidence.capture_rerun(session, claim_ids, run.id)
    lap("evidence")

    run.claims_processed = len(evaluations)
    run.claims_failed = len(failures)
    run.failures = failures or None
    run.status = RunStatus.COMPLETED.value
    run.finished_at = datetime.now(UTC)
    await session.commit()
    lap("commit")
    log.info(
        "run_finished",
        run_id=run.id,
        claims=len(evaluations),
        failed=len(failures),
        alerts=len(alerts),
        seconds=timings,
    )
    return run


async def start_run(session: AsyncSession, scope: RunScope, batch_id: int | None) -> ProcessingRun:
    run = ProcessingRun(
        status=RunStatus.RUNNING.value, scope=scope.value, batch_id=batch_id, rules_version=RULES_VERSION
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def run_in_background(database: Database, settings: Settings, run_id: int) -> None:
    async with database.sessionmaker() as session:
        run = await session.get(ProcessingRun, run_id)
        if run is None:  # pragma: no cover
            return
        try:
            await execute_run(session, run, settings)
        except Exception as exc:
            log.exception("run_failed", run_id=run_id)
            await session.rollback()
            run = await session.get(ProcessingRun, run_id)
            if run is not None:
                run.status = RunStatus.FAILED.value
                run.error = f"{type(exc).__name__}: {exc}"
                run.finished_at = datetime.now(UTC)
                await session.commit()
