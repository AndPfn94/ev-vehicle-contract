# SPDX-License-Identifier: Apache-2.0
"""Separate service and Client fixtures communicating through real Unix sockets."""
import copy
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from conformance import check_response, load


class CachedService:
    """Test service implemented independently from the reference frame parser."""

    def __init__(self, address, connections=1, wire=None, fragmented=False):
        self.address = address
        self.connections = connections
        self.wire = wire
        self.fragmented = fragmented
        self.ready = threading.Event()
        self.failure = None
        self.cache = {
            entry["vehicle"]: entry for entry in load("examples/multiple.json")["vehicles"]
        }
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        if not self.ready.wait(4):
            raise RuntimeError("service startup deadline")
        if self.failure:
            raise self.failure
        return self

    def __exit__(self, *_):
        self.thread.join(4)
        if self.thread.is_alive():
            raise RuntimeError("service did not terminate")
        if self.failure:
            raise self.failure

    def serve(self):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.settimeout(3)
                listener.bind(self.address)
                listener.listen()
                self.ready.set()
                for _ in range(self.connections):
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(2)
                        request = self.read_request(connection)
                        if request is None:
                            continue
                        wire = self.wire
                        if wire is None:
                            entries = []
                            for alias in request["vehicles"]:
                                entry = self.cache.get(alias)
                                if entry is None:
                                    entry = {
                                        "vehicle": alias, "received_at": None,
                                        "status": "unknown_vehicle", "retry_after_s": None,
                                        "sample": None, "estimate": None,
                                    }
                                entries.append(copy.deepcopy(entry))
                            response = {
                                "contract_version": "1.0",
                                "request_id": request["request_id"],
                                "generated_at": "2026-11-22T10:00:02Z",
                                "vehicles": entries,
                            }
                            wire = json.dumps(response, separators=(",", ":")).encode() + b"\n"
                        try:
                            if self.fragmented:
                                for offset in range(0, len(wire), 7):
                                    connection.sendall(wire[offset:offset + 7])
                            else:
                                connection.sendall(wire)
                        except (BrokenPipeError, ConnectionResetError):
                            pass
        except Exception as error:
            self.failure = error
            self.ready.set()
        finally:
            Path(self.address).unlink(missing_ok=True)

    @staticmethod
    def read_request(connection):
        frame = bytearray()
        try:
            while b"\n" not in frame:
                chunk = connection.recv(1024)
                if not chunk:
                    return None
                frame.extend(chunk)
                if len(frame) > 8192:
                    return None
            if frame[-1:] != b"\n" or frame.count(b"\n") != 1:
                return None

            def unique(pairs):
                document = {}
                for key, value in pairs:
                    if key in document:
                        raise ValueError("duplicate request key")
                    document[key] = value
                return document

            request = json.loads(frame.decode("utf-8"), object_pairs_hook=unique)
            if set(request) != {"contract_version", "operation", "request_id", "vehicles"}:
                return None
            if request["contract_version"] != "1.0" or request["operation"] != "snapshot":
                return None
            aliases = request["vehicles"]
            if not isinstance(aliases, list) or not 1 <= len(aliases) <= 12:
                return None
            if any(not isinstance(alias, str) for alias in aliases):
                return None
            if len(set(aliases)) != len(aliases):
                return None
            return request
        except (ValueError, UnicodeError, TypeError):
            return None


class SnapshotClient:
    """Client owns its bounded stream reader; semantic validation is separate."""

    @staticmethod
    def exchange(address, request, raw=None):
        wire = raw
        if wire is None:
            wire = json.dumps(request, separators=(",", ":")).encode() + b"\n"
        deadline = time.monotonic() + 4
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(4)
            connection.connect(address)
            connection.sendall(wire)
            connection.shutdown(socket.SHUT_WR)
            frame = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("response deadline")
                connection.settimeout(remaining)
                chunk = connection.recv(4096)
                if not chunk:
                    break
                frame.extend(chunk)
                if len(frame) > 131072:
                    raise ValueError("response size")
        if not frame.endswith(b"\n") or frame.count(b"\n") != 1:
            raise ValueError("response framing")

        def unique(pairs):
            document = {}
            for key, value in pairs:
                if key in document:
                    raise ValueError("duplicate response key")
                document[key] = value
            return document

        response = json.loads(frame.decode("utf-8"), object_pairs_hook=unique)
        check_response(response, request)
        return response


@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "Unix sockets required")
class SocketTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.environ.get("TEMP"))
        self.addCleanup(self.directory.cleanup)
        self.address = str(Path(self.directory.name) / "data.sock")
        self.request = load("examples/request.json")

    def test_fragmented_exchange_preserves_multiple_vehicle_identities(self):
        self.request["vehicles"] = ["car-b", "car-a"]
        with CachedService(self.address, fragmented=True):
            response = SnapshotClient.exchange(self.address, self.request)
        self.assertEqual([item["vehicle"] for item in response["vehicles"]], ["car-b", "car-a"])
        self.assertEqual([item["sample"]["soc"] for item in response["vehicles"]], [0.32, 0.64])

    def test_repeated_cache_reads_preserve_measurement_and_reception(self):
        with CachedService(self.address, connections=2) as service:
            before = copy.deepcopy(service.cache)
            first = SnapshotClient.exchange(self.address, self.request)
            second = SnapshotClient.exchange(self.address, self.request)
            self.assertEqual(first["vehicles"], second["vehicles"])
            self.assertEqual(service.cache, before)

    def test_unknown_vehicle_is_isolated(self):
        self.request["vehicles"] = ["car-a", "unknown"]
        with CachedService(self.address):
            response = SnapshotClient.exchange(self.address, self.request)
        self.assertEqual(response["vehicles"][0]["status"], "ok")
        self.assertEqual(response["vehicles"][1]["status"], "unknown_vehicle")
        self.assertIsNone(response["vehicles"][1]["sample"])

    def test_control_operation_and_unsupported_version_are_rejected(self):
        for patch in ({"operation": "start"}, {"contract_version": "2.0"}):
            with self.subTest(patch=patch):
                request = self.request | patch
                with CachedService(self.address):
                    with self.assertRaises(ValueError):
                        SnapshotClient.exchange(self.address, request)

    def test_request_duplicate_keys_are_rejected(self):
        raw = b'{"contract_version":"1.0","operation":"snapshot","operation":"start"}\n'
        with CachedService(self.address):
            with self.assertRaises(ValueError):
                SnapshotClient.exchange(self.address, self.request, raw=raw)

    def test_invalid_response_frames_are_rejected(self):
        frames = (b"{}", b"{}\n{}\n", b'{"request_id":"a","request_id":"b"}\n',
                  b"\xff\n", b"x" * 131073 + b"\n")
        for wire in frames:
            with self.subTest(wire=wire[:40]):
                with CachedService(self.address, wire=wire):
                    with self.assertRaises((ValueError, UnicodeError)):
                        SnapshotClient.exchange(self.address, self.request)

    def test_mismatched_response_identity_is_rejected(self):
        response = load("examples/real.json")
        response["request_id"] = "other"
        wire = json.dumps(response, separators=(",", ":")).encode() + b"\n"
        with CachedService(self.address, wire=wire):
            with self.assertRaises(ValueError):
                SnapshotClient.exchange(self.address, self.request)


if __name__ == "__main__":
    unittest.main()
