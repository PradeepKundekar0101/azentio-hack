"""Write the API's OpenAPI schema to docs/openapi.json, the contract shared with the investigation workspace.

Usage: uv run python -m scripts.export_openapi
Placeholder settings are enough: building the schema never connects to the database or storage.
"""

import json

from app.core.config import REPO_ROOT, Settings
from app.main import create_app

OUT = REPO_ROOT / "docs" / "openapi.json"
PLACEHOLDERS = {
    "database_url": "postgresql+psycopg://localhost/schema",
    "spaces_region": "schema",
    "spaces_endpoint_url": "http://127.0.0.1:1",
    "spaces_bucket": "schema",
    "spaces_access_key_id": "schema",
    "spaces_secret_access_key": "schema",
    "session_secret": "schema-only-secret-that-is-at-least-32-chars",
    "demo_password": "schema",
}


def main() -> None:
    schema = create_app(Settings(_env_file=None, **PLACEHOLDERS)).openapi()  # type: ignore[arg-type]
    OUT.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
