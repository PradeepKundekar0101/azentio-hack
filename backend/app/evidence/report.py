"""The downloadable investigation report: structured JSON, and a PDF of the same content."""

from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.money import inr
from app.evidence.chain import to_json

SCHEMA_VERSION = 1

INK = colors.HexColor("#141a33")
MUTED = colors.HexColor("#5b6385")
RULE = colors.HexColor("#e3e6ef")
ACCENT = colors.HexColor("#0f5257")
SOFT = colors.HexColor("#f4f6f8")

KIND_LABELS = {
    "opened": "Investigation opened",
    "recalculated": "Recalculated",
    "decision": "Decision",
    "override": "Override",
    "note": "Note",
    "exported": "Report downloaded",
}


def build_report(view: dict[str, Any], generated_by: str) -> dict[str, Any]:
    """The full evidence history as one JSON document. Snapshots are included in full."""
    return to_json(
        {
            "report": {
                "title": f"Investigation report: claim {view['claim']['claim_id']}",
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(UTC).isoformat(),
                "generated_by": generated_by,
            },
            "claim": view["claim"],
            "investigation": view["investigation"],
            "integrity": {
                **view["integrity"],
                "method": "SHA-256 over each entry's fields and the previous entry's hash",
            },
            "summary": view["summary"],
            "original_calculation": view["original"],
            "findings": view["findings"],
            "evidence_history": list(reversed(view["events"])),
        }
    )


# PDF


def _money(value: Any) -> str:
    # The standard PDF fonts have no rupee sign, so the PDF writes "Rs".
    return "-" if value is None else inr(Decimal(str(value))).replace("₹", "Rs ")


def _when(value: Any) -> str:
    if value is None:
        return "-"
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return moment.astimezone(UTC).strftime("%d %b %Y, %H:%M UTC")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK
    )
    return {
        "title": ParagraphStyle("title", parent=body, fontName="Helvetica-Bold", fontSize=18, leading=22),
        "subtitle": ParagraphStyle("subtitle", parent=body, textColor=MUTED, fontSize=10, leading=14),
        "h2": ParagraphStyle(
            "h2", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=5
        ),
        "body": body,
        "small": ParagraphStyle("small", parent=body, fontSize=7.5, leading=10, textColor=MUTED),
        "mono": ParagraphStyle("mono", parent=body, fontName="Courier", fontSize=7.5, leading=10, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=body, fontSize=8, leading=10.5),
        "num": ParagraphStyle("num", parent=body, fontSize=8, leading=10.5, alignment=TA_RIGHT),
        "label": ParagraphStyle("label", parent=body, fontSize=7, leading=9, textColor=MUTED),
        "value": ParagraphStyle("value", parent=body, fontName="Helvetica-Bold", fontSize=11, leading=14),
    }


def _esc(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _table(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), SOFT), ("LINEBELOW", (0, 0), (-1, 0), 0.6, MUTED)]
    table.setStyle(TableStyle(style))
    return table


def render_pdf(report: dict[str, Any]) -> bytes:
    s = _styles()
    buffer = BytesIO()
    claim = report["claim"]
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=report["report"]["title"],
        author=report["report"]["generated_by"],
    )
    width = doc.width
    story: list[Any] = []

    story.append(Paragraph("INVESTIGATION REPORT", ParagraphStyle("eyebrow", parent=s["label"], textColor=ACCENT)))
    story.append(Paragraph(f"Claim {_esc(claim['claim_id'])}", s["title"]))
    story.append(
        Paragraph(
            f"{_esc(claim['claimant_name'])} · policy {_esc(claim['policy_number'])} · "
            f"{_esc(claim['claim_type'])} · incident {_esc(claim['incident_date'])} · "
            f"requested {_money(claim['requested_amount'])}",
            s["subtitle"],
        )
    )
    story.append(Spacer(1, 6))

    integrity = report["integrity"]
    seal = (
        f"<font color='#1f7a4d'><b>Evidence chain verified</b></font>: "
        f"{integrity['events']} entries, unchanged since recorded."
        if integrity["verified"]
        else f"<font color='#b42318'><b>Evidence chain broken</b></font> at entry "
        f"{integrity['broken_at']}: {_esc(integrity['reason'])}."
    )
    story.append(Paragraph(seal, s["body"]))
    story.append(Paragraph(f"Head hash {integrity['head_hash'] or '-'}", s["mono"]))
    story.append(
        Paragraph(
            f"Generated {_when(report['report']['generated_at'])} by {_esc(report['report']['generated_by'])}. "
            f"Investigation opened {_when((report['investigation'] or {}).get('opened_at'))} by "
            f"{_esc((report['investigation'] or {}).get('opened_by', '-'))}.",
            s["small"],
        )
    )
    story.append(Spacer(1, 8))

    summary = report["summary"]
    tiles = [
        ("Original calculated leakage", _money(summary["original_calculated_leakage"])),
        ("Current calculated leakage", _money(summary["current_calculated_leakage"])),
        ("After analyst overrides", _money(summary["adjusted_calculated_leakage"])),
        ("Estimated, for review", _money(summary["estimated_leakage"])),
    ]
    tile_table = Table(
        [[Paragraph(label, s["label"]) for label, _ in tiles], [Paragraph(value, s["value"]) for _, value in tiles]],
        colWidths=[width / 4] * 4,
    )
    tile_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("LINEAFTER", (0, 0), (-2, -1), 0.6, colors.white),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(tile_table)

    story.append(Paragraph("Findings and recommended corrections", s["h2"]))
    rows: list[list[Any]] = [
        [Paragraph(h, s["label"]) for h in ("Finding", "Rule and calculation", "Recommended", "Applied", "Decision")]
    ]
    for f in report["findings"]:
        rec = f["recommendation"]
        original = f["original_recommendation"] or rec
        applied = _money(f["effective_correction"])
        if f["override"] and not f["override"]["reverted"]:
            applied += f"<br/><font size='7' color='#5b6385'>override: {_esc(f['override']['reason'])}</font>"
        decision = f["decision"]
        rows.append(
            [
                Paragraph(
                    f"<b>{_esc(f['category_label'])}</b><br/>{_esc(f['severity'])} · {_esc(rec['amount_type'])}",
                    s["cell"],
                ),
                Paragraph(
                    _esc(rec["rule_or_pattern"])
                    + (f" · {_esc(rec['policy_rule_id'])}" if rec["policy_rule_id"] else "")
                    + f"<br/><font color='#5b6385'>{_esc((rec['calculation'] or '').replace('₹', 'Rs '))}</font>",
                    s["cell"],
                ),
                Paragraph(_money(original["correction"]), s["num"]),
                Paragraph(applied, s["num"]),
                Paragraph(
                    (
                        f"{_esc(decision['status'])}<br/><font size='7' color='#5b6385'>"
                        f"{_esc(decision['actor'])}, {_when(decision['at'])}</font>"
                        if decision
                        else "<font color='#5b6385'>Not decided</font>"
                    ),
                    s["cell"],
                ),
            ]
        )
    if len(rows) == 1:
        rows.append([Paragraph("No findings on this claim.", s["cell"]), "", "", "", ""])
    story.append(_table(rows, [width * 0.2, width * 0.36, width * 0.13, width * 0.15, width * 0.16]))

    original = report["original_calculation"]
    if original and original.get("payable_steps"):
        story.append(Paragraph("Original calculation, as frozen when the investigation opened", s["h2"]))
        steps = [[Paragraph(h, s["label"]) for h in ("Step", "Explanation", "Before", "Reduction", "After")]]
        for step in original["payable_steps"]:
            steps.append(
                [
                    Paragraph(_esc(step["step_code"]), s["cell"]),
                    Paragraph(_esc(step["explanation"].replace("₹", "Rs ")), s["cell"]),
                    Paragraph(_money(step["amount_before"]), s["num"]),
                    Paragraph(_money(step["reduction"]), s["num"]),
                    Paragraph(_money(step["amount_after"]), s["num"]),
                ]
            )
        story.append(_table(steps, [width * 0.2, width * 0.44, width * 0.12, width * 0.12, width * 0.12]))

    story.append(Paragraph("Evidence history", s["h2"]))
    history = [[Paragraph(h, s["label"]) for h in ("#", "When", "Who", "What", "Hash")]]
    for event in report["evidence_history"]:
        who = event["actor"] + (f" ({event['actor_role']})" if event.get("actor_role") else "")
        detail = _esc(event["summary"].replace("₹", "Rs "))
        payload = event.get("payload") or {}
        if event["kind"] == "override":
            detail += f"<br/><font color='#5b6385'>Reason: {_esc(payload.get('reason', ''))}</font>"
        if event["kind"] == "decision" and payload.get("note"):
            detail += f"<br/><font color='#5b6385'>Note: {_esc(payload['note'])}</font>"
        history.append(
            [
                Paragraph(str(event["seq"]), s["cell"]),
                Paragraph(_when(event["at"]), s["cell"]),
                Paragraph(_esc(who), s["cell"]),
                Paragraph(f"<b>{KIND_LABELS.get(event['kind'], event['kind'])}</b><br/>{detail}", s["cell"]),
                Paragraph(event["hash"][:16] + "…", s["mono"]),
            ]
        )
    story.append(_table(history, [width * 0.05, width * 0.18, width * 0.14, width * 0.48, width * 0.15]))

    story.append(Spacer(1, 10))
    story.append(
        KeepTogether(
            Paragraph(
                "Each entry's hash covers its own content and the previous entry's hash (SHA-256), so a change to any "
                "entry breaks every hash after it. The JSON version of this report contains every entry in full, "
                "including the frozen calculations.",
                s["small"],
            )
        )
    )

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 9 * mm, f"Claims Leakage · claim {claim['claim_id']} · investigation report")
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
