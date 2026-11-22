# SPDX-License-Identifier: Apache-2.0
# Modified for provider configuration 1.1 in package 1.1.0-rc.1.
"""Integrated, offline schema and configuration checks."""
import copy
import unittest

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from conformance import FORMATS, ROOT, check_configuration, load


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.schemas = {
            name: load(name)
            for name in ("vehicle-data.schema.json", "provider.schema.json",
                         "provider-config.schema.json")
        }
        self.registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema))
            for schema in self.schemas.values()
        )

    def test_absolute_schema_references_resolve_offline(self):
        cases = [
            ("vehicle-data.schema.json", "request", "request"),
            ("provider.schema.json", "provider", "provider"),
            ("provider.schema.json", "config", "config"),
            ("provider-config.schema.json", "config", "config-paid"),
        ]
        for schema_file, definition, example in cases:
            reference = self.schemas[schema_file]["$id"] + "#/$defs/" + definition
            validator = Draft202012Validator(
                {"$ref": reference}, registry=self.registry, format_checker=FORMATS
            )
            validator.validate(load("examples/" + example + ".json"))

    def test_every_schema_reference_has_a_local_target(self):
        for schema in self.schemas.values():
            pending = [schema]
            while pending:
                node = pending.pop()
                if isinstance(node, dict):
                    if "$ref" in node:
                        target = schema
                        reference = node["$ref"]
                        self.assertTrue(reference.startswith("#/"))
                        for token in reference[2:].split("/"):
                            target = target[token.replace("~1", "/").replace("~0", "~")]
                    pending.extend(node.values())
                elif isinstance(node, list):
                    pending.extend(node)

    def test_all_example_documents_validate_at_schema_root(self):
        configuration_examples = {
            "provider": "provider.schema.json",
            "provider-paid": "provider.schema.json",
            "config": "provider.schema.json",
            "config-paid": "provider-config.schema.json",
        }
        for path in (ROOT / "examples").glob("*.json"):
            with self.subTest(example=path.name):
                schema_file = configuration_examples.get(path.stem, "vehicle-data.schema.json")
                Draft202012Validator(
                    self.schemas[schema_file], format_checker=FORMATS
                ).validate(load("examples/" + path.name))

    def test_yaml_and_json_configuration_are_identical(self):
        text = (ROOT / "examples/config.yaml").read_text(encoding="utf-8")
        yaml_config = yaml.safe_load(text)
        self.assertEqual(yaml_config, load("examples/config.json"))
        check_configuration(yaml_config, [load("examples/provider.json")])

    def test_neutral_source_categories_use_the_same_configuration_path(self):
        original = load("examples/provider.json")
        for category in ("manufacturer", "integration"):
            provider = copy.deepcopy(original)
            provider["source_kind"] = category
            check_configuration(load("examples/config.json"), [provider])
        provider = copy.deepcopy(original)
        provider["source_kind"] = "unsupported"
        with self.assertRaises(Exception):
            check_configuration(load("examples/config.json"), [provider])

    def test_version_and_license_artifacts(self):
        self.assertEqual((ROOT / "VERSION").read_text().strip(), "1.1.0-rc.1")
        self.assertIn("Apache License", (ROOT / "LICENSE").read_text())
        self.assertIn("Publisher: AndPfn94", (ROOT / "NOTICE").read_text())
        self.assertNotIn("Copyright 2026", (ROOT / "NOTICE").read_text())


if __name__ == "__main__":
    unittest.main()
