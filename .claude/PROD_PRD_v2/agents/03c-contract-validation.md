# 03c -- Cross-Agent Contract Validation

**Status**: SPEC COMPLETE
**Priority**: P0 -- Without this, multi-agent file changes silently break downstream agents
**Depends on**: Ownership KG (DEPENDS_ON edges), cleanup.sh (agent lifecycle), beads (notification)

---

## Purpose

When agent A modifies files, the Ownership KG knows that agent B depends on A (via DEPENDS_ON edges). Today, agent B gets a notification bead -- but nobody validates that B's code is actually compatible with A's changes. The chain of trust is:

```
db-agent adds column "variant_sku" to PRODUCTS table
    |
    v  (DEPENDS_ON edge exists)
api-agent gets bead notification, updates its Pydantic model
    |
    v  (DEPENDS_ON edge exists)
ui-agent gets bead notification... but does it know the API response shape changed?
    |
    v
SILENT BREAKAGE -- ui-agent renders undefined fields, crashes at runtime
```

Contract validation closes this gap. Every boundary between two agents gets a machine-readable contract file. When an agent merges its worktree, cleanup.sh validates that the agent's outputs still conform to the contracts it participates in. If a contract breaks, the merge is blocked and the dependent agent gets a "contract-broken" bead with the exact diff.

### Why Not Pact?

[Pact](https://docs.pact.io/) is the industry standard for consumer-driven contract testing, but it requires a broker, generates contracts from running test suites, and assumes HTTP interactions. Our agents are not microservices -- they are Claude Code sessions editing files in git worktrees. Our contracts are about **file-level interfaces**: Pydantic models, SQL schemas, TypeScript interfaces. We need something lighter:

- **JSON Schema as lingua franca** -- works across Python, TypeScript, SQL
- **Static extraction** -- parse ASTs and type definitions, no running servers
- **Git-native** -- contract files live in the repo, validated in cleanup.sh
- **Beads-native** -- contract violations create beads, not HTTP callbacks

References:
- [JSON Schema as data contracts](https://coding-cloud.com/blog/json-schema-contracts)
- [Pact best practices 2025](https://www.sachith.co.uk/contract-testing-with-pact-best-practices-in-2025-practical-guide-feb-10-2026/)
- [Pactflow schema-based contract testing](https://pactflow.io/blog/contract-testing-using-json-schemas-and-open-api-part-3/)

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Contract extraction misses fields | Silent schema drift | Require contract review on first generation; unit tests for extractors |
| False positives block valid merges | Agent work stuck in worktree | `--skip-contracts` escape hatch in cleanup.sh; contract has `strict: false` mode |
| Contracts become stale (nobody updates them) | False sense of safety | `contract_check` in CI validates contracts match actual code; staleness detector |
| Cross-language extraction is fragile | Python/TS/SQL all different | One extractor per language, tested against real codebase patterns |
| Performance -- AST parsing on every merge | Slow cleanup | Cache parsed schemas; only re-extract changed files (git diff) |
| Circular contract dependencies | Deadlock on merge | Contracts are directional (producer -> consumer); DAG enforced |

---

## Files

### New Files

| File | Purpose |
|------|---------|
| `.claude/contracts/*.contract.json` | Contract definitions (one per agent boundary) |
| `.claude/contracts/CONTRACT_SCHEMA.json` | JSON Schema for contract files themselves (meta-schema) |
| `.claude/scripts/validate-contracts.sh` | Validate agent outputs against contracts |
| `.claude/scripts/generate-contract.sh` | Generate draft contract from current code |
| `.claude/scripts/extract-schema.py` | Extract JSON Schema from Python/TS/SQL source files |

### Modified Files

| File | Change |
|------|--------|
| `.claude/scripts/cleanup.sh` | Add contract validation step before merge |
| `.github/workflows/deploy.yml` | Add contract validation CI step |

---

## Fixes

### Fix 1: Contract Meta-Schema

The schema that all contract files must conform to. This is the contract about contracts.

**File**: `.claude/contracts/CONTRACT_SCHEMA.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://baap.dev/schemas/contract.json",
  "title": "Cross-Agent Contract",
  "description": "Defines the interface contract between a producer agent and one or more consumer agents",
  "type": "object",
  "required": ["contract_id", "version", "producer", "consumers", "schema", "boundary_type"],
  "properties": {
    "contract_id": {
      "type": "string",
      "pattern": "^[a-z0-9-]+$",
      "description": "Unique identifier, matches filename without extension"
    },
    "version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+$",
      "description": "Semantic version of the contract"
    },
    "previous_versions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "version": { "type": "string" },
          "deprecated_at": { "type": "string", "format": "date-time" },
          "migration_notes": { "type": "string" }
        }
      },
      "description": "History of breaking changes for audit trail"
    },
    "producer": {
      "type": "object",
      "required": ["agent_id", "files"],
      "properties": {
        "agent_id": {
          "type": "string",
          "description": "Agent that produces/owns this interface"
        },
        "files": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Source files that define the interface (globs allowed)"
        },
        "extraction": {
          "type": "object",
          "properties": {
            "language": { "enum": ["python", "typescript", "sql"] },
            "method": { "enum": ["pydantic_model", "function_signature", "typescript_interface", "sql_table", "json_schema_literal"] },
            "target": {
              "type": "string",
              "description": "Class name, function name, table name, or interface name to extract"
            }
          },
          "description": "How to auto-extract the schema from source code"
        }
      }
    },
    "consumers": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["agent_id"],
        "properties": {
          "agent_id": { "type": "string" },
          "files": {
            "type": "array",
            "items": { "type": "string" },
            "description": "Consumer files that depend on this contract"
          },
          "usage": {
            "type": "string",
            "description": "How the consumer uses this interface"
          }
        }
      },
      "minItems": 1
    },
    "boundary_type": {
      "enum": ["api_response", "db_schema", "file_format", "function_call", "event_payload", "config"],
      "description": "What kind of boundary this contract covers"
    },
    "schema": {
      "type": "object",
      "description": "The actual JSON Schema that the producer's output must conform to. This is the contract payload -- a standard JSON Schema object."
    },
    "strict": {
      "type": "boolean",
      "default": true,
      "description": "If true, additionalProperties not in schema cause failure. If false, only required fields are checked."
    },
    "validation_mode": {
      "enum": ["block_merge", "warn_only", "notify_consumers"],
      "default": "block_merge",
      "description": "What happens when contract validation fails"
    },
    "metadata": {
      "type": "object",
      "properties": {
        "created_at": { "type": "string", "format": "date-time" },
        "created_by": { "type": "string" },
        "last_validated": { "type": "string", "format": "date-time" },
        "description": { "type": "string" },
        "related_beads": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    }
  },
  "additionalProperties": false
}
```

### Fix 2: Example Contract -- DB-to-API Boundary

A real contract for the boundary between a db-agent (manages Snowflake tables) and an api-agent (serves FastAPI endpoints). The db-agent produces a table schema; the api-agent consumes it via its Pydantic model.

**File**: `.claude/contracts/db-to-api-products.contract.json`

```json
{
  "contract_id": "db-to-api-products",
  "version": "1.0.0",
  "producer": {
    "agent_id": "db-agent",
    "files": ["dbt/models/staging/stg_products.sql", "dbt/models/marts/dim_products.sql"],
    "extraction": {
      "language": "sql",
      "method": "sql_table",
      "target": "DIM_PRODUCTS"
    }
  },
  "consumers": [
    {
      "agent_id": "api-agent",
      "files": ["backend/app/models/product.py", "backend/app/routers/products.py"],
      "usage": "Reads DIM_PRODUCTS via Snowflake connector, maps to ProductResponse Pydantic model"
    }
  ],
  "boundary_type": "db_schema",
  "schema": {
    "type": "object",
    "required": ["PRODUCT_ID", "PRODUCT_NAME", "CATEGORY", "PRICE", "IN_STOCK", "UPDATED_AT"],
    "properties": {
      "PRODUCT_ID": { "type": "string", "description": "Primary key, VARCHAR" },
      "PRODUCT_NAME": { "type": "string" },
      "CATEGORY": { "type": "string" },
      "SUBCATEGORY": { "type": ["string", "null"] },
      "PRICE": { "type": "number", "minimum": 0 },
      "IN_STOCK": { "type": "boolean" },
      "VARIANT_SKU": { "type": ["string", "null"], "description": "Added in v1.0.0" },
      "UPDATED_AT": { "type": "string", "format": "date-time" }
    },
    "additionalProperties": false
  },
  "strict": true,
  "validation_mode": "block_merge",
  "metadata": {
    "created_at": "2026-02-14T00:00:00Z",
    "created_by": "generate-contract.sh",
    "description": "Ensures DIM_PRODUCTS table schema matches what api-agent's Pydantic models expect"
  }
}
```

### Fix 3: Example Contract -- API-to-UI Boundary

**File**: `.claude/contracts/api-to-ui-products.contract.json`

```json
{
  "contract_id": "api-to-ui-products",
  "version": "1.0.0",
  "producer": {
    "agent_id": "api-agent",
    "files": ["backend/app/models/product.py", "backend/app/routers/products.py"],
    "extraction": {
      "language": "python",
      "method": "pydantic_model",
      "target": "ProductResponse"
    }
  },
  "consumers": [
    {
      "agent_id": "ui-agent",
      "files": ["ui/src/types/product.ts", "ui/src/hooks/useProducts.ts", "ui/src/components/ProductCard.tsx"],
      "usage": "Fetches GET /api/products, expects ProductResponse JSON, renders in ProductCard"
    }
  ],
  "boundary_type": "api_response",
  "schema": {
    "type": "object",
    "required": ["id", "name", "category", "price", "in_stock"],
    "properties": {
      "id": { "type": "string" },
      "name": { "type": "string" },
      "category": { "type": "string" },
      "subcategory": { "type": ["string", "null"] },
      "price": { "type": "number" },
      "in_stock": { "type": "boolean" },
      "variant_sku": { "type": ["string", "null"] },
      "updated_at": { "type": "string" }
    },
    "additionalProperties": false
  },
  "strict": true,
  "validation_mode": "block_merge",
  "metadata": {
    "created_at": "2026-02-14T00:00:00Z",
    "created_by": "generate-contract.sh",
    "description": "Ensures API response shape matches what ui-agent's TypeScript types expect"
  }
}
```

### Fix 4: Schema Extractor

The core engine that reads Python, TypeScript, and SQL source files and produces JSON Schema objects. Uses AST parsing for Python and regex-based extraction for TypeScript and SQL (lightweight, no compiler dependency).

**File**: `.claude/scripts/extract-schema.py`

```python
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
```

### Fix 5: Contract Validation Script

The script that cleanup.sh calls before merging. It reads every contract file, re-extracts the schema from the producer's current source code, and validates that the extracted schema is compatible with (a superset of) the contracted schema. If any contract breaks, it exits non-zero and prints the diff.

**File**: `.claude/scripts/validate-contracts.sh`

```bash
#!/usr/bin/env bash
# validate-contracts.sh -- Validate agent outputs against cross-agent contracts
#
# Usage:
#   validate-contracts.sh [--agent AGENT_ID] [--contracts-dir DIR] [--project-root DIR]
#
# When --agent is specified, only contracts where that agent is the producer are checked.
# When omitted, ALL contracts are validated.
#
# Exit codes:
#   0 = all contracts valid
#   1 = one or more contracts broken
#   2 = error (missing files, bad config)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ID=""
CONTRACTS_DIR=""
PROJECT_ROOT=""
SKIP_NOTIFICATION=false

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent) AGENT_ID="$2"; shift 2 ;;
    --contracts-dir) CONTRACTS_DIR="$2"; shift 2 ;;
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    --skip-notification) SKIP_NOTIFICATION=true; shift ;;
    --help|-h)
      echo "Usage: validate-contracts.sh [--agent AGENT_ID] [--contracts-dir DIR] [--project-root DIR]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ── Defaults ──────────────────────────────────────────────────────────────────
if [ -z "$PROJECT_ROOT" ]; then
  PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

if [ -z "$CONTRACTS_DIR" ]; then
  CONTRACTS_DIR="$PROJECT_ROOT/.claude/contracts"
fi

EXTRACT_SCRIPT="$PROJECT_ROOT/scripts/extract-schema.py"

# Find Python
PYTHON=""
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null && python --version 2>&1 | grep -q "Python 3"; then
  PYTHON="python"
else
  echo "Error: Python 3 not found" >&2
  exit 2
fi

# ── Validation engine ─────────────────────────────────────────────────────────
FAILED=0
PASSED=0
SKIPPED=0
FAILURES=""

validate_contract() {
  local contract_file="$1"
  local contract_id
  contract_id="$($PYTHON -c "import json; print(json.load(open('$contract_file'))['contract_id'])")"

  # Check if we should skip this contract (agent filter)
  if [ -n "$AGENT_ID" ]; then
    local producer_agent
    producer_agent="$($PYTHON -c "import json; print(json.load(open('$contract_file'))['producer']['agent_id'])")"
    if [ "$producer_agent" != "$AGENT_ID" ]; then
      SKIPPED=$((SKIPPED + 1))
      return 0
    fi
  fi

  echo "  Validating: $contract_id"

  # Extract contract details
  local contract_json
  contract_json="$($PYTHON -c "
import json, sys
c = json.load(open('$contract_file'))
print(json.dumps({
    'contract_id': c['contract_id'],
    'version': c['version'],
    'language': c['producer'].get('extraction', {}).get('language', ''),
    'method': c['producer'].get('extraction', {}).get('method', ''),
    'target': c['producer'].get('extraction', {}).get('target', ''),
    'files': c['producer'].get('files', []),
    'schema': c['schema'],
    'strict': c.get('strict', True),
    'validation_mode': c.get('validation_mode', 'block_merge'),
    'consumers': [{'agent_id': cons['agent_id']} for cons in c.get('consumers', [])],
}))
")"

  local language method target strict validation_mode
  language="$($PYTHON -c "import json; print(json.loads('$contract_json'.replace(\"'\", \"\"))['language'])" 2>/dev/null || echo "")"

  # If no extraction config, skip (manually maintained contract)
  if [ -z "$language" ] || [ "$language" = "" ]; then
    echo "    Skipped (no extraction config -- manually maintained)"
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi

  # Use Python for reliable JSON parsing
  local details
  details="$($PYTHON << 'PYEOF'
import json, sys, os

contract_file = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CONTRACT_FILE", "")
c = json.load(open(contract_file))

extraction = c["producer"].get("extraction", {})
print(extraction.get("language", ""))
print(extraction.get("method", ""))
print(extraction.get("target", ""))
print(json.dumps(c["producer"].get("files", [])))
print(json.dumps(c["schema"]))
print(str(c.get("strict", True)))
print(c.get("validation_mode", "block_merge"))
print(json.dumps([cons["agent_id"] for cons in c.get("consumers", [])]))
PYEOF
  )" 2>/dev/null || true

  # Fallback: parse directly with Python
  local extracted_schema=""
  local found_source=false

  # Find the first existing source file
  local source_files
  source_files="$($PYTHON -c "import json; [print(f) for f in json.load(open('$contract_file'))['producer']['files']]")"

  local source_file=""
  while IFS= read -r f; do
    local full_path="$PROJECT_ROOT/$f"
    if [ -f "$full_path" ]; then
      source_file="$full_path"
      found_source=true
      break
    fi
  done <<< "$source_files"

  if [ "$found_source" = false ]; then
    echo "    WARNING: No producer source files found -- cannot re-extract schema"
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi

  # Re-extract schema from current source
  local lang meth tgt
  lang="$($PYTHON -c "import json; print(json.load(open('$contract_file'))['producer']['extraction']['language'])")"
  meth="$($PYTHON -c "import json; print(json.load(open('$contract_file'))['producer']['extraction']['method'])")"
  tgt="$($PYTHON -c "import json; print(json.load(open('$contract_file'))['producer']['extraction']['target'])")"

  extracted_schema="$($PYTHON "$EXTRACT_SCRIPT" --language "$lang" --method "$meth" --target "$tgt" --file "$source_file" 2>&1)" || {
    echo "    ERROR: Schema extraction failed: $extracted_schema"
    FAILED=$((FAILED + 1))
    FAILURES="$FAILURES\n  - $contract_id: extraction failed"
    return 1
  }

  # Validate: check that contracted schema is a subset of extracted schema
  # (every required field in the contract must exist in the extracted schema)
  local validation_result
  validation_result="$($PYTHON << PYEOF
import json, sys

contracted = json.loads('''$(echo "$($PYTHON -c "import json; print(json.dumps(json.load(open('$contract_file'))['schema']))")")''')
extracted = json.loads('''$extracted_schema''')
strict = $(echo "$($PYTHON -c "import json; print('True' if json.load(open('$contract_file')).get('strict', True) else 'False')")")

errors = []

# Check required fields exist in extracted
contracted_required = set(contracted.get("required", []))
extracted_props = set(extracted.get("properties", {}).keys())
contracted_props = set(contracted.get("properties", {}).keys())

missing_required = contracted_required - extracted_props
if missing_required:
    errors.append(f"Missing required fields in source: {sorted(missing_required)}")

# Check that contracted properties exist in extracted (if strict)
if strict:
    missing_props = contracted_props - extracted_props
    if missing_props:
        errors.append(f"Missing properties in source: {sorted(missing_props)}")

# Check type compatibility for fields present in both
for field in contracted_props & extracted_props:
    c_type = contracted["properties"][field].get("type")
    e_type = extracted["properties"][field].get("type")

    if c_type and e_type:
        # Normalize to sets for comparison
        c_types = set(c_type) if isinstance(c_type, list) else {c_type}
        e_types = set(e_type) if isinstance(e_type, list) else {e_type}

        # Extracted types should be a superset of (or equal to) contracted types
        if not c_types.issubset(e_types):
            errors.append(f"Type mismatch for '{field}': contract={c_type}, source={e_type}")

if errors:
    print("FAIL")
    for e in errors:
        print(f"  {e}")
else:
    print("PASS")
PYEOF
  )" || {
    echo "    ERROR: Validation script failed"
    FAILED=$((FAILED + 1))
    FAILURES="$FAILURES\n  - $contract_id: validation script error"
    return 1
  }

  local status
  status="$(echo "$validation_result" | head -1)"

  if [ "$status" = "PASS" ]; then
    echo "    PASS"
    PASSED=$((PASSED + 1))
  else
    echo "    FAIL"
    echo "$validation_result" | tail -n +2 | while IFS= read -r line; do
      echo "      $line"
    done

    local val_mode
    val_mode="$($PYTHON -c "import json; print(json.load(open('$contract_file')).get('validation_mode', 'block_merge'))")"

    FAILED=$((FAILED + 1))
    FAILURES="$FAILURES\n  - $contract_id: schema mismatch"

    # Create notification beads for consumers
    if [ "$SKIP_NOTIFICATION" = false ] && command -v bd &>/dev/null; then
      local consumers
      consumers="$($PYTHON -c "import json; [print(c['agent_id']) for c in json.load(open('$contract_file'))['consumers']]")"
      while IFS= read -r consumer; do
        if [ -n "$consumer" ]; then
          bd create "CONTRACT BROKEN: $contract_id -- $consumer must update" \
            --priority 1 2>/dev/null || true
          echo "    Bead created for consumer: $consumer"
        fi
      done <<< "$consumers"
    fi

    if [ "$val_mode" = "warn_only" ]; then
      echo "    (validation_mode=warn_only -- not blocking merge)"
      FAILED=$((FAILED - 1))  # Don't count as failure for exit code
      PASSED=$((PASSED + 1))
    fi
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
echo "Contract Validation"
echo "==================="
echo "Project: $PROJECT_ROOT"
echo "Contracts: $CONTRACTS_DIR"
[ -n "$AGENT_ID" ] && echo "Agent filter: $AGENT_ID"
echo ""

if [ ! -d "$CONTRACTS_DIR" ]; then
  echo "No contracts directory found at $CONTRACTS_DIR -- nothing to validate."
  exit 0
fi

contract_files=("$CONTRACTS_DIR"/*.contract.json)
if [ ! -f "${contract_files[0]}" ]; then
  echo "No contract files found in $CONTRACTS_DIR"
  exit 0
fi

for contract_file in "${contract_files[@]}"; do
  if [ -f "$contract_file" ]; then
    validate_contract "$contract_file" || true
  fi
done

echo ""
echo "Results: $PASSED passed, $FAILED failed, $SKIPPED skipped"

if [ $FAILED -gt 0 ]; then
  echo ""
  echo "FAILURES:"
  echo -e "$FAILURES"
  echo ""
  echo "To bypass: cleanup.sh <agent> merge --skip-contracts"
  exit 1
fi

exit 0
```

### Fix 6: Contract Generation Script

Generates a draft contract by examining the DEPENDS_ON edges in the Ownership KG and extracting schemas from the boundary files.

**File**: `.claude/scripts/generate-contract.sh`

```bash
#!/usr/bin/env bash
# generate-contract.sh -- Generate a draft contract between two agents
#
# Usage:
#   generate-contract.sh <producer_agent> <consumer_agent> [--boundary-type TYPE] [--output FILE]
#
# Examples:
#   generate-contract.sh db-agent api-agent --boundary-type db_schema
#   generate-contract.sh api-agent ui-agent --boundary-type api_response --output .claude/contracts/api-to-ui.contract.json
#
# The script:
# 1. Queries the Ownership KG for DEPENDS_ON edges between the two agents
# 2. Identifies boundary files (producer's outputs that consumer reads)
# 3. Attempts to extract schema from producer files
# 4. Generates a draft contract.json
set -euo pipefail

PRODUCER="${1:?Usage: generate-contract.sh <producer_agent> <consumer_agent> [--boundary-type TYPE]}"
CONSUMER="${2:?Missing consumer agent}"
shift 2

BOUNDARY_TYPE="api_response"
OUTPUT=""
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --boundary-type) BOUNDARY_TYPE="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [ -z "$OUTPUT" ]; then
  OUTPUT="$PROJECT_ROOT/.claude/contracts/${PRODUCER}-to-${CONSUMER}.contract.json"
fi

# Find Python
PYTHON=""
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null; then
  PYTHON="python"
else
  echo "Error: Python 3 required" >&2
  exit 1
fi

EXTRACT_SCRIPT="$PROJECT_ROOT/scripts/extract-schema.py"

echo "Generating contract: $PRODUCER -> $CONSUMER"
echo "Boundary type: $BOUNDARY_TYPE"
echo ""

# ── Step 1: Discover boundary files ──────────────────────────────────────────
# Attempt to find files owned by each agent.
# Strategy: Check if ownership KG MCP is available, else use heuristics.

discover_files() {
  local agent="$1"
  local role="$2"  # producer or consumer

  # Heuristic: look for conventional directory patterns
  local patterns=()
  case "$agent" in
    *db*|*data*)
      patterns=("dbt/models/**/*.sql" "migrations/**/*.sql" "db/**/*.sql")
      ;;
    *api*|*backend*)
      patterns=("backend/**/*.py" "src/api/**/*.py" "api/**/*.py" "src/**/*.py")
      ;;
    *ui*|*frontend*)
      patterns=("ui/src/**/*.ts" "ui/src/**/*.tsx" "frontend/src/**/*.ts" "frontend/src/**/*.tsx")
      ;;
    *)
      patterns=("src/**/*" "lib/**/*")
      ;;
  esac

  for pattern in "${patterns[@]}"; do
    # Use find with globbing
    local found
    found="$(cd "$PROJECT_ROOT" && find . -path "./$pattern" -type f 2>/dev/null | head -20 | sed 's|^\./||')" || true
    if [ -n "$found" ]; then
      echo "$found"
    fi
  done
}

echo "Discovering producer files ($PRODUCER)..."
PRODUCER_FILES="$(discover_files "$PRODUCER" producer)"
if [ -z "$PRODUCER_FILES" ]; then
  echo "  No files found for producer '$PRODUCER'. You will need to fill in files manually."
  PRODUCER_FILES=""
fi

echo "Discovering consumer files ($CONSUMER)..."
CONSUMER_FILES="$(discover_files "$CONSUMER" consumer)"
if [ -z "$CONSUMER_FILES" ]; then
  echo "  No files found for consumer '$CONSUMER'. You will need to fill in files manually."
  CONSUMER_FILES=""
fi

# ── Step 2: Detect extraction method ─────────────────────────────────────────

detect_extraction() {
  local first_file="$1"
  if [ -z "$first_file" ]; then
    echo "unknown unknown unknown"
    return
  fi

  case "$first_file" in
    *.py)
      # Look for Pydantic models
      if grep -q "BaseModel\|BaseSchema" "$PROJECT_ROOT/$first_file" 2>/dev/null; then
        # Find the first class name
        local class_name
        class_name="$(grep -m1 "class \w\+.*BaseModel\|class \w\+.*BaseSchema" "$PROJECT_ROOT/$first_file" 2>/dev/null | sed 's/class \(\w\+\).*/\1/')" || true
        echo "python pydantic_model ${class_name:-UnknownModel}"
      else
        # Look for function signatures
        local func_name
        func_name="$(grep -m1 "def \w\+" "$PROJECT_ROOT/$first_file" 2>/dev/null | sed 's/.*def \(\w\+\).*/\1/')" || true
        echo "python function_signature ${func_name:-unknown}"
      fi
      ;;
    *.ts|*.tsx)
      # Look for interface or type
      local iface_name
      iface_name="$(grep -m1 "interface \w\+\|type \w\+ =" "$PROJECT_ROOT/$first_file" 2>/dev/null | sed 's/.*\(interface\|type\) \(\w\+\).*/\2/')" || true
      echo "typescript typescript_interface ${iface_name:-UnknownInterface}"
      ;;
    *.sql)
      echo "sql sql_table UNKNOWN_TABLE"
      ;;
    *)
      echo "unknown unknown unknown"
      ;;
  esac
}

FIRST_PRODUCER_FILE="$(echo "$PRODUCER_FILES" | head -1)"
read -r LANG METHOD TARGET <<< "$(detect_extraction "$FIRST_PRODUCER_FILE")"

echo ""
echo "Detected extraction: language=$LANG, method=$METHOD, target=$TARGET"

# ── Step 3: Attempt schema extraction ────────────────────────────────────────

EXTRACTED_SCHEMA='{}'
if [ -n "$FIRST_PRODUCER_FILE" ] && [ "$LANG" != "unknown" ] && [ -f "$EXTRACT_SCRIPT" ]; then
  echo "Extracting schema from $FIRST_PRODUCER_FILE..."
  EXTRACTED_SCHEMA="$($PYTHON "$EXTRACT_SCRIPT" \
    --language "$LANG" \
    --method "$METHOD" \
    --target "$TARGET" \
    --file "$PROJECT_ROOT/$FIRST_PRODUCER_FILE" \
    --pretty 2>&1)" || {
    echo "  Warning: Extraction failed. Using empty schema."
    EXTRACTED_SCHEMA='{}'
  }
fi

# ── Step 4: Build contract JSON ──────────────────────────────────────────────

# Convert file lists to JSON arrays
producer_files_json="$($PYTHON -c "
import json
files = '''$PRODUCER_FILES'''.strip().split('\n')
files = [f for f in files if f]
print(json.dumps(files[:5]))  # Limit to first 5
")"

consumer_files_json="$($PYTHON -c "
import json
files = '''$CONSUMER_FILES'''.strip().split('\n')
files = [f for f in files if f]
print(json.dumps(files[:5]))  # Limit to first 5
")"

CONTRACT_ID="${PRODUCER}-to-${CONSUMER}"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$(dirname "$OUTPUT")"

$PYTHON << PYEOF > "$OUTPUT"
import json
from datetime import datetime

contract = {
    "contract_id": "$CONTRACT_ID",
    "version": "1.0.0",
    "producer": {
        "agent_id": "$PRODUCER",
        "files": json.loads('$producer_files_json'),
        "extraction": {
            "language": "$LANG",
            "method": "$METHOD",
            "target": "$TARGET"
        }
    },
    "consumers": [
        {
            "agent_id": "$CONSUMER",
            "files": json.loads('$consumer_files_json'),
            "usage": "TODO: Describe how $CONSUMER uses $PRODUCER's output"
        }
    ],
    "boundary_type": "$BOUNDARY_TYPE",
    "schema": json.loads('''$EXTRACTED_SCHEMA'''),
    "strict": True,
    "validation_mode": "block_merge",
    "metadata": {
        "created_at": "$TIMESTAMP",
        "created_by": "generate-contract.sh",
        "description": "Auto-generated contract for $PRODUCER -> $CONSUMER boundary. Review and edit before committing."
    }
}

# Clean up extraction if unknown
if contract["producer"]["extraction"]["language"] == "unknown":
    del contract["producer"]["extraction"]

print(json.dumps(contract, indent=2))
PYEOF

echo ""
echo "Contract written to: $OUTPUT"
echo ""
echo "IMPORTANT: Review the generated contract before committing."
echo "  - Verify the schema matches your expectations"
echo "  - Fill in any TODO fields"
echo "  - Adjust strict/validation_mode as needed"
echo "  - Add additional consumer files if needed"
```

### Fix 7: Modified cleanup.sh -- Add Contract Validation Before Merge

This is the critical integration point. The existing cleanup.sh merges the agent worktree to main. We add a contract validation step between the agent's test pass and the merge.

**File**: `.claude/scripts/cleanup.sh` (modified)

The following shows the exact change to apply:

```diff
--- a/cleanup.sh
+++ b/cleanup.sh
@@ -1,10 +1,12 @@
 #!/usr/bin/env bash
-# cleanup.sh — Merge agent results to main and remove worktree
+# cleanup.sh — Validate contracts, merge agent results to main, remove worktree
 #
 # Usage:
-#   cleanup.sh <agent_name> <merge|discard>
+#   cleanup.sh <agent_name> <merge|discard> [--skip-contracts] [--agent-id AGENT_ID]
 #
 # Examples:
+#   cleanup.sh reactive-20260210_143000 merge --agent-id db-agent
 #   cleanup.sh reactive-20260210_143000 merge     # Merge to main + push
 #   cleanup.sh reactive-20260210_143000 discard   # Throw away changes
 set -euo pipefail
@@ -13,6 +15,22 @@
 ACTION="${2:?Missing action: merge or discard}"
 AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
 WORKTREE="$AGENT_DIR/$NAME"
 BRANCH="agent/$NAME"
+SKIP_CONTRACTS=false
+AGENT_ID=""
+
+# Parse optional args
+shift 2
+while [[ $# -gt 0 ]]; do
+  case "$1" in
+    --skip-contracts) SKIP_CONTRACTS=true; shift ;;
+    --agent-id) AGENT_ID="$2"; shift 2 ;;
+    *) echo "Unknown arg: $1" >&2; exit 1 ;;
+  esac
+done

 # ── Validate ─────────────────────────────────────────────────────────────────
 if [ ! -d "$WORKTREE" ]; then
@@ -33,6 +51,28 @@
 case "$ACTION" in
   merge)
     echo "Merging agent/$NAME to main..."
+
+    # ── Contract Validation ──────────────────────────────────────────────────
+    CONTRACT_SCRIPT="$PROJECT/.claude/../scripts/validate-contracts.sh"
+    # Try project-local first, then global
+    if [ ! -f "$CONTRACT_SCRIPT" ]; then
+      CONTRACT_SCRIPT="$PROJECT/scripts/validate-contracts.sh"
+    fi
+
+    if [ -f "$CONTRACT_SCRIPT" ] && [ "$SKIP_CONTRACTS" = false ]; then
+      echo ""
+      echo "── Contract Validation ──"
+      VALIDATE_ARGS="--project-root $PROJECT"
+      if [ -n "$AGENT_ID" ]; then
+        VALIDATE_ARGS="$VALIDATE_ARGS --agent $AGENT_ID"
+      fi
+      if ! bash "$CONTRACT_SCRIPT" $VALIDATE_ARGS; then
+        echo ""
+        echo "ERROR: Contract validation failed. Merge blocked."
+        echo "  Fix the contract violations above, or use --skip-contracts to bypass."
+        exit 1
+      fi
+      echo ""
+    fi

     # Commit any uncommitted changes in the worktree
     cd "$WORKTREE"
```

The full modified file:

```bash
#!/usr/bin/env bash
# cleanup.sh -- Validate contracts, merge agent results to main, remove worktree
#
# Usage:
#   cleanup.sh <agent_name> <merge|discard> [--skip-contracts] [--agent-id AGENT_ID]
#
# Examples:
#   cleanup.sh reactive-20260210_143000 merge --agent-id db-agent
#   cleanup.sh reactive-20260210_143000 merge     # Merge to main + push
#   cleanup.sh reactive-20260210_143000 discard   # Throw away changes
set -euo pipefail

NAME="${1:?Usage: cleanup.sh <agent_name> <merge|discard> [--skip-contracts] [--agent-id ID]}"
ACTION="${2:?Missing action: merge or discard}"
AGENT_DIR="${AGENT_FARM_DIR:-$HOME/agents}"
WORKTREE="$AGENT_DIR/$NAME"
BRANCH="agent/$NAME"
SKIP_CONTRACTS=false
AGENT_ID=""

# Parse optional args
shift 2
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-contracts) SKIP_CONTRACTS=true; shift ;;
    --agent-id) AGENT_ID="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# ── Validate ─────────────────────────────────────────────────────────────────
if [ ! -d "$WORKTREE" ]; then
  echo "Error: Worktree not found at $WORKTREE" >&2
  echo "Active worktrees:"
  git worktree list 2>/dev/null || true
  exit 1
fi

# Find the main repo (parent of worktree)
PROJECT="$(cd "$WORKTREE" && git rev-parse --git-common-dir 2>/dev/null | sed 's|/\.git$||')"
if [ -z "$PROJECT" ] || [ ! -d "$PROJECT" ]; then
  echo "Error: Could not find parent repo for worktree" >&2
  exit 1
fi

case "$ACTION" in
  merge)
    echo "Merging agent/$NAME to main..."

    # ── Contract Validation ──────────────────────────────────────────────────
    CONTRACT_SCRIPT="$PROJECT/scripts/validate-contracts.sh"

    if [ -f "$CONTRACT_SCRIPT" ] && [ "$SKIP_CONTRACTS" = false ]; then
      echo ""
      echo "── Contract Validation ──"
      VALIDATE_ARGS="--project-root $PROJECT"
      if [ -n "$AGENT_ID" ]; then
        VALIDATE_ARGS="$VALIDATE_ARGS --agent $AGENT_ID"
      fi
      if ! bash "$CONTRACT_SCRIPT" $VALIDATE_ARGS; then
        echo ""
        echo "ERROR: Contract validation failed. Merge blocked."
        echo "  Fix the contract violations above, or use --skip-contracts to bypass."
        exit 1
      fi
      echo ""
    fi

    # Commit any uncommitted changes in the worktree
    cd "$WORKTREE"
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
      git add -A
      git commit -m "Agent $NAME: final results [$(hostname -s)]" --no-verify
    fi

    # Switch to main repo and merge
    cd "$PROJECT"
    MAIN_BRANCH="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo main)"
    git checkout "$MAIN_BRANCH" 2>/dev/null
    git merge "$BRANCH" --no-ff -m "Merge $BRANCH results" --no-verify

    # Push
    git push 2>/dev/null && echo "Pushed to remote." || echo "Warning: Push failed. Run 'git push' manually."

    echo "Merged: $BRANCH → $MAIN_BRANCH"
    ;;

  discard)
    echo "Discarding agent/$NAME changes..."
    ;;

  *)
    echo "Error: Unknown action '$ACTION'. Use: merge or discard" >&2
    exit 1
    ;;
esac

# ── Remove worktree and branch ──────────────────────────────────────────────
cd "$PROJECT"
git worktree remove "$WORKTREE" --force 2>/dev/null || {
  echo "Warning: Could not remove worktree. Trying manual cleanup..." >&2
  rm -rf "$WORKTREE"
  git worktree prune
}
git branch -D "$BRANCH" 2>/dev/null || true

echo "Cleaned up: $WORKTREE removed, branch $BRANCH deleted"
```

### Fix 8: Contract Evolution -- Version Bump Script

When a producer agent legitimately needs to make a breaking change, this script updates the contract version, archives the old schema in `previous_versions`, and creates notification beads for all consumers.

**File**: `.claude/scripts/bump-contract.sh`

```bash
#!/usr/bin/env bash
# bump-contract.sh -- Bump contract version for a breaking change
#
# Usage:
#   bump-contract.sh <contract_file> <major|minor|patch> --reason "Added variant_sku column"
#
# Examples:
#   bump-contract.sh .claude/contracts/db-to-api-products.contract.json minor --reason "Added variant_sku"
#   bump-contract.sh .claude/contracts/api-to-ui-products.contract.json major --reason "Renamed id to product_id"
set -euo pipefail

CONTRACT_FILE="${1:?Usage: bump-contract.sh <contract_file> <major|minor|patch> --reason \"...\"}"
BUMP_TYPE="${2:?Missing bump type: major, minor, or patch}"
shift 2

REASON=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reason) REASON="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [ -z "$REASON" ]; then
  echo "Error: --reason is required for contract bumps" >&2
  exit 1
fi

if [ ! -f "$CONTRACT_FILE" ]; then
  echo "Error: Contract file not found: $CONTRACT_FILE" >&2
  exit 1
fi

PYTHON=""
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null; then
  PYTHON="python"
else
  echo "Error: Python 3 required" >&2
  exit 1
fi

# Bump version and archive old schema
$PYTHON << PYEOF > "${CONTRACT_FILE}.tmp"
import json
from datetime import datetime, timezone

with open("$CONTRACT_FILE") as f:
    contract = json.load(f)

old_version = contract["version"]
parts = old_version.split(".")
major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

bump_type = "$BUMP_TYPE"
if bump_type == "major":
    major += 1
    minor = 0
    patch = 0
elif bump_type == "minor":
    minor += 1
    patch = 0
elif bump_type == "patch":
    patch += 1
else:
    raise ValueError(f"Invalid bump type: {bump_type}")

new_version = f"{major}.{minor}.{patch}"

# Archive previous version
if "previous_versions" not in contract:
    contract["previous_versions"] = []

contract["previous_versions"].append({
    "version": old_version,
    "deprecated_at": datetime.now(timezone.utc).isoformat(),
    "migration_notes": "$REASON"
})

contract["version"] = new_version

# Update metadata
if "metadata" not in contract:
    contract["metadata"] = {}
contract["metadata"]["last_validated"] = datetime.now(timezone.utc).isoformat()

print(json.dumps(contract, indent=2))
PYEOF

mv "${CONTRACT_FILE}.tmp" "$CONTRACT_FILE"

echo "Contract bumped: $old_version -> $(python3 -c "import json; print(json.load(open('$CONTRACT_FILE'))['version'])")"

# Create notification beads for consumers
if command -v bd &>/dev/null; then
  CONTRACT_ID="$($PYTHON -c "import json; print(json.load(open('$CONTRACT_FILE'))['contract_id'])")"
  CONSUMERS="$($PYTHON -c "import json; [print(c['agent_id']) for c in json.load(open('$CONTRACT_FILE'))['consumers']]")"

  while IFS= read -r consumer; do
    if [ -n "$consumer" ]; then
      bd create "CONTRACT UPDATED: $CONTRACT_ID v$(python3 -c "import json; print(json.load(open('$CONTRACT_FILE'))['version'])") -- $consumer review required. Reason: $REASON" \
        --priority 1 2>/dev/null || true
      echo "Notification bead created for: $consumer"
    fi
  done <<< "$CONSUMERS"
fi

echo ""
echo "Next steps:"
echo "  1. Update the schema in $CONTRACT_FILE to reflect the new interface"
echo "  2. Re-extract: python3 scripts/extract-schema.py --language ... --method ... --target ... --file ..."
echo "  3. Run validation: bash scripts/validate-contracts.sh"
echo "  4. Commit the updated contract file"
```

### Fix 9: CI Integration

Add contract validation as a CI step so contracts are always checked on push, not just on agent merge.

**Addition to**: `.github/workflows/deploy.yml`

Add this job before the deploy job:

```yaml
  validate-contracts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Validate all contracts
        run: |
          if [ -d ".claude/contracts" ] && ls .claude/contracts/*.contract.json 1>/dev/null 2>&1; then
            bash scripts/validate-contracts.sh --skip-notification
          else
            echo "No contracts found -- skipping validation"
          fi
```

---

## Success Criteria

### SC-1: Contract Definition Covers All Boundaries

Every DEPENDS_ON edge in the Ownership KG has a corresponding `.claude/contracts/*.contract.json` file. Verified by:

```bash
# List all DEPENDS_ON edges (from Ownership KG)
# For each edge, check contract exists
for edge in $(get_depends_on_edges); do
  producer=$(echo $edge | cut -d: -f1)
  consumer=$(echo $edge | cut -d: -f2)
  contract=".claude/contracts/${producer}-to-${consumer}.contract.json"
  [ -f "$contract" ] || echo "MISSING: $contract"
done
```

**Target**: 100% coverage of agent boundaries that cross language/runtime boundaries.

### SC-2: cleanup.sh Blocks Broken Contracts

When a producer agent changes an interface without updating the contract:

1. `cleanup.sh <name> merge` runs contract validation
2. Validation detects the schema mismatch
3. Merge is blocked (exit code 1)
4. A bead is created for each consumer agent with the contract ID and error details
5. The agent operator sees exact field-level diffs

**Test procedure**:
```bash
# In a test worktree:
# 1. Remove a required field from a Pydantic model
# 2. Run cleanup.sh -- should fail
# 3. Check that bead was created
# 4. Run cleanup.sh --skip-contracts -- should succeed (escape hatch)
```

### SC-3: Schema Extraction Accuracy

The extract-schema.py script correctly extracts JSON Schema from:

| Source | Extraction Method | Test |
|--------|-------------------|------|
| Pydantic BaseModel | `pydantic_model` | Extract ProductResponse, verify all fields and types |
| Python function | `function_signature` | Extract API handler, verify params and return type |
| TypeScript interface | `typescript_interface` | Extract Product interface, verify fields |
| TypeScript type alias | `typescript_interface` | Extract `type X = { ... }`, verify fields |
| SQL CREATE TABLE | `sql_table` | Extract DIM_PRODUCTS, verify columns and nullability |
| dbt SELECT model | `sql_table` | Extract columns from final SELECT |

**Target**: Extraction produces valid JSON Schema for >90% of patterns found in the codebase.

### SC-4: Contract Evolution Creates Audit Trail

When `bump-contract.sh` runs:

1. The contract version increments correctly (semver)
2. The old version is archived in `previous_versions` array
3. Migration notes are recorded
4. Consumer agents get notification beads
5. The contract file remains valid against CONTRACT_SCHEMA.json

### SC-5: False Positive Rate

The contract validation system should NOT block merges that do not actually break compatibility:

- Adding a new optional field to a producer (backward-compatible) = PASS
- Adding a new required field with a default value = PASS
- Reordering fields = PASS
- Changing a non-nullable field to nullable = depends on `strict` mode

**Target**: <5% false positive rate on real codebase changes over 30 days.

### SC-6: Performance

- Schema extraction: <2 seconds per file
- Full contract validation (all contracts): <10 seconds
- No impact on cleanup.sh when no contracts exist (graceful no-op)

---

## Verification

### Step 1: Unit Test the Extractor

```bash
# Create test fixtures
mkdir -p /tmp/contract-test

# Python fixture
cat > /tmp/contract-test/model.py << 'EOF'
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class ProductResponse(BaseModel):
    id: str
    name: str
    category: str
    subcategory: Optional[str] = None
    price: float = Field(description="Price in USD")
    in_stock: bool
    tags: List[str] = []
    updated_at: datetime
EOF

# Extract and verify
python3 scripts/extract-schema.py \
  --language python \
  --method pydantic_model \
  --target ProductResponse \
  --file /tmp/contract-test/model.py \
  --pretty

# Expected: JSON Schema with 8 properties, required=[category, id, in_stock, name, price, updated_at]
```

```bash
# TypeScript fixture
cat > /tmp/contract-test/types.ts << 'EOF'
export interface Product {
  id: string;
  name: string;
  category: string;
  subcategory?: string | null;
  price: number;
  in_stock: boolean;
  tags: string[];
  updated_at: string;
}
EOF

python3 scripts/extract-schema.py \
  --language typescript \
  --method typescript_interface \
  --target Product \
  --file /tmp/contract-test/types.ts \
  --pretty
```

```bash
# SQL fixture
cat > /tmp/contract-test/table.sql << 'EOF'
CREATE TABLE DIM_PRODUCTS (
    PRODUCT_ID VARCHAR(50) NOT NULL,
    PRODUCT_NAME VARCHAR(255) NOT NULL,
    CATEGORY VARCHAR(100) NOT NULL,
    SUBCATEGORY VARCHAR(100),
    PRICE DECIMAL(10,2) NOT NULL,
    IN_STOCK BOOLEAN NOT NULL,
    UPDATED_AT TIMESTAMP_NTZ NOT NULL
);
EOF

python3 scripts/extract-schema.py \
  --language sql \
  --method sql_table \
  --target DIM_PRODUCTS \
  --file /tmp/contract-test/table.sql \
  --pretty
```

### Step 2: End-to-End Contract Validation

```bash
# Place the example contracts in the repo
cp .claude/contracts/db-to-api-products.contract.json /tmp/contract-test/

# Run validation (should pass if source files exist and match)
bash scripts/validate-contracts.sh --project-root /path/to/repo

# Intentionally break a contract
# Edit the Pydantic model to remove a required field, then re-run
# Should fail and create a bead
```

### Step 3: cleanup.sh Integration Test

```bash
# Create a test worktree
cd ~/Projects/baap
git worktree add ~/agents/test-contracts -b agent/test-contracts

# Make a change that breaks a contract
cd ~/agents/test-contracts
# ... edit a file ...

# Try to merge -- should be blocked
bash .claude/scripts/cleanup.sh test-contracts merge --agent-id api-agent
# Expected: exit 1 with contract violation details

# Bypass and merge
bash .claude/scripts/cleanup.sh test-contracts merge --skip-contracts
# Expected: exit 0, merge succeeds
```

### Step 4: Contract Generation

```bash
# Generate a contract between two agents
bash scripts/generate-contract.sh api-agent ui-agent \
  --boundary-type api_response \
  --output /tmp/contract-test/api-to-ui.contract.json

# Verify the output is valid JSON and contains expected fields
python3 -c "
import json
c = json.load(open('/tmp/contract-test/api-to-ui.contract.json'))
assert c['contract_id'] == 'api-agent-to-ui-agent'
assert c['version'] == '1.0.0'
assert c['boundary_type'] == 'api_response'
assert 'schema' in c
print('Contract generation: PASS')
"
```

### Step 5: Contract Evolution

```bash
# Bump a contract version
bash scripts/bump-contract.sh \
  .claude/contracts/db-to-api-products.contract.json \
  minor \
  --reason "Added variant_sku column"

# Verify version was bumped and history preserved
python3 -c "
import json
c = json.load(open('.claude/contracts/db-to-api-products.contract.json'))
assert c['version'] == '1.1.0'
assert len(c['previous_versions']) == 1
assert c['previous_versions'][0]['version'] == '1.0.0'
assert 'variant_sku' in c['previous_versions'][0]['migration_notes']
print('Contract evolution: PASS')
"
```

---

## Design Decisions

### Why JSON Schema over Protocol Buffers / Avro?

- JSON Schema is readable by both Python (jsonschema library) and TypeScript (ajv library)
- No compilation step -- works with existing JSON tooling
- Matches the actual data format (JSON) flowing between agents
- Human-editable when auto-extraction falls short

### Why Static Extraction over Runtime Recording?

Pact-style runtime recording requires running servers and making actual HTTP calls. Our agents are CLI sessions editing files -- there is no "runtime" to record. Static AST parsing gives us the schema without executing anything.

### Why Per-Boundary Contracts, Not Per-Agent?

An agent might produce multiple interfaces (e.g., api-agent serves `/products` and `/orders`). Each interface gets its own contract. This is more granular than per-agent but avoids the combinatorial explosion of per-endpoint contracts.

### Why `strict: true` by Default?

Additive changes (new optional fields) are safe. But if a producer adds fields that consumers do not expect, it can still cause issues (e.g., UI renders unknown data, bandwidth increases). Strict mode catches these early. Teams can set `strict: false` for boundaries where additive changes are always safe.

### Why Beads for Notifications, Not Slack/Email?

Beads are the Baap-native notification system. They persist across sessions, can be searched, and are already integrated into the agent lifecycle. A "contract-broken" bead shows up when the consumer agent starts its next session -- exactly when it needs to know.

---

## Future Enhancements

1. **Ownership KG integration**: When `get_dependents(agent)` returns edges, auto-check if contracts exist for each edge. Create "contract-missing" beads for uncovered boundaries.

2. **Backward-compatible change detection**: Automatically determine if a schema change is backward-compatible (additive optional field) vs breaking (removed required field, type change). Only block on breaking changes.

3. **Cross-repo contracts**: When the boundary crosses repos (e.g., baap -> BC_ANALYTICS), store contracts in a shared location or use git submodules.

4. **Contract testing in agent prompts**: Inject contract awareness into agent system prompts so they know their output must conform to contracts. An agent could self-validate before committing.

5. **Visual contract graph**: Display agent-to-agent contracts as a directed graph in the UI, showing version status, last validation date, and health.
