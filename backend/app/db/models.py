"""Every table in the plan. Core tables mirror the input contracts; the rest record imports, every rule
evaluation, duplicate decisions and alerts, so every number on screen traces back to a stored record."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core import enums

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Money = Annotated[Decimal, mapped_column(Numeric(12, 2))]
Json = Annotated[Any, mapped_column(JSONB)]
CreatedAt = Annotated[datetime, mapped_column(DateTime(timezone=True), server_default=func.now())]
IntId = Annotated[int, mapped_column(BigInteger, Identity(), primary_key=True)]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def one_of(column: str, values: type[StrEnum], name: str | None = None) -> CheckConstraint:
    allowed = ", ".join(f"'{v.value}'" for v in values)
    return CheckConstraint(f"{column} in ({allowed})", name=name or column)


def batch_fk() -> Mapped[int | None]:
    return mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"))


def claim_fk(nullable: bool = False) -> Mapped[Any]:
    return mapped_column(String(20), ForeignKey("claims.claim_id", ondelete="CASCADE"), nullable=nullable)


def run_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("processing_runs.id", ondelete="CASCADE"))


# Reference data


class ServiceCode(Base):
    __tablename__ = "service_codes"
    __table_args__ = (one_of("category", enums.Category),)

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(20))
    repeatable: Mapped[bool]
    min_interval_days: Mapped[int | None]
    max_per_week: Mapped[int | None]


class Provider(Base):
    __tablename__ = "providers"

    provider_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)


# Imports


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (one_of("status", enums.BatchStatus),)

    id: Mapped[IntId]
    uploaded_by: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[CreatedAt]
    files: Mapped[Json]  # [{"file_name", "storage_key", "size", "content_type", "datasets"}]
    status: Mapped[str] = mapped_column(String(20))
    counts: Mapped[Json]  # {dataset: {"received", "accepted", "warnings", "rejected"}}
    error: Mapped[str | None] = mapped_column(Text)


class ImportIssue(Base):
    __tablename__ = "import_issues"
    __table_args__ = (one_of("severity", enums.IssueSeverity),)

    id: Mapped[IntId]
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), index=True)
    dataset: Mapped[str | None] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(Text)
    sheet: Mapped[str | None] = mapped_column(Text)
    row_number: Mapped[int | None] = mapped_column(Integer)
    field: Mapped[str | None] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    raw_row: Mapped[Json | None]


# Core tables (mirror the input contracts). source_row is {"file_name", "sheet", "row_number"}.


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        one_of("deductible_basis", enums.DeductibleBasis),
        CheckConstraint("benefit_period_end > benefit_period_start", name="benefit_period_order"),
        CheckConstraint("copay_percent between 0 and 50", name="copay_percent_range"),
    )

    policy_number: Mapped[str] = mapped_column(String(20), primary_key=True)
    policyholder_name: Mapped[str] = mapped_column(Text)
    insured_member_ids: Mapped[list[str]] = mapped_column(ARRAY(Text))
    product_name: Mapped[str] = mapped_column(Text)
    benefit_period_start: Mapped[date] = mapped_column(Date)
    benefit_period_end: Mapped[date] = mapped_column(Date)
    overall_limit: Mapped[Money]
    deductible_amount: Mapped[Money]
    deductible_basis: Mapped[str] = mapped_column(String(20))
    copay_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    import_batch_id: Mapped[int | None] = batch_fk()
    source_row: Mapped[Json | None]


class PolicyRule(Base):
    __tablename__ = "policy_rules"
    __table_args__ = (
        one_of("rule_type", enums.RuleType),
        one_of("scope_type", enums.ScopeType),
        one_of("limit_basis", enums.LimitBasis),
        CheckConstraint(
            "rule_type <> 'sub_limit' or (limit_basis is not null and limit_amount > 0)", name="sub_limit_terms"
        ),
    )

    rule_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    policy_number: Mapped[str] = mapped_column(
        String(20), ForeignKey("policies.policy_number", ondelete="CASCADE"), index=True
    )
    rule_type: Mapped[str] = mapped_column(String(20))
    scope_type: Mapped[str] = mapped_column(String(20))
    scope_value: Mapped[str] = mapped_column(String(40))
    limit_basis: Mapped[str | None] = mapped_column(String(20))
    limit_amount: Mapped[Money | None]
    clause_ref: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    import_batch_id: Mapped[int | None] = batch_fk()
    source_row: Mapped[Json | None]


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        one_of("claim_type", enums.ClaimType),
        one_of("status", enums.ClaimStatus),
        one_of("source", enums.ClaimSource),
        Index("ix_claims_claimant_id_incident_date", "claimant_id", "incident_date"),
    )

    claim_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    policy_number: Mapped[str] = mapped_column(String(20), ForeignKey("policies.policy_number"), index=True)
    claimant_id: Mapped[str] = mapped_column(String(40))
    claimant_name: Mapped[str] = mapped_column(Text)
    incident_date: Mapped[date] = mapped_column(Date)
    submission_date: Mapped[date] = mapped_column(Date)
    claim_type: Mapped[str] = mapped_column(String(20))
    requested_amount: Mapped[Money]
    incident_reference: Mapped[str | None] = mapped_column(Text)
    incident_reference_norm: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(10), server_default=enums.ClaimSource.FILE.value)
    import_batch_id: Mapped[int | None] = batch_fk()
    source_row: Mapped[Json | None]
    created_at: Mapped[CreatedAt]


class LineItem(Base):
    __tablename__ = "line_items"
    __table_args__ = (
        one_of("category", enums.Category),
        Index("ix_line_items_service_code_service_date", "service_code", "service_date"),
    )

    line_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(20), ForeignKey("claims.claim_id", ondelete="CASCADE"), index=True)
    invoice_reference: Mapped[str] = mapped_column(Text)
    invoice_reference_norm: Mapped[str] = mapped_column(Text, index=True)
    provider_id: Mapped[str] = mapped_column(String(10))
    provider_name: Mapped[str] = mapped_column(Text)
    service_date: Mapped[date] = mapped_column(Date)
    service_code: Mapped[str] = mapped_column(String(20), ForeignKey("service_codes.code"))
    service_description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit_price: Mapped[Money]
    line_amount: Mapped[Money]
    import_batch_id: Mapped[int | None] = batch_fk()
    source_row: Mapped[Json | None]


class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (one_of("settlement_status", enums.SettlementStatus),)

    settlement_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(20), ForeignKey("claims.claim_id", ondelete="CASCADE"), index=True)
    settlement_date: Mapped[date] = mapped_column(Date)
    approved_amount: Mapped[Money]
    paid_amount: Mapped[Money]
    settlement_status: Mapped[str] = mapped_column(String(20))
    import_batch_id: Mapped[int | None] = batch_fk()
    source_row: Mapped[Json | None]


# Processing results


class ProcessingRun(Base):
    __tablename__ = "processing_runs"
    __table_args__ = (one_of("status", enums.RunStatus), one_of("scope", enums.RunScope))

    id: Mapped[IntId]
    started_at: Mapped[CreatedAt]
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(10))
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"))
    claims_processed: Mapped[int] = mapped_column(Integer, server_default="0")
    claims_failed: Mapped[int] = mapped_column(Integer, server_default="0")
    failures: Mapped[Json | None]  # [{"claim_id", "error"}]
    rules_version: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text)


class ValidationResult(Base):
    __tablename__ = "validation_results"
    __table_args__ = (one_of("outcome", enums.Outcome), Index("ix_validation_results_claim_id", "claim_id"))

    id: Mapped[IntId]
    run_id: Mapped[int] = run_fk()
    claim_id: Mapped[str] = claim_fk()
    line_id: Mapped[str | None] = mapped_column(String(30), ForeignKey("line_items.line_id", ondelete="CASCADE"))
    check_code: Mapped[str] = mapped_column(String(40))
    policy_rule_id: Mapped[str | None] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(20))
    expected: Mapped[str | None] = mapped_column(Text)
    actual: Mapped[str | None] = mapped_column(Text)
    amount_impact: Mapped[Money]
    inputs: Mapped[Json | None]
    explanation: Mapped[str] = mapped_column(Text)


class PayableStep(Base):
    __tablename__ = "payable_steps"
    __table_args__ = (Index("ix_payable_steps_claim_id", "claim_id"),)

    id: Mapped[IntId]
    run_id: Mapped[int] = run_fk()
    claim_id: Mapped[str] = claim_fk()
    step_no: Mapped[int] = mapped_column(Integer)
    step_code: Mapped[str] = mapped_column(String(40))
    amount_before: Mapped[Money]
    amount_after: Mapped[Money]
    reduction: Mapped[Money]
    policy_rule_id: Mapped[str | None] = mapped_column(String(40))
    explanation: Mapped[str] = mapped_column(Text)


class DuplicateMatch(Base):
    __tablename__ = "duplicate_matches"
    __table_args__ = (
        one_of("matched_source", enums.MatchSource),
        one_of("match_type", enums.MatchType),
        one_of("decision", enums.MatchDecision),
        Index("ix_duplicate_matches_claim_id", "claim_id"),
    )

    id: Mapped[IntId]
    run_id: Mapped[int] = run_fk()
    claim_id: Mapped[str] = claim_fk()
    line_id: Mapped[str | None] = mapped_column(String(30), ForeignKey("line_items.line_id", ondelete="CASCADE"))
    matched_claim_id: Mapped[str] = claim_fk()
    matched_line_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("line_items.line_id", ondelete="CASCADE")
    )
    matched_source: Mapped[str] = mapped_column(String(20))
    match_type: Mapped[str] = mapped_column(String(30))
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    signals: Mapped[Json | None]
    decision: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(Text)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        one_of("category", enums.AlertCategory),
        one_of("severity", enums.Severity),
        one_of("amount_type", enums.AmountType),
        one_of("status", enums.AlertStatus),
        CheckConstraint("run_id is not null or graph_build_id is not null", name="raised_by"),
        Index("ix_alerts_category_severity", "category", "severity"),
        Index("ix_alerts_claim_id", "claim_id"),
    )

    id: Mapped[IntId]
    # Stable across runs ("ALR-" + a hash of what the alert is about), so decisions can reference it.
    finding_id: Mapped[str] = mapped_column(String(20), index=True)
    # Raised by a processing run (rules, duplicates, documents) or by a graph build (cross-claim alerts).
    run_id: Mapped[int | None] = mapped_column(ForeignKey("processing_runs.id", ondelete="CASCADE"))
    graph_build_id: Mapped[int | None] = mapped_column(ForeignKey("graph_builds.build_id", ondelete="CASCADE"))
    claim_id: Mapped[str] = claim_fk()
    line_id: Mapped[str | None] = mapped_column(String(30), ForeignKey("line_items.line_id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Money | None]
    amount_type: Mapped[str] = mapped_column(String(10))
    calculation: Mapped[str | None] = mapped_column(Text)
    rule_or_pattern: Mapped[str] = mapped_column(String(40))
    policy_rule_id: Mapped[str | None] = mapped_column(String(40))
    explanation: Mapped[str] = mapped_column(Text)
    supporting: Mapped[Json]
    status: Mapped[str] = mapped_column(String(20), server_default=enums.AlertStatus.OPEN.value)
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    # Set while an alert waits for a senior claims reviewer or the SIU; cleared when they decide it.
    escalated_to: Mapped[str | None] = mapped_column(String(20))
    escalated_by: Mapped[str | None] = mapped_column(String(100))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[CreatedAt]


class GraphBuild(Base):
    """One build of the correlation graph. `groups` lists the (group_id, version) pairs current in this build."""

    __tablename__ = "graph_builds"

    build_id: Mapped[IntId]
    started_at: Mapped[CreatedAt]
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scope: Mapped[Json]  # {"claim_ids": [...]} or {"all": true}
    node_count: Mapped[int] = mapped_column(Integer, server_default="0")
    edge_count: Mapped[int] = mapped_column(Integer, server_default="0")
    group_count: Mapped[int] = mapped_column(Integer, server_default="0")
    config: Mapped[Json]
    groups: Mapped[Json | None]  # [{"group_id", "version"}]
    run_id: Mapped[int | None] = mapped_column(ForeignKey("processing_runs.id", ondelete="SET NULL"))


class GraphNode(Base):
    """One distinct entity, keyed on normalised identifiers: node_id is "<node_type>:<node_key>"."""

    __tablename__ = "graph_nodes"
    __table_args__ = (one_of("node_type", enums.NodeType),)

    node_id: Mapped[str] = mapped_column(Text, primary_key=True)
    node_type: Mapped[str] = mapped_column(String(20))
    node_key: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    attributes: Mapped[Json | None]


class GraphEdge(Base):
    """Claim-to-entity edges are structural; claim-to-claim edges are links with the evidence that made them."""

    __tablename__ = "graph_edges"
    __table_args__ = (
        one_of("strength", enums.EdgeStrength),
        Index("ix_graph_edges_build_id_from_node", "build_id", "from_node"),
        Index("ix_graph_edges_build_id_to_node", "build_id", "to_node"),
    )

    edge_id: Mapped[IntId]
    build_id: Mapped[int] = mapped_column(ForeignKey("graph_builds.build_id", ondelete="CASCADE"))
    from_node: Mapped[str] = mapped_column(Text)
    to_node: Mapped[str] = mapped_column(Text)
    edge_type: Mapped[str] = mapped_column(String(40))
    strength: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[Json | None]  # {"fields": [...], "values": {...}, "source_records": {...}}
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))


class RelationshipGroup(Base):
    """A related-claim group; a new version is written only when its content changes."""

    __tablename__ = "relationship_groups"

    group_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    build_id: Mapped[int] = mapped_column(ForeignKey("graph_builds.build_id", ondelete="CASCADE"))
    claim_ids: Mapped[list[str]] = mapped_column(ARRAY(Text))
    policy_count: Mapped[int] = mapped_column(Integer)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text))
    total_requested: Mapped[Money]
    summary: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[CreatedAt]


class AnalysisEvent(Base):
    """Every system and AI analysis step, for the audit trail (append-only)."""

    __tablename__ = "analysis_events"
    __table_args__ = (
        one_of("event_type", enums.EventType),
        one_of("actor_type", enums.ActorType),
        Index("ix_analysis_events_claim_id", "claim_id"),
    )

    event_id: Mapped[IntId]
    event_type: Mapped[str] = mapped_column(String(40))
    claim_id: Mapped[str | None] = mapped_column(String(20))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(String(10))
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    payload: Mapped[Json | None]
    created_at: Mapped[CreatedAt]


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (one_of("parse_status", enums.ParseStatus),)

    id: Mapped[IntId]
    claim_id: Mapped[str | None] = mapped_column(String(20), ForeignKey("claims.claim_id", ondelete="SET NULL"))
    storage_key: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    phash: Mapped[str | None] = mapped_column(String(64))  # images only (app/documents/phash.py)
    file_name: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column(Integer)
    parse_status: Mapped[str] = mapped_column(String(20))
    extracted: Mapped[Json | None]
    issues: Mapped[Json | None]
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[CreatedAt]


class User(Base):
    """A person who can sign in. Roles are enforced in the API, never only in the interface."""

    __tablename__ = "users"
    __table_args__ = (one_of("role", enums.Role),)

    id: Mapped[IntId]
    username: Mapped[str] = mapped_column(String(100), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[CreatedAt]


class AuditLog(Base):
    """Every processing run, import, alert status change and document confirmation."""

    __tablename__ = "audit_log"

    id: Mapped[IntId]
    at: Mapped[CreatedAt]
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(Text)
    details: Mapped[Json | None]


class Investigation(Base):
    """One per claim under investigation. Holds the head of its evidence chain."""

    __tablename__ = "investigations"

    claim_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("claims.claim_id", ondelete="CASCADE"), primary_key=True
    )
    opened_by: Mapped[str] = mapped_column(String(100))
    opened_at: Mapped[CreatedAt]
    event_count: Mapped[int] = mapped_column(Integer, server_default="0")
    head_hash: Mapped[str | None] = mapped_column(String(64))


class EvidenceEvent(Base):
    """Append-only evidence history. Each entry stores the hash of the one before it, so any later edit
    breaks the chain. Alerts are rebuilt on every run, so entries refer to findings by a stable key and
    keep their own copy of what was shown, never only an alert ID."""

    __tablename__ = "evidence_events"
    __table_args__ = (
        one_of("kind", enums.EvidenceKind),
        Index("uq_evidence_events_claim_seq", "claim_id", "seq", unique=True),
    )

    id: Mapped[IntId]
    claim_id: Mapped[str] = claim_fk()
    seq: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(100))
    actor_role: Mapped[str | None] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20))
    finding_key: Mapped[str | None] = mapped_column(String(200))
    alert_id: Mapped[int | None] = mapped_column(BigInteger)
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[Json]
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
