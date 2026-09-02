from ..contract_adapters import AdapterError, ContractAdapter


PHASES = ["expand", "backfill", "switch", "contract"]
ROOT_FIELDS = {"writer", "readers", "entities", "migration", "integrity"}
ENTITY_FIELDS = {"name", "type", "nullable"}


def _strings(value, location):
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise AdapterError(location + " must be a string array")
    if len(value) != len(set(value)):
        raise AdapterError(location + " contains duplicates")
    return value


def _entities(document):
    result = {}
    for index, raw in enumerate(document["entities"]):
        location = "$.entities[%d]" % index
        if isinstance(raw, str):
            entity = {"name": raw, "type": None, "nullable": True}
        elif isinstance(raw, dict):
            unsupported = set(raw) - ENTITY_FIELDS
            if unsupported:
                raise AdapterError(location + " uses unsupported fields: %s" % ", ".join(sorted(unsupported)))
            name = raw.get("name")
            if not isinstance(name, str) or not name:
                raise AdapterError(location + ".name must be a non-empty string")
            if "type" in raw and not isinstance(raw["type"], str):
                raise AdapterError(location + ".type must be a string")
            if "nullable" in raw and not isinstance(raw["nullable"], bool):
                raise AdapterError(location + ".nullable must be boolean")
            entity = {"name": name, "type": raw.get("type"), "nullable": raw.get("nullable", True)}
        else:
            raise AdapterError(location + " must be a string or object")
        if not entity["name"] or entity["name"] in result:
            raise AdapterError("$.entities contains empty or duplicate names")
        result[entity["name"]] = entity
    return result


class DataAdapter(ContractAdapter):
    kind = "data"

    def validate(self, document):
        if not isinstance(document, dict):
            raise AdapterError("data contract must be an object")
        unsupported = set(document) - ROOT_FIELDS
        if unsupported:
            raise AdapterError("data contract uses unsupported fields: %s" % ", ".join(sorted(unsupported)))
        if not isinstance(document.get("writer"), str) or not document["writer"]:
            raise AdapterError("data contract requires one writer")
        _strings(document.get("readers"), "$.readers")
        if not isinstance(document.get("entities"), list):
            raise AdapterError("data contract requires entities")
        _entities(document)
        migration = document.get("migration")
        if not isinstance(migration, dict):
            raise AdapterError("data contract requires migration metadata")
        unsupported_migration = set(migration) - {"phases", "reconciliation", "rollback"}
        if unsupported_migration:
            raise AdapterError("data migration uses unsupported fields: %s" % ", ".join(sorted(unsupported_migration)))
        if migration.get("phases") != PHASES:
            raise AdapterError("data migration phases must be expand/backfill/switch/contract")
        for field in ("reconciliation", "rollback"):
            if not isinstance(migration.get(field), dict) or not migration[field]:
                raise AdapterError("data migration %s metadata is incomplete" % field)
        if "integrity" in document:
            _strings(document["integrity"], "$.integrity")
        return {"kind": self.kind, "valid": True}

    def compare(self, previous, proposed):
        self.validate(previous)
        self.validate(proposed)
        old_entities, new_entities = _entities(previous), _entities(proposed)
        findings = []
        if previous["writer"] != proposed["writer"]:
            findings.append({"path": "$.writer", "kind": "writer-changed", "severity": "breaking"})
        for name in sorted(set(old_entities) - set(new_entities)):
            findings.append({"path": "$.entities." + name, "kind": "entity-removed", "severity": "breaking"})
        for name in sorted(set(new_entities) - set(old_entities)):
            findings.append({"path": "$.entities." + name, "kind": "entity-added", "severity": "additive"})
        for name in sorted(set(old_entities) & set(new_entities)):
            old, new = old_entities[name], new_entities[name]
            if old["type"] != new["type"]:
                findings.append({"path": "$.entities.%s.type" % name, "kind": "entity-type-changed", "severity": "breaking"})
            if old["nullable"] and not new["nullable"]:
                findings.append({"path": "$.entities.%s.nullable" % name, "kind": "nullability-restricted", "severity": "breaking"})
            elif not old["nullable"] and new["nullable"]:
                findings.append({"path": "$.entities.%s.nullable" % name, "kind": "nullability-relaxed", "severity": "additive"})
        for reader in sorted(set(proposed["readers"]) - set(previous["readers"])):
            findings.append({"path": "$.readers." + reader, "kind": "reader-added", "severity": "additive"})
        if previous.get("integrity", []) != proposed.get("integrity", []):
            findings.append({"path": "$.integrity", "kind": "integrity-changed", "severity": "breaking"})
        breaking = any(item["severity"] == "breaking" for item in findings)
        additive = any(item["severity"] == "additive" for item in findings)
        return {"classification": "breaking" if breaking else ("additive" if additive else "unchanged"),
                "compatible": not breaking, "findings": findings}
