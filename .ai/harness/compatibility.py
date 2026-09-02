"""Deterministic, dependency-free JSON Schema compatibility analysis."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
from typing import Any, Dict, List

SUPPORTED = {"type", "properties", "required", "items", "enum", "additionalProperties", "$ref", "description", "title", "$schema", "$id"}
VALID_TYPES = {"null", "boolean", "object", "array", "number", "string", "integer"}

@dataclass(frozen=True)
class Finding:
    path: str
    kind: str
    message: str
    severity: str

class CompatibilityError(ValueError):
    pass

def _type_set(value: Any):
    if value is None: return None
    values = value if isinstance(value, list) else [value]
    if (not values or not all(isinstance(item, str) and item in VALID_TYPES for item in values)
            or len(values) != len(set(values))):
        raise CompatibilityError("type must be a string or string array")
    return set(values)

def _json_values(values: Any, path: str):
    if not isinstance(values, list):
        raise CompatibilityError("enum must be an array at %s" % path)
    try:
        encoded = {json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for item in values}
    except (TypeError, ValueError) as exc:
        raise CompatibilityError("enum contains a non-JSON value at %s" % path) from exc
    if not values or len(encoded) != len(values):
        raise CompatibilityError("enum must be non-empty and unique at %s" % path)
    return encoded

def _required(value: Any, path: str):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise CompatibilityError("required must be a string array at %s" % path)
    if len(value) != len(set(value)):
        raise CompatibilityError("required contains duplicates at %s" % path)
    return set(value)

def compare(previous: Dict[str, Any], proposed: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(previous, dict) or not isinstance(proposed, dict):
        raise CompatibilityError("schemas must be JSON objects")
    findings: List[Finding] = []
    def walk(old: Dict[str, Any], new: Dict[str, Any], path: str) -> None:
        if not isinstance(old, dict) or not isinstance(new, dict):
            raise CompatibilityError("schema nodes must be objects at %s" % path)
        if any(not isinstance(key, str) for key in set(old) | set(new)):
            raise CompatibilityError("schema keyword names must be strings at %s" % path)
        unknown = (set(old) | set(new)) - SUPPORTED
        if unknown:
            raise CompatibilityError("unsupported schema keywords at %s: %s" % (path, ", ".join(sorted(unknown))))
        if "$ref" in old or "$ref" in new:
            for value in (old.get("$ref"), new.get("$ref")):
                if value is not None and (not isinstance(value, str) or not value):
                    raise CompatibilityError("$ref must be a non-empty string at %s" % path)
            semantic_siblings = (
                (set(old) | set(new)) - {"$ref", "description", "title", "$schema", "$id"}
            )
            if semantic_siblings:
                raise CompatibilityError(
                    "unsupported $ref siblings at %s: %s"
                    % (path, ", ".join(sorted(semantic_siblings)))
                )
            if old.get("$ref") != new.get("$ref"):
                findings.append(Finding(path, "ref-changed", "reference target changed", "breaking"))
            return
        old_types, new_types = _type_set(old.get("type")), _type_set(new.get("type"))
        if old_types is None and new_types is not None:
            findings.append(Finding(path, "type-constrained", "proposed schema adds a type constraint", "breaking"))
        elif old_types is not None and new_types is None:
            findings.append(Finding(path, "type-unconstrained", "proposed schema removes a type constraint", "additive"))
        elif old_types is not None and new_types is not None:
            if not old_types.issubset(new_types):
                findings.append(Finding(path, "type-narrowed", "proposed type no longer accepts every previous type", "breaking"))
            elif old_types != new_types:
                findings.append(Finding(path, "type-widened", "proposed type accepts additional values", "additive"))
        old_enum, new_enum = old.get("enum"), new.get("enum")
        if old_enum is not None or new_enum is not None:
            if old_enum is None:
                findings.append(Finding(path, "enum-constrained", "proposed schema adds an enum constraint", "breaking"))
            elif new_enum is None:
                findings.append(Finding(path, "enum-unconstrained", "proposed schema removes an enum constraint", "additive"))
            elif not _json_values(old_enum, path).issubset(_json_values(new_enum, path)):
                findings.append(Finding(path, "enum-narrowed", "proposed enum removes an existing value", "breaking"))
            elif _json_values(old_enum, path) != _json_values(new_enum, path):
                findings.append(Finding(path, "enum-widened", "proposed enum adds values", "additive"))
        old_props, new_props = old.get("properties", {}), new.get("properties", {})
        if not isinstance(old_props, dict) or not isinstance(new_props, dict):
            raise CompatibilityError("properties must be an object at %s" % path)
        if any(not isinstance(name, str) for name in set(old_props) | set(new_props)):
            raise CompatibilityError("property names must be strings at %s" % path)
        old_required = _required(old.get("required", []), path)
        new_required = _required(new.get("required", []), path)
        for name in sorted(set(old_props) - set(new_props)):
            findings.append(Finding(path + "." + name, "property-removed", "property was removed", "breaking"))
        for name in sorted(set(new_props) - set(old_props)):
            if name not in new_required:
                findings.append(Finding(path + "." + name, "property-added", "optional property was added", "additive"))
        for name in sorted(new_required - old_required):
            findings.append(Finding(path + "." + name, "required-added", "new required property breaks old inputs", "breaking"))
        for name in sorted(old_required - new_required):
            findings.append(Finding(path + "." + name, "required-removed", "required property became optional", "additive"))
        for name in sorted(set(old_props) & set(new_props)):
            walk(old_props[name], new_props[name], path + "." + name)
        if "items" not in old and "items" in new:
            if not isinstance(new["items"], dict): raise CompatibilityError("items must be an object at %s" % path)
            findings.append(Finding(path + "[]", "items-constrained", "proposed array adds an item constraint", "breaking"))
        elif "items" in old and "items" not in new:
            if not isinstance(old["items"], dict): raise CompatibilityError("items must be an object at %s" % path)
            findings.append(Finding(path + "[]", "items-unconstrained", "proposed array removes an item constraint", "additive"))
        elif "items" in old and "items" in new:
            if not isinstance(old["items"], dict) or not isinstance(new["items"], dict): raise CompatibilityError("items must be an object at %s" % path)
            walk(old["items"], new["items"], path + "[]")
        old_additional, new_additional = old.get("additionalProperties", True), new.get("additionalProperties", True)
        if not isinstance(old_additional, (bool, dict)) or not isinstance(new_additional, (bool, dict)):
            raise CompatibilityError("additionalProperties must be a boolean or object at %s" % path)
        if isinstance(old_additional, dict) and isinstance(new_additional, dict):
            walk(old_additional, new_additional, path + ".*")
        elif old_additional is not new_additional:
            if new_additional is False or (old_additional is True and isinstance(new_additional, dict)):
                findings.append(Finding(path + ".*", "additional-properties-restricted", "proposed schema restricts additional properties", "breaking"))
            else:
                findings.append(Finding(path + ".*", "additional-properties-relaxed", "proposed schema accepts more additional properties", "additive"))
    walk(previous, previous, "$")
    walk(proposed, proposed, "$")
    walk(previous, proposed, "$")
    breaking = any(item.severity == "breaking" for item in findings)
    additive = any(item.severity == "additive" for item in findings)
    classification = "breaking" if breaking else ("additive" if additive else "unchanged")
    return {"classification": classification, "compatible": not breaking, "findings": [asdict(item) for item in findings]}
