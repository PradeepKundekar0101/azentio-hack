"""Builds the typed synthetic dataset: policies, clean claims and every planted scenario with its expected finding.

Expected amounts are computed here by construction (e.g. (rate - limit) x days); `oracle.py` recomputes them
independently from the rendered rows.
"""

import random
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Any

from app.core.money import q2
from scripts.datagen.common import (
    TODAY,
    ZERO,
    Provider,
    near_score,
    norm_ref,
    percent_of,
    providers,
    ref_similarity,
    service_codes,
)
from scripts.datagen.model import Claim, Line, Policy, Rule, Settlement

# ---- products and policy wording ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Product:
    copay: int
    deductibles: tuple[int, ...]
    overall_limits: tuple[int, ...]
    room_limit: int
    diag_limit: int
    physio_limit: int | None
    covers_daycare: bool


PRODUCTS = {
    "Silver": Product(20, (5000, 7500, 10000), (300000, 400000), 3000, 10000, None, False),
    "Gold": Product(10, (2000, 3000, 5000), (500000, 600000, 750000), 5000, 15000, 20000, True),
    "Platinum": Product(0, (0, 2500), (800000, 1000000), 8000, 25000, 30000, True),
}

CLAIM_TYPE_CLAUSES = {
    "inpatient": "Section 2.1 In-patient hospitalisation",
    "daycare": "Section 2.2 Day-care procedures",
    "outpatient": "Section 2.3 Out-patient treatment",
    "pharmacy": "Section 2.4 Pharmacy bills",
    "diagnostics": "Section 2.5 Diagnostic tests",
}
CATEGORY_CLAUSES = {
    "room": "Section 3.1 Room rent",
    "icu": "Section 3.2 Intensive care",
    "consultation": "Section 3.3 Consultation fees",
    "procedure": "Section 3.4 Surgical and medical procedures",
    "pharmacy": "Section 3.5 Medicines and drugs",
    "diagnostics": "Section 3.6 Diagnostic tests",
    "consumables": "Section 3.7 Medical consumables",
    "physiotherapy": "Section 3.8 Physiotherapy",
    "other": "Section 3.9 Other hospital charges",
}
EXCLUSION_CLAUSES = {
    "PRC-COSM": "Section 5.1 Cosmetic and plastic surgery",
    "PRC-LIPO": "Section 5.2 Cosmetic weight-loss procedures",
    "PRC-LASIK": "Section 5.3 Correction of refractive error",
    "PRC-IVF": "Section 5.4 Infertility treatment",
    "PHA-VIT": "Section 5.5 Vitamins, tonics and supplements",
    "PRC-BARI": "Section 5.6 Bariatric surgery",
    "PRC-DENT": "Section 5.7 Dental treatment",
}
SCENARIO_EXCLUSIONS = ("PRC-COSM", "PRC-LIPO", "PRC-LASIK", "PRC-IVF", "PHA-VIT")

PLAN_COUNTS = {
    "claimant_not_insured": 15,
    "not_covered": 20,
    "outside_benefit_period": 15,
    "excluded_service": 40,
    "room_rent_above_per_day_limit": 60,
    "per_claim_sub_limit": 30,
    "per_period_sub_limit": 15,
    "overall_limit": 15,
    "settled_without_copay": 25,
    "settled_without_deductible": 15,
    "settled_above_approved": 10,
    "exact_duplicate_claim": 20,
    "duplicate_line_within_claim": 25,
    "duplicate_line_across_claims": 15,
    "near_duplicate": 25,
    "legitimate_repeat": 40,
}
FULL_POLICIES = 300
FULL_OPEN_CLAIMS = 1500
FULL_SETTLED_CLAIMS = 1500

BASE_PRICE = {
    "RM-GEN": 1500, "RM-SEMI": 2500, "RM-PVT": 4000, "RM-DLX": 6500, "ICU-STD": 9000,
    "CON-GP": 500, "CON-SPL": 1000, "CON-FUP": 600, "CON-TELE": 400, "CON-EMR": 1200, "CON-VIS": 800,
    "PRC-APPX": 65000, "PRC-CHOL": 75000, "PRC-CATA": 35000, "PRC-HERN": 55000, "PRC-KNEE": 220000,
    "PRC-CSEC": 60000, "PRC-ANGIO": 150000, "PRC-ENDO": 6000, "PRC-DIAL": 2800,
    "PRC-COSM": 85000, "PRC-LIPO": 120000, "PRC-LASIK": 65000, "PRC-IVF": 150000,
    "PHA-ABX": 450, "PHA-ANLG": 120, "PHA-IVFL": 350, "PHA-INS": 650, "PHA-CARD": 380, "PHA-OTC": 90,
    "PHA-VIT": 550,
    "DX-CBC": 400, "DX-LFT": 800, "DX-KFT": 750, "DX-LIPID": 900, "DX-HBA1C": 600, "DX-XRAY": 700,
    "DX-USG": 1800, "DX-CT": 4500, "DX-MRI": 7500, "DX-ECG": 350, "DX-ECHO": 2500, "DX-TMT": 2200,
    "CS-SYR": 45, "CS-GLV": 30, "CS-DRS": 250, "CS-IMPL": 60000, "CS-STENT": 35000,
    "PHY-SES": 1000, "PHY-OCC": 1100, "PHY-REHAB": 1300,
    "OTH-REG": 1000, "OTH-NURS": 900,
}  # fmt: skip

SPECIALIST_PROVIDERS = {
    "Swasthya Clinic": "clinic",
    "Parivar Family Clinic": "clinic",
    "Suvidha Diagnostic Centre": "diagnostics",
    "Shubham Physiotherapy Centre": "physio",
    "Kiran Dialysis Centre": "dialysis",
    "Akshaya Kidney Care": "dialysis",
    "Udaya Eye Hospital": "eye",
    "Sankalp Cancer Centre": "cancer",
}

MALE = (
    "Aarav Vivaan Aditya Arjun Rohan Karan Rahul Vikram Sanjay Manoj Suresh Rajesh Anil Deepak Nikhil Pranav "
    "Siddharth Harish Gopal Imran Farhan Joseph Thomas Venkatesh Ramesh Kiran Ashok Mohan Naveen Yash"
).split()
FEMALE = (
    "Ananya Diya Priya Kavya Sneha Pooja Meera Lakshmi Divya Anjali Neha Shreya Radha Sunita Geeta Asha Nisha "
    "Ritu Fatima Ayesha Mary Revathi Swati Bhavna Ishita Tanvi Aditi Rekha Usha Jaya"
).split()
SURNAMES = (
    "Sharma Verma Iyer Nair Reddy Rao Patel Shah Mehta Gupta Singh Kumar Das Ghosh Banerjee Mukherjee Joshi "
    "Kulkarni Deshpande Pillai Menon Naidu Choudhary Agarwal Bhat Hegde Shetty Khan Fernandes D'Souza Varghese "
    "Saxena Mishra Pandey Yadav Jain Bose Kapoor Malhotra"
).split()

GAP_DAYS = 10  # clean claims of one claimant are at least this far apart, so they are never duplicate candidates


@dataclass
class Plan:
    claim_type: str
    provider: Provider
    span: int
    build: Callable[[date], list[Line]]


@dataclass
class BuildResult:
    policies: list[Policy]
    claims: list[Claim]
    findings: list[dict[str, Any]]
    legit: list[dict[str, Any]]
    mismatched: list[Claim]
    ids: dict[str, int]
    builder: "Builder"


@dataclass
class IdScheme:
    policy: int
    claim: int
    line: int
    settlement: int
    member: int


FULL_IDS = IdScheme(policy=100000, claim=100000, line=1000000, settlement=100000, member=100000)
DEMO_IDS = IdScheme(policy=900000, claim=900000, line=9000000, settlement=900000, member=900000)


def _days(n: int) -> timedelta:
    return timedelta(days=n)


def _round_price(value: Decimal) -> Decimal:
    step = Decimal(50) if value >= 1000 else Decimal(10) if value >= 100 else Decimal("0.5")
    return q2((value / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step)


def _ceil_rupee(value: Decimal) -> Decimal:
    return value.quantize(Decimal(1), rounding=ROUND_CEILING)


def entitlement(policy: Policy, amount: Decimal, deductible_left: Decimal | None = None) -> tuple[Decimal, Decimal]:
    """(payable, deductible applied) for a claim with no failing checks, before the overall-limit cap."""
    available = policy.deductible if deductible_left is None else deductible_left
    deductible = min(available, amount)
    after = amount - deductible
    return after - percent_of(after, policy.copay), deductible


class ScenarioFailed(Exception):
    pass


@dataclass
class Builder:
    seed: int
    scale: float = 1.0
    demo: bool = False
    rng: random.Random = field(init=False)
    policies: list[Policy] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    legit: list[dict[str, Any]] = field(default_factory=list)
    mismatched: list[Claim] = field(default_factory=list)
    calendar: dict[str, list[tuple[date, date]]] = field(default_factory=lambda: defaultdict(list))

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.ids = DEMO_IDS if self.demo else FULL_IDS
        self.codes = service_codes()
        self.provider_list = providers()
        self.factor = {p.provider_id: Decimal(self.rng.randint(85, 125)) / 100 for p in self.provider_list}
        self.style = {p.provider_id: self.rng.randrange(4) for p in self.provider_list}
        self.prefix = {
            p.provider_id: "".join(w[0] for w in p.name.split() if w[0].isupper())[:3] for p in self.provider_list
        }
        pool = [n for n in range(100, 99999) if n != 452]
        self.rng.shuffle(pool)
        self.serials = iter(pool)
        self.member_seq = 0
        self.claim_seq = 0
        self.policy_seq = 0

    # ---- counts ----------------------------------------------------------------------------------------------

    def count(self, scenario: str) -> int:
        if self.demo:
            return 2
        return max(1, round(PLAN_COUNTS[scenario] * self.scale))

    # ---- small helpers ---------------------------------------------------------------------------------------

    def serial(self) -> int:
        return next(self.serials)

    def ref(self, provider: Provider, style: int | None = None) -> str:
        n = self.serial()
        style = self.style[provider.provider_id] if style is None else style
        prefix = self.prefix[provider.provider_id]
        if style == 0:
            return f"INV-{n:05d}"
        if style == 1:
            return f"{prefix}/BILL/{n:05d}"
        if style == 2:
            return f"{prefix}-{n:06d}"
        return f"{prefix}{n:07d}"

    def incident_ref(self, claim_type: str) -> str | None:
        if claim_type == "inpatient":
            return f"ADM-{self.serial():06d}"
        if claim_type == "daycare":
            return f"DC-{self.serial():06d}"
        return f"OPD-{self.serial():06d}" if self.rng.random() < 0.4 else None

    def price(self, code: str, provider: Provider) -> Decimal:
        jitter = Decimal(self.rng.randint(95, 105)) / 100
        return _round_price(Decimal(BASE_PRICE[code]) * self.factor[provider.provider_id] * jitter)

    def line(self, code: str, day: date, qty: int, provider: Provider, ref: str, price: Decimal | None = None) -> Line:
        return Line(code, day, Decimal(qty), price if price is not None else self.price(code, provider), ref, provider)

    def name(self, surname: str | None = None) -> str:
        first = self.rng.choice(MALE if self.rng.random() < 0.5 else FEMALE)
        return f"{first} {surname or self.rng.choice(SURNAMES)}"

    def new_member(self) -> str:
        self.member_seq += 1
        return f"MEM-{self.ids.member + self.member_seq:06d}"

    def providers_for(self, kind: str) -> list[Provider]:
        hospitals = [p for p in self.provider_list if p.name not in SPECIALIST_PROVIDERS]
        extra = {"outpatient": "clinic", "pharmacy": "clinic", "diagnostics": "diagnostics", "physio": "physio"}
        extra.update({"dialysis": "dialysis", "cataract": "eye"})
        special = [p for p in self.provider_list if SPECIALIST_PROVIDERS.get(p.name) == extra.get(kind)]
        return hospitals + special

    # ---- policies --------------------------------------------------------------------------------------------

    def new_policy(
        self,
        product_name: str,
        kind: str = "general",
        basis: str | None = None,
        deductible: int | None = None,
        overall: int | None = None,
        early_start: bool = False,
        members: int | None = None,
        exclusions: list[str] | None = None,
    ) -> Policy:
        product = PRODUCTS[product_name]
        self.policy_seq += 1
        number = f"POL-{self.ids.policy + self.policy_seq:06d}"
        surname = self.rng.choice(SURNAMES)
        size = members or self.rng.choices((1, 2, 3, 4), (3, 3, 2.5, 1.5))[0]
        member_ids = [self.new_member() for _ in range(size)]
        names = {member: self.name(surname) for member in member_ids}
        if early_start:
            start = date(2025, 8, 1) + _days(self.rng.randint(0, 120))
        else:
            start = date(2025, 7, 1) + _days(self.rng.randint(0, 330))
        end = date(start.year + 1, start.month, start.day) - _days(1)
        ded = deductible if deductible is not None else self.rng.choice(product.deductibles)
        if basis is None:
            basis = "per_claim" if ded == 0 or self.rng.random() < 0.55 else "per_period"
        policy = Policy(
            number=number,
            holder_name=names[member_ids[0]],
            members=member_ids,
            member_names=names,
            product=product_name,
            start=start,
            end=end,
            overall_limit=Decimal(overall or self.rng.choice(product.overall_limits)),
            deductible=Decimal(ded),
            basis=basis,
            copay=product.copay,
            kind=kind,
        )
        if basis == "per_period":
            last = min(end, TODAY - _days(5))
            policy.split = start + _days((last - start).days // 2)
        if exclusions is None:
            exclusions = self.rng.sample(SCENARIO_EXCLUSIONS, self.rng.randint(1, 3))
        self.make_rules(policy, product, exclusions)
        self.policies.append(policy)
        return policy

    def make_rules(self, policy: Policy, product: Product, exclusions: list[str]) -> None:
        counters: dict[str, int] = defaultdict(int)

        def add(prefix: str, **values: Any) -> Rule:
            counters[prefix] += 1
            rule = Rule(
                rule_id=f"{policy.number}-{prefix}-{counters[prefix]:02d}", policy_number=policy.number, **values
            )
            policy.rules.append(rule)
            return rule

        claim_types = [t for t in CLAIM_TYPE_CLAUSES if product.covers_daycare or t != "daycare"]
        for claim_type in claim_types:
            add(
                "CV",
                rule_type="coverage",
                scope_type="claim_type",
                scope_value=claim_type,
                limit_basis=None,
                limit_amount=None,
                clause_ref=CLAIM_TYPE_CLAUSES[claim_type],
                description=f"{claim_type.capitalize()} claims are covered.",
            )
        policy.covered_claim_types = set(claim_types)
        categories = [c for c in CATEGORY_CLAUSES if product.physio_limit is not None or c != "physiotherapy"]
        for category in categories:
            add(
                "CV",
                rule_type="coverage",
                scope_type="category",
                scope_value=category,
                limit_basis=None,
                limit_amount=None,
                clause_ref=CATEGORY_CLAUSES[category],
                description=f"Charges in the {category} category are covered.",
            )
        policy.covered_categories = set(categories)
        for code in sorted(exclusions):
            policy.exclusions[code] = add(
                "EX",
                rule_type="exclusion",
                scope_type="service_code",
                scope_value=code,
                limit_basis=None,
                limit_amount=None,
                clause_ref=EXCLUSION_CLAUSES[code],
                description=f"{self.codes[code].description} is excluded.",
            )
        policy.room_rule = add(
            "SL",
            rule_type="sub_limit",
            scope_type="category",
            scope_value="room",
            limit_basis="per_day",
            limit_amount=Decimal(product.room_limit),
            clause_ref="Section 4.1 Room rent limit",
            description=f"Room rent is payable up to Rs {product.room_limit} per day.",
        )
        policy.diag_rule = add(
            "SL",
            rule_type="sub_limit",
            scope_type="category",
            scope_value="diagnostics",
            limit_basis="per_claim",
            limit_amount=Decimal(product.diag_limit),
            clause_ref="Section 4.2 Diagnostics limit per claim",
            description=f"Diagnostic tests are payable up to Rs {product.diag_limit} per claim.",
        )
        if product.physio_limit is not None:
            policy.physio_rule = add(
                "SL",
                rule_type="sub_limit",
                scope_type="category",
                scope_value="physiotherapy",
                limit_basis="per_period",
                limit_amount=Decimal(product.physio_limit),
                clause_ref="Section 4.3 Physiotherapy limit per policy period",
                description=f"Physiotherapy is payable up to Rs {product.physio_limit} per policy period.",
            )

    # ---- calendar and placement ------------------------------------------------------------------------------

    def is_free(self, claimant: str, first: date, last: date) -> bool:
        return all(
            (first - end).days >= GAP_DAYS or (start - last).days >= GAP_DAYS for start, end in self.calendar[claimant]
        )

    def window(self, policy: Policy, status: str) -> tuple[date, date]:
        lo, hi = policy.start, min(policy.end, TODAY - _days(5))
        if status == "settled":
            hi = min(hi, TODAY - _days(50))
            if policy.split:
                hi = min(hi, policy.split)
        elif policy.split:
            lo = max(lo, policy.split + _days(1))
        return lo, hi

    def place(
        self,
        policy: Policy,
        claimant: str,
        span: int,
        status: str,
        lo: date | None = None,
        hi: date | None = None,
        bounds: tuple[date, date] | None = None,
    ) -> date | None:
        wlo, whi = bounds or self.window(policy, status)
        lo = max(wlo, lo) if lo else wlo
        hi = min(whi, hi) if hi else whi
        hi = hi - _days(span)
        if hi < lo:
            return None
        for _ in range(40):
            incident = lo + _days(self.rng.randint(0, (hi - lo).days))
            if incident in policy.incident_dates:
                continue
            if self.is_free(claimant, incident, incident + _days(span)):
                return incident
        return None

    # ---- claim templates -------------------------------------------------------------------------------------

    def plan(self, kind: str, policy: Policy, provider: Provider | None = None, **opts: Any) -> Plan:
        rng = self.rng
        if kind == "outpatient":
            prov = provider or rng.choice(self.providers_for("outpatient"))

            def build_outpatient(day: date) -> list[Line]:
                main = opts.get("ref") or self.ref(prov, opts.get("style"))
                lines = [self.line(rng.choice(["CON-GP", "CON-SPL", "CON-TELE", "CON-EMR"]), day, 1, prov, main)]
                drugs = rng.sample(["PHA-ABX", "PHA-ANLG", "PHA-OTC", "PHA-CARD", "PHA-INS"], rng.randint(0, 2))
                pharmacy_ref = main if opts.get("single") or rng.random() < 0.5 else self.ref(prov)
                lines += [self.line(code, day, rng.randint(1, 3), prov, pharmacy_ref) for code in drugs]
                if rng.random() < 0.3:
                    lines.append(self.line(rng.choice(["DX-CBC", "DX-ECG", "DX-XRAY"]), day, 1, prov, main))
                return lines

            return Plan("outpatient", prov, 0, build_outpatient)
        if kind == "pharmacy":
            prov = provider or rng.choice(self.providers_for("pharmacy"))

            def build_pharmacy(day: date) -> list[Line]:
                ref = opts.get("ref") or self.ref(prov, opts.get("style"))
                codes = rng.sample(
                    ["PHA-ABX", "PHA-ANLG", "PHA-OTC", "PHA-CARD", "PHA-INS", "PHA-IVFL"], rng.randint(1, 4)
                )
                return [self.line(code, day, rng.randint(1, 5), prov, ref) for code in codes]

            return Plan("pharmacy", prov, 0, build_pharmacy)
        if kind == "diagnostics":
            prov = provider or rng.choice(self.providers_for("diagnostics"))
            cap = policy.diag_rule.limit_amount * Decimal("0.6")  # type: ignore[union-attr,operator]

            def build_diagnostics(day: date) -> list[Line]:
                ref = opts.get("ref") or self.ref(prov, opts.get("style"))
                for _ in range(30):
                    codes = rng.sample(
                        ["DX-CBC", "DX-LFT", "DX-KFT", "DX-LIPID", "DX-HBA1C", "DX-XRAY", "DX-USG", "DX-CT", "DX-ECG",
                         "DX-ECHO", "DX-TMT"],
                        rng.randint(2, 4),
                    )  # fmt: skip
                    lines = [self.line(code, day, 1, prov, ref) for code in codes]
                    if sum(line.amount for line in lines) <= cap:
                        return lines
                return [self.line("DX-CBC", day, 1, prov, ref)]

            return Plan("diagnostics", prov, 0, build_diagnostics)
        if kind == "daycare":
            procedure = opts.get("procedure") or rng.choice(["PRC-CATA", "PRC-ENDO"])
            pool = self.providers_for("cataract" if procedure == "PRC-CATA" else "daycare")
            prov = provider or rng.choice(pool)

            def build_daycare(day: date) -> list[Line]:
                ref = opts.get("ref") or self.ref(prov, opts.get("style"))
                lines = [
                    self.line(procedure, day, 1, prov, ref),
                    self.line("CS-GLV", day, rng.randint(2, 4), prov, ref),
                    self.line("CS-SYR", day, rng.randint(4, 10), prov, ref),
                    self.line("PHA-ANLG", day, rng.randint(1, 3), prov, ref),
                    self.line("OTH-REG", day, 1, prov, ref),
                ]
                if rng.random() < 0.5:
                    lines.append(self.line("DX-CBC", day, 1, prov, ref))
                return lines

            return Plan("daycare", prov, 0, build_daycare)
        if kind == "inpatient":
            return self.plan_inpatient(policy, provider, **opts)
        if kind == "physio":
            prov = provider or rng.choice(self.providers_for("physio"))
            code = opts.get("code") or rng.choices(["PHY-SES", "PHY-OCC", "PHY-REHAB"], (70, 15, 15))[0]
            sessions = opts.get("sessions") or rng.randint(3, 6)
            gaps = [rng.randint(3, 4) for _ in range(sessions - 1)]
            unit = opts.get("price") or self.price(code, prov)

            def build_physio(day: date) -> list[Line]:
                ref = self.ref(prov)
                days = [day]
                for gap in gaps:
                    days.append(days[-1] + _days(gap))
                return [self.line(code, d, 1, prov, ref, unit) for d in days]

            return Plan("outpatient", prov, sum(gaps), build_physio)
        raise ValueError(kind)

    def plan_inpatient(self, policy: Policy, provider: Provider | None, **opts: Any) -> Plan:
        rng = self.rng
        prov = provider or rng.choice(self.providers_for("inpatient"))
        los = opts.get("los") or rng.randint(2, 6)
        fmt = opts.get("fmt") or ("A" if rng.random() < 0.4 else "B")
        icu = opts.get("icu", rng.random() < 0.15)
        limit = policy.room_rule.limit_amount  # type: ignore[union-attr]
        room_rate = opts.get("room_rate")
        if room_rate is None:
            options = [
                code
                for code in ("RM-GEN", "RM-SEMI", "RM-PVT", "RM-DLX")
                if BASE_PRICE[code] * 1.3 <= float(limit) * 0.85
            ]  # type: ignore[arg-type]
            room_code = rng.choice(options)
            room_rate = min(self.price(room_code, prov), _round_price(limit * Decimal("0.8")))  # type: ignore[operator]
        else:
            room_code = opts.get("room_code", "RM-PVT")
        max_amount = opts.get("max_amount")
        procedure = opts.get("procedure", "random")
        if procedure == "random":
            choices = ["PRC-APPX", "PRC-CHOL", "PRC-HERN", "PRC-CSEC", "PRC-ANGIO", "PRC-KNEE"]
            if max_amount is not None:
                choices = [c for c in choices if BASE_PRICE[c] * 1.6 <= float(max_amount) * 0.6]
            procedure = rng.choice(choices) if choices and rng.random() < 0.6 else None
        diag_cap = policy.diag_rule.limit_amount * Decimal("0.5")  # type: ignore[union-attr,operator]
        separate_pharmacy = rng.random() < 0.4

        def build_inpatient(day: date) -> list[Line]:
            main = self.ref(prov)
            pharmacy_ref = self.ref(prov) if separate_pharmacy else main
            lines: list[Line] = [self.line("OTH-REG", day, 1, prov, main)]
            room_start = day
            room_days = los
            if icu:
                lines.append(self.line("ICU-STD", day, 1, prov, main))
                room_start, room_days = day + _days(1), los - 1
            if fmt == "A":
                lines.append(self.line(room_code, room_start, room_days, prov, main, room_rate))
                lines.append(self.line("CON-VIS", day, los, prov, main))
                lines.append(self.line("OTH-NURS", day, los, prov, main))
            else:
                visit = self.price("CON-VIS", prov)
                for offset in range(room_days):
                    lines.append(self.line(room_code, room_start + _days(offset), 1, prov, main, room_rate))
                for offset in range(los):
                    lines.append(self.line("CON-VIS", day + _days(offset), 1, prov, main, visit))
                lines.append(self.line("OTH-NURS", day, los, prov, main))
            for _ in range(20):
                picks = rng.sample(["DX-CBC", "DX-LFT", "DX-KFT", "DX-XRAY", "DX-ECG", "DX-USG"], rng.randint(1, 3))
                tests = [self.line(c, day, 1, prov, main) for c in picks]
                if sum(t.amount for t in tests) <= diag_cap:
                    break
            lines += tests
            lines.append(self.line("PHA-IVFL", day, rng.randint(2, 6), prov, pharmacy_ref))
            lines.append(self.line("PHA-ABX", day + _days(1), rng.randint(1, 3), prov, pharmacy_ref))
            lines.append(self.line("CS-SYR", day, rng.randint(5, 15), prov, main))
            lines.append(self.line("CS-GLV", day + _days(1), rng.randint(4, 10), prov, main))
            if procedure:
                lines.append(self.line(procedure, day + _days(1), 1, prov, main))
                if procedure == "PRC-KNEE":
                    lines.append(self.line("CS-IMPL", day + _days(1), 1, prov, main))
                if procedure == "PRC-ANGIO":
                    lines.append(self.line("CS-STENT", day + _days(1), 1, prov, main))
            return lines

        return Plan("inpatient", prov, los - 1, build_inpatient)

    # ---- claims ----------------------------------------------------------------------------------------------

    def new_claim(
        self,
        policy: Policy,
        claimant: str,
        incident: date,
        plan_or_type: Plan | str,
        status: str,
        lines: list[Line],
        tag: str,
        name: str | None = None,
    ) -> Claim:
        claim_type = plan_or_type.claim_type if isinstance(plan_or_type, Plan) else plan_or_type
        self.claim_seq += 1
        last = max([incident, *(line.service_date for line in lines)])
        if status == "open":
            submission = min(last + _days(self.rng.randint(1, 12)), TODAY)
        else:
            submission = last + _days(self.rng.randint(1, 10))
        return Claim(
            policy=policy,
            claimant_id=claimant,
            claimant_name=name or policy.member_names.get(claimant) or self.name(),
            incident_date=incident,
            submission_date=submission,
            claim_type=claim_type,
            status=status,
            lines=lines,
            incident_ref=self.incident_ref(claim_type),
            seq=self.claim_seq,
            tag=tag,
        )

    def draft(
        self,
        policy: Policy,
        kind: str,
        status: str,
        claimant: str | None = None,
        tag: str = "clean",
        extra_span: int = 0,
        lo: date | None = None,
        hi: date | None = None,
        bounds: tuple[date, date] | None = None,
        name: str | None = None,
        **opts: Any,
    ) -> Claim | None:
        claimant = claimant or self.rng.choice(policy.members)
        plan = self.plan(kind, policy, **opts)
        incident = self.place(policy, claimant, plan.span + extra_span, status, lo, hi, bounds)
        if incident is None:
            return None
        return self.new_claim(policy, claimant, incident, plan, status, plan.build(incident), tag, name)

    def fits(self, policy: Policy, *claims: Claim) -> bool:
        if policy.kind != "general":
            return True
        total = sum((c.requested for c in claims), ZERO)
        physio = sum((line.amount for c in claims for line in c.lines if line.category == "physiotherapy"), ZERO)
        if policy.budget_used + total > policy.budget:
            return False
        if physio and policy.physio_rule is not None:
            return policy.physio_used + physio <= policy.physio_rule.limit_amount * Decimal("0.5")  # type: ignore[operator]
        return True

    def commit(self, *claims: Claim) -> None:
        first = min(c.first_date for c in claims)
        last = max(c.last_date for c in claims)
        self.calendar[claims[0].claimant_id].append((first, last))
        for claim in claims:
            claim.lines.sort(key=lambda line: line.service_date)
            self.claims.append(claim)
            policy = claim.policy
            policy.incident_dates.add(claim.incident_date)
            policy.budget_used += claim.requested
            policy.physio_used += sum((line.amount for line in claim.lines if line.category == "physiotherapy"), ZERO)

    def settle(self, claim: Claim, approved: Decimal, paid: Decimal | None = None, status: str = "paid") -> None:
        when = min(claim.submission_date + _days(self.rng.randint(5, 25)), TODAY)
        claim.settlement = Settlement(when, approved, approved if paid is None else paid, status)

    def settle_clean(self, claim: Claim) -> None:
        payable, _ = entitlement(claim.policy, claim.line_total)
        roll = self.rng.random()
        if payable == 0:  # within the deductible: nothing to pay
            self.settle(claim, ZERO, ZERO, "rejected")
        elif roll < 0.04:
            self.settle(claim, payable, q2(_round_price(payable * Decimal("0.7"))), "partially_paid")
        elif roll < 0.07:
            self.settle(claim, ZERO, ZERO, "rejected")
        else:
            self.settle(claim, payable)

    def add_finding(self, scenario: str, category: str, amount: Decimal, claim: Claim, **extra: Any) -> None:
        finding = {
            "scenario": scenario,
            "category": category,
            "check_code": None,
            "match_type": None,
            "amount_type": "calculated",
            "expected_amount": q2(amount),
            "claim": claim,
            "line": None,
            "policy_rule_id": None,
            "matched_claim": None,
            "matched_line": None,
        }
        finding.update(extra)
        self.findings.append(finding)

    # ---- build -----------------------------------------------------------------------------------------------

    def build(self) -> BuildResult:
        self.make_general_policies()
        self.plant_all()
        self.fill_clean()
        self.plant_mismatches()
        self.settle_per_period()
        self.assign_ids()
        return BuildResult(self.policies, self.claims, self.findings, self.legit, self.mismatched, {}, self)

    def make_general_policies(self) -> None:
        if self.demo:
            layout = [("Silver", "per_claim"), ("Silver", "per_claim"), ("Gold", "per_claim"), ("Gold", "per_claim")]
            layout += [("Gold", "per_claim"), ("Gold", "per_claim"), ("Platinum", "per_claim")]
            layout += [("Platinum", "per_claim"), ("Silver", "per_period"), ("Gold", "per_period")]
            for product, basis in layout:
                self.new_policy(
                    product, basis=basis, members=self.rng.randint(2, 4), exclusions=list(SCENARIO_EXCLUSIONS)
                )
            return
        dedicated = self.count("per_period_sub_limit") + self.count("overall_limit")
        general = max(16, round(FULL_POLICIES * self.scale) - dedicated)
        for _ in range(general):
            product = self.rng.choices(["Silver", "Gold", "Platinum"], (35, 40, 25))[0]
            self.new_policy(product)

    def hosts(self, predicate: Callable[[Policy], bool] = lambda p: True) -> list[Policy]:
        found = [p for p in self.policies if p.kind == "general" and p.basis == "per_claim" and predicate(p)]
        if not found:
            raise ScenarioFailed("no host policy")
        return found

    def plant_all(self) -> None:
        planters: list[tuple[str, Callable[[int], bool]]] = [
            ("per_period_sub_limit", self.plant_per_period),
            ("overall_limit", self.plant_overall),
            ("exact_duplicate_claim", self.plant_exact_duplicate),
            ("near_duplicate", self.plant_near_duplicate),
            ("legitimate_repeat", self.plant_legit_repeat),
            ("duplicate_line_across_claims", self.plant_line_across),
            ("duplicate_line_within_claim", self.plant_line_within),
            ("room_rent_above_per_day_limit", self.plant_room),
            ("per_claim_sub_limit", self.plant_per_claim),
            ("excluded_service", self.plant_excluded),
            ("not_covered", self.plant_not_covered),
            ("claimant_not_insured", self.plant_not_insured),
            ("outside_benefit_period", self.plant_outside_period),
            ("settled_without_copay", self.plant_settled_without_copay),
            ("settled_without_deductible", self.plant_settled_without_deductible),
            ("settled_above_approved", self.plant_settled_above_approved),
        ]
        for scenario, planter in planters:
            n = self.count(scenario)
            self.current_count = n
            for index in range(n):
                for _ in range(400):
                    if planter(index):
                        break
                else:
                    raise ScenarioFailed(f"could not plant {scenario} #{index}")

    # ---- policy scenarios ------------------------------------------------------------------------------------

    def plant_simple(
        self,
        scenario: str,
        policy: Policy,
        kind: str,
        status: str,
        amend: Callable[[Claim], dict[str, Any] | None],
        **draft_opts: Any,
    ) -> bool:
        claim = self.draft(policy, kind, status, tag=scenario, **draft_opts)
        if claim is None:
            return False
        finding = amend(claim)
        if finding is None or not self.fits(policy, claim):
            return False
        self.commit(claim)
        category = finding.pop("category")
        amount = finding.pop("amount")
        self.add_finding(scenario, category, amount, claim, **finding)
        return True

    def plant_not_insured(self, index: int) -> bool:
        policy = self.rng.choice(self.hosts())
        claimant = self.new_member()
        kind = self.rng.choice(["outpatient", "diagnostics", "pharmacy", "inpatient"])
        return self.plant_simple(
            "claimant_not_insured",
            policy,
            kind,
            "open",
            lambda c: {"category": "NOT_COVERED", "amount": c.requested, "check_code": "C02"},
            claimant=claimant,
            name=self.name(),
            max_amount=policy.budget_left,
        )

    def plant_not_covered(self, index: int) -> bool:
        policy = self.rng.choice(self.hosts(lambda p: p.product == "Silver"))
        if index < self.current_count // 2:
            return self.plant_simple(
                "not_covered",
                policy,
                "daycare",
                "open",
                lambda c: {"category": "NOT_COVERED", "amount": c.requested, "check_code": "C03"},
            )

        def add_physio(claim: Claim) -> dict[str, Any]:
            line = self.line("PHY-SES", claim.incident_date, 1, claim.provider, claim.lines[0].invoice_ref)
            claim.lines.append(line)
            return {"category": "NOT_COVERED", "amount": line.amount, "check_code": "C04", "line": line}

        return self.plant_simple("not_covered", policy, "outpatient", "open", add_physio)

    def plant_outside_period(self, index: int) -> bool:
        policy = self.rng.choice(self.hosts())
        after = policy.end <= TODAY - _days(25) and self.rng.random() < 0.5
        if after:
            bounds = (policy.end + _days(5), TODAY - _days(10))
        else:
            bounds = (policy.start - _days(70), policy.start - _days(5))
        kind = self.rng.choice(["outpatient", "diagnostics", "pharmacy", "inpatient"])
        return self.plant_simple(
            "outside_benefit_period",
            policy,
            kind,
            "open",
            lambda c: {"category": "OUT_OF_BENEFIT_PERIOD", "amount": c.requested, "check_code": "C01"},
            bounds=bounds,
            max_amount=policy.budget_left,
        )

    def plant_excluded(self, index: int) -> bool:
        policy = self.rng.choice(self.hosts(lambda p: bool(p.exclusions)))
        code = self.rng.choice(sorted(policy.exclusions))
        if code == "PHA-VIT":
            kind = self.rng.choice(["outpatient", "pharmacy"])
        else:
            kind = "daycare" if "daycare" in policy.covered_claim_types else "inpatient"

        def add_excluded(claim: Claim) -> dict[str, Any]:
            when = claim.incident_date if kind != "inpatient" else claim.incident_date + _days(1)
            qty = self.rng.randint(1, 3) if code == "PHA-VIT" else 1
            line = self.line(code, when, qty, claim.provider, claim.lines[0].invoice_ref)
            claim.lines.append(line)
            rule = policy.exclusions[code]
            return {
                "category": "EXCLUDED_SERVICE",
                "amount": line.amount,
                "check_code": "C05",
                "line": line,
                "policy_rule_id": rule.rule_id,
            }

        opts: dict[str, Any] = {"procedure": None} if kind == "inpatient" else {}
        return self.plant_simple("excluded_service", policy, kind, "open", add_excluded, **opts)

    def plant_room(self, index: int) -> bool:
        demo_case = self.demo and index == 0
        policy = self.rng.choice(self.hosts(lambda p: p.product == "Gold" if demo_case else True))
        limit = policy.room_rule.limit_amount  # type: ignore[union-attr]
        excess = Decimal(2000) if demo_case else Decimal(self.rng.choice([500, 1000, 1500, 2000, 2500, 3000]))
        los = 3 if demo_case else self.rng.randint(2, 6)
        rate = limit + excess  # type: ignore[operator]
        code = "RM-PVT" if rate <= 7000 else "RM-DLX"

        def find_room(claim: Claim) -> dict[str, Any]:
            line = next(line for line in claim.lines if line.category == "room")
            return {
                "category": "SUB_LIMIT_EXCEEDED",
                "amount": excess * los,
                "check_code": "C06",
                "line": line,
                "policy_rule_id": policy.room_rule.rule_id,  # type: ignore[union-attr]
            }

        return self.plant_simple(
            "room_rent_above_per_day_limit",
            policy,
            "inpatient",
            "open",
            find_room,
            los=los,
            fmt="A",
            icu=False,
            room_rate=rate,
            room_code=code,
            max_amount=policy.budget_left,
        )

    def plant_per_claim(self, index: int) -> bool:
        policy = self.rng.choice(self.hosts())
        limit = policy.diag_rule.limit_amount  # type: ignore[union-attr]
        excess = Decimal(self.rng.choice(range(500, 6001, 250)))

        def overfill(claim: Claim) -> dict[str, Any] | None:
            prov, ref, day = claim.provider, claim.lines[0].invoice_ref, claim.incident_date
            codes = [
                "DX-MRI",
                *self.rng.sample(["DX-CT", "DX-ECHO", "DX-TMT", "DX-USG", "DX-LFT", "DX-KFT", "DX-CBC"], 3),
            ]
            claim.lines = [self.line(code, day, 1, prov, ref) for code in codes]
            others = sum((line.amount for line in claim.lines[1:]), ZERO)
            mri = limit + excess - others  # type: ignore[operator]
            if mri < 3000:
                extra = self.line("DX-CT", day, 1, prov, ref) if "DX-CT" not in codes else None
                if extra is None:
                    return None
                claim.lines.append(extra)
                mri -= extra.amount
                if mri < 3000:
                    return None
            claim.lines[0].unit_price = q2(mri)
            return {
                "category": "SUB_LIMIT_EXCEEDED",
                "amount": excess,
                "check_code": "C07",
                "policy_rule_id": policy.diag_rule.rule_id,  # type: ignore[union-attr]
            }

        return self.plant_simple("per_claim_sub_limit", policy, "diagnostics", "open", overfill)

    def plant_per_period(self, index: int) -> bool:
        limit = self.rng.choice([20000, 25000, 30000])
        policy = self.new_policy("Platinum", kind="per_period", basis="per_claim", deductible=0, early_start=True)
        policy.physio_rule.limit_amount = Decimal(limit)  # type: ignore[union-attr]
        policy.physio_rule.description = f"Physiotherapy is payable up to Rs {limit} per policy period."  # type: ignore[union-attr]
        claimant = self.rng.choice(policy.members)
        provider = self.rng.choice(self.providers_for("physio"))
        used = ZERO
        bills: list[Claim] = []
        lo = policy.start
        target = Decimal(limit) * Decimal(self.rng.choice(["0.6", "0.7", "0.8"]))
        bounds = (policy.start, min(policy.end, TODAY - _days(5)))
        while used < target and len(bills) < (1 if self.demo else 4):
            room = Decimal(limit) - used - 2000
            unit = self.price("PHY-SES", provider)
            sessions = min(self.rng.randint(4, 8), int(room // unit))
            if sessions < 2:
                break
            claim = self.draft(
                policy, "physio", "open", claimant, "per_period_history", lo=lo, bounds=bounds,
                provider=provider, code="PHY-SES", sessions=sessions, price=unit,
            )  # fmt: skip
            if claim is None:
                self.drop(policy)
                return False
            bills.append(claim)
            self.commit(claim)
            used += claim.line_total
            lo = claim.last_date + _days(GAP_DAYS)
        remaining = Decimal(limit) - used
        sessions = self.rng.randint(5, 8)
        excess_target = Decimal(self.rng.choice(range(1000, 5001, 500)))
        unit = _round_price((remaining + excess_target) / sessions)
        if not bills or unit < 700 or unit > 2600 or unit * sessions <= remaining:
            self.drop(policy)
            return False
        claim = self.draft(
            policy, "physio", "open", claimant, "per_period_sub_limit", lo=lo, bounds=bounds,
            provider=provider, code="PHY-SES", sessions=sessions, price=unit,
        )  # fmt: skip
        if claim is None:
            self.drop(policy)
            return False
        for bill in bills:
            if bill.last_date <= TODAY - _days(50) and self.rng.random() < 0.6:
                bill.status = "settled"
                bill.submission_date = bill.last_date + _days(self.rng.randint(1, 10))
                self.settle(bill, bill.line_total)
        self.commit(claim)
        self.add_finding(
            "per_period_sub_limit",
            "SUB_LIMIT_EXCEEDED",
            claim.line_total - remaining,
            claim,
            check_code="C08",
            policy_rule_id=policy.physio_rule.rule_id,  # type: ignore[union-attr]
        )
        return True

    def drop(self, policy: Policy) -> None:
        """Remove a dedicated policy whose scenario could not be completed, with any claims already placed."""
        doomed = [c for c in self.claims if c.policy is policy]
        for claim in doomed:
            self.claims.remove(claim)
        self.policies.remove(policy)

    def big_inpatient(
        self, policy: Policy, status: str, claimant: str, target: Decimal, lo: date, tag: str
    ) -> Claim | None:
        bounds = (policy.start, min(policy.end, TODAY - _days(5)))
        extras = {"PRC-KNEE": 60000, "PRC-ANGIO": 35000}
        options = [
            code
            for code in ("PRC-KNEE", "PRC-ANGIO", "PRC-CHOL", "PRC-APPX", "PRC-CSEC")
            if Decimal(BASE_PRICE[code] * 13 // 10 + extras.get(code, 0) + 40000) < target
        ]
        procedure = self.rng.choice(options or ["PRC-APPX"])
        claim = self.draft(
            policy,
            "inpatient",
            status,
            claimant,
            tag,
            lo=lo,
            bounds=None if status == "settled" else bounds,
            procedure=procedure,
        )
        if claim is None:
            return None
        main = next(line for line in claim.lines if line.code == procedure)
        new_price = main.unit_price + target - claim.line_total
        if new_price < 20000:
            return None
        main.unit_price = q2(new_price)
        return claim

    def plant_overall(self, index: int) -> bool:
        product = self.rng.choice(["Silver", "Gold"])
        policy = self.new_policy(
            product,
            kind="overall",
            basis="per_claim",
            overall=self.rng.choice([300000, 400000, 500000]),
            early_start=True,
        )
        limit, copay, ded = policy.overall_limit, policy.copay, policy.deductible
        factor = 1 - Decimal(copay) / 100
        claimant = self.rng.choice(policy.members)
        history = 1 if self.demo else self.rng.randint(1, 3)
        goal = q2(limit * Decimal(self.rng.choice(["0.78", "0.82", "0.86", "0.9"])))
        paid_total = ZERO
        lo = policy.start
        for k in range(history):
            want_paid = (goal - paid_total) / (history - k)
            target = _ceil_rupee(want_paid / factor) + ded
            claim = self.big_inpatient(policy, "settled", claimant, target, lo, "overall_history")
            if claim is None:
                self.drop(policy)
                return False
            payable, _ = entitlement(policy, claim.line_total)
            self.settle(claim, payable)
            self.commit(claim)
            paid_total += payable
            lo = claim.last_date + _days(GAP_DAYS)
        remaining = limit - paid_total
        excess = Decimal(self.rng.choice(range(10000, 80001, 500)))
        target = _ceil_rupee((remaining + excess) / factor) + ded
        claim = self.big_inpatient(policy, "open", claimant, target, lo, "overall_limit")
        if claim is None or remaining <= 0:
            self.drop(policy)
            return False
        payable, _ = entitlement(policy, claim.line_total)
        self.commit(claim)
        self.add_finding("overall_limit", "OVERALL_LIMIT_EXCEEDED", payable - remaining, claim, check_code="C11")
        return True

    def settled_scenario(
        self,
        scenario: str,
        predicate: Callable[[Policy], bool],
        settle: Callable[[Claim], Decimal],
        fit: Decimal | None = None,
    ) -> bool:
        policy = self.rng.choice(self.hosts(predicate))
        kinds = ["inpatient", "diagnostics", "outpatient"]
        if "daycare" in policy.covered_claim_types:
            kinds.append("daycare")
        kind = "inpatient" if fit is not None else self.rng.choice(kinds)
        opts: dict[str, Any] = {"max_amount": policy.budget_left}
        if fit is not None:
            opts["procedure"] = "PRC-HERN"
        claim = self.draft(policy, kind, "settled", tag=scenario, **opts)
        if claim is None:
            return False
        if fit is not None:
            main = next(line for line in claim.lines if line.code == "PRC-HERN")
            main.unit_price = q2(main.unit_price + fit + policy.deductible - claim.line_total)
            if main.unit_price < 20000:
                return False
        if claim.line_total <= policy.deductible + 2000 or not self.fits(policy, claim):
            return False
        expected = settle(claim)
        if expected <= 0:
            return False
        self.commit(claim)
        self.add_finding(scenario, "SETTLEMENT_OVERPAYMENT", expected, claim, check_code="C12")
        return True

    def plant_settled_without_copay(self, index: int) -> bool:
        demo_case = self.demo and index == 0

        def settle(claim: Claim) -> Decimal:
            policy = claim.policy
            after = claim.line_total - policy.deductible
            self.settle(claim, after)
            return percent_of(after, policy.copay)

        predicate: Callable[[Policy], bool] = (lambda p: p.product == "Gold") if demo_case else (lambda p: p.copay > 0)
        return self.settled_scenario("settled_without_copay", predicate, settle, Decimal(84000) if demo_case else None)

    def plant_settled_without_deductible(self, index: int) -> bool:
        def settle(claim: Claim) -> Decimal:
            policy = claim.policy
            paid = claim.line_total - percent_of(claim.line_total, policy.copay)
            self.settle(claim, paid)
            return paid - entitlement(policy, claim.line_total)[0]

        return self.settled_scenario("settled_without_deductible", lambda p: p.deductible > 0, settle)

    def plant_settled_above_approved(self, index: int) -> bool:
        def settle(claim: Claim) -> Decimal:
            payable, _ = entitlement(claim.policy, claim.line_total)
            extra = Decimal(self.rng.choice(range(1000, 15001, 500)))
            self.settle(claim, payable, payable + extra)
            return extra

        return self.settled_scenario("settled_above_approved", lambda p: True, settle)

    # ---- duplicate scenarios ---------------------------------------------------------------------------------

    def duplicate_kind(self, policy: Policy, kinds: list[str]) -> str:
        allowed = [k for k in kinds if k != "daycare" or "daycare" in policy.covered_claim_types]
        return self.rng.choice(allowed)

    @staticmethod
    def ref_variant(ref: str, rng: random.Random) -> str:
        """A different spelling of the same reference: it normalises to the same value."""
        options = [ref.lower(), ref.replace("-", " "), ref.replace("/", "-"), ref.replace("-", "")]
        if ref.startswith("INV-"):
            options.append("INV " + str(int(ref[4:])))
        options = [o for o in options if o != ref and norm_ref(o) == norm_ref(ref)]
        return rng.choice(options) if options else ref.lower()

    def plant_exact_duplicate(self, index: int) -> bool:
        policy = self.rng.choice(self.hosts())
        by_incident = index % 10 >= 7
        status = "settled" if index % 2 == 0 else "open"
        kind = self.duplicate_kind(
            policy,
            ["inpatient", "daycare"]
            if by_incident
            else ["outpatient", "diagnostics", "daycare", "inpatient", "pharmacy"],
        )
        original = self.draft(policy, kind, status, tag="exact_duplicate_original", max_amount=policy.budget_left / 2)
        if original is None or (status == "settled" and original.line_total <= policy.deductible + 500):
            return False
        refs = {line.invoice_ref for line in original.lines}
        if by_incident:
            mapping = {ref: self.ref(original.provider) for ref in sorted(refs)}
        else:
            mapping = {ref: self.ref_variant(ref, self.rng) for ref in sorted(refs)}
        lines = [line.copy(invoice_ref=mapping[line.invoice_ref]) for line in original.lines]
        duplicate = self.new_claim(
            policy,
            original.claimant_id,
            original.incident_date,
            original.claim_type,
            "open",
            lines,
            "exact_duplicate_claim",
        )
        duplicate.incident_ref = self.ref_variant(original.incident_ref, self.rng) if original.incident_ref else None
        duplicate.submission_date = original.submission_date + _days(self.rng.randint(15, 45))
        if duplicate.submission_date > TODAY or not self.fits(policy, original, duplicate):
            return False
        if status == "settled":
            self.settle(original, entitlement(policy, original.line_total)[0])
            if duplicate.submission_date <= original.settlement.settlement_date:  # type: ignore[union-attr]
                duplicate.submission_date = original.settlement.settlement_date + _days(3)  # type: ignore[union-attr]
                if duplicate.submission_date > TODAY:
                    return False
        self.commit(original, duplicate)
        self.add_finding(
            "exact_duplicate_claim",
            "EXACT_DUPLICATE_CLAIM",
            duplicate.requested,
            duplicate,
            match_type="exact_claim",
            matched_claim=original,
        )
        return True

    def plant_near_duplicate(self, index: int) -> bool:
        policy = self.rng.choice(self.hosts())
        demo_case = self.demo and index == 0
        partial = index % 5 == 4
        gap = 2 if demo_case else self.rng.randint(1, 3)
        status = "settled" if self.rng.random() < 0.4 else "open"
        kind = (
            "outpatient"
            if demo_case
            else self.duplicate_kind(policy, ["outpatient", "diagnostics", "pharmacy", "daycare"])
        )
        opts: dict[str, Any] = {"style": 0, "single": True}
        if demo_case:
            opts["ref"] = "INV-00452"
        original = self.draft(policy, kind, status, tag="near_duplicate_original", extra_span=gap, **opts)
        if original is None or (status == "settled" and original.line_total <= policy.deductible + 500):
            return False
        ref = original.lines[0].invoice_ref
        number = int(norm_ref(ref)[3:])
        letter = self.rng.choice("ABR")
        variant = (
            "INV452A"
            if demo_case
            else self.rng.choice([f"INV{number}{letter}", f"INV-{number:05d}-{letter}", f"INV/{number}{letter}"])
        )
        lines = [line.copy(invoice_ref=variant, service_date=line.service_date + _days(gap)) for line in original.lines]
        total = original.line_total
        target = total * (
            Decimal("0.015") if demo_case else Decimal(self.rng.choice(["0.01", "0.015", "0.02", "0.025", "0.03"]))
        )
        target = q2(target.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if not demo_case and self.rng.random() < 0.5:
            target = -target
        if partial:
            present = {line.code for line in lines}
            extras = [c for c in ("PHA-OTC", "CS-DRS", "DX-ECG", "PHA-ANLG") if c not in present]
            if not extras:
                return False
            extra = self.line(extras[0], lines[0].service_date, 1, original.provider, variant)
            lines.append(extra)
            target = abs(target)
            tweak = target - extra.amount
        else:
            tweak = target
        singles = [line for line in lines[: len(original.lines)] if line.qty == 1]
        if not singles:
            return False
        biggest = max(singles, key=lambda line: line.amount)
        if biggest.unit_price + tweak <= biggest.unit_price / 2:
            return False
        biggest.unit_price = q2(biggest.unit_price + tweak)
        duplicate = self.new_claim(
            policy,
            original.claimant_id,
            original.incident_date + _days(gap),
            original.claim_type,
            "open",
            lines,
            "near_duplicate",
        )
        duplicate.incident_ref = None
        duplicate.submission_date = max(duplicate.submission_date, original.submission_date + _days(1))
        if duplicate.submission_date > TODAY:
            return False
        a, b = original.line_total, duplicate.line_total
        diff = max(abs(a - b) / min(a, b), abs(a - b) / max(a, b))
        codes_a, codes_b = {line.code for line in original.lines}, {line.code for line in lines}
        jaccard = len(codes_a & codes_b) / len(codes_a | codes_b)
        score = near_score(ref_similarity(ref, variant), gap, float(diff), jaccard)
        if score < 0.82 or norm_ref(ref) == norm_ref(variant) or not self.fits(policy, original, duplicate):
            return False
        if status == "settled":
            self.settle(original, entitlement(policy, original.line_total)[0])
        self.commit(original, duplicate)
        overlap = sum((line.amount for line in lines if line.code in codes_a), ZERO)
        self.add_finding(
            "near_duplicate",
            "NEAR_DUPLICATE",
            overlap,
            duplicate,
            match_type="near_duplicate",
            amount_type="estimated",
            matched_claim=original,
        )
        return True

    def plant_legit_repeat(self, index: int) -> bool:
        cycle = ["PHY-SES", "PRC-DIAL", "CON-FUP", "PHY-REHAB", "OTH-NURS", "PHY-OCC"]
        code = cycle[index % len(cycle)]
        needs_cover = code.startswith("PHY") or code == "PRC-DIAL"
        policy = self.rng.choice(self.hosts(lambda p: p.physio_rule is not None if needs_cover else True))
        if self.demo and index == 0:
            gap = 7
        elif code in ("PHY-SES", "PHY-OCC"):
            gap = self.rng.randint(2, 7)
        elif code == "PRC-DIAL":
            gap = self.rng.randint(2, 4)
        elif code == "CON-FUP":
            gap = 7
        else:
            gap = self.rng.randint(1, 7)
        kind = {"PRC-DIAL": "dialysis", "CON-FUP": "outpatient", "OTH-NURS": "outpatient"}.get(code, "physio")
        provider = self.rng.choice(self.providers_for(kind))
        claim_type = "daycare" if code == "PRC-DIAL" else "outpatient"
        claimant = self.rng.choice(policy.members)
        first_day = self.place(policy, claimant, gap, "open")
        if first_day is None:
            return False
        unit = self.price(code, provider)
        first_ref = self.ref(provider)
        for _ in range(20):
            second_ref = self.ref(provider)
            if ref_similarity(first_ref, second_ref) < 0.85:
                break
        else:
            return False
        first = self.new_claim(
            policy,
            claimant,
            first_day,
            claim_type,
            "open",
            [self.line(code, first_day, 1, provider, first_ref, unit)],
            "legit_repeat_first",
        )
        second_day = first_day + _days(gap)
        second = self.new_claim(
            policy,
            claimant,
            second_day,
            claim_type,
            "open",
            [self.line(code, second_day, 1, provider, second_ref, unit)],
            "legitimate_repeat",
        )
        second.submission_date = max(second.submission_date, first.submission_date + _days(1))
        if second.submission_date > TODAY or not self.fits(policy, first, second):
            return False
        self.commit(first, second)
        self.legit.append(
            {
                "claim": second,
                "line": second.lines[0],
                "matched_claim": first,
                "matched_line": first.lines[0],
                "service_code": code,
            }
        )
        return True

    def plant_line_across(self, index: int) -> bool:
        policy = self.rng.choice(self.hosts())
        kind = self.duplicate_kind(policy, ["inpatient", "daycare", "outpatient"])
        status = "settled" if index % 2 == 0 else "open"
        gap = self.rng.randint(8, 14)
        first = self.draft(
            policy, kind, status, tag="line_across_original", extra_span=gap, max_amount=policy.budget_left / 2
        )
        if first is None or (status == "settled" and first.line_total <= policy.deductible + 500):
            return False
        candidates = [
            line
            for line in first.lines
            if line.code.split("-")[0] in ("PHA", "CS") or line.code in ("DX-CBC", "DX-ECG", "DX-XRAY")
        ]
        if not candidates:
            return False
        copied = self.rng.choice(candidates)
        day = first.last_date + _days(gap)
        consult = self.line(self.rng.choice(["CON-SPL", "CON-GP"]), day, 1, first.provider, self.ref(first.provider))
        repeat = copied.copy()
        second = self.new_claim(
            policy, first.claimant_id, day, "outpatient", "open", [consult, repeat], "duplicate_line_across_claims"
        )
        second.submission_date = max(second.submission_date, first.submission_date + _days(1))
        a, b = first.line_total, second.line_total
        if (
            second.submission_date > TODAY
            or abs(a - b) / max(a, b) < Decimal("0.2")
            or not self.fits(policy, first, second)
        ):
            return False
        if status == "settled":
            self.settle(first, entitlement(policy, first.line_total)[0])
        self.commit(first, second)
        self.add_finding(
            "duplicate_line_across_claims",
            "DUPLICATE_LINE_ITEM",
            repeat.amount,
            second,
            match_type="duplicate_line",
            line=repeat,
            matched_claim=first,
            matched_line=copied,
        )
        return True

    def plant_line_within(self, index: int) -> bool:
        policy = self.rng.choice(self.hosts())
        kind = self.duplicate_kind(policy, ["outpatient", "inpatient", "pharmacy", "daycare"])

        def double(claim: Claim) -> dict[str, Any] | None:
            candidates = [
                line for line in claim.lines
                if line.code.split("-")[0] in ("PHA", "CS") or line.code in ("CON-GP", "CON-SPL", "CON-EMR", "OTH-REG")
            ]  # fmt: skip
            if not candidates:
                return None
            original = self.rng.choice(candidates)
            repeat = original.copy()
            claim.lines.insert(claim.lines.index(original) + 1, repeat)
            return {
                "category": "DUPLICATE_LINE_ITEM",
                "amount": repeat.amount,
                "match_type": "duplicate_line",
                "line": repeat,
                "matched_line": original,
            }

        opts: dict[str, Any] = {"max_amount": policy.budget_left} if kind == "inpatient" else {}
        return self.plant_simple("duplicate_line_within_claim", policy, kind, "open", double, **opts)

    # ---- clean claims ----------------------------------------------------------------------------------------

    def clean_kind(self, policy: Policy) -> str:
        kinds = {"outpatient": 38, "pharmacy": 18, "diagnostics": 16, "daycare": 9, "inpatient": 7, "physio": 8}
        if "daycare" not in policy.covered_claim_types:
            kinds.pop("daycare")
        if policy.physio_rule is None:
            kinds.pop("physio")
        return self.rng.choices(list(kinds), list(kinds.values()))[0]

    def fill_clean(self) -> None:
        if self.demo:
            targets = {"open": 6, "settled": 4}
        else:
            targets = {
                "open": round(FULL_OPEN_CLAIMS * self.scale),
                "settled": round(FULL_SETTLED_CLAIMS * self.scale),
            }
        if not self.demo:  # the demo pack adds a few clean claims on top of its scenarios
            for claim in self.claims:
                targets[claim.status] -= 1
        general = [p for p in self.policies if p.kind == "general"]
        attempts = 0
        while (targets["open"] > 0 or targets["settled"] > 0) and attempts < 200000:
            attempts += 1
            status = self.rng.choices(["open", "settled"], [max(targets["open"], 0), max(targets["settled"], 0)])[0]
            policy = self.rng.choice(general)
            kind = self.clean_kind(policy)
            opts: dict[str, Any] = {"max_amount": policy.budget_left} if kind == "inpatient" else {}
            claim = self.draft(policy, kind, status, **opts)
            if claim is None or not self.fits(policy, claim):
                continue
            if status == "settled":
                if policy.basis == "per_period" and claim.line_total <= policy.deductible + 500:
                    continue
                if policy.basis == "per_claim":
                    self.settle_clean(claim)
            self.commit(claim)
            targets[status] -= 1
        if targets["open"] > 0 or targets["settled"] > 0:
            raise ScenarioFailed(f"could not place enough clean claims: {targets}")

    def plant_mismatches(self) -> None:
        """Open clean claims whose requested amount differs from their lines by more than Rs 1 (warning only)."""
        n = 1 if self.demo else max(1, round(25 * self.scale))
        pool = [c for c in self.claims if c.tag == "clean" and c.status == "open" and c.policy.basis == "per_claim"]
        for claim in self.rng.sample(pool, n):
            delta = Decimal(self.rng.choice(range(50, 2001, 50)))
            claim.requested_override = claim.line_total + delta
            claim.tag = "requested_mismatch"
            self.mismatched.append(claim)

    def settle_per_period(self) -> None:
        """Settle clean claims on per-period-deductible policies in incident order; drop any the deductible swallows."""
        for policy in self.policies:
            if policy.basis != "per_period":
                continue
            left = policy.deductible
            settled = sorted(
                (c for c in self.claims if c.policy is policy and c.status == "settled"),
                key=lambda c: (c.incident_date, c.seq),
            )
            for claim in settled:
                if claim.line_total <= left + 500:
                    self.claims.remove(claim)
                    continue
                payable, applied = entitlement(policy, claim.line_total, left)
                left -= applied
                self.settle(claim, payable)

    def assign_ids(self) -> None:
        self.claims.sort(key=lambda c: (c.submission_date, c.incident_date, c.seq))
        line_no = 0
        settlement_no = 0
        for number, claim in enumerate(self.claims, start=1):
            claim.claim_id = f"CLM-{self.ids.claim + number:06d}"
            for line in claim.lines:
                line_no += 1
                line.line_id = f"LN-{self.ids.line + line_no:07d}"
            if claim.settlement is not None:
                settlement_no += 1
                claim.settlement.settlement_id = f"STL-{self.ids.settlement + settlement_no:06d}"
        self.policies.sort(key=lambda p: p.number)
