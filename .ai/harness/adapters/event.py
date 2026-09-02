from ..contract_adapters import AdapterError, ContractAdapter
from ..compatibility import CompatibilityError, compare as compare_schema


DIRECTIONS = {"publish", "subscribe"}
ORDERING = {"none", "key", "partition", "global"}
DELIVERY = {"at-most-once", "at-least-once", "exactly-once"}
DUPLICATES = {"allowed", "ignore", "reject", "idempotent"}
EVENT_FIELDS = ("direction", "key", "ordering", "delivery", "replay", "duplicates", "dlq")
CLOUD_EVENT_FIELDS = {"specversion", "id", "source", "type"}
CHANNEL_FIELDS = set(EVENT_FIELDS) | {"message"}
MESSAGE_FIELDS = {"payload", "name", "title", "summary", "description"}


def _schema(channel, location):
    message = channel.get("message")
    if not isinstance(message, dict):
        raise AdapterError(location + ".message must be an object")
    unsupported = set(message) - MESSAGE_FIELDS
    if unsupported:
        raise AdapterError(location + ".message uses unsupported fields: %s" % ", ".join(sorted(unsupported)))
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise AdapterError(location + ".message.payload must be a JSON Schema object")
    return payload


def _prefix(result, prefix):
    return [{**item, "path": prefix + item["path"][1:]} for item in result["findings"]]


class EventAdapter(ContractAdapter):
    kind = "event"

    def validate(self, document):
        if not isinstance(document, dict) or not isinstance(document.get("asyncapi"), str):
            raise AdapterError("event contract requires an AsyncAPI version")
        channels = document.get("channels")
        if not isinstance(channels, dict):
            raise AdapterError("AsyncAPI contract requires channels")
        for name, channel in channels.items():
            location = "$.channels.%s" % name
            if not isinstance(name, str) or not name or not isinstance(channel, dict):
                raise AdapterError("AsyncAPI channel entries must be named objects")
            unsupported = set(channel) - CHANNEL_FIELDS
            if unsupported:
                raise AdapterError(location + " uses unsupported fields: %s" % ", ".join(sorted(unsupported)))
            if not isinstance(channel.get("direction"), str) or channel["direction"] not in DIRECTIONS:
                raise AdapterError(location + ".direction is unsupported")
            if not isinstance(channel.get("key"), str) or not channel["key"]:
                raise AdapterError(location + ".key must be a non-empty string")
            if not isinstance(channel.get("ordering"), str) or channel["ordering"] not in ORDERING:
                raise AdapterError(location + ".ordering is unsupported")
            if not isinstance(channel.get("delivery"), str) or channel["delivery"] not in DELIVERY:
                raise AdapterError(location + ".delivery is unsupported")
            if not isinstance(channel.get("replay"), bool):
                raise AdapterError(location + ".replay must be boolean")
            if not isinstance(channel.get("duplicates"), str) or channel["duplicates"] not in DUPLICATES:
                raise AdapterError(location + ".duplicates is unsupported")
            if not isinstance(channel.get("dlq"), (bool, str)):
                raise AdapterError(location + ".dlq must be boolean or a channel name")
            _schema(channel, location)
        envelope = document.get("cloud_events")
        if envelope is not None:
            if not isinstance(envelope, dict) or envelope.get("specversion") != "1.0":
                raise AdapterError("CloudEvents metadata requires specversion 1.0")
            unsupported = set(envelope) - {"specversion", "required_fields"}
            if unsupported:
                raise AdapterError("CloudEvents metadata uses unsupported fields: %s" % ", ".join(sorted(unsupported)))
            required = envelope.get("required_fields")
            if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
                raise AdapterError("CloudEvents required_fields must be a string array")
            if len(required) != len(set(required)):
                raise AdapterError("CloudEvents required_fields contains duplicates")
            if not CLOUD_EVENT_FIELDS.issubset(required):
                raise AdapterError("CloudEvents required_fields is incomplete")
        return {"kind": self.kind, "valid": True, "cloud_events": envelope is not None}

    def compare(self, previous, proposed):
        self.validate(previous)
        self.validate(proposed)
        old_channels, new_channels = previous["channels"], proposed["channels"]
        findings = []
        for channel in sorted(set(old_channels) - set(new_channels)):
            findings.append({"path": "$.channels." + channel, "kind": "channel-removed", "severity": "breaking"})
        for channel in sorted(set(new_channels) - set(old_channels)):
            findings.append({"path": "$.channels." + channel, "kind": "channel-added", "severity": "additive"})
        for channel in sorted(set(old_channels) & set(new_channels)):
            old, new = old_channels[channel], new_channels[channel]
            prefix = "$.channels." + channel
            for field in EVENT_FIELDS:
                if old[field] != new[field]:
                    findings.append({"path": prefix + "." + field, "kind": field + "-changed", "severity": "breaking"})
            try:
                findings.extend(_prefix(compare_schema(_schema(old, prefix), _schema(new, prefix)), prefix + ".message.payload"))
            except CompatibilityError as exc:
                raise AdapterError(str(exc)) from exc
        if previous.get("cloud_events") != proposed.get("cloud_events"):
            findings.append({"path": "$.cloud_events", "kind": "cloud-events-changed", "severity": "breaking"})
        breaking = any(item["severity"] == "breaking" for item in findings)
        additive = any(item["severity"] == "additive" for item in findings)
        return {"classification": "breaking" if breaking else ("additive" if additive else "unchanged"),
                "compatible": not breaking, "findings": findings}
