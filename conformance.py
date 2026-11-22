# SPDX-License-Identifier: Apache-2.0
# Modified for provider configuration 1.1 in package 1.1.0-rc.1.
"""Portable Vehicle Data Contract checks. Requires jsonschema>=4.18,<5."""
import argparse
import json
from datetime import datetime
from math import isfinite
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
FORMATS = FormatChecker()


@FORMATS.checks("date-time")
def valid_datetime(value):
    if not isinstance(value, str):
        return True
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def decode_frame(frame, maximum):
    if len(frame) > maximum or not frame.endswith(b"\n") or b"\n" in frame[:-1]:
        raise ValueError("invalid frame boundary")
    return decode_json(frame, maximum)


def decode_json(data, maximum):
    if len(data) > maximum:
        raise ValueError("JSON size limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("non-JSON number")

    def finite_number(value):
        parsed = float(value)
        if not isfinite(parsed):
            raise ValueError("non-finite number")
        return parsed

    return json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=reject_constant, parse_float=finite_number)


def validate(value, definition, schema_file="vehicle-data.schema.json"):
    schema = load(schema_file)
    Draft202012Validator.check_schema(schema)
    selected = {"$ref": "#/$defs/" + definition, "$defs": schema["$defs"]}
    Draft202012Validator(selected, format_checker=FORMATS).validate(value)


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def check_response(response, request):
    validate(request, "request")
    validate(response, "response")
    if response["request_id"] != request["request_id"]:
        raise ValueError("request identity mismatch")
    entries = response["vehicles"]
    aliases = [entry["vehicle"] for entry in entries]
    if len(set(aliases)) != len(aliases) or set(aliases) != set(request["vehicles"]):
        raise ValueError("vehicle identity mismatch")
    generated = instant(response["generated_at"])
    for entry in entries:
        sample, received = entry["sample"], entry["received_at"]
        if (sample is None) != (received is None):
            raise ValueError("sample requires its reception time")
        if received is not None and instant(received) > generated:
            raise ValueError("future reception time")
        if sample is not None:
            if len(json.dumps(sample).encode("utf-8")) > 8192:
                raise ValueError("sample size")
            if sample["vehicle"] != entry["vehicle"] or sample["quality"] == "simulated":
                raise ValueError("unqualified sample identity")
            if instant(sample["measured_at"]) > instant(received):
                raise ValueError("future measurement time")
            if entry["status"] == "ok":
                if sample["quality"] != "valid":
                    raise ValueError("ok requires a real sample")
            elif sample["quality"] != "stale":
                raise ValueError("retained sample must be stale")
        elif entry["status"] in ("ok", "stale"):
            raise ValueError("missing sample")
        if entry["estimate"] is not None:
            if instant(entry["estimate"]["calculated_at"]) > generated:
                raise ValueError("future estimate")
    encoded = json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) + 1 > 131072:
        raise ValueError("response size")


def check_configuration(config, providers):
    schema_file = "provider.schema.json"
    if isinstance(config, dict) and config.get("schema_version") == "1.1":
        schema_file = "provider-config.schema.json"
    validate(config, "config", schema_file)
    indexed = {}
    for provider in providers:
        validate(provider, "provider", "provider.schema.json")
        key = (provider["provider_id"], provider["provider_version"])
        if key in indexed:
            raise ValueError("duplicate provider")
        indexed[key] = provider
    source_ids, vehicles = set(), set()
    for source in config["sources"]:
        if source["id"] in source_ids or vehicles.intersection(source["vehicles"]):
            raise ValueError("duplicate source or vehicle")
        source_ids.add(source["id"])
        vehicles.update(source["vehicles"])
        if len(vehicles) > 12:
            raise ValueError("vehicle limit")
        provider = indexed[(source["provider_id"], source["provider_version"])]
        if source.get("allow_paid_requests", False) and provider["cost_class"] != "paid":
            raise ValueError("paid requests require a provider with cost_class paid")
        if source["poll_interval_s"] < provider["minimum_poll_interval_s"]:
            raise ValueError("provider cooldown")
        fields = {field["key"]: field for field in provider["fields"]}
        if len(fields) != len(provider["fields"]):
            raise ValueError("duplicate field")
        settings = source["settings"]
        if settings.keys() - fields.keys():
            raise ValueError("unknown configuration key")
        for key, field in fields.items():
            if key not in settings:
                if field["required"]:
                    raise ValueError("missing required field")
                continue
            value, kind = settings[key], field["kind"]
            expected = {"text": str, "secret_ref": str, "select": str,
                        "boolean": bool, "integer": int, "number": (int, float)}[kind]
            if not isinstance(value, expected) or (kind in ("integer", "number") and isinstance(value, bool)):
                raise ValueError("field type")
            if isinstance(value, str) and not 1 <= len(value) <= 500:
                raise ValueError("field length")
            if kind == "select" and value not in field.get("choices", []):
                raise ValueError("unknown choice")
            if kind == "secret_ref":
                import re
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value) is None:
                    raise ValueError("secret reference")
            if kind in ("integer", "number"):
                if value < field.get("minimum", -float("inf")) or value > field.get("maximum", float("inf")):
                    raise ValueError("field range")
    parts = Path(config["socket_path"]).parts
    if ".." in parts or "." in config["socket_path"].split("/"):
        raise ValueError("socket traversal")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    args = parser.parse_args()
    check_response(decode_json(args.response.read_bytes(), 131072),
                   decode_json(args.request.read_bytes(), 8192))
    print("Vehicle Data Contract 1.0 PASS")


if __name__ == "__main__":
    main()
