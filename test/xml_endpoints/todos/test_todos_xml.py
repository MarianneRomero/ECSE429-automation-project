"""Todos endpoints with XML payloads (exploratory session 1).

Generic XML behaviour (and DOC-02 / BUG-06) comes from contracts.py; this module
adds what is specific to todos, including BUG-02 for malformed XML.
"""

import json

import pytest

from contracts import XmlContract, XmlRelationshipContract, relationships_of
from support import XML, bug, call, content_type, snapshot, to_xml, xml_fields, xml_root


class TestTodosXml(XmlContract):
    PARENT = "todos"

    def test_post_xml_boolean_field(self, create):
        response = call("POST", "/todos", to_xml("todo", {"title": "done in xml", "doneStatus": True}), accept=XML)
        fields = xml_fields(xml_root(response))
        try:
            assert response.status_code == 201
            assert fields["doneStatus"] == "true"
        finally:
            call("DELETE", f"/todos/{fields['id']}")

    @pytest.mark.parametrize("fields, message", [
        ({"title": ""}, "title : can not be empty"),
        ({"description": "no title"}, "title : field is mandatory"),
        ({"title": "t", "doneStatus": "banana"}, "doneStatus should be BOOLEAN"),
    ], ids=["empty-title", "missing-title", "non-boolean-doneStatus"])
    def test_validation_errors_are_xml_without_side_effects(self, fields, message):
        before = snapshot()
        response = call("POST", "/todos", to_xml("todo", fields), accept=XML)
        assert response.status_code == 400
        assert content_type(response) == XML
        assert message in xml_root(response).findtext("errorMessage")
        assert snapshot() == before


class TestTodoMalformedXml:
    """BUG-02: the 400 for malformed XML is labelled text/html."""

    BROKEN = "<todo><title>broken</todo>"

    def test_malformed_xml_returns_400_without_side_effects(self):
        before = snapshot()
        assert call("POST", "/todos", self.BROKEN, accept=XML).status_code == 400
        assert snapshot() == before

    @bug("BUG-02", documented=True)
    def test_malformed_xml_error_is_labelled_xml_as_expected(self):
        response = call("POST", "/todos", self.BROKEN, accept=XML)
        assert content_type(response) == XML

    @bug("BUG-02")
    def test_malformed_xml_error_is_labelled_html_actual(self):
        response = call("POST", "/todos", self.BROKEN, accept=XML)
        assert content_type(response) == "text/html"
        assert "Mismatched title and todo" in xml_root(response).findtext("errorMessage")

    @bug("BUG-02")
    def test_malformed_xml_error_without_accept_is_json_labelled_html_actual(self):
        response = call("POST", "/todos", self.BROKEN, content_type=XML)
        assert content_type(response) == "text/html"
        assert "Mismatched title and todo" in json.loads(response.text)["errorMessages"][0]


@pytest.mark.parametrize("relationship, child_collection", relationships_of("todos"))
class TestTodoRelationshipsXml(XmlRelationshipContract):
    PARENT = "todos"
