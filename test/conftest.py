"""Fixtures shared by every test module.

- `api_ready` checks once per session that the server is reachable.
- `create` builds the objects a test needs and deletes them afterwards, so every
  test sets up its own initial conditions and tests can run in any order.
"""

import pytest
import requests

from support import BASE_URL, call

# Terminal output hooks (section headers, per-test lines, bug summary).
from reporting import (  # noqa: F401
    pytest_collection_modifyitems,
    pytest_configure,
    pytest_report_teststatus,
    pytest_runtest_logreport,
    pytest_sessionstart,
    pytest_terminal_summary,
)


@pytest.fixture(scope="session", autouse=True)
def api_ready():
    """Ensure the system is ready to be tested before any test runs."""
    try:
        response = requests.get(f"{BASE_URL}/todos", timeout=5)
    except requests.ConnectionError:
        pytest.exit(
            f"Todo Manager API is not running at {BASE_URL}. "
            "Start it with: java -jar runTodoManagerRestAPI-1.5.5.jar",
            returncode=3,
        )
    if response.status_code != 200 or "todos" not in response.json():
        pytest.exit(f"{BASE_URL}/todos answered {response.status_code}; is this the Todo Manager?", returncode=3)


@pytest.fixture
def create():
    """Factory: create(collection, **fields) -> the created object as a dict.

    Everything created is deleted at teardown (a 404 there just means the test
    deleted it itself).
    """
    created = []

    def _create(collection, **fields):
        if collection in ("todos", "categories"):
            fields.setdefault("title", f"unit-test {collection}")
        response = call("POST", f"/{collection}", fields)
        assert response.status_code == 201, response.text
        obj = response.json()
        created.append((collection, obj["id"]))
        return obj

    yield _create
    for collection, object_id in reversed(created):
        call("DELETE", f"/{collection}/{object_id}")


@pytest.fixture
def todo(create):
    return create("todos", title="unit-test todo", description="todo description")


@pytest.fixture
def project(create):
    return create("projects", title="unit-test project", description="project description")


@pytest.fixture
def category(create):
    return create("categories", title="unit-test category", description="category description")


@pytest.fixture
def missing_id(create):
    """Factory: an id that is guaranteed not to exist in `collection`."""

    def _missing_id(collection):
        object_id = create(collection)["id"]
        assert call("DELETE", f"/{collection}/{object_id}").status_code == 200
        return object_id

    return _missing_id
