"""Structured output schemas and a dependency-free validator."""

from __future__ import annotations

import re
from typing import Any, Dict, List


class SchemaError(ValueError):
    """Raised when provider output violates its declared JSON Schema."""


SERVICE_ID_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
CONTRACT_ID_PATTERN = r"^[a-z][a-z0-9.-]*[a-z0-9]$"
VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$"
CONTRACT_REF_PATTERN = (
    r"^[a-z][a-z0-9.-]*[a-z0-9]@[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$"
)
SOURCE_HASH_PATTERN = r"^(pending|sha256:[a-f0-9]{64})$"
REQUIREMENT_ID_PATTERN = r"^R[1-9][0-9]*$"

STRING_LIST_SCHEMA: Dict[str, Any] = {
    "type": "array",
    "maxItems": 50,
    "items": {"type": "string", "minLength": 1, "maxLength": 300},
}

CONTRACT_REF_LIST_SCHEMA: Dict[str, Any] = {
    "type": "array",
    "maxItems": 30,
    "items": {"type": "string", "pattern": CONTRACT_REF_PATTERN},
}

SERVICE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id",
        "domain",
        "paths",
        "owns_data",
        "exposes",
        "consumes",
        "dependencies",
        "forbidden_dependencies",
    ],
    "properties": {
        "id": {"type": "string", "pattern": SERVICE_ID_PATTERN},
        "domain": {"type": "string", "minLength": 2, "maxLength": 120},
        "paths": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {"type": "string", "minLength": 1, "maxLength": 300},
        },
        "owns_data": STRING_LIST_SCHEMA,
        "exposes": CONTRACT_REF_LIST_SCHEMA,
        "consumes": CONTRACT_REF_LIST_SCHEMA,
        "dependencies": {
            "type": "array",
            "maxItems": 30,
            "items": {"type": "string", "pattern": SERVICE_ID_PATTERN},
        },
        "forbidden_dependencies": {
            "type": "array",
            "maxItems": 30,
            "items": {"type": "string", "pattern": SERVICE_ID_PATTERN},
        },
    },
}

CONTRACT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id",
        "kind",
        "version",
        "owner",
        "status",
        "source",
        "source_hash",
        "producers",
        "consumers",
        "compatibility",
        "change_type",
        "invariants",
        "verification",
        "rollout",
        "rollback",
    ],
    "properties": {
        "id": {"type": "string", "pattern": CONTRACT_ID_PATTERN},
        "kind": {
            "type": "string",
            "enum": ["api", "event", "data", "frontend", "workflow", "operations"],
        },
        "version": {"type": "string", "pattern": VERSION_PATTERN},
        "owner": {"type": "string", "pattern": SERVICE_ID_PATTERN},
        "status": {"type": "string", "enum": ["draft", "approved", "deprecated"]},
        "source": {"type": "string", "minLength": 1, "maxLength": 300},
        "source_hash": {"type": "string", "pattern": SOURCE_HASH_PATTERN},
        "producers": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {"type": "string", "pattern": SERVICE_ID_PATTERN},
        },
        "consumers": {
            "type": "array",
            "maxItems": 30,
            "items": {"type": "string", "pattern": SERVICE_ID_PATTERN},
        },
        "compatibility": {
            "type": "string",
            "enum": ["backward", "forward", "full", "none"],
        },
        "change_type": {"type": "string", "enum": ["none", "additive", "breaking"]},
        "invariants": STRING_LIST_SCHEMA,
        "verification": STRING_LIST_SCHEMA,
        "rollout": {"type": "string", "minLength": 2, "maxLength": 1000},
        "rollback": {"type": "string", "minLength": 2, "maxLength": 1000},
    },
}

TASK_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id",
        "title",
        "description",
        "dependencies",
        "acceptance_criteria",
        "owner",
        "scope",
        "files",
        "risks",
        "review_required",
    ],
    "properties": {
        "id": {"type": "string", "pattern": r"^T[1-9][0-9]*$"},
        "title": {"type": "string", "minLength": 3, "maxLength": 160},
        "description": {"type": "string", "minLength": 3, "maxLength": 2000},
        "dependencies": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string", "pattern": r"^T[1-9][0-9]*$"},
        },
        "acceptance_criteria": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {"type": "string", "minLength": 5, "maxLength": 1000},
        },
        "owner": {
            "type": "string",
            "enum": ["architect", "backend", "frontend", "database", "qa", "reviewer", "documenter", "release"],
        },
        "scope": {"type": "string", "enum": ["S", "M"]},
        "files": {
            "type": "array",
            "minItems": 1,
            "maxItems": 30,
            "items": {"type": "string", "minLength": 1, "maxLength": 300},
        },
        "risks": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "string",
                "enum": [
                    "database",
                    "destructive",
                    "production",
                    "credentials",
                    "external-write",
                    "security",
                    "public-contract",
                ],
            },
        },
        "review_required": {"type": "boolean"},
        "requirement_refs": {
            "type": "array",
            "maxItems": 30,
            "items": {"type": "string", "pattern": REQUIREMENT_ID_PATTERN},
        },
        "verification_commands": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 40,
                "items": {"type": "string", "minLength": 1, "maxLength": 500},
            },
        },
        "service": {"type": "string", "pattern": SERVICE_ID_PATTERN},
        "layer": {
            "type": "string",
            "enum": [
                "architecture",
                "frontend",
                "backend",
                "api",
                "event",
                "database",
                "integration",
                "operations",
                "documentation",
            ],
        },
        "contract_reads": CONTRACT_REF_LIST_SCHEMA,
        "contract_writes": CONTRACT_REF_LIST_SCHEMA,
        "produces": CONTRACT_REF_LIST_SCHEMA,
        "data_entities": STRING_LIST_SCHEMA,
        "environments": STRING_LIST_SCHEMA,
        "integration_tests": STRING_LIST_SCHEMA,
        "deploy_after": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string", "pattern": SERVICE_ID_PATTERN},
        },
        "rollback": {"type": "string", "maxLength": 1000},
    },
}

PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "tasks"],
    "properties": {
        "summary": {"type": "string", "minLength": 3, "maxLength": 3000},
        "program_id": {"type": "string", "minLength": 1, "maxLength": 120},
        "workstream_id": {"type": "string", "minLength": 1, "maxLength": 120},
        "parent_feature": {"type": "string", "minLength": 1, "maxLength": 160},
        "services": {"type": "array", "maxItems": 50, "items": SERVICE_SCHEMA},
        "contracts": {"type": "array", "maxItems": 100, "items": CONTRACT_SCHEMA},
        "tasks": {"type": "array", "minItems": 1, "maxItems": 24, "items": TASK_SCHEMA},
    },
}

EXECUTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["outcome", "summary", "evidence", "changed_files", "memory"],
    "properties": {
        "outcome": {"type": "string", "enum": ["success", "failed", "needs_replan"]},
        "summary": {"type": "string", "minLength": 3, "maxLength": 4000},
        "evidence": {
            "type": "array",
            "maxItems": 30,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["criterion", "result", "detail"],
                "properties": {
                    "criterion": {"type": "string", "minLength": 1, "maxLength": 1000},
                    "result": {"type": "string", "enum": ["pass", "fail"]},
                    "detail": {"type": "string", "minLength": 1, "maxLength": 3000},
                    "command": {"type": "string", "maxLength": 1000},
                },
            },
        },
        "changed_files": {
            "type": "array",
            "maxItems": 100,
            "items": {"type": "string", "minLength": 1, "maxLength": 300},
        },
        "memory": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "content", "tags"],
                "properties": {
                    "kind": {"type": "string", "enum": ["working", "episodic", "semantic"]},
                    "content": {"type": "string", "minLength": 1, "maxLength": 5000},
                    "tags": {
                        "type": "array",
                        "maxItems": 20,
                        "items": {"type": "string", "minLength": 1, "maxLength": 80},
                    },
                },
            },
        },
    },
}

REVIEW_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "summary", "findings", "evidence_checked"],
    "properties": {
        "verdict": {"type": "string", "enum": ["approve", "revise", "block"]},
        "summary": {"type": "string", "minLength": 3, "maxLength": 4000},
        "findings": {
            "type": "array",
            "maxItems": 30,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "description"],
                "properties": {
                    "severity": {"type": "string", "enum": ["note", "minor", "major", "blocker"]},
                    "description": {"type": "string", "minLength": 3, "maxLength": 2000},
                    "file": {"type": "string", "maxLength": 300},
                },
            },
        },
        "evidence_checked": {
            "type": "array",
            "maxItems": 30,
            "items": {"type": "string", "minLength": 1, "maxLength": 1000},
        },
    },
}


def validate(instance: Any, schema: Dict[str, Any], path: str = "$") -> None:
    """Validate the JSON Schema subset used by AI-Kit."""

    expected = schema.get("type")
    type_ok = {
        "object": lambda value: isinstance(value, dict),
        "array": lambda value: isinstance(value, list),
        "string": lambda value: isinstance(value, str),
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda value: isinstance(value, bool),
        "null": lambda value: value is None,
    }
    if expected and (expected not in type_ok or not type_ok[expected](instance)):
        raise SchemaError("%s must be %s" % (path, expected))
    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaError("%s must be one of %s" % (path, schema["enum"]))

    if isinstance(instance, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in instance]
        if missing:
            raise SchemaError("%s missing required keys: %s" % (path, ", ".join(missing)))
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unexpected = sorted(set(instance) - set(properties))
            if unexpected:
                raise SchemaError("%s has unexpected keys: %s" % (path, ", ".join(unexpected)))
        for key, value in instance.items():
            if key in properties:
                validate(value, properties[key], "%s.%s" % (path, key))

    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise SchemaError("%s has too few items" % path)
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise SchemaError("%s has too many items" % path)
        item_schema = schema.get("items")
        if item_schema:
            for index, value in enumerate(instance):
                validate(value, item_schema, "%s[%d]" % (path, index))

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise SchemaError("%s is too short" % path)
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise SchemaError("%s is too long" % path)
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            raise SchemaError("%s does not match required pattern" % path)
