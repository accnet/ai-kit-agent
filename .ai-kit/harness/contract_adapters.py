"""Common adapter contract for project-owned contract kinds."""
from __future__ import annotations
from typing import Any, Dict

class AdapterError(ValueError): pass

class ContractAdapter:
    kind = "unknown"
    def validate(self, document: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(document, dict): raise AdapterError("contract document must be an object")
        return {"kind": self.kind, "valid": True}
    def compare(self, previous: Dict[str, Any], proposed: Dict[str, Any]) -> Dict[str, Any]:
        return {"classification": "unchanged", "compatible": True, "findings": []}

    def analyze(self, previous: Dict[str, Any], proposed: Dict[str, Any]) -> Dict[str, Any]:
        """Validate both documents and return deterministic compatibility evidence."""
        self.validate(previous); self.validate(proposed)
        result = self.compare(previous, proposed)
        result["adapter"] = self.__class__.__name__
        result["verification"] = {"network": False, "writes": False}
        return result
