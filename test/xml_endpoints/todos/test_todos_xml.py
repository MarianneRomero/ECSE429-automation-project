"""Todos endpoints with XML payloads (exploratory session 1).

Generic XML behaviour (and BUG-05 / BUG-06) comes from contracts.py; this module
adds what is specific to todos, including BUG-02 for malformed XML.

Where each documented endpoint is tested (in XML):

    GET/POST /todos, GET /todos?field=value     TestTodosXml, TestTodoMalformedXml
    GET/POST/PUT /todos/:id                     TestTodosXml
    GET/POST /todos/:id/tasksof                 TestTodoRelationshipsXml[tasksof-projects]
    GET/POST /todos/:id/categories              TestTodoRelationshipsXml[categories-categories]

Each class docstring lists the tests it inherits from contracts.py. The first line
of a class docstring is used as its header in the test output (see reporting.py).
"""

import json

import pytest

from contracts import XmlContract, XmlRelationshipContract, relationships_of
from support import XML, bug, call, content_type, snapshot, to_xml, xml_fields, xml_root


class TestTodosXml(XmlContract):
    """/todos and /todos/:id with XML payloads

    Inherited from XmlContract:
        GET /todos                      test_get_collection_as_xml
        GET /todos?title=...            test_filter_query_answered_in_xml
        POST /todos                     test_post_xml_body_creates_object_and_returns_xml
        POST /todos                     test_json_body_can_be_answered_in_xml
        PUT/PATCH/DELETE /todos         test_unsupported_method_returns_405_with_empty_body
        GET /todos/:id                  test_not_found_error_is_xml
        GET /todos/:id                  test_get_one_returns_a_bare_element_as_documented (BUG-05, xfail)
        GET /todos/:id                  test_get_one_returns_a_list_wrapper_actual (BUG-05)
        POST /todos/:id                 test_post_xml_body_amends_object
        PUT /todos/:id                  test_put_xml_body_replaces_object
    """

    PARENT = "todos"

    def test_post_xml_boolean_field(self, create):
        """POST /todos: <doneStatus>true</doneStatus> in an XML body is stored as true."""
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
        """POST /todos: an invalid XML body gets a 400 error in XML and nothing is created."""
        before = snapshot()
        response = call("POST", "/todos", to_xml("todo", fields), accept=XML)
        assert response.status_code == 400
        assert content_type(response) == XML
        assert message in xml_root(response).findtext("errorMessage")
        assert snapshot() == before


class TestTodoMalformedXml:
    """POST /todos with a malformed XML body

    BUG-02: the 400 for malformed XML is labelled text/html.
    """

    BROKEN = "<todo><title>broken</todo>"

    def test_malformed_xml_returns_400_without_side_effects(self):
        """POST /todos: a malformed XML body gets 400 and nothing is created."""
        before = snapshot()
        assert call("POST", "/todos", self.BROKEN, accept=XML).status_code == 400
        assert snapshot() == before

    @bug("BUG-02", documented=True)
    def test_malformed_xml_error_is_labelled_xml_as_expected(self):
        """POST /todos: the 400 error should have Content-Type application/xml."""
        response = call("POST", "/todos", self.BROKEN, accept=XML)
        assert content_type(response) == XML

    @bug("BUG-02")
    def test_malformed_xml_error_is_labelled_html_actual(self):
        """POST /todos: the 400 error is actually labelled text/html, though its body is XML."""
        response = call("POST", "/todos", self.BROKEN, accept=XML)
        assert content_type(response) == "text/html"
        assert "Mismatched title and todo" in xml_root(response).findtext("errorMessage")

    @bug("BUG-02")
    def test_malformed_xml_error_without_accept_is_json_labelled_html_actual(self):
        """POST /todos without an Accept header: the 400 error body is JSON but labelled text/html."""
        response = call("POST", "/todos", self.BROKEN, content_type=XML)
        assert content_type(response) == "text/html"
        assert "Mismatched title and todo" in json.loads(response.text)["errorMessages"][0]


@pytest.mark.parametrize("relationship, child_collection", relationships_of("todos"))
class TestTodoRelationshipsXml(XmlRelationshipContract):
    """/todos/:id/<relationship> with XML payloads

    Runs once for tasksof (todo -> projects) and once for categories (todo -> categories).
    Every test is inherited from XmlRelationshipContract:
        GET /todos/:id/<relationship>   test_get_related_items_as_xml
        GET /todos/:id                  test_relationship_ids_appear_inside_parent_xml
        POST /todos/:id/<relationship>  test_post_xml_body_without_id_creates_and_links_a_new_object
        POST /todos/:id/<relationship>  test_post_xml_body_creates_relationship_as_documented (BUG-06, xfail)
        POST /todos/:id/<relationship>  test_post_xml_body_cannot_find_existing_child_actual (BUG-06)
    """

    PARENT = "todos"
