#!/usr/bin/env python
"""
Fetch and cache widget schemas for testing.

Usage:
    python tests/fetch_schemas.py

This script is used in CI to pre-fetch schemas before running tests.
"""

import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from core.schema_fetcher import get_schema_db_path, update_schema_database


def main():
    print("Fetching widget schemas from GitHub...")

    success, message = update_schema_database()

    if success:
        print(message)
        print(f"Schema database: {get_schema_db_path()}")
        return 0
    else:
        print(f"Failed: {message}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
