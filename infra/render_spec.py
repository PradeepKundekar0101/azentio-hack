"""Render infra/app-spec.yaml with values from backend/.env and the deployment-only .env.do (both gitignored).

Prints the filled spec to stdout; never write it inside the repository.
.env.do holds DEPLOY_SESSION_SECRET and DEPLOY_DEMO_PASSWORD, so the deployed app never shares the local login.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"\$\{([A-Z_]+)\}")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def main() -> None:
    env = {**read_env(ROOT / "backend" / ".env"), **read_env(ROOT / ".env.do")}
    env.setdefault("APP_URL", "${APP_URL}")  # App Platform bindable variable, resolved by DigitalOcean
    spec = (ROOT / "infra" / "app-spec.yaml").read_text()
    missing = sorted({key for key in PLACEHOLDER.findall(spec) if not env.get(key)})
    if missing:
        sys.exit(f"missing values: {', '.join(missing)}")
    sys.stdout.write(PLACEHOLDER.sub(lambda m: env[m.group(1)], spec))


if __name__ == "__main__":
    main()
