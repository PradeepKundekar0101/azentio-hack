"""Renders supporting documents from their printed content: invoice PDFs in two layouts, scanned-looking invoice
images, and discharge summary PDFs. Every renderer is deterministic: the same content gives the same bytes.

Invoice content: number, provider_name, provider_city, provider_id, invoice_date, patient_name, member_id,
policy_number, visit_date, lines [{code, description, service_date, quantity, unit_price, amount}], total.
Discharge summary content: hospital_name, hospital_city, patient_name, member_id, policy_number, admission_date,
discharge_date, diagnosis, icd10, procedures [text], treating_doctor.
"""

import io
import random
from datetime import date
from decimal import Decimal
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def money(value: Decimal) -> str:
    """Indian digit grouping with paise: 142000 -> 1,42,000.00."""
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


def quantity(value: Decimal) -> str:
    return f"{value.normalize():f}"


def invoice_layout_a(doc: dict[str, Any]) -> bytes:
    """Hospital tax invoice: boxed header, coded table."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, invariant=1, pageCompression=0)
    width, height = A4
    pdf.setTitle(f"Invoice {doc['number']}")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, height - 50, doc["provider_name"])
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, height - 66, f"{doc['provider_city']}, India    Provider ID: {doc['provider_id']}")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawRightString(width - 40, height - 50, "TAX INVOICE")
    pdf.rect(40, height - 160, width - 80, 78)
    pdf.setFont("Helvetica", 10)
    left = [
        f"Invoice No: {doc['number']}",
        f"Invoice Date: {ddmmyyyy(doc['invoice_date'])}",
        f"Admission / Visit Date: {ddmmyyyy(doc['visit_date'])}",
    ]
    right = [f"Patient: {doc['patient_name']}", f"Member ID: {doc['member_id']}", f"Policy No: {doc['policy_number']}"]
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
    for line in doc["lines"]:
        y -= 16
        pdf.drawString(columns[0], y, line["code"])
        pdf.drawString(columns[1], y, line["description"][:38])
        pdf.drawString(columns[2], y, ddmmyyyy(line["service_date"]))
        pdf.drawRightString(columns[3] + 25, y, quantity(line["quantity"]))
        pdf.drawRightString(columns[4] + 60, y, money(line["unit_price"]))
        pdf.drawRightString(width - 40, y, money(line["amount"]))
    pdf.line(40, y - 8, width - 40, y - 8)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(370, y - 26, "Total (Rs)")
    pdf.drawRightString(width - 40, y - 26, money(doc["total"]))
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(40, 40, "This is a computer-generated invoice. Synthetic sample data for testing.")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def invoice_layout_b(doc: dict[str, Any]) -> bytes:
    """Clinic bill of supply: centred header, no codes, quantity x rate in one column."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, invariant=1, pageCompression=0)
    width, height = A4
    pdf.setTitle(f"Bill {doc['number']}")
    pdf.setFont("Times-Bold", 18)
    pdf.drawCentredString(width / 2, height - 60, doc["provider_name"].upper())
    pdf.setFont("Times-Roman", 11)
    pdf.drawCentredString(width / 2, height - 78, f"{doc['provider_city']} | BILL OF SUPPLY")
    pdf.line(60, height - 90, width - 60, height - 90)
    details = [
        ("Bill Number", doc["number"]),
        ("Bill Date", ddmmyyyy(doc["invoice_date"])),
        ("Patient Name", doc["patient_name"]),
        ("Insurance Policy", doc["policy_number"]),
        ("Date of Treatment", ddmmyyyy(doc["visit_date"])),
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
    for line in doc["lines"]:
        y -= 17
        pdf.drawString(70, y, line["description"][:36])
        pdf.drawString(300, y, ddmmyyyy(line["service_date"]))
        pdf.drawString(380, y, f"{quantity(line['quantity'])} x {money(line['unit_price'])}")
        pdf.drawRightString(width - 70, y, f"Rs. {money(line['amount'])}")
    y -= 24
    pdf.line(300, y + 12, width - 70, y + 12)
    pdf.setFont("Times-Bold", 12)
    pdf.drawString(300, y - 4, "Net Amount Payable")
    pdf.drawRightString(width - 70, y - 4, f"Rs. {money(doc['total'])}")
    pdf.setFont("Times-Italic", 9)
    pdf.drawString(70, 50, "Received with thanks. Synthetic sample document.")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def invoice_scan(doc: dict[str, Any], seed: str, fmt: str = "png", angle: float | None = None) -> bytes:
    """A scanned-looking invoice: drawn at 150 dpi, slightly rotated, speckled and softened.

    `seed` drives the speckle noise and (unless `angle` is given) the rotation, so two scans of one bill with
    different seeds differ in bytes but stay perceptually near-identical."""
    rng = random.Random(seed)
    image = Image.new("L", (1240, 1754), 246)
    draw = ImageDraw.Draw(image)
    big, normal = ImageFont.load_default(size=40), ImageFont.load_default(size=26)
    draw.text((90, 90), doc["provider_name"], fill=20, font=big)
    draw.text((90, 150), f"{doc['provider_city']}  -  INVOICE", fill=40, font=normal)
    header = [
        f"Invoice No: {doc['number']}",
        f"Date: {ddmmyyyy(doc['invoice_date'])}",
        f"Patient: {doc['patient_name']}  ({doc['member_id']})",
        f"Policy: {doc['policy_number']}",
    ]
    y = 230
    for text in header:
        draw.text((90, y), text, fill=30, font=normal)
        y += 40
    y += 30
    for x, title in zip((90, 560, 760, 950), ("Description", "Date", "Qty x Rate", "Amount"), strict=True):
        draw.text((x, y), title, fill=10, font=normal)
    draw.line((90, y + 36, 1150, y + 36), fill=60, width=2)
    for line in doc["lines"]:
        y += 48
        draw.text((90, y), line["description"][:30], fill=35, font=normal)
        draw.text((560, y), ddmmyyyy(line["service_date"]), fill=35, font=normal)
        draw.text((760, y), f"{quantity(line['quantity'])} x {money(line['unit_price'])}", fill=35, font=normal)
        draw.text((950, y), money(line["amount"]), fill=35, font=normal)
    y += 70
    draw.line((560, y - 14, 1150, y - 14), fill=60, width=2)
    draw.text((560, y), f"TOTAL Rs. {money(doc['total'])}", fill=10, font=big)
    for _ in range(9000):
        draw.point((rng.randrange(1240), rng.randrange(1754)), fill=rng.randrange(80, 200))
    rotation = angle if angle is not None else rng.choice([-1.6, -1.1, 0.9, 1.4])
    image = image.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    image = image.filter(ImageFilter.GaussianBlur(0.7))
    buffer = io.BytesIO()
    if fmt == "jpeg":
        image.save(buffer, format="JPEG", quality=72)
    else:
        image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def discharge_summary(doc: dict[str, Any]) -> bytes:
    """Hospital discharge summary: patient block, stay dates, diagnosis, procedures, treating doctor."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, invariant=1, pageCompression=0)
    width, height = A4
    pdf.setTitle(f"Discharge summary {doc['patient_name']}")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(width / 2, height - 52, doc["hospital_name"])
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(width / 2, height - 68, f"{doc['hospital_city']}, India")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawCentredString(width / 2, height - 96, "DISCHARGE SUMMARY")
    pdf.line(50, height - 104, width - 50, height - 104)
    pdf.setFont("Helvetica", 10)
    rows = [
        ("Patient Name", doc["patient_name"]),
        ("Member ID", doc["member_id"]),
        ("Policy No", doc["policy_number"]),
        ("Date of Admission", ddmmyyyy(doc["admission_date"])),
        ("Date of Discharge", ddmmyyyy(doc["discharge_date"])),
        ("Treating Doctor", doc["treating_doctor"]),
    ]
    y = height - 128
    for label, value in rows:
        pdf.drawString(60, y, f"{label}:")
        pdf.drawString(200, y, value)
        y -= 17
    y -= 12
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(60, y, "Diagnosis")
    pdf.setFont("Helvetica", 10)
    y -= 16
    icd = f" (ICD-10 {doc['icd10']})" if doc.get("icd10") else ""
    pdf.drawString(70, y, f"{doc['diagnosis']}{icd}")
    y -= 26
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(60, y, "Procedures Performed")
    pdf.setFont("Helvetica", 10)
    for text in doc["procedures"] or ["No surgical procedure. Managed conservatively."]:
        y -= 16
        pdf.drawString(70, y, f"- {text}")
    y -= 26
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(60, y, "Condition at Discharge")
    pdf.setFont("Helvetica", 10)
    y -= 16
    pdf.drawString(70, y, "Stable. Advised review in the out-patient clinic after one week.")
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(50, 40, "Synthetic sample document for testing.")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
