"""Scenarios for cross-claim correlation, document analysis and settlement corrections, planted on top of the base
data set after its own scenarios and clean claims.

- Relationships between claims under different policies (shared invoice, shared incident, overlapping stays,
  a reused bill document, chains of these), each recorded with the group and tags it must produce.
- Controls that must not form groups: a busy provider, a family policy, the cleared legitimate repeats.
- Claims with several issues at once, with their hand-computed corrections.
- Demo pack only: supporting documents for about 40 claims (invoices in two layouts, scans, discharge summaries)
  with planted differences from the claim record, each with its expected discrepancy type and amount.

Every added claim is clean under the policy checks; whatever a base check still finds on it (the duplicate lines of a
reused invoice, the planted room-rent breach of a multi-issue claim) is added to the findings, so the independent
checker reproduces the answer key exactly.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.core.money import q2
from scripts.datagen.builder import SPECIALIST_PROVIDERS, Builder, ScenarioFailed, entitlement
from scripts.datagen.common import TODAY, ZERO, percent_of, service_codes
from scripts.datagen.documents import discharge_summary, invoice_layout_a, invoice_layout_b, invoice_scan
from scripts.datagen.model import Claim, Line, Policy

RELATIONSHIP_COUNTS = {
    "invoice_reused_across_policies": 8,
    "incident_claimed_twice": 5,
    "concurrent_stays": 4,
    "document_reused": 0,  # documents exist only in the demo pack
    "chain": 2,
}
DEMO_RELATIONSHIP_COUNTS = {
    "invoice_reused_across_policies": 3,
    "incident_claimed_twice": 2,
    "concurrent_stays": 2,
    "document_reused": 3,
    "chain": 1,
}
TAGS = {
    "invoice_reused_across_policies": ["INVOICE_REUSED_ACROSS_POLICIES"],
    "incident_claimed_twice": ["INCIDENT_CLAIMED_TWICE"],
    "concurrent_stays": ["CONCURRENT_STAYS"],
    "document_reused": ["DOCUMENT_REUSED"],
    "chain": ["INCIDENT_CLAIMED_TWICE", "INVOICE_REUSED_ACROSS_POLICIES"],
}
BUSY_PROVIDER_CLAIMS = 200
MULTI_ISSUE = {"full": 3, "demo": 2}

# Planted document differences in the demo pack (the showcase claim carries one of the first, second and last).
DEMO_DISCREPANCY_COUNTS = {
    "amount_higher_than_invoice": 6,
    "only_in_claim": 5,
    "only_in_document": 3,
    "quantity_or_unit_price_mismatch": 4,
    "service_date_mismatch": 3,
    "invoice_number_differs": 2,
    "patient_name_differs": 2,
    "stay_shorter_than_billed": 4,
    "procedure_not_documented": 3,
}
CLEAN_DOCUMENT_CLAIMS = 10
SCANNED_INVOICES = 3

DIAGNOSES = {
    "PRC-APPX": ("Acute appendicitis", "K35.80"),
    "PRC-CHOL": ("Symptomatic cholelithiasis", "K80.20"),
    "PRC-HERN": ("Unilateral inguinal hernia", "K40.90"),
    "PRC-CSEC": ("Obstructed labour", "O66.9"),
    "PRC-ANGIO": ("Coronary artery disease", "I25.10"),
    "PRC-KNEE": ("Primary osteoarthritis of the knee", "M17.11"),
}
DEFAULT_DIAGNOSIS = ("Acute gastroenteritis with dehydration", "A09")
DOCTORS = ("Dr. Meera Rao", "Dr. Arvind Menon", "Dr. Kavita Shah", "Dr. Suresh Pillai", "Dr. Farah Khan")


def _days(n: int) -> timedelta:
    return timedelta(days=n)


@dataclass(eq=False)
class Relationship:
    scenario: str
    claims: list[Claim]
    shared: dict[str, str]

    @property
    def tags(self) -> list[str]:
        return TAGS[self.scenario]


@dataclass(eq=False)
class DocLine:
    """One printed invoice line; `claim_line` is the claim line it stands for (None when not claimed)."""

    code: str
    description: str
    service_date: date
    qty: Decimal
    unit_price: Decimal
    claim_line: Line | None

    @property
    def amount(self) -> Decimal:
        return q2(self.qty * self.unit_price)

    @classmethod
    def of(cls, line: Line) -> "DocLine":
        return cls(line.code, line.description, line.service_date, line.qty, line.unit_price, line)


@dataclass(eq=False)
class Document:
    doc_type: str  # invoice or discharge_summary
    kind: str  # pdf or scan
    layout: str  # A, B, scan or summary
    claim: Claim
    content: dict[str, Any]
    clean: bool = True
    reuse_of: "Document | None" = None
    near_copy: bool = False
    file: str = ""

    def assign_file(self) -> None:
        stem = f"{self.claim.claim_id.lower()}_{self.doc_type}"
        self.file = f"{stem}.{'png' if self.kind == 'scan' else 'pdf'}"


@dataclass(eq=False)
class Discrepancy:
    scenario: str  # planted scenario, or "derived" for a difference that follows from another
    type: str
    document: Document
    line: Line | None = None
    amount: Decimal | None = None
    amount_type: str | None = None

    @property
    def planted(self) -> bool:
        return self.scenario != "derived"


@dataclass(eq=False)
class ExpectedCorrections:
    claim: Claim
    items: list[tuple[str, Decimal, Line | None]]

    @property
    def payable(self) -> Decimal:
        return self.claim.requested - sum((amount for _, amount, _ in self.items), ZERO)


@dataclass
class InvestigationData:
    relationships: list[Relationship] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    discrepancies: list[Discrepancy] = field(default_factory=list)
    multi_issue: list[ExpectedCorrections] = field(default_factory=list)
    showcase: ExpectedCorrections | None = None
    busy_provider: str = ""
    family_policy: str = ""


class Investigation:
    """Plants every scenario through the builder's own helpers, so placement rules (benefit windows, claimant
    calendars, budgets) are the same as for the base data."""

    def __init__(self, builder: Builder) -> None:
        self.b = builder
        self.rng = builder.rng
        self.data = InvestigationData()
        self.dedicated: set[str] = set()
        self.document_policies: list[Policy] = []

    # ---- helpers ---------------------------------------------------------------------------------------------

    def count(self, scenario: str) -> int:
        if self.b.demo:
            return DEMO_RELATIONSHIP_COUNTS[scenario]
        n = RELATIONSHIP_COUNTS[scenario]
        return max(1, round(n * self.b.scale)) if n else 0

    def policies(self, product: str, n: int) -> list[Policy]:
        """n new single-member per-claim policies of one product sharing one benefit period."""
        made = [self.b.new_policy(product, basis="per_claim", members=1) for _ in range(n)]
        for policy in made[1:]:
            policy.start, policy.end = made[0].start, made[0].end
        self.dedicated.update(p.number for p in made)
        return made

    def hosts(self, product: str | None = None) -> list[Policy]:
        return [
            p for p in self.b.hosts(lambda p: product is None or p.product == product) if p.number not in self.dedicated
        ]

    @staticmethod
    def single_ref(claim: Claim) -> None:
        ref = claim.lines[0].invoice_ref
        for line in claim.lines:
            line.invoice_ref = ref

    def later(self, claim: Claim, after: Claim, lo: int = 10, hi: int = 40) -> bool:
        claim.submission_date = after.submission_date + _days(self.rng.randint(lo, hi))
        if after.settlement is not None and claim.submission_date <= after.settlement.settlement_date:
            claim.submission_date = after.settlement.settlement_date + _days(3)
        return claim.submission_date <= TODAY

    def settle_entitled(self, claim: Claim) -> None:
        self.b.settle(claim, entitlement(claim.policy, claim.line_total)[0])

    def add_member(self, policy: Policy, name: str) -> str:
        member = self.b.new_member()
        policy.members.append(member)
        policy.member_names[member] = name
        return member

    def retry(self, scenario: str, planter: Callable[[], Any]) -> Any:
        for _ in range(400):
            result = planter()
            if result:
                return result
        raise ScenarioFailed(f"could not plant {scenario}")

    # ---- plant -----------------------------------------------------------------------------------------------

    def plant(self) -> InvestigationData:
        for _ in range(self.count("invoice_reused_across_policies")):
            pair = self.retry("invoice reuse", lambda: self.invoice_reuse("invoice_reused_across_policies"))
            self.relate("invoice_reused_across_policies", pair, invoice=pair[0].lines[0].invoice_ref)
        for _ in range(self.count("incident_claimed_twice")):
            pair = self.retry("incident twice", self.incident_twice)
            self.relate("incident_claimed_twice", pair, incident=pair[0].incident_ref or "")
        for _ in range(self.count("concurrent_stays")):
            pair = self.retry("concurrent stays", self.concurrent_stays)
            self.relate("concurrent_stays", pair, claimant=pair[0].claimant_id)
        for _ in range(self.count("chain")):
            chain = self.retry("chain", self.chain)
            self.relate("chain", chain, invoice=chain[0].lines[0].invoice_ref, incident=chain[1].incident_ref or "")
        for index in range(self.count("document_reused")):
            pair = self.retry("document reuse", lambda i=index: self.document_reuse(i))
            self.relate("document_reused", pair, document=pair[0].lines[0].invoice_ref)
        for _ in range(MULTI_ISSUE["demo" if self.b.demo else "full"]):
            self.data.multi_issue.append(self.retry("multi-issue claim", self.multi_issue))
        if self.b.demo:
            self.data.showcase = self.retry("showcase claim", self.showcase)
            self.document_claims()
        else:
            self.busy_provider()
        self.family_policy()
        return self.data

    def relate(self, scenario: str, claims: list[Claim], **shared: str) -> None:
        self.data.relationships.append(Relationship(scenario, list(claims), shared))

    # ---- cross-claim relationships ---------------------------------------------------------------------------

    def reuse_invoice(self, original: Claim, policy: Policy, scenario: str) -> Claim | None:
        """A claim under another policy, by another claimant, billing the same invoice lines (number re-spelled)."""
        b = self.b
        claimant = policy.members[0]
        if not b.is_free(claimant, original.first_date, original.last_date):
            return None
        refs = {ref: b.ref_variant(ref, self.rng) for ref in sorted({ln.invoice_ref for ln in original.lines})}
        lines = [ln.copy(invoice_ref=refs[ln.invoice_ref]) for ln in original.lines]
        copy = b.new_claim(policy, claimant, original.incident_date, original.claim_type, "open", lines, scenario)
        if not self.later(copy, original) or not b.fits(policy, copy):
            return None
        return copy

    def record_reused_lines(self, scenario: str, original: Claim, copy: Claim) -> None:
        for orig, line in zip(original.lines, copy.lines, strict=True):
            self.b.add_finding(
                scenario,
                "DUPLICATE_LINE_ITEM",
                line.amount,
                copy,
                match_type="duplicate_line",
                line=line,
                matched_claim=original,
                matched_line=orig,
            )

    def invoice_reuse(self, scenario: str) -> list[Claim] | None:
        pair = self.reuse_pair(scenario)
        if pair is None:
            return None
        self.commit_reuse(scenario, *pair)
        return pair

    def commit_reuse(self, scenario: str, original: Claim, copy: Claim) -> None:
        self.b.commit(original)
        self.b.commit(copy)
        self.record_reused_lines(scenario, original, copy)

    def reuse_pair(self, scenario: str, kind: str | None = None) -> list[Claim] | None:
        """An original claim and a copy billing its invoice under another policy (neither committed yet)."""
        b = self.b
        product = self.rng.choice(["Silver", "Gold", "Platinum"])
        first, second = self.policies(product, 2)
        kind = kind or self.rng.choice(["outpatient", "diagnostics", "pharmacy"])
        status = self.rng.choice(["settled", "open"])
        opts = {"max_amount": first.budget_left / 3, "icu": False} if kind == "inpatient" else {}
        original = b.draft(first, kind, status, tag=f"{scenario}_original", **opts)
        if original is None or (status == "settled" and original.line_total <= first.deductible + 500):
            return None
        self.single_ref(original)
        if status == "settled":
            self.settle_entitled(original)
        copy = self.reuse_invoice(original, second, scenario)
        if copy is None:
            return None
        return [original, copy]

    def claim_incident_again(self, original: Claim, policy: Policy, scenario: str) -> Claim | None:
        """The same admission (incident reference) claimed again under another policy covering the same person,
        on re-issued invoice numbers and with a few lines left out."""
        b = self.b
        member = self.add_member(policy, original.claimant_name)
        refs = {ref: b.ref(original.provider) for ref in sorted({ln.invoice_ref for ln in original.lines})}
        lines = [ln.copy(invoice_ref=refs[ln.invoice_ref]) for ln in original.lines]
        optional = [ln for ln in lines if ln.category in ("pharmacy", "consumables")]
        for line in self.rng.sample(optional, min(len(optional), self.rng.randint(1, 2))):
            lines.remove(line)
        again = b.new_claim(policy, member, original.incident_date, original.claim_type, "open", lines, scenario)
        again.incident_ref = b.ref_variant(original.incident_ref or "", self.rng)
        if not self.later(again, original, 5, 30) or not b.fits(policy, again):
            return None
        return again

    def incident_twice(self) -> list[Claim] | None:
        b = self.b
        product = self.rng.choice(["Silver", "Gold", "Platinum"])
        first, second = self.policies(product, 2)
        original = b.draft(
            first, "inpatient", "open", tag="incident_twice_original", icu=False, max_amount=first.budget_left / 3
        )
        if original is None:
            return None
        again = self.claim_incident_again(original, second, "incident_claimed_twice")
        if again is None:
            return None
        b.commit(original)
        b.commit(again)
        return [original, again]

    def concurrent_stays(self) -> list[Claim] | None:
        b = self.b
        (policy,) = self.policies(self.rng.choice(["Silver", "Gold", "Platinum"]), 1)
        member = policy.members[0]
        hospitals = b.providers_for("inpatient")
        prov_a, prov_b = self.rng.sample(hospitals[: len(hospitals) - 5] or hospitals, 2)
        los = self.rng.randint(3, 5)
        # Per-day room lines (format B), so the service dates on each claim show the whole stay.
        first = b.draft(
            policy,
            "inpatient",
            "open",
            claimant=member,
            tag="concurrent_stay",
            provider=prov_a,
            los=los,
            fmt="B",
            icu=False,
            max_amount=policy.budget_left / 3,
            extra_span=3,
        )
        if first is None:
            return None
        start = first.incident_date + _days(self.rng.randint(1, los - 1))
        plan = b.plan_inpatient(
            policy, prov_b, los=self.rng.randint(2, 4), fmt="B", icu=False, max_amount=policy.budget_left / 3
        )
        second = b.new_claim(policy, member, start, plan, "open", plan.build(start), "concurrent_stays")
        lo, hi = b.window(policy, "open")
        if second.last_date > hi or start in policy.incident_dates or not b.fits(policy, first, second):
            return None
        b.commit(first, second)
        return [first, second]

    def chain(self) -> list[Claim] | None:
        """A shares an invoice with B (other policy, other claimant); B's admission is claimed again as C."""
        pair = self.reuse_pair("chain", kind="inpatient")
        if pair is None:
            return None
        original, reused = pair
        (third,) = self.policies(original.policy.product, 1)
        third.start, third.end = original.policy.start, original.policy.end
        again = self.claim_incident_again(reused, third, "chain")
        if again is None:
            return None
        self.commit_reuse("chain", original, reused)
        self.b.commit(again)
        return [original, reused, again]

    def document_reuse(self, index: int) -> list[Claim] | None:
        """One bill document attached to two claims of different claimants; the second claim lists the same
        services under a new invoice number. Two copies are byte-identical, one is a re-scan."""
        b = self.b
        product = self.rng.choice(["Silver", "Gold", "Platinum"])
        first, second = self.policies(product, 2)
        kind = self.rng.choice(["outpatient", "diagnostics"])
        original = b.draft(first, kind, "open", tag="document_reuse_original")
        if original is None:
            return None
        self.single_ref(original)
        member = second.members[0]
        if not b.is_free(member, original.first_date, original.last_date):
            return None
        ref = b.ref(original.provider)
        lines = [ln.copy(invoice_ref=ref) for ln in original.lines]
        copy = b.new_claim(
            second, member, original.incident_date, original.claim_type, "open", lines, "document_reused"
        )
        if not self.later(copy, original) or not b.fits(second, copy):
            return None
        b.commit(original)
        b.commit(copy)
        scan = index == 2
        doc = self.invoice_document(original, kind="scan" if scan else "pdf", layout="scan" if scan else "AB"[index])
        content = dict(doc.content, lines=[DocLine.of(ln) for ln in copy.lines])  # same print, the copy's lines
        reused = Document("invoice", doc.kind, doc.layout, copy, content, clean=False, reuse_of=doc, near_copy=scan)
        self.data.documents.append(reused)
        self.data.discrepancies += [
            Discrepancy("derived", "INVOICE_REF_MISMATCH", reused),
            Discrepancy("derived", "PATIENT_MISMATCH", reused),
        ]
        return [original, copy]

    # ---- claims with several issues --------------------------------------------------------------------------

    def room_claim(self, los: int, rate: Decimal, tag: str, **opts: Any) -> Claim | None:
        policy = self.rng.choice(self.hosts("Gold"))
        code = "RM-PVT" if rate <= 7000 else "RM-DLX"
        claim = self.b.draft(
            policy,
            "inpatient",
            "open",
            tag=tag,
            los=los,
            fmt="A",
            icu=False,
            room_rate=rate,
            room_code=code,
            max_amount=policy.budget_left,
            **opts,
        )
        return claim

    def policy_steps(self, claim: Claim, total: Decimal, items: list[tuple[str, Decimal, Line | None]]) -> None:
        """Deductible then co-pay on `total` (per-claim deductible; budgets keep claims under the overall limit)."""
        policy = claim.policy
        deductible = min(policy.deductible, total)
        items.append(("APPLY_DEDUCTIBLE", deductible, None))
        after = total - deductible
        items.append(("APPLY_COPAY", percent_of(after, policy.copay), None))

    def multi_issue(self) -> ExpectedCorrections | None:
        """A room rate above the daily limit, a repeated line and a co-pay on one claim."""
        policy_limit = Decimal(5000)
        excess = Decimal(self.rng.choice([500, 1000, 1500, 2000]))
        los = self.rng.randint(3, 5)
        claim = self.room_claim(los, policy_limit + excess, "multi_issue")
        if claim is None:
            return None
        room = next(ln for ln in claim.lines if ln.category == "room")
        candidates = [ln for ln in claim.lines if ln.code.split("-")[0] in ("PHA", "CS")]
        original = self.rng.choice(candidates)
        repeat = original.copy()
        claim.lines.insert(claim.lines.index(original) + 1, repeat)
        if not self.b.fits(claim.policy, claim):
            return None
        self.b.commit(claim)
        rule = claim.policy.room_rule
        self.b.add_finding(
            "multi_issue_room_rent",
            "SUB_LIMIT_EXCEEDED",
            excess * los,
            claim,
            check_code="C06",
            line=room,
            policy_rule_id=rule.rule_id,
        )  # type: ignore[union-attr]
        self.b.add_finding(
            "multi_issue_duplicate_line",
            "DUPLICATE_LINE_ITEM",
            repeat.amount,
            claim,
            match_type="duplicate_line",
            line=repeat,
            matched_line=original,
        )
        items: list[tuple[str, Decimal, Line | None]] = [
            ("REMOVE_DUPLICATE_LINE", repeat.amount, repeat),
            ("CAP_AT_SUB_LIMIT", excess * los, room),
        ]
        self.policy_steps(claim, claim.line_total - repeat.amount - excess * los, items)
        return ExpectedCorrections(claim, items)

    def showcase(self) -> ExpectedCorrections | None:
        """The demo-script claim: a procedure billed above the invoice, a charge the invoice does not show, five
        room days at Rs 6,000 against a three-day stay, then the room sub-limit, deductible and co-pay."""
        los, stay, rate = 5, 3, Decimal(6000)
        claim = self.room_claim(los, rate, "showcase", procedure="PRC-HERN")
        if claim is None:
            return None
        self.single_ref(claim)
        procedure = next(ln for ln in claim.lines if ln.code == "PRC-HERN")
        procedure.unit_price = Decimal("12000.00")
        ref = claim.lines[0].invoice_ref
        extra = self.b.line("OTH-AMB", claim.incident_date, 1, claim.provider, ref, Decimal("1200.00"))
        claim.lines.append(extra)
        if not self.b.fits(claim.policy, claim):
            return None
        self.b.commit(claim)
        room = next(ln for ln in claim.lines if ln.category == "room")
        limit = claim.policy.room_rule.limit_amount  # type: ignore[union-attr]
        self.b.add_finding(
            "showcase_room_rent",
            "SUB_LIMIT_EXCEEDED",
            (rate - limit) * los,
            claim,
            check_code="C06",
            line=room,
            policy_rule_id=claim.policy.room_rule.rule_id,
        )  # type: ignore[union-attr,operator]
        invoice_price = Decimal("9500.00")
        doc = self.invoice_document(claim, layout="A", clean=False)
        doc_lines = []
        for line in doc.content["lines"]:
            if line.claim_line is extra:
                continue
            if line.claim_line is procedure:
                line.unit_price = invoice_price
            doc_lines.append(line)
        doc.content["lines"] = doc_lines
        summary = self.summary_document(claim, stay_days=stay, clean=False)
        self.data.discrepancies += [
            Discrepancy(
                "amount_higher_than_invoice",
                "AMOUNT_MISMATCH",
                doc,
                procedure,
                procedure.amount - invoice_price,
                "calculated",
            ),
            Discrepancy("only_in_claim", "ONLY_IN_CLAIM", doc, extra, extra.amount, "calculated"),
            Discrepancy("derived", "TOTAL_MISMATCH", doc),
            Discrepancy(
                "stay_shorter_than_billed", "STAY_LENGTH_MISMATCH", summary, room, (los - stay) * rate, "calculated"
            ),
        ]
        reduced_room = rate * stay
        # Line corrections in the plan's priority order: unsupported lines, then adjustments, then room days.
        items: list[tuple[str, Decimal, Line | None]] = [
            ("REMOVE_UNSUPPORTED_LINE", extra.amount, extra),
            ("ADJUST_TO_DOCUMENT", procedure.amount - invoice_price, procedure),
            ("REDUCE_ROOM_DAYS", room.amount - reduced_room, room),
            ("CAP_AT_SUB_LIMIT", (rate - limit) * stay, room),  # type: ignore[operator]
        ]
        corrected = claim.line_total - sum((amount for _, amount, _ in items), ZERO)
        self.policy_steps(claim, corrected, items)
        return ExpectedCorrections(claim, items)

    # ---- documents -------------------------------------------------------------------------------------------

    def invoice_document(
        self, claim: Claim, kind: str = "pdf", layout: str | None = None, clean: bool = True
    ) -> Document:
        ref = claim.lines[0].invoice_ref
        lines = [DocLine.of(ln) for ln in claim.lines if ln.invoice_ref == ref]
        content = {
            "number": ref,
            "provider_name": claim.provider.name,
            "provider_city": claim.provider.city,
            "provider_id": claim.provider.provider_id,
            "invoice_date": claim.last_date + _days(1),
            "patient_name": claim.claimant_name,
            "member_id": claim.claimant_id,
            "policy_number": claim.policy.number,
            "visit_date": claim.incident_date,
            "lines": lines,
        }
        layout = layout or ("scan" if kind == "scan" else self.rng.choice("AB"))
        doc = Document("invoice", kind, layout, claim, content, clean=clean)
        self.data.documents.append(doc)
        return doc

    def summary_document(
        self, claim: Claim, stay_days: int | None = None, drop_procedures: bool = False, clean: bool = True
    ) -> Document:
        billed = self.billed_days(claim)
        procedures = [ln for ln in claim.lines if ln.category == "procedure"]
        diagnosis, icd = DIAGNOSES.get(procedures[0].code, DEFAULT_DIAGNOSIS) if procedures else DEFAULT_DIAGNOSIS
        if drop_procedures:
            diagnosis, icd = DEFAULT_DIAGNOSIS
        content = {
            "hospital_name": claim.provider.name,
            "hospital_city": claim.provider.city,
            "patient_name": claim.claimant_name,
            "member_id": claim.claimant_id,
            "policy_number": claim.policy.number,
            "admission_date": claim.incident_date,
            "discharge_date": claim.incident_date + _days(stay_days if stay_days is not None else billed),
            "diagnosis": diagnosis,
            "icd10": icd,
            "procedures": []
            if drop_procedures
            else [f"{ln.description} on {ln.service_date.strftime('%d/%m/%Y')}" for ln in procedures],
            "treating_doctor": self.rng.choice(DOCTORS),
        }
        doc = Document("discharge_summary", "pdf", "summary", claim, content, clean=clean)
        self.data.documents.append(doc)
        return doc

    @staticmethod
    def billed_days(claim: Claim) -> int:
        return int(sum((ln.qty for ln in claim.lines if ln.category in ("room", "icu")), ZERO))

    def document_claim(
        self,
        kind: str,
        status: str = "open",
        require: Callable[[Claim], bool] = lambda claim: True,
        **opts: Any,
    ) -> Claim:
        """A new clean claim on a single invoice, for a supporting document. Document claims use their own policies
        (three members each), added whenever the existing ones have no room left, so the base claims keep theirs."""
        failures = 0

        def attempt() -> Claim | None:
            nonlocal failures
            failures += 1
            if not self.document_policies or failures % 25 == 0:
                product = self.rng.choice(["Gold", "Platinum"])
                policy = self.b.new_policy(product, basis="per_claim", members=3, early_start=True)
                self.dedicated.add(policy.number)
                self.document_policies.append(policy)
            policy = self.rng.choice(self.document_policies)
            if kind == "daycare" and "daycare" not in policy.covered_claim_types:
                return None
            extra = {"max_amount": policy.budget_left / 2, "icu": False, **opts} if kind == "inpatient" else opts
            claim = self.b.draft(policy, kind, status, tag="document", **extra)
            if claim is None or not self.b.fits(policy, claim) or not require(claim):
                return None
            if status == "settled" and claim.line_total <= policy.deductible + 500:
                return None
            self.single_ref(claim)
            if status == "settled":
                self.settle_entitled(claim)
            self.b.commit(claim)
            return claim

        return self.retry(f"document claim ({kind})", attempt)

    def document_claims(self) -> None:
        rng = self.rng
        disc = self.data.discrepancies

        def planted(
            scenario: str,
            kind: str,
            doc: Document,
            line: Line | None = None,
            amount: Decimal | None = None,
            amount_type: str | None = None,
        ) -> None:
            disc.append(Discrepancy(scenario, kind, doc, line, amount, amount_type))
            doc.clean = False

        def invoice(claim: Claim, scan: bool = False) -> Document:
            return self.invoice_document(claim, kind="scan" if scan else "pdf")

        def doc_line(doc: Document, line: Line) -> DocLine:
            return next(x for x in doc.content["lines"] if x.claim_line is line)

        # Claim line amount higher than the invoice: a single-quantity line printed at a lower price.
        for k in range(DEMO_DISCREPANCY_COUNTS["amount_higher_than_invoice"] - 1):  # two on settled claims
            claim = self.document_claim(rng.choice(["diagnostics", "daycare"]), "settled" if k < 2 else "open")
            doc = invoice(claim)
            line = max((ln for ln in claim.lines if ln.qty == 1), key=lambda ln: ln.amount)
            printed = doc_line(doc, line)
            printed.unit_price = q2(line.unit_price * Decimal(rng.choice([75, 80, 85, 90])) / 100)
            planted(
                "amount_higher_than_invoice", "AMOUNT_MISMATCH", doc, line, line.amount - printed.amount, "calculated"
            )
            planted("derived", "TOTAL_MISMATCH", doc)
        # Line in the claim but not on the invoice.
        for _ in range(DEMO_DISCREPANCY_COUNTS["only_in_claim"] - 1):
            claim = self.document_claim("diagnostics", require=lambda c: len(c.lines) >= 2)
            doc = invoice(claim)
            line = rng.choice(claim.lines[1:])
            doc.content["lines"] = [x for x in doc.content["lines"] if x.claim_line is not line]
            planted("only_in_claim", "ONLY_IN_CLAIM", doc, line, line.amount, "calculated")
            planted("derived", "TOTAL_MISMATCH", doc)
        # Line on the invoice but not in the claim (benign).
        for _ in range(DEMO_DISCREPANCY_COUNTS["only_in_document"]):
            claim = self.document_claim(rng.choice(["outpatient", "pharmacy"]))
            doc = invoice(claim)
            code, price = rng.choice([("CS-DRS", Decimal("180.00")), ("OTH-DIET", Decimal("450.00"))])
            doc.content["lines"].append(
                DocLine(code, service_codes()[code].description, claim.incident_date, Decimal(1), price, None)
            )
            planted("only_in_document", "ONLY_IN_DOCUMENT", doc)
            planted("derived", "TOTAL_MISMATCH", doc)
        # Quantity or unit price mismatch on a multi-quantity line.
        for k in range(DEMO_DISCREPANCY_COUNTS["quantity_or_unit_price_mismatch"]):
            claim = self.document_claim("pharmacy", require=lambda c: any(ln.qty >= 2 for ln in c.lines))
            doc = invoice(claim)
            line = next(ln for ln in claim.lines if ln.qty >= 2)
            printed = doc_line(doc, line)
            if k % 2 == 0:
                printed.qty = line.qty - 1
                planted(
                    "quantity_or_unit_price_mismatch",
                    "QUANTITY_MISMATCH",
                    doc,
                    line,
                    (line.qty - printed.qty) * line.unit_price,
                    "calculated",
                )
            else:
                printed.unit_price = q2(line.unit_price * Decimal("0.8"))
                planted(
                    "quantity_or_unit_price_mismatch",
                    "UNIT_PRICE_MISMATCH",
                    doc,
                    line,
                    q2((line.unit_price - printed.unit_price) * line.qty),
                    "calculated",
                )
            planted("derived", "TOTAL_MISMATCH", doc)
        # Service date mismatch (informational).
        for _ in range(DEMO_DISCREPANCY_COUNTS["service_date_mismatch"]):
            claim = self.document_claim("pharmacy")
            doc = invoice(claim)
            line = claim.lines[0]
            doc_line(doc, line).service_date = line.service_date + _days(rng.choice([1, 2]))
            planted("service_date_mismatch", "SERVICE_DATE_MISMATCH", doc, line)
        # Invoice number on the document differs from the claim.
        for _ in range(DEMO_DISCREPANCY_COUNTS["invoice_number_differs"]):
            claim = self.document_claim(rng.choice(["outpatient", "diagnostics"]))
            doc = invoice(claim)
            doc.content["number"] = self.b.ref(claim.provider)
            planted("invoice_number_differs", "INVOICE_REF_MISMATCH", doc)
        # Patient name on the document differs from the claimant.
        for _ in range(DEMO_DISCREPANCY_COUNTS["patient_name_differs"]):
            claim = self.document_claim(rng.choice(["outpatient", "diagnostics"]))
            doc = invoice(claim)
            doc.content["patient_name"] = self.b.name()
            planted("patient_name_differs", "PATIENT_MISMATCH", doc)
        # Discharge summary stay shorter than the room days billed (two days fewer).
        for _ in range(DEMO_DISCREPANCY_COUNTS["stay_shorter_than_billed"] - 1):
            claim = self.document_claim("inpatient", los=rng.randint(4, 6))
            invoice(claim)
            billed = self.billed_days(claim)
            summary = self.summary_document(claim, stay_days=billed - 2, clean=False)
            room = next(ln for ln in claim.lines if ln.category == "room")
            planted(
                "stay_shorter_than_billed", "STAY_LENGTH_MISMATCH", summary, room, 2 * room.unit_price, "calculated"
            )
        # Procedure billed but not mentioned in the discharge summary.
        for _ in range(DEMO_DISCREPANCY_COUNTS["procedure_not_documented"]):
            claim = self.document_claim("inpatient", procedure=rng.choice(["PRC-APPX", "PRC-CHOL", "PRC-HERN"]))
            invoice(claim)
            summary = self.summary_document(claim, drop_procedures=True, clean=False)
            line = next(ln for ln in claim.lines if ln.category == "procedure")
            planted("procedure_not_documented", "PROCEDURE_NOT_DOCUMENTED", summary, line, line.amount, "estimated")
        # Clean documents that match the claim exactly.
        kinds = ["outpatient", "diagnostics", "pharmacy", "daycare", "outpatient", "diagnostics"]
        for k, kind in enumerate(kinds):
            invoice(self.document_claim(kind), scan=k == 0)
        for _ in range(CLEAN_DOCUMENT_CLAIMS - len(kinds)):
            claim = self.document_claim("inpatient", procedure=rng.choice(["PRC-APPX", "PRC-CHOL", None]))
            invoice(claim)
            self.summary_document(claim)

    # ---- controls --------------------------------------------------------------------------------------------

    def busy_provider(self) -> None:
        """Top the busiest hospital up to over 200 unrelated claims (full set only)."""
        b = self.b
        hospitals = {p.provider_id for p in b.provider_list if p.name not in SPECIALIST_PROVIDERS}
        counts: dict[str, int] = {}
        for claim in b.claims:
            pid = claim.provider.provider_id
            if pid in hospitals:
                counts[pid] = counts.get(pid, 0) + 1
        busy = max(sorted(counts), key=lambda pid: counts[pid])
        provider = next(p for p in b.provider_list if p.provider_id == busy)
        self.data.busy_provider = busy
        target = round((BUSY_PROVIDER_CLAIMS + 10) * b.scale) if b.scale < 1 else BUSY_PROVIDER_CLAIMS + 10
        hosts = self.hosts()
        attempts = 0
        while counts[busy] < target and attempts < 50000:
            attempts += 1
            policy = self.rng.choice(hosts)
            kind = b.clean_kind(policy)
            if kind == "physio":
                continue
            status = self.rng.choice(["open", "settled"])
            opts: dict[str, Any] = {"max_amount": policy.budget_left} if kind == "inpatient" else {}
            claim = b.draft(policy, kind, status, provider=provider, **opts)
            if claim is None or not b.fits(policy, claim):
                continue
            if status == "settled":
                b.settle_clean(claim)
            b.commit(claim)
            counts[busy] += 1

    def family_policy(self) -> None:
        """A four-member policy whose members each claim separately."""
        b = self.b
        claimants: dict[str, set[str]] = {}
        for claim in b.claims:
            claimants.setdefault(claim.policy.number, set()).add(claim.claimant_id)
        family = sorted(
            (p for p in b.policies if len(p.members) == 4 and p.kind == "general" and p.number not in self.dedicated),
            key=lambda p: (-len(claimants.get(p.number, set())), p.number),
        )
        policy = family[0]
        for member in policy.members:
            if member in claimants.get(policy.number, set()):
                continue
            self.retry("family member claim", lambda m=member: self.member_claim(policy, m))
        self.data.family_policy = policy.number

    def member_claim(self, policy: Policy, member: str) -> bool:
        claim = self.b.draft(policy, "outpatient", "open", claimant=member)
        if claim is None or not self.b.fits(policy, claim):
            return False
        self.b.commit(claim)
        return True


# ---- answer key and files ------------------------------------------------------------------------------------


def _amount(value: Decimal | None) -> str | None:
    return None if value is None else f"{q2(value):.2f}"


def _line_id(line: Line | None) -> str | None:
    return line.line_id if line is not None else None


def _corrections(expected: ExpectedCorrections) -> dict[str, Any]:
    return {
        "claim_id": expected.claim.claim_id,
        "requested_amount": _amount(expected.claim.requested),
        "expected_corrections": [
            {"type": kind, "amount": _amount(amount), "line_id": _line_id(line)}
            for kind, amount, line in expected.items
        ],
        "recommended_payable": _amount(expected.payable),
    }


def printed(doc: Document) -> dict[str, Any]:
    """What the document shows, in plain JSON (the extraction target)."""
    c = doc.content
    if doc.doc_type == "discharge_summary":
        return {
            "patient_name": c["patient_name"],
            "hospital_name": c["hospital_name"],
            "admission_date": c["admission_date"].isoformat(),
            "discharge_date": c["discharge_date"].isoformat(),
            "diagnosis": c["diagnosis"],
            "icd10": c["icd10"],
            "procedures_performed": c["procedures"],
            "treating_doctor": c["treating_doctor"],
        }
    lines = c["lines"]
    total = sum((x.amount for x in lines), ZERO)
    return {
        "invoice_number": c["number"],
        "provider_name": c["provider_name"],
        "invoice_date": c["invoice_date"].isoformat(),
        "patient_name": c["patient_name"],
        "policy_number": c["policy_number"],
        "admission_date": c["visit_date"].isoformat(),
        "lines": [
            {
                "line_id": _line_id(x.claim_line),
                "service_code": x.code,
                "description": x.description,
                "service_date": x.service_date.isoformat(),
                "quantity": f"{x.qty.normalize():f}",
                "unit_price": _amount(x.unit_price),
                "amount": _amount(x.amount),
            }
            for x in lines
        ],
        "subtotal": _amount(total),
        "taxes": "0.00",
        "total": _amount(total),
    }


def investigation_key(data: InvestigationData, legitimate_repeats: int) -> dict[str, Any]:
    for doc in data.documents:
        doc.assign_file()
    relationships = sorted(
        (
            {
                "scenario": rel.scenario,
                "tags": sorted(rel.tags),
                "claim_ids": sorted(c.claim_id for c in rel.claims),
                "shared": rel.shared,
            }
            for rel in data.relationships
        ),
        key=lambda r: (r["scenario"], r["claim_ids"]),
    )
    documents = sorted(
        (
            {
                "file": doc.file,
                "claim_id": doc.claim.claim_id,
                "doc_type": doc.doc_type,
                "kind": doc.kind,
                "layout": doc.layout,
                "clean": doc.clean,
                "reuse_of": doc.reuse_of.file if doc.reuse_of else None,
                "expected": printed(doc),
            }
            for doc in data.documents
        ),
        key=lambda d: d["file"],
    )
    discrepancies = sorted(
        (
            {
                "scenario": d.scenario,
                "planted": d.planted,
                "type": d.type,
                "claim_id": d.document.claim.claim_id,
                "file": d.document.file,
                "line_id": _line_id(d.line),
                "expected_amount": _amount(d.amount),
                "amount_type": d.amount_type,
            }
            for d in data.discrepancies
        ),
        key=lambda d: (d["claim_id"], d["file"], d["type"], d["line_id"] or ""),
    )
    return {
        "relationships": relationships,
        "controls": {
            "busy_provider": data.busy_provider or None,
            "family_policy": data.family_policy,
            "cleared_repeats": legitimate_repeats,
        },
        "multi_issue_claims": sorted((_corrections(m) for m in data.multi_issue), key=lambda m: m["claim_id"]),
        "showcase": _corrections(data.showcase) if data.showcase else None,
        "documents": documents,
        "document_discrepancies": discrepancies,
    }


def render_documents(data: InvestigationData, seed: int) -> dict[str, bytes]:
    """File name -> bytes for every document (files are assigned by investigation_key)."""
    files: dict[str, bytes] = {}
    for doc in data.documents:
        content = dict(doc.content)
        content["lines"] = [
            {
                "code": x.code,
                "description": x.description,
                "service_date": x.service_date,
                "quantity": x.qty,
                "unit_price": x.unit_price,
                "amount": x.amount,
            }
            for x in content.get("lines", [])
        ]
        content["total"] = sum((x["amount"] for x in content["lines"]), ZERO)
        if doc.doc_type == "discharge_summary":
            data_bytes = discharge_summary(content)
        elif doc.reuse_of is not None and not doc.near_copy:
            data_bytes = files.get(doc.reuse_of.file) or b""
        elif doc.kind == "scan":
            # The two scans of a reused bill share the rotation, so only the speckle noise differs between them.
            reused = doc.near_copy or any(other.reuse_of is doc for other in data.documents)
            data_bytes = invoice_scan(content, f"{seed}:{doc.file}", angle=0.9 if reused else None)
        elif doc.layout == "A":
            data_bytes = invoice_layout_a(content)
        else:
            data_bytes = invoice_layout_b(content)
        files[doc.file] = data_bytes
    for doc in data.documents:  # byte-identical copies whose original was rendered later
        if doc.reuse_of is not None and not doc.near_copy:
            files[doc.file] = files[doc.reuse_of.file]
    return files
