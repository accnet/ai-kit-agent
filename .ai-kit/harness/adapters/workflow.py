from ..contract_adapters import AdapterError, ContractAdapter


SEMANTIC_FIELDS = ("source_of_truth", "timeout", "retry", "idempotency", "compensation")
ROOT_FIELDS = {"states", "terminal_states", "transitions"} | set(SEMANTIC_FIELDS)


def _states(document):
    states = document.get("states")
    if not isinstance(states, list) or not states or any(not isinstance(item, str) or not item for item in states):
        raise AdapterError("workflow states must be a non-empty string array")
    if len(states) != len(set(states)):
        raise AdapterError("workflow states contain duplicates")
    return set(states)


def _transition_set(document, states):
    transitions = document.get("transitions")
    if not isinstance(transitions, list):
        raise AdapterError("workflow transitions must be an array")
    result = set()
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            raise AdapterError("$.transitions[%d] must be an object" % index)
        unsupported = set(transition) - {"from", "to"}
        if unsupported:
            raise AdapterError("$.transitions[%d] uses unsupported fields: %s" % (index, ", ".join(sorted(unsupported))))
        source, target = transition.get("from"), transition.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            raise AdapterError("workflow transition states must be strings")
        if source not in states or target not in states:
            raise AdapterError("workflow transition references unknown state")
        edge = (source, target)
        if edge in result:
            raise AdapterError("workflow transitions contain duplicates")
        result.add(edge)
    return result


class WorkflowAdapter(ContractAdapter):
    kind = "workflow"

    def validate(self, document):
        if not isinstance(document, dict):
            raise AdapterError("workflow contract must be an object")
        unsupported = set(document) - ROOT_FIELDS
        if unsupported:
            raise AdapterError("workflow contract uses unsupported fields: %s" % ", ".join(sorted(unsupported)))
        states = _states(document)
        _transition_set(document, states)
        terminal = document.get("terminal_states")
        if (not isinstance(terminal, list) or not terminal
                or any(not isinstance(item, str) or item not in states for item in terminal)):
            raise AdapterError("workflow terminal_states must reference known states")
        if len(terminal) != len(set(terminal)):
            raise AdapterError("workflow terminal_states contain duplicates")
        if not isinstance(document.get("source_of_truth"), str) or not document["source_of_truth"]:
            raise AdapterError("workflow source_of_truth must be a non-empty string")
        for field in ("timeout", "retry", "idempotency", "compensation"):
            if not isinstance(document.get(field), dict) or not document[field]:
                raise AdapterError("workflow %s metadata is incomplete" % field)
        return {"kind": self.kind, "valid": True}

    def compare(self, previous, proposed):
        self.validate(previous)
        self.validate(proposed)
        old_states, new_states = _states(previous), _states(proposed)
        old_edges = _transition_set(previous, old_states)
        new_edges = _transition_set(proposed, new_states)
        findings = []
        for state in sorted(old_states - new_states):
            findings.append({"path": "$.states." + state, "kind": "state-removed", "severity": "breaking"})
        for state in sorted(new_states - old_states):
            findings.append({"path": "$.states." + state, "kind": "state-added", "severity": "additive"})
        for edge in sorted(old_edges - new_edges):
            findings.append({"path": "$.transitions.%s->%s" % edge, "kind": "transition-removed", "severity": "breaking"})
        for edge in sorted(new_edges - old_edges):
            findings.append({"path": "$.transitions.%s->%s" % edge, "kind": "transition-added", "severity": "additive"})
        if set(previous["terminal_states"]) != set(proposed["terminal_states"]):
            findings.append({"path": "$.terminal_states", "kind": "terminal-states-changed", "severity": "breaking"})
        for field in SEMANTIC_FIELDS:
            if previous[field] != proposed[field]:
                findings.append({"path": "$." + field, "kind": field + "-changed", "severity": "breaking"})
        breaking = any(item["severity"] == "breaking" for item in findings)
        additive = any(item["severity"] == "additive" for item in findings)
        return {"classification": "breaking" if breaking else ("additive" if additive else "unchanged"),
                "compatible": not breaking, "findings": findings}
