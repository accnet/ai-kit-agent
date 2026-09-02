#!/usr/bin/env python3
"""Dependency-free contract fixtures for the Grid-First v2 public schemas."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / ".contracts"
V2_SOURCES = (
    "template.v2.schema.json",
    "block.v2.schema.json",
    "preset.v1.schema.json",
    "builder-preview.v2.schema.json",
)
V1_HASHES = {
    "block-definitions.schema.json": "1148ee9ba9e26f58c73c92835558d07beaf455fef2c25d90ce095ed5e9c49441",
    "block.schema.json": "89f6b9566eddfab4ffd370be1b2c2aadb0037bac04cb991b369dcce8d54dbca7",
    "context.schema.json": "cd593707067b0ed781ca9c364c03179a9ae2e23100d2c90c8ab188a4819ec9d8",
    "display-rule.schema.json": "9cc669cd0ac59ec6a4529fe2daf5f75936e5c3b9f8e696c7fa015ecf43674ba2",
    "section.schema.json": "ab6e00d82b6932fac72f6a50acf2ac27311b3609687785b39c246db2a08a9848",
    "settings.schema.json": "116c7c0df10bc0f7b0d37dd6a4002ebc319575a751b4708bd070f572d6f02e62",
    "surface.schema.json": "f8192ed3974ac75a982be3ed4b77595689d2e94cdd474aa51c4eff14f3be5ef8",
    "template.schema.json": "d455e8aca1e5b603aee2fc9cd15f072d9e97cb250af2cfa0bedaf7e3cf219470",
}


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
            raise ContractError("contract reference escapes .contracts: %s" % name)
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
                self._validate(
                    item,
                    schema["additionalProperties"],
                    current_path,
                    "%s.%s" % (location, key),
                )

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


def report(name, passed, detail=""):
    print(("PASS" if passed else "FAIL") + ": " + name + (" - " + detail if detail else ""))
    return passed


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


def assert_permutation(order, values, location):
    if len(order) != len(values) or set(order) != set(values):
        raise ContractError("%s must exactly permute sibling keys" % location)


def validate_template_invariants(document):
    assert_permutation(document["container_order"], document["containers"], "container_order")
    for container_id, container in document["containers"].items():
        assert_permutation(
            container["column_order"],
            container["columns"],
            "containers.%s.column_order" % container_id,
        )
        for column_id, column in container["columns"].items():
            assert_permutation(
                column["block_order"],
                column["blocks"],
                "containers.%s.columns.%s.block_order" % (container_id, column_id),
            )


def validate_product_profile(document, manifests):
    families = set()
    capability_counts = {}
    for container in document["containers"].values():
        for column in container["columns"].values():
            for block in column["blocks"].values():
                manifest = manifests.get(block["type"])
                if manifest is None:
                    raise ContractError("missing manifest for %s" % block["type"])
                family = manifest.get("compatibility_family")
                if family:
                    families.add(family)
                for capability in manifest.get("capabilities", []):
                    capability_counts[capability] = capability_counts.get(capability, 0) + 1

    if len(families) != 1:
        raise ContractError("Product document must use exactly one compatibility family")
    requirements = {
        "atomic": {"product-gallery", "product-form"},
        "native-compatible": {
            "woo-before-summary",
            "woo-summary",
            "woo-after-summary",
        },
    }
    family = next(iter(families))
    required = requirements[family]
    if any(capability_counts.get(capability) != 1 for capability in required):
        raise ContractError("Product compatibility capabilities must occur exactly once")
    forbidden = set().union(*(items for key, items in requirements.items() if key != family))
    if forbidden.intersection(capability_counts):
        raise ContractError("Product compatibility families cannot be mixed")


def template_fixture(template="product"):
    return {
        "schema": 2,
        "template": template,
        "label": "Product",
        "render_post_content": False,
        "containers": {
            "product_main": {
                "settings": {
                    "width": "boxed",
                    "gap": "medium",
                    "padding_y": "medium",
                    "background": "surface-primary",
                },
                "rules": {},
                "columns": {
                    "media": {
                        "settings": {
                            "span": {"desktop": 7, "tablet": 12, "mobile": 12},
                            "vertical_align": "top",
                        },
                        "blocks": {
                            "gallery_1": {"type": "product-gallery", "settings": {}},
                        },
                        "block_order": ["gallery_1"],
                    },
                    "summary": {
                        "settings": {
                            "span": {"desktop": 5, "tablet": 12, "mobile": 12},
                            "vertical_align": "top",
                        },
                        "blocks": {
                            "title_1": {"type": "product-title", "settings": {}},
                            "form_1": {"type": "buy-buttons", "settings": {}},
                        },
                        "block_order": ["title_1", "form_1"],
                    },
                },
                "column_order": ["media", "summary"],
            }
        },
        "container_order": ["product_main"],
    }


def block_manifests():
    base = {
        "schema": 2,
        "label": "Block",
        "category": "commerce",
        "contexts": ["product"],
        "regions": ["main"],
        "settings": {},
        "assets": {"css": "style.css"},
        "inserter": True,
    }

    def manifest(block_type, capability=None, family=None):
        result = {**base, "type": block_type, "label": block_type.replace("-", " ").title()}
        if capability:
            result["capabilities"] = [capability]
        if family:
            result["compatibility_family"] = family
        return result

    return {
        "product-gallery": manifest("product-gallery", "product-gallery", "atomic"),
        "product-title": manifest("product-title"),
        "buy-buttons": manifest("buy-buttons", "product-form", "atomic"),
        "native-before-summary": manifest(
            "native-before-summary", "woo-before-summary", "native-compatible"
        ),
        "native-summary": manifest("native-summary", "woo-summary", "native-compatible"),
        "native-after-summary": manifest(
            "native-after-summary", "woo-after-summary", "native-compatible"
        ),
    }


def native_product_fixture():
    document = template_fixture()
    media = document["containers"]["product_main"]["columns"]["media"]
    summary = document["containers"]["product_main"]["columns"]["summary"]
    media["blocks"] = {
        "before_1": {"type": "native-before-summary", "settings": {}},
    }
    media["block_order"] = ["before_1"]
    summary["blocks"] = {
        "summary_1": {"type": "native-summary", "settings": {}},
        "after_1": {"type": "native-after-summary", "settings": {}},
    }
    summary["block_order"] = ["summary_1", "after_1"]
    return document


def preset_fixture():
    return {
        "schema": 1,
        "type": "hero-split",
        "label": "Hero split",
        "category": "marketing",
        "contexts": ["index", "page"],
        "regions": ["main"],
        "container": {
            "settings": {"width": "boxed", "gap": "medium", "padding_y": "large"},
            "columns": [
                {
                    "settings": {
                        "span": {"desktop": 7, "tablet": 12, "mobile": 12},
                        "vertical_align": "center",
                    },
                    "blocks": [
                        {"type": "heading", "settings": {"text": "New collection"}},
                        {"type": "button", "settings": {"label": "Shop now"}},
                    ],
                },
                {
                    "settings": {
                        "span": {"desktop": 5, "tablet": 12, "mobile": 12},
                        "vertical_align": "center",
                    },
                    "blocks": [{"type": "image", "settings": {"image": 105}}],
                },
            ],
        },
    }


def preview_documents():
    def empty_document(template):
        return {
            "schema": 2,
            "template": template,
            "containers": {},
            "container_order": [],
        }

    return {
        "header": empty_document("header-group"),
        "page": empty_document("index"),
        "footer": empty_document("footer-group"),
    }


def preview_request():
    return {
        "type": "starterkit-preview-render-request",
        "contractVersion": 2,
        "revision": 4,
        "surface": {"templateId": "index", "context": "index", "resourceId": 0},
        "documents": preview_documents(),
        "parentOrigin": "https://site1.local",
    }


def recursively_contains_identity(value):
    forbidden = {"id", "container_id", "column_id", "block_id", "container_order", "column_order", "block_order"}
    if isinstance(value, dict):
        return bool(forbidden.intersection(value)) or any(recursively_contains_identity(item) for item in value.values())
    if isinstance(value, list):
        return any(recursively_contains_identity(item) for item in value)
    return False


def main():
    results = []

    loaded = {}
    parse_errors = []
    for source in V2_SOURCES:
        try:
            _, loaded[source] = VALIDATOR.load(source)
        except (OSError, json.JSONDecodeError, ContractError) as error:
            parse_errors.append("%s: %s" % (source, error))
    results.append(report("all four v2 contract sources parse", not parse_errors, "; ".join(parse_errors)))

    metadata_errors = []
    expected = {
        "template.v2.schema.json": ("starterkit.template-document@2.0.0", 2, "none", "breaking"),
        "block.v2.schema.json": ("starterkit.block-manifest@2.0.0", 2, "none", "breaking"),
        "preset.v1.schema.json": ("starterkit.container-preset@1.0.0", 1, "new", "additive"),
        "builder-preview.v2.schema.json": ("starterkit.builder-preview@2.0.0", 2, "none", "breaking"),
    }
    for source, schema in loaded.items():
        contract = schema.get("x-starterkit-contract", {})
        contract_id, version, compatibility, change_type = expected[source]
        if contract.get("contractId") != contract_id:
            metadata_errors.append("%s contractId" % source)
        if contract.get("version") != version:
            metadata_errors.append("%s version" % source)
        if contract.get("status") != "draft" or contract.get("sourceHash") != "pending":
            metadata_errors.append("%s approval state" % source)
        if contract.get("compatibility") != compatibility or contract.get("changeType") != change_type:
            metadata_errors.append("%s compatibility" % source)
        for field in ("owner", "writerTask", "producers", "consumers", "rollout", "rollback"):
            if not contract.get(field):
                metadata_errors.append("%s %s" % (source, field))
        if schema.get("additionalProperties") is not False:
            metadata_errors.append("%s open top-level object" % source)
    results.append(report("contract ownership, version, compatibility, rollout, rollback, and draft state are explicit", not metadata_errors, ", ".join(metadata_errors)))

    changed_v1 = []
    for source, expected_hash in V1_HASHES.items():
        path = CONTRACTS / source
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"
        if actual != expected_hash:
            changed_v1.append("%s=%s" % (source, actual))
    results.append(report("all active v1 contract sources remain byte-identical", not changed_v1, "; ".join(changed_v1)))

    atomic = template_fixture()
    valid, detail = expect_valid("template.v2.schema.json", atomic, validate_template_invariants)
    results.append(report("valid Container/Column/Block template and all three permutations pass", valid, detail))

    template_failures = []
    mutations = []
    broken = deepcopy(atomic)
    broken["container_order"] = []
    mutations.append(("container permutation", broken))
    broken = deepcopy(atomic)
    broken["containers"]["product_main"]["column_order"] = ["media", "media"]
    mutations.append(("column permutation", broken))
    broken = deepcopy(atomic)
    broken["containers"]["product_main"]["columns"]["summary"]["block_order"] = ["form_1"]
    mutations.append(("block permutation", broken))
    for span in (0, 13):
        broken = deepcopy(atomic)
        broken["containers"]["product_main"]["columns"]["media"]["settings"]["span"]["desktop"] = span
        mutations.append(("span %d" % span, broken))
    broken = deepcopy(atomic)
    broken["containers"]["product_main"]["columns"]["media"]["unknown"] = True
    mutations.append(("unknown column field", broken))
    broken = deepcopy(atomic)
    broken["containers"]["product_main"]["settings"]["raw_css"] = "position:fixed"
    mutations.append(("raw CSS field", broken))
    for label, fixture in mutations:
        invalid, error = expect_invalid("template.v2.schema.json", fixture, validate_template_invariants)
        if not invalid:
            template_failures.append(label + ": " + error)
    results.append(report("broken permutations, span bounds, and unknown layout fields fail closed", not template_failures, "; ".join(template_failures)))

    manifests = block_manifests()
    block_failures = []
    for block_type, manifest in manifests.items():
        valid, detail = expect_valid("block.v2.schema.json", manifest)
        if not valid:
            block_failures.append("%s: %s" % (block_type, detail))
    for label, mutate in (
        ("unknown context", lambda item: item.update({"contexts": ["blog"]})),
        ("unknown region", lambda item: item.update({"regions": ["sidebar"]})),
        ("legacy placement field", lambda item: item.update({"allowed_sections": ["*"]})),
        ("duplicate context", lambda item: item.update({"contexts": ["product", "product"]})),
    ):
        broken = deepcopy(manifests["buy-buttons"])
        mutate(broken)
        invalid, detail = expect_invalid("block.v2.schema.json", broken)
        if not invalid:
            block_failures.append("%s: %s" % (label, detail))
    results.append(report("Block context/region/capability metadata accepts valid manifests and rejects legacy or unknown placement", not block_failures, "; ".join(block_failures)))

    profile_failures = []
    for label, document in (("atomic", atomic), ("native-compatible", native_product_fixture())):
        try:
            validate_template_invariants(document)
            validate_product_profile(document, manifests)
        except ContractError as error:
            profile_failures.append("valid %s: %s" % (label, error))
    mixed = deepcopy(atomic)
    summary = mixed["containers"]["product_main"]["columns"]["summary"]
    summary["blocks"]["native_1"] = {"type": "native-summary", "settings": {}}
    summary["block_order"].append("native_1")
    duplicate = deepcopy(atomic)
    duplicate_summary = duplicate["containers"]["product_main"]["columns"]["summary"]
    duplicate_summary["blocks"]["form_2"] = {"type": "buy-buttons", "settings": {}}
    duplicate_summary["block_order"].append("form_2")
    incomplete = native_product_fixture()
    incomplete_summary = incomplete["containers"]["product_main"]["columns"]["summary"]
    del incomplete_summary["blocks"]["after_1"]
    incomplete_summary["block_order"].remove("after_1")
    for label, document in (("mixed", mixed), ("duplicate", duplicate), ("incomplete", incomplete)):
        try:
            validate_product_profile(document, manifests)
            profile_failures.append("%s profile unexpectedly accepted" % label)
        except ContractError:
            pass
    results.append(report("atomic/native-compatible Product families are complete, exclusive, and non-duplicated", not profile_failures, "; ".join(profile_failures)))

    preset = preset_fixture()
    valid, detail = expect_valid("preset.v1.schema.json", preset)
    preset_failures = [] if valid and not recursively_contains_identity(preset) else [detail or "preset retained identity"]
    for label, mutate in (
        ("instance id", lambda item: item["container"].update({"id": "hero_1"})),
        ("order array", lambda item: item["container"].update({"column_order": ["left"]})),
        ("invalid span", lambda item: item["container"]["columns"][0]["settings"]["span"].update({"mobile": 13})),
        ("unknown context", lambda item: item.update({"contexts": ["post"]})),
    ):
        broken = deepcopy(preset)
        mutate(broken)
        invalid, error = expect_invalid("preset.v1.schema.json", broken)
        if not invalid:
            preset_failures.append(label + ": " + error)
    results.append(report("creation-only Preset subtree has no IDs/live orders and rejects malformed recipes", not preset_failures, "; ".join(preset_failures)))

    preview_failures = []
    for label, fixture in (
        ("render request", preview_request()),
        (
            "container selection",
            {"type": "starterkit-preview-select", "contractVersion": 2, "revision": 4, "owner": {"group": "page", "containerId": "hero"}},
        ),
        (
            "column selection",
            {"type": "starterkit-preview-select", "contractVersion": 2, "revision": 4, "owner": {"group": "page", "containerId": "hero", "columnId": "left"}},
        ),
        (
            "block edit",
            {"type": "starterkit-preview-edit", "contractVersion": 2, "revision": 4, "owner": {"group": "page", "containerId": "hero", "columnId": "left", "blockId": "title"}, "settingKey": "text", "value": "Hello"},
        ),
        (
            "block move",
            {"type": "starterkit-preview-move-block", "contractVersion": 2, "revision": 4, "owner": {"group": "page", "containerId": "hero", "columnId": "left", "blockId": "title"}, "toColumnId": "right", "toIndex": 0},
        ),
        (
            "typed error",
            {"type": "starterkit-preview-render-error", "contractVersion": 2, "revision": 4, "status": 422, "code": "invalid-contract", "message": "Document rejected"},
        ),
    ):
        valid, detail = expect_valid("builder-preview.v2.schema.json", fixture)
        if not valid:
            preview_failures.append("%s: %s" % (label, detail))
    invalid_preview = []
    broken = preview_request()
    broken["debug"] = True
    invalid_preview.append(("unknown request field", broken))
    invalid_preview.append(("wrong version", {**preview_request(), "contractVersion": 1}))
    invalid_preview.append(
        (
            "block owner missing column",
            {"type": "starterkit-preview-edit", "contractVersion": 2, "revision": 4, "owner": {"group": "page", "containerId": "hero", "blockId": "title"}, "settingKey": "text", "value": "Hello"},
        )
    )
    invalid_preview.append(
        (
            "edit uses container owner",
            {"type": "starterkit-preview-edit", "contractVersion": 2, "revision": 4, "owner": {"group": "page", "containerId": "hero"}, "settingKey": "text", "value": "Hello"},
        )
    )
    invalid_preview.append(
        (
            "unknown owner field",
            {"type": "starterkit-preview-select", "contractVersion": 2, "revision": 4, "owner": {"group": "page", "containerId": "hero", "sectionId": "legacy"}},
        )
    )
    invalid_preview.append(
        (
            "unknown group",
            {"type": "starterkit-preview-select", "contractVersion": 2, "revision": 4, "owner": {"group": "sidebar", "containerId": "hero"}},
        )
    )
    for label, fixture in invalid_preview:
        invalid, detail = expect_invalid("builder-preview.v2.schema.json", fixture)
        if not invalid:
            preview_failures.append("%s: %s" % (label, detail))
    results.append(report("Preview request/response/error and full owner paths pass while malformed/legacy messages fail", not preview_failures, "; ".join(preview_failures)))

    passed = sum(results)
    if passed == len(results):
        print("Grid-First v2 contract tests OK: %d assertions" % passed)
        return 0
    print("Grid-First v2 contract tests FAILED: %d/%d assertions passed" % (passed, len(results)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
