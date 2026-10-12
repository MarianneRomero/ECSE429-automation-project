"""Projects endpoints with XML payloads (exploratory session 2).

Generic XML behaviour (and BUG-05 / BUG-06) comes from contracts.py; this module
adds what is specific to projects.

Where each documented endpoint is tested (in XML):

    GET/POST /projects, GET /projects?field=value   TestProjectsXml
    GET/POST/PUT /projects/:id                      TestProjectsXml
    GET/POST /projects/:id/tasks                    TestProjectRelationshipsXml[tasks-todos]
    GET/POST /projects/:id/categories               TestProjectRelationshipsXml[categories-categories]

Each class docstring lists the tests it inherits from contracts.py. The first line
of a class docstring is used as its header in the test output (see reporting.py).
"""

import pytest

from contracts import XmlContract, XmlRelationshipContract, relationships_of
from support import XML, call, content_type, snapshot, to_xml, xml_fields, xml_root


class TestProjectsXml(XmlContract):
    """/projects and /projects/:id with XML payloads

    Inherited from XmlContract:
        GET /projects                   test_get_collection_as_xml
        GET /projects?title=...         test_filter_query_answered_in_xml
        POST /projects                  test_post_xml_body_creates_object_and_returns_xml
        POST /projects                  test_json_body_can_be_answered_in_xml
        PUT/PATCH/DELETE /projects      test_unsupported_method_returns_405_with_empty_body
        GET /projects/:id               test_not_found_error_is_xml
        GET /projects/:id               test_get_one_returns_a_bare_element_as_documented (BUG-05, xfail)
        GET /projects/:id               test_get_one_returns_a_list_wrapper_actual (BUG-05)
        POST /projects/:id              test_post_xml_body_amends_object
        PUT /projects/:id               test_put_xml_body_replaces_object
    """

    PARENT = "projects"

    def test_post_xml_boolean_fields(self):
        """POST /projects: <active> and <completed> in an XML body are stored as booleans."""
        body = to_xml("project", {"title": "flags in xml", "active": True, "completed": False})
        response = call("POST", "/projects", body, accept=XML)
        fields = xml_fields(xml_root(response))
        try:
            assert response.status_code == 201
            assert (fields["active"], fields["completed"]) == ("true", "false")
        finally:
            call("DELETE", f"/projects/{fields['id']}")

    @pytest.mark.parametrize("field", ["completed", "active"])
    def test_non_boolean_flag_error_is_xml_without_side_effects(self, field):
        """POST /projects: a non-boolean active/completed gets a 400 error in XML and nothing is created."""
        before = snapshot()
        response = call("POST", "/projects", to_xml("project", {"title": "t", field: "yes"}), accept=XML)
        assert response.status_code == 400
        assert content_type(response) == XML
        assert f"{field} should be BOOLEAN" in xml_root(response).findtext("errorMessage")
        assert snapshot() == before


@pytest.mark.parametrize("relationship, child_collection", relationships_of("projects"))
class TestProjectRelationshipsXml(XmlRelationshipContract):
    """/projects/:id/<relationship> with XML payloads

    Runs once for tasks (project -> todos) and once for categories (project -> categories).
    Every test is inherited from XmlRelationshipContract:
        GET /projects/:id/<relationship>    test_get_related_items_as_xml
        GET /projects/:id                   test_relationship_ids_appear_inside_parent_xml
        POST /projects/:id/<relationship>   test_post_xml_body_without_id_creates_and_links_a_new_object
        POST /projects/:id/<relationship>   test_post_xml_body_creates_relationship_as_documented (BUG-06, xfail)
        POST /projects/:id/<relationship>   test_post_xml_body_cannot_find_existing_child_actual (BUG-06)
    """

    PARENT = "projects"
