"""
Writes the JSON Schema of the signal metadata file.

Run from the project root: python -m tools.gen_schema [out_path]
"""

import json
import sys

from src.json import Schema


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "signals.schema.json"
    schema = Schema.model_json_schema()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
