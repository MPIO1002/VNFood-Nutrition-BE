from __future__ import annotations

import sys

from calcucalo.api.auth import get_auth_service


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    service = get_auth_service()
    service.initialize_schema()
    info = service.database.ping()
    print(f"Authentication schema is ready in database '{info['database']}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
