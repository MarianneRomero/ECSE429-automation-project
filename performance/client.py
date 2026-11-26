"""HTTP access to the Todo Manager for the performance experiments.

Reuses the Part A configuration and helpers from test/support.py and the
readiness check from test/conftest.py, so both suites talk to the same server in
the same way. The only difference from Part A's `call()` is that requests go
through one `requests.Session`: connections are kept alive, so the measured time
is the server's work plus one round trip, not a new TCP handshake every time.
"""

import sys
from pathlib import Path

import requests

TEST_DIR = Path(__file__).resolve().parent.parent / "test"
sys.path.insert(0, str(TEST_DIR))

from support import BASE_URL, JSON, SINGULAR, TIMEOUT, items  # noqa: E402
from conftest import _not_ready_reason  # noqa: E402

RESOURCES = tuple(SINGULAR)  # ("todos", "projects", "categories")


def not_ready_reason():
    """Why the server cannot be tested (Part A's check), or None when it is ready."""
    return _not_ready_reason()


class ApiClient:
    """Thin Session-based twin of support.call() with untimed setup helpers."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Accept": JSON})

    def request(self, method, path, body=None):
        """Send one request; dict bodies go out as JSON, as in support.call()."""
        return self.session.request(method, f"{BASE_URL}{path}", json=body, timeout=TIMEOUT)

    # ---- untimed helpers used for setup, restore and cleanup

    def list_ids(self, resource):
        response = self.request("GET", f"/{resource}")
        response.raise_for_status()
        return [obj["id"] for obj in items(response, resource)]

    def create(self, resource, payload):
        response = self.request("POST", f"/{resource}", payload)
        if response.status_code != 201:
            raise RuntimeError(f"POST /{resource} answered {response.status_code}: {response.text}")
        return response.json()["id"]

    def delete(self, resource, object_id):
        self.request("DELETE", f"/{resource}/{object_id}")

    def wipe(self, resources=RESOURCES):
        """Delete every object in the given collections (including the server's defaults)."""
        for resource in resources:
            for object_id in self.list_ids(resource):
                self.delete(resource, object_id)

    def close(self):
        self.session.close()
