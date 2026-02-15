#!/usr/bin/env python3
"""
extract-schema.py -- Extract JSON Schema from Python, TypeScript, or SQL source files.

Usage:
    python extract-schema.py --language python --method pydantic_model --target ProductResponse --file backend/app/models/product.py
    python extract-schema.py --language typescript --method typescript_interface --target Product --file ui/src/types/product.ts
    python extract-schema.py --language sql --method sql_table --target DIM_PRODUCTS --file dbt/models/marts/dim_products.sql

Output: JSON Schema on stdout.
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


# =============================================================================
# PYTHON EXTRACTOR -- Pydantic models and function signatures
# =============================================================================

# Map Python type annotations to JSON Schema types
PYTHON_TYPE_MAP = {
    "str": {"type": "string"},
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "bool": {"type": "boolean"},
    "None": {"type": "null"},
    "NoneType": {"type": "null"},
    "list": {"type": "array"},
    "dict": {"type": "object"},
    "Any": {},
    "datetime": {"type": "string", "format": "date-time"},
    "date": {"type": "string", "format": "date"},
    "Decimal": {"type": "number"},
    "UUID": {"type": "string", "format": "uuid"},
}


def _python_annotation_to_json_schema(annotation_node: ast.expr) -> dict:
    """Convert a Python AST annotation node to a JSON Schema fragment."""

    # Simple name: str, int, float, bool, etc.
    if isinstance(annotation_node, ast.Name):
        name = annotation_node.id
        if name in PYTHON_TYPE_MAP:
            return PYTHON_TYPE_MAP[name].copy()
        # Unknown type -- treat as object reference
        return {"type": "object", "description": f"Reference to {name}"}

    # Attribute: datetime.datetime, etc.
    if isinstance(annotation_node, ast.Attribute):
        attr_name = annotation_node.attr
        if attr_name in PYTHON_TYPE_MAP:
            return PYTHON_TYPE_MAP[attr_name].copy()
        return {"type": "object", "description": f"Reference to {attr_name}"}

    # Constant (Python 3.8+ for None, True, etc.)
    if isinstance(annotation_node, ast.Constant):
        if annotation_node.value is None:
            return {"type": "null"}
        return {"type": "string", "const": str(annotation_node.value)}

    # Subscript: Optional[X], List[X], Dict[K, V], Union[X, Y]
    if isinstance(annotation_node, ast.Subscript):
        base = annotation_node.value
        base_name = ""
        if isinstance(base, ast.Name):
            base_name = base.id
        elif isinstance(base, ast.Attribute):
            base_name = base.attr

        slice_node = annotation_node.slice

        if base_name == "Optional":
            inner = _python_annotation_to_json_schema(slice_node)
            # Optional[X] -> anyOf: [X, null] or type: [X_type, "null"]
            if "type" in inner and isinstance(inner["type"], str):
                inner["type"] = [inner["type"], "null"]
                return inner
            return {"anyOf": [inner, {"type": "null"}]}

        if base_name == "List" or base_name == "list":
            items_schema = _python_annotation_to_json_schema(slice_node)
            return {"type": "array", "items": items_schema}

        if base_name == "Dict" or base_name == "dict":
            if isinstance(slice_node, ast.Tuple) and len(slice_node.elts) == 2:
                val_schema = _python_annotation_to_json_schema(slice_node.elts[1])
                return {"type": "object", "additionalProperties": val_schema}
            return {"type": "object"}

        if base_name == "Union":
            if isinstance(slice_node, ast.Tuple):
                variants = [_python_annotation_to_json_schema(e) for e in slice_node.elts]
                # Check if it is Optional (Union[X, None])
                null_variants = [v for v in variants if v.get("type") == "null"]
                non_null = [v for v in variants if v.get("type") != "null"]
                if len(null_variants) == 1 and len(non_null) == 1:
                    result = non_null[0].copy()
                    if "type" in result and isinstance(result["type"], str):
                        result["type"] = [result["type"], "null"]
                        return result
                    return {"anyOf": [result, {"type": "null"}]}
                return {"anyOf": variants}

    # BinOp: X | Y  (Python 3.10+ union syntax)
    if isinstance(annotation_node, ast.BinOp) and isinstance(annotation_node.op, ast.BitOr):
        left = _python_annotation_to_json_schema(annotation_node.left)
        right = _python_annotation_to_json_schema(annotation_node.right)
        if right.get("type") == "null" and "type" in left and isinstance(left["type"], str):
            left["type"] = [left["type"], "null"]
            return left
        return {"anyOf": [left, right]}

    # Fallback
    return {"type": "object", "description": "Could not parse annotation"}


def extract_pydantic_model(source: str, target: str) -> dict:
    """Extract JSON Schema from a Pydantic BaseModel class definition."""
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name != target:
            continue

        # Check it inherits from BaseModel (or any *Model pattern)
        is_model = False
        for base in node.bases:
            base_name = ""
            if isinstance(base, ast.Name):
                base_name = base.id
            elif isinstance(base, ast.Attribute):
                base_name = base.attr
            if "Model" in base_name or "Schema" in base_name:
                is_model = True
                break

        if not is_model and node.bases:
            # Still extract -- might be a dataclass or plain class with annotations
            pass

        properties = {}
        required = []

        for item in node.body:
            # Annotated assignment: field_name: type = default
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_name = item.target.id
                if field_name.startswith("_"):
                    continue  # Skip private fields

                field_schema = _python_annotation_to_json_schema(item.annotation)

                # Extract description from Field(..., description="...")
                if item.value and isinstance(item.value, ast.Call):
                    for kw in item.value.keywords:
                        if kw.arg == "description" and isinstance(kw.value, ast.Constant):
                            field_schema["description"] = kw.value.value

                properties[field_name] = field_schema

                # Required if no default value and not Optional
                has_default = item.value is not None
                is_optional = False
                if "type" in field_schema:
                    t = field_schema["type"]
                    if isinstance(t, list) and "null" in t:
                        is_optional = True
                if "anyOf" in field_schema:
                    for v in field_schema["anyOf"]:
                        if v.get("type") == "null":
                            is_optional = True

                if not has_default and not is_optional:
                    required.append(field_name)

        schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = sorted(required)

        return schema

    raise ValueError(f"Pydantic model '{target}' not found in source")


def extract_function_signature(source: str, target: str) -> dict:
    """Extract JSON Schema for a function's parameters and return type."""
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != target:
            continue

        # Parameters
        params_properties = {}
        params_required = []

        args = node.args
        # Calculate which args have defaults
        num_defaults = len(args.defaults)
        num_args = len(args.args)
        first_default_idx = num_args - num_defaults

        for i, arg in enumerate(args.args):
            if arg.arg == "self" or arg.arg == "cls":
                continue
            param_schema = {}
            if arg.annotation:
                param_schema = _python_annotation_to_json_schema(arg.annotation)
            else:
                param_schema = {"description": "No type annotation"}
            params_properties[arg.arg] = param_schema

            if i < first_default_idx:
                params_required.append(arg.arg)

        # Return type
        return_schema = {}
        if node.returns:
            return_schema = _python_annotation_to_json_schema(node.returns)

        result = {
            "type": "object",
            "properties": {
                "parameters": {
                    "type": "object",
                    "properties": params_properties,
                },
                "returns": return_schema,
            },
        }
        if params_required:
            result["properties"]["parameters"]["required"] = sorted(params_required)

        return result

    raise ValueError(f"Function '{target}' not found in source")


# =============================================================================
# TYPESCRIPT EXTRACTOR -- Interfaces and type aliases
# =============================================================================

# Map TS types to JSON Schema types
TS_TYPE_MAP = {
    "string": {"type": "string"},
    "number": {"type": "number"},
    "boolean": {"type": "boolean"},
    "null": {"type": "null"},
    "undefined": {"type": "null"},
    "any": {},
    "unknown": {},
    "void": {"type": "null"},
    "Date": {"type": "string", "format": "date-time"},
    "Record<string, any>": {"type": "object"},
}


def _ts_type_to_json_schema(ts_type: str) -> dict:
    """Convert a TypeScript type string to JSON Schema."""
    ts_type = ts_type.strip()

    # Direct mapping
    if ts_type in TS_TYPE_MAP:
        return TS_TYPE_MAP[ts_type].copy()

    # Nullable: X | null, X | undefined
    if " | " in ts_type:
        parts = [p.strip() for p in ts_type.split(" | ")]
        null_parts = [p for p in parts if p in ("null", "undefined")]
        real_parts = [p for p in parts if p not in ("null", "undefined")]

        if null_parts and len(real_parts) == 1:
            inner = _ts_type_to_json_schema(real_parts[0])
            if "type" in inner and isinstance(inner["type"], str):
                inner["type"] = [inner["type"], "null"]
                return inner
            return {"anyOf": [inner, {"type": "null"}]}

        if len(real_parts) > 1:
            schemas = [_ts_type_to_json_schema(p) for p in real_parts]
            if null_parts:
                schemas.append({"type": "null"})
            return {"anyOf": schemas}

    # Array: X[] or Array<X>
    array_bracket = re.match(r"^(.+)\[\]$", ts_type)
    if array_bracket:
        inner_type = array_bracket.group(1)
        return {"type": "array", "items": _ts_type_to_json_schema(inner_type)}

    array_generic = re.match(r"^Array<(.+)>$", ts_type)
    if array_generic:
        inner_type = array_generic.group(1)
        return {"type": "array", "items": _ts_type_to_json_schema(inner_type)}

    # Record<K, V>
    record_match = re.match(r"^Record<(.+),\s*(.+)>$", ts_type)
    if record_match:
        val_type = record_match.group(2)
        return {"type": "object", "additionalProperties": _ts_type_to_json_schema(val_type)}

    # String literal type
    if ts_type.startswith("'") or ts_type.startswith('"'):
        return {"type": "string", "const": ts_type.strip("'\"") }

    # Numeric literal
    try:
        num = float(ts_type)
        return {"type": "number", "const": num}
    except ValueError:
        pass

    # Unknown reference type
    return {"type": "object", "description": f"Reference to {ts_type}"}


def extract_typescript_interface(source: str, target: str) -> dict:
    """Extract JSON Schema from a TypeScript interface or type alias."""

    # Match: interface Target { ... } or export interface Target { ... }
    # Use a state machine to handle nested braces
    interface_pattern = re.compile(
        rf"(?:export\s+)?interface\s+{re.escape(target)}\s*(?:extends\s+\w+(?:\s*,\s*\w+)*)?\s*\{{",
        re.MULTILINE,
    )

    match = interface_pattern.search(source)
    if not match:
        # Try type alias: type Target = { ... }
        type_pattern = re.compile(
            rf"(?:export\s+)?type\s+{re.escape(target)}\s*=\s*\{{",
            re.MULTILINE,
        )
        match = type_pattern.search(source)

    if not match:
        raise ValueError(f"TypeScript interface/type '{target}' not found in source")

    # Extract body between braces (handle nesting)
    start = match.end()
    depth = 1
    pos = start
    while pos < len(source) and depth > 0:
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
        pos += 1

    body = source[start : pos - 1]

    # Parse fields from body
    properties = {}
    required = []

    # Match lines like: fieldName: Type; or fieldName?: Type;
    field_pattern = re.compile(
        r"^\s*(?:readonly\s+)?(\w+)(\?)?:\s*(.+?)\s*;?\s*(?://.*)?$",
        re.MULTILINE,
    )

    for field_match in field_pattern.finditer(body):
        field_name = field_match.group(1)
        is_optional = field_match.group(2) == "?"
        field_type = field_match.group(3).rstrip(";").strip()

        properties[field_name] = _ts_type_to_json_schema(field_type)

        if not is_optional:
            required.append(field_name)

    schema = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = sorted(required)

    return schema


# =============================================================================
# SQL EXTRACTOR -- Table schemas from CREATE TABLE or dbt models
# =============================================================================

SQL_TYPE_MAP = {
    "VARCHAR": {"type": "string"},
    "CHAR": {"type": "string"},
    "TEXT": {"type": "string"},
    "STRING": {"type": "string"},
    "INT": {"type": "integer"},
    "INTEGER": {"type": "integer"},
    "BIGINT": {"type": "integer"},
    "SMALLINT": {"type": "integer"},
    "TINYINT": {"type": "integer"},
    "FLOAT": {"type": "number"},
    "DOUBLE": {"type": "number"},
    "DECIMAL": {"type": "number"},
    "NUMBER": {"type": "number"},
    "NUMERIC": {"type": "number"},
    "REAL": {"type": "number"},
    "BOOLEAN": {"type": "boolean"},
    "BOOL": {"type": "boolean"},
    "DATE": {"type": "string", "format": "date"},
    "DATETIME": {"type": "string", "format": "date-time"},
    "TIMESTAMP": {"type": "string", "format": "date-time"},
    "TIMESTAMP_NTZ": {"type": "string", "format": "date-time"},
    "TIMESTAMP_LTZ": {"type": "string", "format": "date-time"},
    "TIMESTAMP_TZ": {"type": "string", "format": "date-time"},
    "TIME": {"type": "string", "format": "time"},
    "VARIANT": {"type": "object"},
    "OBJECT": {"type": "object"},
    "ARRAY": {"type": "array"},
    "BINARY": {"type": "string", "contentEncoding": "base64"},
    "VARBINARY": {"type": "string", "contentEncoding": "base64"},
}


def extract_sql_table(source: str, target: str) -> dict:
    """Extract JSON Schema from a CREATE TABLE statement or dbt model.

    Handles:
    - CREATE TABLE target (col1 TYPE, col2 TYPE NOT NULL, ...)
    - CREATE OR REPLACE TABLE ...
    - dbt-style: {{ config(...) }} followed by SELECT col1, col2 AS alias, ...
    - Column comments: COMMENT 'description'
    """

    # Strategy 1: CREATE TABLE
    create_pattern = re.compile(
        rf"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TRANSIENT\s+)?TABLE\s+(?:\w+\.)*{re.escape(target)}\s*\(",
        re.IGNORECASE | re.MULTILINE,
    )
    match = create_pattern.search(source)

    if match:
        # Find matching closing paren
        start = match.end()
        depth = 1
        pos = start
        while pos < len(source) and depth > 0:
            if source[pos] == "(":
                depth += 1
            elif source[pos] == ")":
                depth -= 1
            pos += 1

        body = source[start : pos - 1]

        properties = {}
        required = []

        # Parse column definitions
        col_pattern = re.compile(
            r"^\s*(\w+)\s+([\w()]+(?:\(\d+(?:,\s*\d+)?\))?)"
            r"(?:\s+(NOT\s+NULL|NULL))?"
            r"(?:\s+DEFAULT\s+\S+)?"
            r"(?:\s+COMMENT\s+'([^']*)')?"
            r"\s*,?\s*$",
            re.IGNORECASE | re.MULTILINE,
        )

        for col_match in col_pattern.finditer(body):
            col_name = col_match.group(1).upper()
            col_type_raw = col_match.group(2).upper()
            nullable = col_match.group(3)
            comment = col_match.group(4)

            # Skip constraints
            if col_name in ("PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT", "INDEX"):
                continue

            # Strip size specifiers: VARCHAR(255) -> VARCHAR
            base_type = re.sub(r"\(.*\)", "", col_type_raw).strip()

            col_schema = SQL_TYPE_MAP.get(base_type, {"type": "string"}).copy()

            # Handle nullability
            is_not_null = nullable and "NOT" in nullable.upper() if nullable else False
            if not is_not_null:
                if "type" in col_schema and isinstance(col_schema["type"], str):
                    col_schema["type"] = [col_schema["type"], "null"]

            if comment:
                col_schema["description"] = comment

            properties[col_name] = col_schema
            if is_not_null:
                required.append(col_name)

        if properties:
            schema = {"type": "object", "properties": properties}
            if required:
                schema["required"] = sorted(required)
            return schema

    # Strategy 2: dbt model -- parse SELECT columns
    # Look for final SELECT statement
    select_pattern = re.compile(
        r"(?:^|\n)\s*SELECT\s+([\s\S]+?)(?:FROM\s+|$)",
        re.IGNORECASE,
    )
    select_matches = list(select_pattern.finditer(source))
    if select_matches:
        # Use the last SELECT (handles CTEs)
        select_body = select_matches[-1].group(1)

        properties = {}
        # Parse SELECT columns: col, expr AS alias, etc.
        # Split by commas (not inside parens)
        columns = []
        depth = 0
        current = ""
        for char in select_body:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                columns.append(current.strip())
                current = ""
                continue
            current += char
        if current.strip():
            columns.append(current.strip())

        for col in columns:
            col = col.strip()
            if not col or col == "*":
                continue

            # Extract alias: ... AS alias or just column_name
            alias_match = re.search(r"\bAS\s+(\w+)\s*$", col, re.IGNORECASE)
            if alias_match:
                col_name = alias_match.group(1).upper()
            else:
                # Just a column reference: take the last identifier
                ident_match = re.search(r"(\w+)\s*$", col)
                if ident_match:
                    col_name = ident_match.group(1).upper()
                else:
                    continue

            # Type inference from casting: col::TYPE or CAST(col AS TYPE)
            cast_match = re.search(r"::(\w+)", col) or re.search(
                r"CAST\s*\(.*\s+AS\s+(\w+)", col, re.IGNORECASE
            )
            if cast_match:
                sql_type = cast_match.group(1).upper()
                col_schema = SQL_TYPE_MAP.get(sql_type, {"type": "string"}).copy()
            else:
                # No type info -- default to string
                col_schema = {"type": "string", "description": "Type inferred from dbt model"}

            properties[col_name] = col_schema

        if properties:
            return {
                "type": "object",
                "properties": properties,
                "description": f"Schema extracted from dbt model for {target}. Types may need manual review.",
            }

    raise ValueError(f"SQL table '{target}' not found in source (no CREATE TABLE or SELECT)")


# =============================================================================
# MAIN -- Dispatch to the right extractor
# =============================================================================

EXTRACTORS = {
    ("python", "pydantic_model"): extract_pydantic_model,
    ("python", "function_signature"): extract_function_signature,
    ("typescript", "typescript_interface"): extract_typescript_interface,
    ("sql", "sql_table"): extract_sql_table,
}


def main():
    parser = argparse.ArgumentParser(
        description="Extract JSON Schema from source code"
    )
    parser.add_argument("--language", required=True, choices=["python", "typescript", "sql"])
    parser.add_argument(
        "--method",
        required=True,
        choices=["pydantic_model", "function_signature", "typescript_interface", "sql_table", "json_schema_literal"],
    )
    parser.add_argument("--target", required=True, help="Class/function/interface/table name")
    parser.add_argument("--file", required=True, help="Source file path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output")

    args = parser.parse_args()

    source_path = Path(args.file)
    if not source_path.exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    source = source_path.read_text()

    if args.method == "json_schema_literal":
        # Special case: the file itself is already a JSON Schema
        try:
            schema = json.loads(source)
            json.dump(schema, sys.stdout, indent=2 if args.pretty else None)
            sys.exit(0)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {args.file}: {e}", file=sys.stderr)
            sys.exit(1)

    key = (args.language, args.method)
    if key not in EXTRACTORS:
        print(f"Error: No extractor for {args.language}/{args.method}", file=sys.stderr)
        sys.exit(1)

    try:
        schema = EXTRACTORS[key](source, args.target)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    json.dump(schema, sys.stdout, indent=2 if args.pretty else None)
    print()  # trailing newline


if __name__ == "__main__":
    main()
