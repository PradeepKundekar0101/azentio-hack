"""Datasets, their fields, and header/dataset-name synonyms.

Headers and names are compared in "compact" form: lowercase with everything except letters and digits removed,
so "Claim ID", "claim_id", "ClaimID" and "CLAIM-ID" all match `claim_id`.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum


class Dataset(StrEnum):
    POLICIES = "policies"
    POLICY_RULES = "policy_rules"
    CLAIMS = "claims"
    LINE_ITEMS = "line_items"
    SETTLEMENTS = "settlements"


# Parents load before children, so references inside one upload resolve.
LOAD_ORDER = (Dataset.POLICIES, Dataset.POLICY_RULES, Dataset.CLAIMS, Dataset.LINE_ITEMS, Dataset.SETTLEMENTS)


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclass(frozen=True)
class DatasetSpec:
    dataset: Dataset
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()
    synonyms: dict[str, tuple[str, ...]] = field(default_factory=dict)
    names: tuple[str, ...] = ()

    @property
    def fields(self) -> tuple[str, ...]:
        return self.required + self.optional


SPECS: dict[Dataset, DatasetSpec] = {
    Dataset.POLICIES: DatasetSpec(
        Dataset.POLICIES,
        required=(
            "policy_number",
            "policyholder_name",
            "insured_member_ids",
            "product_name",
            "benefit_period_start",
            "benefit_period_end",
            "overall_limit",
            "deductible_amount",
            "deductible_basis",
            "copay_percent",
        ),
        synonyms={
            "policy_number": ("policyno",),
            "policyholder_name": ("policyholder",),
            "insured_member_ids": ("memberids", "insuredmembers"),
            "product_name": ("product", "plan"),
            "benefit_period_start": ("periodstart", "coverstart"),
            "benefit_period_end": ("periodend", "coverend"),
            "overall_limit": ("suminsured",),
            "deductible_amount": ("deductible",),
            "deductible_basis": ("deductibletype",),
            "copay_percent": ("copay", "copaypct"),
        },
        names=("policies", "policy"),
    ),
    Dataset.POLICY_RULES: DatasetSpec(
        Dataset.POLICY_RULES,
        required=("rule_id", "policy_number", "rule_type", "scope_type", "scope_value", "clause_ref"),
        optional=("limit_basis", "limit_amount", "description"),
        synonyms={
            "rule_id": ("ruleno",),
            "policy_number": ("policyno",),
            "clause_ref": ("clause", "clausereference"),
        },
        names=("policyrules", "rules"),
    ),
    Dataset.CLAIMS: DatasetSpec(
        Dataset.CLAIMS,
        required=(
            "claim_id",
            "policy_number",
            "claimant_id",
            "claimant_name",
            "incident_date",
            "submission_date",
            "claim_type",
            "requested_amount",
            "status",
        ),
        optional=("incident_reference",),
        synonyms={
            "claim_id": ("claimno", "claimnumber"),
            "policy_number": ("policyno", "policynum"),
            "claimant_id": ("memberid", "insuredid"),
            "claimant_name": ("membername", "patientname"),
            "incident_date": ("dateofincident", "admissiondate"),
            "submission_date": ("dateofsubmission", "submitteddate"),
            "requested_amount": ("claimamount", "amountclaimed", "claimedamount"),
            "incident_reference": ("incidentref",),
            "status": ("claimstatus",),
        },
        names=("claims",),
    ),
    Dataset.LINE_ITEMS: DatasetSpec(
        Dataset.LINE_ITEMS,
        required=(
            "line_id",
            "claim_id",
            "invoice_reference",
            "provider_id",
            "provider_name",
            "service_date",
            "service_code",
            "service_description",
            "category",
            "quantity",
            "unit_price",
            "line_amount",
        ),
        synonyms={
            "line_id": ("lineno", "lineitemid"),
            "invoice_reference": ("invoiceno", "invoicenumber", "invoiceref", "billno"),
            "provider_id": ("providercode", "hospitalid"),
            "provider_name": ("hospitalname",),
            "service_date": ("dateofservice",),
            "service_code": ("procedurecode",),
            "service_description": ("description",),
            "category": ("servicecategory",),
            "quantity": ("qty", "units"),
            "unit_price": ("rate", "unitrate"),
            "line_amount": ("amount", "linetotal"),
        },
        names=("lineitems", "lines", "claimlines"),
    ),
    Dataset.SETTLEMENTS: DatasetSpec(
        Dataset.SETTLEMENTS,
        required=(
            "settlement_id",
            "claim_id",
            "settlement_date",
            "approved_amount",
            "paid_amount",
            "settlement_status",
        ),
        synonyms={
            "settlement_id": ("settlementno",),
            "claim_id": ("claimno",),
            "approved_amount": ("approved",),
            "paid_amount": ("paid", "amountpaid"),
            "settlement_status": ("status",),
        },
        names=("settlements", "payments"),
    ),
}


def dataset_from_name(name: str) -> Dataset | None:
    """Match a file stem, sheet name or JSON key to a dataset."""
    key = compact(name)
    for spec in SPECS.values():
        if key in spec.names:
            return spec.dataset
    # File names like "claims_data_2026" or "demo_line_items": accept a contained name, longest first.
    candidates = sorted(((n, s.dataset) for s in SPECS.values() for n in s.names), key=lambda c: -len(c[0]))
    for candidate, dataset in candidates:
        if candidate in key:
            return dataset
    return None


@dataclass
class HeaderMap:
    columns: dict[str, str]  # original header -> field
    missing: list[str]  # required fields with no column
    unknown: list[str]  # original headers that match no field


def map_headers(dataset: Dataset, headers: list[str]) -> HeaderMap:
    spec = SPECS[dataset]
    lookup: dict[str, str] = {}
    for name in spec.fields:
        lookup[compact(name)] = name
        for synonym in spec.synonyms.get(name, ()):
            lookup[synonym] = name
    columns: dict[str, str] = {}
    unknown: list[str] = []
    for header in headers:
        target = lookup.get(compact(header))
        if target is None or target in columns.values():
            unknown.append(header)
        else:
            columns[header] = target
    missing = [name for name in spec.required if name not in columns.values()]
    return HeaderMap(columns=columns, missing=missing, unknown=unknown)


def dataset_from_headers(headers: list[str]) -> Dataset | None:
    """Pick the dataset whose required fields the headers cover best (all of them, for a match)."""
    best: tuple[int, Dataset] | None = None
    for dataset in LOAD_ORDER:
        header_map = map_headers(dataset, headers)
        if header_map.missing:
            continue
        score = len(header_map.columns)
        if best is None or score > best[0]:
            best = (score, dataset)
    return best[1] if best else None
