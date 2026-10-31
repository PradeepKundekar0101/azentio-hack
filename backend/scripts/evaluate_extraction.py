"""Measure document extraction with the real model against the demo pack's answer key.

Usage: uv run python -m scripts.evaluate_extraction [--folder ../data/sample/demo] [--concurrency 6] [--limit N]
Needs ANTHROPIC_API_KEY. Reports, over the demo documents: classification accuracy, the share that passes
validation, the share of extracted values verified with a box (clean PDFs), and the share of printed values read
correctly. The plan's targets are 95% for validation and for verified values.
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT, get_settings
from app.documents.extract_sourced import extract_document
from app.documents.parse import parse_items
from app.documents.read import DocumentReader
from app.documents.validate import normalise_value


def expected_values(doc: dict[str, Any]) -> dict[str, str]:
    e = doc["expected"]
    if doc["doc_type"] == "discharge_summary":
        keys = ("patient_name", "hospital_name", "admission_date", "discharge_date")
        return {f"header.{k}": e[k] for k in keys}
    values = {f"header.{k}": e[k] for k in ("invoice_number", "patient_name", "invoice_date", "total")}
    for i, line in enumerate(e["lines"]):
        values[f"lines[{i}].amount"] = line["amount"]
    return values


async def evaluate_one(reader: DocumentReader, folder: Path, doc: dict[str, Any]) -> dict[str, Any]:
    path = folder / "documents" / doc["file"]
    data = path.read_bytes()
    file_type = "pdf" if path.suffix == ".pdf" else "png"
    parsed = await asyncio.to_thread(parse_items, data) if file_type == "pdf" else None
    result = await extract_document(reader, parsed, data, file_type, None)
    by_path = {f.field_path: f for f in result.fields}
    expected = expected_values(doc)
    correct = 0
    for path_name, value in expected.items():
        found = by_path.get(path_name)
        name = path_name.rsplit(".", 1)[-1]
        if found is not None and found.value_normalised == normalise_value(name, value):
            correct += 1
    filled = [f for f in result.fields if f.value_text is not None]
    return {
        "file": doc["file"],
        "kind": doc["kind"],
        "clean": doc["clean"],
        "doc_type_ok": result.doc_type == doc["doc_type"],
        "status": result.status,
        "errors": result.validation_errors,
        "filled": len(filled),
        "verified": sum(1 for f in filled if f.provenance_status == "verified" and f.bbox),
        "correct": correct,
        "expected": len(expected),
    }


async def evaluate(folder: Path, concurrency: int, limit: int | None) -> list[dict[str, Any]]:
    reader = DocumentReader(get_settings())
    if not reader.enabled:
        raise SystemExit("ANTHROPIC_API_KEY is not set")
    key = json.loads((folder / "answer_key.json").read_text())
    docs = [d for d in key["investigation"]["documents"] if d["reuse_of"] is None][:limit]
    gate = asyncio.Semaphore(concurrency)

    async def run(doc: dict[str, Any]) -> dict[str, Any]:
        async with gate:
            return await evaluate_one(reader, folder, doc)

    return await asyncio.gather(*(run(d) for d in docs))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folder", type=Path, default=REPO_ROOT / "data" / "sample" / "demo")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    results = asyncio.run(evaluate(args.folder, args.concurrency, args.limit))
    for r in sorted(results, key=lambda r: r["file"]):
        flag = "" if r["status"] == "ok" and r["doc_type_ok"] else "  <--"
        counts = f"verified {r['verified']}/{r['filled']} correct {r['correct']}/{r['expected']}"
        print(f"{r['file']:40} {r['status']:12} {counts}{flag}")
        for error in r["errors"]:
            print(f"    {error}")
    n = len(results)
    clean_pdfs = [r for r in results if r["clean"] and r["kind"] == "pdf"]
    verified = sum(r["verified"] for r in clean_pdfs) / max(1, sum(r["filled"] for r in clean_pdfs))
    print(f"\ndocuments {n}")
    print(f"classified correctly  {sum(r['doc_type_ok'] for r in results) / n:.1%}")
    print(f"validation passed     {sum(r['status'] == 'ok' for r in results) / n:.1%}  (target 95%)")
    print(f"verified, clean PDFs  {verified:.1%}  (target 95%)")
    print(
        f"values read correctly {sum(r['correct'] for r in results) / max(1, sum(r['expected'] for r in results)):.1%}"
    )


if __name__ == "__main__":
    main()
