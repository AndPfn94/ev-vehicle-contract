# SPDX-License-Identifier: Apache-2.0
"""Offline checks of the paid configuration gate and version isolation."""
import copy
import unittest

import yaml
from jsonschema.exceptions import ValidationError

from conformance import ROOT, check_configuration, check_response, load, validate


class CostConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.legacy = load("examples/config.json")
        self.legacy_provider = load("examples/provider.json")
        self.config = load("examples/config-paid.json")
        self.provider = load("examples/provider-paid.json")

    def test_paid_example_uses_the_same_json_and_yaml_model(self):
        yaml_config = yaml.safe_load((ROOT / "examples/config-paid.yaml").read_bytes())
        self.assertEqual(yaml_config, self.config)
        check_configuration(self.config, [self.provider])

    def test_missing_and_false_opt_in_are_valid_without_a_policy(self):
        for cost_class in ("free", "paid", "unknown"):
            for include_false in (False, True):
                with self.subTest(cost_class=cost_class, include_false=include_false):
                    config = copy.deepcopy(self.config)
                    source = config["sources"][0]
                    del source["cost_policy_ref"]
                    if include_false:
                        source["allow_paid_requests"] = False
                    else:
                        del source["allow_paid_requests"]
                    before = copy.deepcopy(config)
                    check_configuration(config, [self.provider | {"cost_class": cost_class}])
                    self.assertEqual(config, before)

    def test_legacy_and_new_schema_remain_distinct(self):
        check_configuration(self.legacy, [self.legacy_provider])
        legacy = self.legacy["sources"][0]
        for patch in ({"allow_paid_requests": True}, {"cost_policy_ref": "policy-a"}):
            with self.subTest(patch=patch), self.assertRaises(ValidationError):
                config = self.legacy | {"sources": [legacy | patch]}
                check_configuration(config, [self.legacy_provider])
        with self.assertRaises(ValidationError):
            validate(self.config, "config", "provider.schema.json")
        with self.assertRaises(ValidationError):
            validate(self.legacy, "config", "provider-config.schema.json")
        with self.assertRaises(ValidationError):
            check_configuration(self.config | {"schema_version": "1.2"}, [self.provider])

    def test_paid_opt_in_requires_a_valid_policy_reference(self):
        config = copy.deepcopy(self.config)
        source = config["sources"][0]
        del source["cost_policy_ref"]
        with self.assertRaises(ValidationError):
            check_configuration(config, [self.provider])
        for reference in (None, "", 0, "a" * 65, "/private/policy", "../policy", "policy\n"):
            with self.subTest(reference=reference), self.assertRaises(ValidationError):
                source["cost_policy_ref"] = reference
                check_configuration(config, [self.provider])

    def test_policy_reference_requires_an_explicit_boolean_true(self):
        config = copy.deepcopy(self.config)
        source = config["sources"][0]
        del source["allow_paid_requests"]
        with self.assertRaises(ValidationError):
            check_configuration(config, [self.provider])
        for flag in (False, "true", 1, None):
            with self.subTest(flag=flag), self.assertRaises(ValidationError):
                source["allow_paid_requests"] = flag
                check_configuration(config, [self.provider])

    def test_opt_in_requires_paid_classification_from_matching_metadata(self):
        for cost_class in ("free", "unknown"):
            with self.subTest(cost_class=cost_class), self.assertRaisesRegex(ValueError, "cost_class paid"):
                check_configuration(self.config, [self.provider | {"cost_class": cost_class}])

    def test_existing_source_constraints_and_private_policy_boundary(self):
        source = self.config["sources"][0]
        for patch, error in (
            ({"poll_interval_s": 60}, ValueError),
            ({"settings": source["settings"] | {"cost_policy_ref": "policy-a"}}, ValueError),
            ({"budget": 200}, ValidationError),
            ({"tariff": 5}, ValidationError),
            ({"account_owner_consent": True}, ValidationError),
        ):
            with self.subTest(patch=patch), self.assertRaises(error):
                check_configuration(self.config | {"sources": [source | patch]}, [self.provider])

    def test_wire_rejects_configuration_version_and_cost_policy_data(self):
        request = load("examples/request.json")
        response = load("examples/real.json")
        check_response(response, request)
        with self.assertRaises(ValidationError):
            check_response(response, request | {"contract_version": "1.1"})
        with self.assertRaises(ValidationError):
            check_response(response, request | {"cost_policy_ref": "policy-a"})
        with self.assertRaises(ValidationError):
            check_response(response | {"cost_policy_ref": "policy-a"}, request)
