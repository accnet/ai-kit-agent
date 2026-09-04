from ..contract_adapters import ContractAdapter, AdapterError
from ..compatibility import compare

class JsonSchemaAdapter(ContractAdapter):
    kind = "schema"
    def validate(self, document):
        if not isinstance(document, dict) or ("type" not in document and "$ref" not in document):
            raise AdapterError("JSON Schema requires type or $ref")
        return {"kind": self.kind, "valid": True}
    def compare(self, previous, proposed): return compare(previous, proposed)
