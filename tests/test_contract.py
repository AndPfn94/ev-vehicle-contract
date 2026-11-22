# SPDX-License-Identifier: Apache-2.0
"""Portable examples and adversarial conformance vectors."""
import copy
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator

from conformance import ROOT, check_configuration, check_response, decode_frame, load, validate


class ContractTests(unittest.TestCase):
    def test_cli_accepts_documented_pretty_printed_examples(self):
        completed = subprocess.run(
            [sys.executable, "-B", str(ROOT / "conformance.py"),
             "--request", str(ROOT / "examples/request.json"),
             "--response", str(ROOT / "examples/real.json")],
            check=True, capture_output=True, text=True,
        )
        self.assertIn("Vehicle Data Contract 1.0 PASS", completed.stdout)

    def test_schema_roots_reject_arbitrary_objects(self):
        for name in ("vehicle-data.schema.json", "provider.schema.json"):
            validator = Draft202012Validator(load(name))
            self.assertFalse(validator.is_valid({"command": "start"}))
            self.assertFalse(validator.is_valid({}))

    def test_framing_and_duplicate_keys(self):
        self.assertEqual(decode_frame(b'{"ok":true}\n', 8192), {"ok": True})
        for frame in (b'{}', b'{}\n{}\n', b'{"x":1,"x":2}\n',
                      b'{"soc":NaN}\n', b'{"soc":1e999}\n',
                      b'\xff\n', b'{}\n' + b' ' * 8192):
            with self.subTest(frame=frame[:40]), self.assertRaises(Exception):
                decode_frame(frame, 8192)

    def test_examples(self):
        for name in ("real", "estimated", "stale", "offline", "multiple"):
            with self.subTest(name=name):
                response = load("examples/" + name + ".json")
                request = load("examples/request.json")
                request["vehicles"] = [entry["vehicle"] for entry in response["vehicles"]]
                check_response(response, request)

    def test_invalid_samples(self):
        base = load("examples/real.json")["vehicles"][0]["sample"]
        for patch in ({"soc": 64}, {"soc": True}, {"soc": -0.1},
                      {"measured_at": "2026-02-30T10:00:00Z"},
                      {"measured_at": "2026-11-22T10:00:00+00:00"},
                      {"quality": "estimated"}, {"start": True},
                      {"vehicle": "private id"}, {"version": 2}):
            with self.subTest(patch=patch), self.assertRaises(Exception):
                validate(base | patch, "sample")

    def test_invalid_envelopes(self):
        original = load("examples/real.json")
        request = load("examples/request.json")
        mutations = [
            lambda r: r.update(request_id="other"),
            lambda r: r["vehicles"].append(copy.deepcopy(r["vehicles"][0])),
            lambda r: r["vehicles"][0].update(vehicle="wrong"),
            lambda r: r["vehicles"][0]["sample"].update(vehicle="wrong"),
            lambda r: r["vehicles"][0].update(status="offline"),
            lambda r: r["vehicles"][0]["sample"].update(quality="simulated"),
            lambda r: r["vehicles"][0]["sample"].update(measured_at="2026-11-22T11:00:00Z"),
            lambda r: r["vehicles"][0].update(received_at=None),
        ]
        for mutate in mutations:
            response = copy.deepcopy(original)
            mutate(response)
            with self.subTest(mutate=mutate), self.assertRaises(Exception):
                check_response(response, request)

    def test_configuration_and_rejections(self):
        config, provider = load("examples/config.json"), load("examples/provider.json")
        check_configuration(config, [provider])
        for patch in ({"poll_interval_s": 60}, {"allow_paid_requests": True},
                      {"settings": {"credential": "/etc/private", "account": "local"}},
                      {"settings": {"credential": "credential-a", "account": "local", "command": "run"}},
                      {"settings": {"account": "local"}}):
            value = copy.deepcopy(config)
            value["sources"][0].update(patch)
            with self.subTest(patch=patch), self.assertRaises(Exception):
                check_configuration(value, [provider])


if __name__ == "__main__":
    unittest.main()
