#!/usr/bin/env python3
"""Generates Python operation usage snippets from an sdkgen.lock TypeAPI specification file."""

import argparse
import json
import re
from pathlib import Path


def to_snake_case(name: str) -> str:
    """Convert camelCase, PascalCase, dot.case, or hyphenated names to snake_case."""
    if not name:
        return ""
    # Insert underscore between lower/digit and upper case (e.g. getAll -> get_All)
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Replace dots, hyphens, spaces, or consecutive underscores
    s2 = re.sub(r"[._\-\s]+", "_", s1)
    return s2.lower().strip("_")


def to_pascal_case(name: str) -> str:
    """Convert snake_case, camelCase, dot.case, or hyphenated names to PascalCase."""
    if not name:
        return ""
    parts = re.split(r"[._-]+", name)
    return "".join(p.capitalize() for p in parts if p)


def map_schema_to_type(schema: dict) -> str:
    """Map a TypeAPI schema definition to its corresponding Python type or class name."""
    if not schema or not isinstance(schema, dict):
        return "Any"

    schema_type = schema.get("type")

    if schema_type == "reference":
        return to_pascal_case(schema.get("target", "Any"))

    type_mapping = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "any": "Any",
    }

    if schema_type == "array":
        item_type = map_schema_to_type(schema.get("schema", {}))
        return f"list[{item_type}]"

    if schema_type == "map":
        val_type = map_schema_to_type(schema.get("schema", {}))
        return f"dict[str, {val_type}]"

    return type_mapping.get(schema_type, "Any")


def generate_usage(lock_file_path: Path) -> str:
    """Read sdkgen.lock TypeAPI spec and generate clean Python operation snippets."""
    if not lock_file_path.is_file():
        return "# No sdkgen.lock found to generate usage examples."

    try:
        with open(lock_file_path, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except (json.JSONDecodeError, OSError):
        return "# Failed to parse sdkgen.lock."

    api_key = next(iter(spec.keys()), None)
    if not api_key or "operations" not in spec[api_key]:
        return "# No operations found in spec."

    operations = spec[api_key].get("operations", {})
    lines = []

    for op_id, op in operations.items():
        if "." in op_id:
            tag, method_raw = op_id.split(".", 1)
            tag_accessor = f"client.{to_snake_case(tag)}()"
        else:
            method_raw = op_id
            tag_accessor = "client"

        method_name = to_snake_case(method_raw)
        raw_arguments = op.get("arguments", {})
        call_args = []

        # Normalize arguments format whether it's a list or a dict
        arguments_list = []
        if isinstance(raw_arguments, list):
            arguments_list = raw_arguments
        elif isinstance(raw_arguments, dict):
            for name, data in raw_arguments.items():
                arg_item = dict(data) if isinstance(data, dict) else {}
                arg_item.setdefault("name", name)
                arguments_list.append(arg_item)

        for arg_data in arguments_list:
            if not isinstance(arg_data, dict):
                continue

            arg_name = arg_data.get("name", "arg")
            param_in = arg_data.get("in")
            schema = arg_data.get("schema", {})
            type_name = map_schema_to_type(schema)

            if param_in == "path":
                call_args.append(f'"{to_snake_case(arg_name)}"')
            elif param_in == "body":
                call_args.append(f"{type_name}()")
            elif param_in in ("query", "header"):
                if schema.get("type") == "string":
                    call_args.append(f'"{to_snake_case(arg_name)}"')
                elif schema.get("type") == "integer":
                    call_args.append("1")
                elif schema.get("type") == "boolean":
                    call_args.append("True")
                else:
                    call_args.append("None")

        return_spec = op.get("return", {})
        return_schema = return_spec.get("schema", {})
        return_type = map_schema_to_type(return_schema) if return_schema else None

        description = op.get("description", "").strip()
        if description:
            first_line = description.split(".")[0] + "."
            lines.append(f"# {first_line}")

        call_str = ", ".join(call_args)
        if return_type and return_type != "None":
            lines.append(f"response = {tag_accessor}.{method_name}({call_str})")
        else:
            lines.append(f"{tag_accessor}.{method_name}({call_str})")

        lines.append("")

    return "\n".join(lines).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Python usage snippets from sdkgen.lock.")
    parser.add_argument("--lock-file", type=Path, default=Path("sdkgen.lock"))
    args = parser.parse_args()

    usage_output = generate_usage(args.lock_file)
    print(usage_output)


if __name__ == "__main__":
    main()
