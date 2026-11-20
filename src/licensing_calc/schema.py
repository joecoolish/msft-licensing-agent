"""Reproducibly generate the function tool's Inventory argument schema."""

import argparse
import json
from pathlib import Path

from licensing_calc.models import Inventory


def inventory_schema() -> str:
    return json.dumps(Inventory.model_json_schema(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("agent") / "tools" / "calculate_licenses.schema.json"
    )
    args = parser.parse_args()
    args.output.write_text(inventory_schema(), encoding="utf-8")


if __name__ == "__main__":
    main()
