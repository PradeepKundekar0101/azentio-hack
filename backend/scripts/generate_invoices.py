"""Generate sample invoice documents for the demo pack under data/sample/invoices/.

Usage: uv run python -m scripts.generate_invoices [--seed 42] [--out ../data/sample/invoices]

- 10 PDF invoices in two layouts for new claims of demo-pack members (not in the demo files, so uploading them
  creates new claims), two of them with a planted policy issue;
- 2 scanned-looking images (PNG and JPEG): rasterised, slightly rotated, with speckle noise;
- 1 PDF that re-issues an invoice already in the demo pack (an exact duplicate once confirmed).

manifest.json lists, per file, the claim it represents, its line items and total, and the findings the
independent checker computes when that claim is added to the demo pack.
"""

import argparse
import io
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import REPO_ROOT
from scripts.datagen.builder import Builder
from scripts.datagen.common import TODAY
from scripts.datagen.model import Claim, Line
from scripts.datagen.oracle import check
from scripts.datagen.render import Row, plain_amount, render

DEFAULT_OUT = REPO_ROOT / "data" / "sample" / "invoices"
INVOICE_CLAIM_BASE = 950000


@dataclass
class Invoice:
    file: str
    kind: str  # pdf or scan
    layout: str
    claim: Claim
    claim_id: str
    duplicate_of: str | None = None

    @property
    def reference(self) -> str:
        return self.claim.lines[0].invoice_ref

    @property
    def total(self) -> Decimal:
        return self.claim.line_total

    @property
    def invoice_date(self) -> date:
        return self.claim.last_date + timedelta(days=1)


def money(value: Decimal) -> str:
    rupees, paise = f"{value:.2f}".split(".")
    digits = rupees
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    return f"{digits}.{paise}"


def ddmmyyyy(value: date) -> str:
    return value.strftime("%d/%m/%Y")


# ---- claims behind the documents ----------------------------------------------------------------------------


def invoice_claims(builder: Builder, rng: random.Random) -> list[Claim]:
    """Twelve new open claims for demo members, each on a single invoice."""
    general = [p for p in builder.policies if p.kind == "general"]
    specs: list[tuple[str, dict[str, Any], str | None]] = [
        ("outpatient", {"single": True}, None),
        ("inpatient", {"fmt": "A", "icu": False, "procedure": "PRC-APPX"}, None),
        ("diagnostics", {}, None),
        ("pharmacy", {}, None),
        ("daycare", {"procedure": "PRC-CATA"}, None),
        ("inpatient", {"fmt": "A", "icu": False}, "room"),
        ("outpatient", {"single": True}, "vitamins"),
        ("inpatient", {"fmt": "A", "icu": False, "procedure": "PRC-HERN"}, None),
        ("diagnostics", {}, None),
        ("outpatient", {"single": True}, None),
        ("pharmacy", {}, None),
        ("diagnostics", {}, None),
    ]
    claims = []
    for kind, opts, issue in specs:
        for _ in range(200):
            policy = rng.choice(general)
            if kind == "daycare" and "daycare" not in policy.covered_claim_types:
                continue
            if issue == "vitamins" and "PHA-VIT" not in policy.exclusions:
                continue
            extra = dict(opts)
            if issue == "room":
                extra["room_rate"] = policy.room_rule.limit_amount + 1500  # type: ignore[union-attr,operator]
                extra["los"] = 3
            claim = builder.draft(policy, kind, "open", tag="invoice", **extra)
            if claim is None:
                continue
            ref = claim.lines[0].invoice_ref
            for line in claim.lines:
                line.invoice_ref = ref
            if issue == "vitamins":
                claim.lines.append(builder.line("PHA-VIT", claim.incident_date, 2, claim.provider, ref))
            builder.commit(claim)
            builder.claims.remove(claim)
            claims.append(claim)
            break
        else:
            raise RuntimeError(f"could not place an invoice claim of kind {kind}")
    return claims


def claim_rows(claim: Claim, claim_id: str, line_prefix: str) -> tuple[Row, list[Row]]:
    row: Row = {
        "claim_id": claim_id,
        "policy_number": claim.policy.number,
        "claimant_id": claim.claimant_id,
        "claimant_name": claim.claimant_name,
        "incident_date": claim.incident_date.isoformat(),
        "submission_date": TODAY.isoformat(),  # documents are uploaded and confirmed today
        "claim_type": claim.claim_type,
        "requested_amount": plain_amount(claim.line_total),
        "incident_reference": None,
        "status": "open",
    }
    lines = [
        {
            "line_id": f"{line_prefix}{k:02d}",
            "claim_id": claim_id,
            "invoice_reference": line.invoice_ref,
            "provider_id": line.provider.provider_id,
            "provider_name": line.provider.name,
            "service_date": line.service_date.isoformat(),
            "service_code": line.code,
            "service_description": line.description,
            "category": line.category,
            "quantity": plain_amount(line.qty),
            "unit_price": plain_amount(line.unit_price),
            "line_amount": plain_amount(line.amount),
        }
        for k, line in enumerate(claim.lines, start=1)
    ]
    return row, lines


def expected_findings(demo_rows: dict[str, list[Row]], invoice: Invoice) -> list[dict[str, Any]]:
    """Findings the checker reports for this document's claim when it is added to the demo pack."""
    row, lines = claim_rows(invoice.claim, invoice.claim_id, f"LN-DOC{invoice.claim_id[-4:]}-")
    rows = {ds: list(items) for ds, items in demo_rows.items()}
    rows["claims"].append(row)
    rows["line_items"].extend(lines)
    report = check(rows)
    if report.anomalies:
        raise RuntimeError(f"{invoice.file}: {report.anomalies}")
    out = []
    for finding in report.findings:
        if finding["claim_id"] != invoice.claim_id:
            continue
        line_id = finding["line_id"]
        code = next((x["service_code"] for x in lines if x["line_id"] == line_id), None) if line_id else None
        out.append(
            {
                "category": finding["category"],
                "check_code": finding["check_code"],
                "match_type": finding["match_type"],
                "expected_amount": finding["expected_amount"],
                "policy_rule_id": finding["policy_rule_id"],
                "matched_claim_id": finding["matched_claim_id"],
                "service_code": code,
            }
        )
    return sorted(out, key=lambda f: (f["category"], f["expected_amount"]))


# ---- rendering ----------------------------------------------------------------------------------------------


def pdf_layout_a(invoice: Invoice) -> bytes:
    """Hospital tax invoice: boxed header, coded table."""
    claim = invoice.claim
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, invariant=1, pageCompression=0)
    width, height = A4
    pdf.setTitle(f"Invoice {invoice.reference}")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, height - 50, claim.provider.name)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, height - 66, f"{claim.provider.city}, India    Provider ID: {claim.provider.provider_id}")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawRightString(width - 40, height - 50, "TAX INVOICE")
    pdf.rect(40, height - 160, width - 80, 78)
    pdf.setFont("Helvetica", 10)
    left = [
        f"Invoice No: {invoice.reference}",
        f"Invoice Date: {ddmmyyyy(invoice.invoice_date)}",
        f"Admission / Visit Date: {ddmmyyyy(claim.incident_date)}",
    ]
    right = [
        f"Patient: {claim.claimant_name}",
        f"Member ID: {claim.claimant_id}",
        f"Policy No: {claim.policy.number}",
    ]
    for k, (a, b) in enumerate(zip(left, right, strict=True)):
        pdf.drawString(50, height - 102 - 18 * k, a)
        pdf.drawString(width / 2 + 10, height - 102 - 18 * k, b)
    columns = [40, 105, 300, 370, 410, 480]
    y = height - 190
    pdf.setFont("Helvetica-Bold", 9)
    for x, title in zip(columns, ["Code", "Description", "Date", "Qty", "Rate (Rs)", "Amount (Rs)"], strict=True):
        pdf.drawString(x, y, title)
    pdf.line(40, y - 4, width - 40, y - 4)
    pdf.setFont("Helvetica", 9)
    for line in claim.lines:
        y -= 16
        pdf.drawString(columns[0], y, line.code)
        pdf.drawString(columns[1], y, line.description[:38])
        pdf.drawString(columns[2], y, ddmmyyyy(line.service_date))
        pdf.drawRightString(columns[3] + 25, y, plain_amount(line.qty))
        pdf.drawRightString(columns[4] + 60, y, money(line.unit_price))
        pdf.drawRightString(width - 40, y, money(line.amount))
    pdf.line(40, y - 8, width - 40, y - 8)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(370, y - 26, "Total (Rs)")
    pdf.drawRightString(width - 40, y - 26, money(invoice.total))
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(40, 40, "This is a computer-generated invoice. Synthetic sample data for testing.")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def pdf_layout_b(invoice: Invoice) -> bytes:
    """Clinic bill of supply: centred header, no codes, quantity x rate in one column."""
    claim = invoice.claim
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, invariant=1, pageCompression=0)
    width, height = A4
    pdf.setTitle(f"Bill {invoice.reference}")
    pdf.setFont("Times-Bold", 18)
    pdf.drawCentredString(width / 2, height - 60, claim.provider.name.upper())
    pdf.setFont("Times-Roman", 11)
    pdf.drawCentredString(width / 2, height - 78, f"{claim.provider.city} | BILL OF SUPPLY")
    pdf.line(60, height - 90, width - 60, height - 90)
    details = [
        ("Bill Number", invoice.reference),
        ("Bill Date", ddmmyyyy(invoice.invoice_date)),
        ("Patient Name", claim.claimant_name),
        ("Insurance Policy", claim.policy.number),
        ("Date of Treatment", ddmmyyyy(claim.incident_date)),
    ]
    y = height - 115
    for label, value in details:
        pdf.drawString(70, y, f"{label}:")
        pdf.drawString(200, y, value)
        y -= 16
    y -= 14
    pdf.setFont("Times-Bold", 11)
    pdf.drawString(70, y, "Particulars")
    pdf.drawString(300, y, "Date")
    pdf.drawString(380, y, "Qty x Rate")
    pdf.drawRightString(width - 70, y, "Amount")
    pdf.setFont("Times-Roman", 11)
    for line in claim.lines:
        y -= 17
        pdf.drawString(70, y, line.description[:36])
        pdf.drawString(300, y, ddmmyyyy(line.service_date))
        pdf.drawString(380, y, f"{plain_amount(line.qty)} x {money(line.unit_price)}")
        pdf.drawRightString(width - 70, y, f"Rs. {money(line.amount)}")
    y -= 24
    pdf.line(300, y + 12, width - 70, y + 12)
    pdf.setFont("Times-Bold", 12)
    pdf.drawString(300, y - 4, "Net Amount Payable")
    pdf.drawRightString(width - 70, y - 4, f"Rs. {money(invoice.total)}")
    pdf.setFont("Times-Italic", 9)
    pdf.drawString(70, 50, "Received with thanks. Synthetic sample document.")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def scan_image(invoice: Invoice, rng: random.Random, fmt: str) -> bytes:
    """A scanned-looking invoice: drawn at 150 dpi, slightly rotated, speckled and softened."""
    claim = invoice.claim
    image = Image.new("L", (1240, 1754), 246)
    draw = ImageDraw.Draw(image)
    big, normal = ImageFont.load_default(size=40), ImageFont.load_default(size=26)
    draw.text((90, 90), claim.provider.name, fill=20, font=big)
    draw.text((90, 150), f"{claim.provider.city}  -  INVOICE", fill=40, font=normal)
    header = [
        f"Invoice No: {invoice.reference}",
        f"Date: {ddmmyyyy(invoice.invoice_date)}",
        f"Patient: {claim.claimant_name}  ({claim.claimant_id})",
        f"Policy: {claim.policy.number}",
    ]
    y = 230
    for text in header:
        draw.text((90, y), text, fill=30, font=normal)
        y += 40
    y += 30
    for x, title in zip((90, 560, 760, 950), ("Description", "Date", "Qty x Rate", "Amount"), strict=True):
        draw.text((x, y), title, fill=10, font=normal)
    draw.line((90, y + 36, 1150, y + 36), fill=60, width=2)
    for line in claim.lines:
        y += 48
        draw.text((90, y), line.description[:30], fill=35, font=normal)
        draw.text((560, y), ddmmyyyy(line.service_date), fill=35, font=normal)
        draw.text((760, y), f"{plain_amount(line.qty)} x {money(line.unit_price)}", fill=35, font=normal)
        draw.text((950, y), money(line.amount), fill=35, font=normal)
    y += 70
    draw.line((560, y - 14, 1150, y - 14), fill=60, width=2)
    draw.text((560, y), f"TOTAL Rs. {money(invoice.total)}", fill=10, font=big)
    for _ in range(9000):
        draw.point((rng.randrange(1240), rng.randrange(1754)), fill=rng.randrange(80, 200))
    angle = rng.choice([-1.6, -1.1, 0.9, 1.4])
    image = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    image = image.filter(ImageFilter.GaussianBlur(0.7))
    buffer = io.BytesIO()
    if fmt == "jpeg":
        image.save(buffer, format="JPEG", quality=72)
    else:
        image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


# ---- generation ---------------------------------------------------------------------------------------------


def line_json(line: Line) -> dict[str, Any]:
    return {
        "service_code": line.code,
        "description": line.description,
        "service_date": line.service_date.isoformat(),
        "quantity": plain_amount(line.qty),
        "unit_price": f"{line.unit_price:.2f}",
        "amount": f"{line.amount:.2f}",
    }


def generate(out: Path, seed: int = 42) -> dict[str, Any]:
    builder = Builder(seed=seed, demo=True)
    result = builder.build()
    demo_rows, _ = render(result, seed, 1.0, True)
    rng = random.Random(seed * 31 + 7)
    claims = invoice_claims(builder, rng)
    invoices = [
        Invoice(f"invoice_{k:02d}.pdf", "pdf", "A" if k % 2 else "B", claim, f"CLM-{INVOICE_CLAIM_BASE + k:06d}")
        for k, claim in enumerate(claims[:10], start=1)
    ]
    invoices.append(Invoice("scan_01.png", "scan", "scan", claims[10], f"CLM-{INVOICE_CLAIM_BASE + 11:06d}"))
    invoices.append(Invoice("scan_02.jpg", "scan", "scan", claims[11], f"CLM-{INVOICE_CLAIM_BASE + 12:06d}"))
    originals = [
        c
        for c in result.claims
        if c.tag == "clean" and c.status == "settled" and len({line.invoice_ref for line in c.lines}) == 1
    ]
    original = max(originals, key=lambda c: (c.line_total, c.claim_id))
    copy = Claim(
        policy=original.policy,
        claimant_id=original.claimant_id,
        claimant_name=original.claimant_name,
        incident_date=original.incident_date,
        submission_date=original.submission_date,
        claim_type=original.claim_type,
        status="open",
        lines=[line.copy() for line in original.lines],
        incident_ref=None,
        seq=0,
    )
    invoices.append(
        Invoice("invoice_duplicate.pdf", "pdf", "B", copy, f"CLM-{INVOICE_CLAIM_BASE + 13:06d}", original.claim_id)
    )

    out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    for invoice in invoices:
        if invoice.kind == "pdf":
            data = pdf_layout_a(invoice) if invoice.layout == "A" else pdf_layout_b(invoice)
        else:
            data = scan_image(invoice, rng, "jpeg" if invoice.file.endswith(".jpg") else "png")
        (out / invoice.file).write_bytes(data)
        claim = invoice.claim
        manifest[invoice.file] = {
            "claim_id": invoice.claim_id,
            "in_demo_files": False,
            "duplicate_of_claim_id": invoice.duplicate_of,
            "kind": invoice.kind,
            "layout": invoice.layout,
            "invoice_reference": invoice.reference,
            "invoice_date": invoice.invoice_date.isoformat(),
            "provider_id": claim.provider.provider_id,
            "provider_name": claim.provider.name,
            "policy_number": claim.policy.number,
            "claimant_id": claim.claimant_id,
            "claimant_name": claim.claimant_name,
            "claim_type": claim.claim_type,
            "incident_date": claim.incident_date.isoformat(),
            "line_items": [line_json(line) for line in claim.lines],
            "total": f"{invoice.total:.2f}",
            "expected_findings": expected_findings(demo_rows, invoice),
        }
    text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (out / "manifest.json").write_text(text, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    manifest = generate(args.out, args.seed)
    for name, entry in manifest.items():
        found = ", ".join(f"{f['category']} {f['expected_amount']}" for f in entry["expected_findings"]) or "none"
        print(f"{name}: {entry['claim_id']} {entry['invoice_reference']} total {entry['total']}; findings: {found}")


if __name__ == "__main__":
    main()
