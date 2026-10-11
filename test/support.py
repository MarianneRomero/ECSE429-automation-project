"""Shared helpers for the Todo Manager API unit tests.

Everything that talks to the server goes through `call`, so every test uses the
same base URL, headers and timeout. Bug IDs refer to the exploratory session
notes (Session_1/2/3_Notes.docx and ECSE429_ES_notes_table.xlsx).
"""

import os
import xml.etree.ElementTree as ET

import pytest
import requests

BASE_URL = os.environ.get("TODO_API_URL", "http://localhost:4567").rstrip("/")
TIMEOUT = 5

JSON = "application/json"
XML = "application/xml"

# Singular element names used in XML bodies, e.g. <todo>...</todo>.
SINGULAR = {"todos": "todo", "projects": "project", "categories": "category"}

# (parent collection, relationship name, child collection) for every relationship
# the Swagger documents.
RELATIONSHIPS = [
    ("todos", "categories", "categories"),
    ("todos", "tasksof", "projects"),
    ("projects", "categories", "categories"),
    ("projects", "tasks", "todos"),
    ("categories", "todos", "todos"),
    ("categories", "projects", "projects"),
]

# Allow headers observed in the exploratory sessions; they match the Swagger.
ALLOW_COLLECTION = {"OPTIONS", "GET", "HEAD", "POST"}
ALLOW_INSTANCE = {"OPTIONS", "GET", "HEAD", "POST", "PUT", "DELETE"}
ALLOW_RELATIONSHIP_ITEM = {"OPTIONS", "DELETE"}

# Every behaviour that differs from the documentation, keyed by the ID used in the
# exploratory session notes. BUG-04 and BUG-06 were found while preparing this suite
# (BUG-05 was withdrawn: one-way relationships are documented).
BUGS = {
    "BUG-01": "GET/HEAD/POST on relationship item URLs return 404 instead of the documented 405",
    "BUG-02": "400 errors for malformed JSON/XML bodies are labelled Content-Type text/html",
    "BUG-03": "POST to a relationship with a nonexistent id returns 404, Swagger documents 400",
    "BUG-04": "GET /:id/<relationship> for a nonexistent :id returns every parent's related items",
    "BUG-06": "XML relationship POST cannot link an existing object: <id> is read as a number, 404",
    "DOC-01": "PUT /:id is a full replace, but the docs describe it as an amend like POST",
    "DOC-02": "GET /:id wraps the single object in a list; the docs example shows a bare object",
}


def bug(bug_id, documented=False):
    """Tag a test with the bug it demonstrates.

    documented=True marks the test that asserts what the documentation promises.
    It is a strict xfail: it shows as XFAIL (with the bug ID as the reason) while
    the bug exists, and turns into a failure if the bug is ever fixed, so the pair
    of tests gets revisited.
    """
    marks = [pytest.mark.bug(bug_id)]
    if documented:
        marks.append(pytest.mark.xfail(strict=True, reason=f"{bug_id}: {BUGS[bug_id]}"))

    def decorate(func):
        for mark in marks:
            func = mark(func)
        return func

    return decorate


def call(method, path, body=None, accept=JSON, content_type=None, params=None):
    """Send one request. Dict bodies go out as JSON, string bodies as-is (XML)."""
    headers = {"Accept": accept}
    kwargs = {}
    if isinstance(body, dict):
        kwargs["json"] = body
    elif body is not None:
        headers["Content-Type"] = content_type or XML
        kwargs["data"] = body.encode("utf-8")
    if content_type:
        headers["Content-Type"] = content_type
    return requests.request(
        method, f"{BASE_URL}{path}", headers=headers, params=params,
        timeout=TIMEOUT, **kwargs,
    )


def to_xml(root, fields):
    """Build an XML request body such as <todo><title>x</title></todo>."""
    element = ET.Element(root)
    for name, value in fields.items():
        ET.SubElement(element, name).text = str(value).lower() if isinstance(value, bool) else str(value)
    return ET.tostring(element, encoding="unicode")


def xml_root(response):
    return ET.fromstring(response.text)


def xml_fields(element):
    """Flatten the scalar children of an XML element into a dict."""
    return {child.tag: (child.text or "") for child in element if len(child) == 0}


def items(response, collection):
    """The list of objects in a JSON response such as {"todos": [...]}."""
    return response.json()[collection]


def ids(objects):
    return {obj["id"] for obj in objects}


def related_ids(obj, relationship):
    """Ids listed under a relationship inside an object, e.g. todo["categories"]."""
    return {ref["id"] for ref in obj.get(relationship, [])}


def get_one(collection, object_id):
    """The single object behind /collection/:id (unwrapping DOC-02's list)."""
    response = call("GET", f"/{collection}/{object_id}")
    assert response.status_code == 200, response.text
    return items(response, collection)[0]


def link(parent, parent_id, relationship, child_id):
    return call("POST", f"/{parent}/{parent_id}/{relationship}", {"id": str(child_id)})


def snapshot():
    """The full state of the server, normalised so it can be compared with ==."""
    state = {}
    for collection in SINGULAR:
        objects = items(call("GET", f"/{collection}"), collection)
        state[collection] = {
            obj["id"]: {
                key: sorted(ref["id"] for ref in value) if isinstance(value, list) else value
                for key, value in obj.items()
            }
            for obj in objects
        }
    return state


def content_type(response):
    return response.headers.get("Content-Type", "").split(";")[0].strip()


def allowed(response):
    return {verb.strip() for verb in response.headers.get("Allow", "").split(",") if verb.strip()}
