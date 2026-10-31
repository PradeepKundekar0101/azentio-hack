"""Generate the synthetic claims data set, the demo pack and their answer keys under data/sample/.

Usage: uv run python -m scripts.generate_data [--seed 42] [--scale 1.0] [--out ../data/sample]

Every run re-reads its own CSV, Excel and JSON output, checks the three are identical, and recomputes every
answer-key entry with an independent checker (scripts/datagen/oracle.py). It fails loudly on any difference.
"""

import argparse
import time
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT
from scripts.datagen.builder import Builder, BuildResult
from scripts.datagen.oracle import verify
from scripts.datagen.readback import read_all
from scripts.datagen.render import Row, render, write_all

DEFAULT_OUT = REPO_ROOT / "data" / "sample"


class GenerationError(RuntimeError):
    pass


def build(seed: int, scale: float, demo: bool) -> tuple[BuildResult, dict[str, list[Row]], dict[str, Any]]:
    """Build one data set in memory: typed records, file rows and the answer key."""
    result = Builder(seed=seed, scale=scale, demo=demo).build()
    rows, key = render(result, seed, scale, demo)
    return result, rows, key


def write_and_verify(directory: Path, rows: dict[str, list[Row]], key: dict[str, Any]) -> None:
    write_all(directory, rows, key)
    formats = read_all(directory)
    plain = {
        ds: [{k: (list(v) if isinstance(v, list) else v) for k, v in row.items()} for row in items]
        for ds, items in rows.items()
    }
    for name, parsed in formats.items():
        if parsed != plain:
            raise GenerationError(f"{directory}: the {name} export does not round-trip to the generated rows")
    problems = verify(formats["csv"], key)
    if problems:
        raise GenerationError(f"{directory}: answer key not verified:\n" + "\n".join(problems[:40]))


def generate(out: Path, seed: int = 42, scale: float = 1.0) -> dict[str, dict[str, Any]]:
    keys = {}
    for demo, directory in ((False, out), (True, out / "demo")):
        _, rows, key = build(seed, scale, demo)
        write_and_verify(directory, rows, key)
        keys["demo" if demo else "full"] = key
    return keys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    started = time.perf_counter()
    keys = generate(args.out, args.seed, args.scale)
    for name, key in keys.items():
        scenarios: dict[str, int] = {}
        for finding in key["findings"]:
            scenarios[finding["scenario"]] = scenarios.get(finding["scenario"], 0) + 1
        print(
            f"{name}: rows {key['counts']}, findings {len(key['findings'])}, "
            f"legitimate repeats {len(key['legitimate_repeats'])}, invalid rows {len(key['invalid_rows'])}"
        )
        print(f"  scenarios {dict(sorted(scenarios.items()))}")
    print(f"verified and written to {args.out} in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
