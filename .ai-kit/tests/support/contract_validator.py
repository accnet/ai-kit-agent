#!/usr/bin/env python3
"""Shared dependency-free JSON-schema validator for active contract tests."""

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / ".ai-kit" / "contracts"


class ContractError(ValueError):
    """Raised when a contract fixture violates a schema or runtime invariant."""


class SchemaValidator:
    """Validate the dependency-free JSON Schema subset used by StarterKit contracts."""

    def __init__(self, contracts_root):
        self.contracts_root = contracts_root
        self.documents = {}

    def load(self, name):
        path = (self.contracts_root / name).resolve()
        if path.parent != self.contracts_root.resolve():
            raise ContractError("contract reference escapes .ai-kit/contracts: %s" % name)
        if path not in self.documents:
            self.documents[path] = json.loads(path.read_text(encoding="utf-8"))
        return path, self.documents[path]

    def validate(self, instance, source):
        path, schema = self.load(source)
        self._validate(instance, schema, path, "$")

    def _resolve_ref(self, ref, current_path):
        source, separator, fragment = ref.partition("#")
        if source:
            target_path, target = self.load(source)
        else:
            target_path, target = current_path, self.documents[current_path]
        if separator and fragment:
            if not fragment.startswith("/"):
                raise ContractError("unsupported JSON pointer: %s" % ref)
            for token in fragment[1:].split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                if not isinstance(target, dict) or token not in target:
                    raise ContractError("unresolved contract reference: %s" % ref)
                target = target[token]
        return target_path, target

    def _validate(self, value, schema, current_path, location):
        if "$ref" in schema:
            target_path, target = self._resolve_ref(schema["$ref"], current_path)
            self._validate(value, target, target_path, location)
            return

        if "oneOf" in schema:
            matches = 0
            for candidate in schema["oneOf"]:
                try:
                    self._validate(value, candidate, current_path, location)
                    matches += 1
                except ContractError:
                    pass
            if matches != 1:
                raise ContractError("%s must match exactly one schema (matched %d)" % (location, matches))

        if "anyOf" in schema:
            for candidate in schema["anyOf"]:
                try:
                    self._validate(value, candidate, current_path, location)
                    break
                except ContractError:
                    continue
            else:
                raise ContractError("%s does not match any allowed schema" % location)

        if "const" in schema and value != schema["const"]:
            raise ContractError("%s must equal %r" % (location, schema["const"]))
        if "enum" in schema and value not in schema["enum"]:
            raise ContractError("%s contains an unsupported value" % location)

        expected = schema.get("type")
        if expected is not None:
            allowed = expected if isinstance(expected, list) else [expected]
            if not any(self._matches_type(value, item) for item in allowed):
                raise ContractError("%s must be %s" % (location, "/".join(allowed)))

        if isinstance(value, dict):
            self._validate_object(value, schema, current_path, location)
        elif isinstance(value, list):
            self._validate_array(value, schema, current_path, location)
        elif isinstance(value, str):
            if len(value) < schema.get("minLength", 0):
                raise ContractError("%s is shorter than minLength" % location)
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                raise ContractError("%s is longer than maxLength" % location)
            if "pattern" in schema and re.search(schema["pattern"], value) is None:
                raise ContractError("%s does not match its pattern" % location)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                raise ContractError("%s is below minimum" % location)
            if "maximum" in schema and value > schema["maximum"]:
                raise ContractError("%s is above maximum" % location)
            if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
                raise ContractError("%s is not above exclusiveMinimum" % location)

    @staticmethod
    def _matches_type(value, expected):
        return {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(expected, False)

    def _validate_object(self, value, schema, current_path, location):
        for key in schema.get("required", []):
            if key not in value:
                raise ContractError("%s is missing required property %s" % (location, key))

        properties = schema.get("properties", {})
        patterns = schema.get("patternProperties", {})
        for key, item in value.items():
            matched = False
            if key in properties:
                self._validate(item, properties[key], current_path, "%s.%s" % (location, key))
                matched = True
            for pattern, child_schema in patterns.items():
                if re.search(pattern, key):
                    self._validate(item, child_schema, current_path, "%s.%s" % (location, key))
                    matched = True
            if not matched and schema.get("additionalProperties") is False:
                raise ContractError("%s contains unknown property %s" % (location, key))
            if not matched and isinstance(schema.get("additionalProperties"), dict):
                self._validate(item, schema["additionalProperties"], current_path, "%s.%s" % (location, key))

    def _validate_array(self, value, schema, current_path, location):
        if len(value) < schema.get("minItems", 0):
            raise ContractError("%s has fewer than minItems" % location)
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ContractError("%s has more than maxItems" % location)
        if schema.get("uniqueItems"):
            fingerprints = [json.dumps(item, sort_keys=True) for item in value]
            if len(fingerprints) != len(set(fingerprints)):
                raise ContractError("%s must contain unique items" % location)
        if "items" in schema:
            for index, item in enumerate(value):
                self._validate(item, schema["items"], current_path, "%s[%d]" % (location, index))


VALIDATOR = SchemaValidator(CONTRACTS)


def expect_valid(source, fixture, invariant=None):
    try:
        VALIDATOR.validate(fixture, source)
        if invariant:
            invariant(fixture)
        return True, ""
    except (ContractError, OSError, json.JSONDecodeError) as error:
        return False, str(error)


def expect_invalid(source, fixture, invariant=None):
    passed, detail = expect_valid(source, fixture, invariant)
    return (not passed), ("unexpectedly accepted" if passed else detail)
