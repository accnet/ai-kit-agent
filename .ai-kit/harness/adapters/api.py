from ..contract_adapters import ContractAdapter, AdapterError
from ..compatibility import CompatibilityError, compare as compare_schema

METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}
ROOT_FIELDS = {"openapi", "info", "paths", "components", "security", "tags", "externalDocs"}
PATH_FIELDS = {"summary", "description"}
OPERATION_FIELDS = {"summary", "description", "operationId", "tags", "security",
                    "x-idempotency-key", "requestBody", "responses", "deprecated"}
COMPONENT_FIELDS = {"schemas", "securitySchemes"}


def _schema(container, path, allowed_fields=None):
    if container is None:
        return None
    if not isinstance(container, dict):
        raise AdapterError("%s must be an object" % path)
    allowed_fields = allowed_fields or {"content", "description"}
    unsupported_container = set(container) - allowed_fields
    if unsupported_container:
        raise AdapterError("%s uses unsupported fields: %s" % (path, ", ".join(sorted(unsupported_container))))
    content = container.get("content", {})
    if not isinstance(content, dict):
        raise AdapterError("%s.content must be an object" % path)
    unsupported = set(content) - {"application/json"}
    if unsupported:
        raise AdapterError("%s uses unsupported media types: %s" % (path, ", ".join(sorted(unsupported))))
    media = content.get("application/json")
    if media is None:
        return None
    if not isinstance(media, dict) or not isinstance(media.get("schema"), dict):
        raise AdapterError("%s.content.application/json.schema must be an object" % path)
    return media["schema"]


def _validated_schema(schema, path):
    if schema is None:
        return None
    try:
        compare_schema(schema, schema)
    except CompatibilityError as exc:
        raise AdapterError("%s: %s" % (path, exc)) from exc
    return schema


def _components(document):
    components = document.get("components", {})
    if not isinstance(components, dict):
        raise AdapterError("$.components must be an object")
    unsupported = set(components) - COMPONENT_FIELDS
    if unsupported:
        raise AdapterError("unsupported OpenAPI components: %s" % ", ".join(sorted(unsupported)))
    schemas = components.get("schemas", {})
    schemes = components.get("securitySchemes", {})
    if not isinstance(schemas, dict) or not isinstance(schemes, dict):
        raise AdapterError("OpenAPI component schemas and securitySchemes must be objects")
    if any(not isinstance(name, str) or not isinstance(value, dict) for name, value in schemas.items()):
        raise AdapterError("OpenAPI component schemas must be named objects")
    if any(not isinstance(name, str) or not isinstance(value, dict) for name, value in schemes.items()):
        raise AdapterError("OpenAPI security schemes must be named objects")
    for name, schema in schemas.items():
        _validated_schema(schema, "$.components.schemas." + name)
    return schemas, schemes


def _prefix(result, prefix):
    return [{**item, "path": prefix + item["path"][1:]} for item in result["findings"]]


class ApiAdapter(ContractAdapter):
    kind = "api"

    def validate(self, document):
        if not isinstance(document, dict) or not isinstance(document.get("openapi"), str):
            raise AdapterError("OpenAPI contract requires an openapi version")
        unsupported_root = set(document) - ROOT_FIELDS
        if unsupported_root:
            raise AdapterError("unsupported OpenAPI root fields: %s" % ", ".join(sorted(unsupported_root)))
        if "security" in document and not isinstance(document["security"], list):
            raise AdapterError("$.security must be an array")
        _components(document)
        paths = document.get("paths")
        if not isinstance(paths, dict):
            raise AdapterError("OpenAPI contract requires paths")
        for path, path_item in paths.items():
            if not isinstance(path, str) or not path.startswith("/") or not isinstance(path_item, dict):
                raise AdapterError("OpenAPI path entries must be /-prefixed objects")
            unsupported = set(path_item) - METHODS - PATH_FIELDS
            if unsupported:
                raise AdapterError("unsupported OpenAPI path fields at $.paths.%s: %s" % (path, ", ".join(sorted(unsupported))))
            for method, operation in ((key, value) for key, value in path_item.items() if key in METHODS):
                location = "$.paths.%s.%s" % (path, method)
                if not isinstance(operation, dict):
                    raise AdapterError("%s must be an object" % location)
                unsupported_operation = set(operation) - OPERATION_FIELDS
                if unsupported_operation:
                    raise AdapterError("unsupported OpenAPI operation fields at %s: %s" % (location, ", ".join(sorted(unsupported_operation))))
                if "security" in operation and not isinstance(operation["security"], list):
                    raise AdapterError("%s.security must be an array" % location)
                if "x-idempotency-key" in operation and not isinstance(operation["x-idempotency-key"], str):
                    raise AdapterError("%s.x-idempotency-key must be a string" % location)
                if "deprecated" in operation and not isinstance(operation["deprecated"], bool):
                    raise AdapterError("%s.deprecated must be boolean" % location)
                request_body = operation.get("requestBody")
                if "requestBody" in operation and not isinstance(request_body, dict):
                    raise AdapterError("%s.requestBody must be an object" % location)
                if isinstance(request_body, dict) and "required" in request_body and not isinstance(request_body["required"], bool):
                    raise AdapterError("%s.requestBody.required must be boolean" % location)
                _validated_schema(_schema(request_body, location + ".requestBody", {"content", "description", "required"}), location + ".requestBody")
                responses = operation.get("responses", {})
                if not isinstance(responses, dict):
                    raise AdapterError("%s.responses must be an object" % location)
                for status, response in responses.items():
                    if not isinstance(status, str):
                        raise AdapterError("%s response status keys must be strings" % location)
                    if not isinstance(response, dict):
                        raise AdapterError("%s.responses.%s must be an object" % (location, status))
                    _validated_schema(_schema(response, location + ".responses.%s" % status), location + ".responses.%s" % status)
        return {"kind": self.kind, "valid": True}

    def compare(self, previous, proposed):
        self.validate(previous)
        self.validate(proposed)
        old_paths, new_paths = previous["paths"], proposed["paths"]
        findings = []
        if previous.get("security", []) != proposed.get("security", []):
            findings.append({"path": "$.security", "kind": "security-changed", "severity": "breaking"})
        old_schemas, old_schemes = _components(previous)
        new_schemas, new_schemes = _components(proposed)
        for name in sorted(set(old_schemes) - set(new_schemes)):
            findings.append({"path": "$.components.securitySchemes." + name, "kind": "security-scheme-removed", "severity": "breaking"})
        for name in sorted(set(new_schemes) - set(old_schemes)):
            findings.append({"path": "$.components.securitySchemes." + name, "kind": "security-scheme-added", "severity": "additive"})
        for name in sorted(set(old_schemes) & set(new_schemes)):
            if old_schemes[name] != new_schemes[name]:
                findings.append({"path": "$.components.securitySchemes." + name, "kind": "security-scheme-changed", "severity": "breaking"})
        for name in sorted(set(old_schemas) - set(new_schemas)):
            findings.append({"path": "$.components.schemas." + name, "kind": "component-schema-removed", "severity": "breaking"})
        for name in sorted(set(new_schemas) - set(old_schemas)):
            findings.append({"path": "$.components.schemas." + name, "kind": "component-schema-added", "severity": "additive"})
        for name in sorted(set(old_schemas) & set(new_schemas)):
            try:
                findings.extend(_prefix(compare_schema(old_schemas[name], new_schemas[name]), "$.components.schemas." + name))
            except CompatibilityError as exc:
                raise AdapterError(str(exc)) from exc
        for path in sorted(set(old_paths) - set(new_paths)):
            findings.append({"path": "$.paths." + path, "kind": "endpoint-removed", "severity": "breaking"})
        for path in sorted(set(new_paths) - set(old_paths)):
            findings.append({"path": "$.paths." + path, "kind": "endpoint-added", "severity": "additive"})
        for path in sorted(set(old_paths) & set(new_paths)):
            old_item, new_item = old_paths[path], new_paths[path]
            old_methods, new_methods = set(old_item) & METHODS, set(new_item) & METHODS
            for method in sorted(old_methods - new_methods):
                findings.append({"path": "$.paths.%s.%s" % (path, method), "kind": "method-removed", "severity": "breaking"})
            for method in sorted(new_methods - old_methods):
                findings.append({"path": "$.paths.%s.%s" % (path, method), "kind": "method-added", "severity": "additive"})
            for method in sorted(old_methods & new_methods):
                prefix = "$.paths.%s.%s" % (path, method)
                old_op, new_op = old_item[method], new_item[method]
                for field in ("security", "x-idempotency-key", "operationId"):
                    if old_op.get(field) != new_op.get(field):
                        findings.append({"path": prefix + "." + field, "kind": field + "-changed", "severity": "breaking"})
                old_request = _schema(old_op.get("requestBody"), prefix + ".requestBody", {"content", "description", "required"})
                new_request = _schema(new_op.get("requestBody"), prefix + ".requestBody", {"content", "description", "required"})
                old_required = (old_op.get("requestBody") or {}).get("required", False)
                new_required = (new_op.get("requestBody") or {}).get("required", False)
                if old_required != new_required:
                    findings.append({"path": prefix + ".requestBody.required", "kind": "request-required-changed",
                                     "severity": "breaking" if new_required else "additive"})
                if old_request is None and new_request is not None:
                    findings.append({"path": prefix + ".requestBody", "kind": "request-added", "severity": "breaking"})
                elif old_request is not None and new_request is None:
                    findings.append({"path": prefix + ".requestBody", "kind": "request-removed", "severity": "additive"})
                elif old_request is not None:
                    try:
                        findings.extend(_prefix(compare_schema(old_request, new_request), prefix + ".requestBody.schema"))
                    except CompatibilityError as exc:
                        raise AdapterError(str(exc)) from exc
                if old_op.get("deprecated", False) != new_op.get("deprecated", False):
                    findings.append({"path": prefix + ".deprecated", "kind": "deprecation-changed", "severity": "additive"})
                old_responses, new_responses = old_op.get("responses", {}), new_op.get("responses", {})
                for status in sorted(set(old_responses) - set(new_responses)):
                    findings.append({"path": prefix + ".responses." + status, "kind": "response-removed", "severity": "breaking"})
                for status in sorted(set(new_responses) - set(old_responses)):
                    findings.append({"path": prefix + ".responses." + status, "kind": "response-added", "severity": "additive"})
                for status in sorted(set(old_responses) & set(new_responses)):
                    old_schema = _schema(old_responses[status], prefix + ".responses." + status)
                    new_schema = _schema(new_responses[status], prefix + ".responses." + status)
                    if old_schema is not None and new_schema is None:
                        findings.append({"path": prefix + ".responses." + status, "kind": "response-schema-removed", "severity": "breaking"})
                    elif old_schema is None and new_schema is not None:
                        findings.append({"path": prefix + ".responses." + status, "kind": "response-schema-added", "severity": "additive"})
                    elif old_schema is not None:
                        try:
                            findings.extend(_prefix(compare_schema(old_schema, new_schema), prefix + ".responses." + status + ".schema"))
                        except CompatibilityError as exc:
                            raise AdapterError(str(exc)) from exc
        breaking = any(item["severity"] == "breaking" for item in findings)
        additive = any(item["severity"] == "additive" for item in findings)
        return {"classification": "breaking" if breaking else ("additive" if additive else "unchanged"),
                "compatible": not breaking, "findings": findings}
