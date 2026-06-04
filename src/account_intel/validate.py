import json
from pathlib import Path
from jsonschema import validate


def validate_json(schema_path: str, payload_path: str) -> None:
    schema = json.loads(Path(schema_path).read_text())
    payload = json.loads(Path(payload_path).read_text())
    validate(instance=payload, schema=schema)
    print(f"PASS: {payload_path} matches {schema_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Validate Account Intelligence OS JSON payloads.")
    parser.add_argument("schema")
    parser.add_argument("payload")
    args = parser.parse_args()
    validate_json(args.schema, args.payload)
