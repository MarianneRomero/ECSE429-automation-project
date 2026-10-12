"""Categories endpoints with XML payloads (exploratory session 3).

Generic XML behaviour (and BUG-05 / BUG-06) comes from contracts.py; this module
adds what is specific to categories.

Where each documented endpoint is tested (in XML):

    GET/POST /categories, GET /categories?field=value   TestCategoriesXml
    GET/POST/PUT /categories/:id                        TestCategoriesXml
    GET/POST /categories/:id/todos                      TestCategoryRelationshipsXml[todos-todos]
    GET/POST /categories/:id/projects                   TestCategoryRelationshipsXml[projects-projects]

Each class docstring lists the tests it inherits from contracts.py. The first line
of a class docstring is used as its header in the test output (see reporting.py).
"""

import pytest

from contracts import XmlContract, XmlRelationshipContract, relationships_of
from support import XML, call, content_type, snapshot, to_xml, xml_root


class TestCategoriesXml(XmlContract):
    """/categories and /categories/:id with XML payloads

    Inherited from XmlContract:
        GET /categories                 test_get_collection_as_xml
        GET /categories?title=...       test_filter_query_answered_in_xml
        POST /categories                test_post_xml_body_creates_object_and_returns_xml
        POST /categories                test_json_body_can_be_answered_in_xml
        PUT/PATCH/DELETE /categories    test_unsupported_method_returns_405_with_empty_body
        GET /categories/:id             test_not_found_error_is_xml
        GET /categories/:id             test_get_one_returns_a_bare_element_as_documented (BUG-05, xfail)
        GET /categories/:id             test_get_one_returns_a_list_wrapper_actual (BUG-05)
        POST /categories/:id            test_post_xml_body_amends_object
        PUT /categories/:id             test_put_xml_body_replaces_object
    """

    PARENT = "categories"

    def test_category_xml_has_only_id_title_description(self, obj):
        """GET /categories/:id: the XML element has exactly <id>, <title> and <description>."""
        element = xml_root(call("GET", f"/categories/{obj['id']}", accept=XML)).find("category")
        assert {child.tag for child in element} == {"id", "title", "description"}

    @pytest.mark.parametrize("fields, message", [
        ({"title": ""}, "title : can not be empty"),
        ({"description": "no title"}, "title : field is mandatory"),
    ], ids=["empty-title", "missing-title"])
    def test_validation_errors_are_xml_without_side_effects(self, fields, message):
        """POST /categories: an empty or missing title gets a 400 error in XML and nothing is created."""
        before = snapshot()
        response = call("POST", "/categories", to_xml("category", fields), accept=XML)
        assert response.status_code == 400
        assert content_type(response) == XML
        assert message in xml_root(response).findtext("errorMessage")
        assert snapshot() == before


@pytest.mark.parametrize("relationship, child_collection", relationships_of("categories"))
class TestCategoryRelationshipsXml(XmlRelationshipContract):
    """/categories/:id/<relationship> with XML payloads

    Runs once for todos (category -> todos) and once for projects (category -> projects).
    Every test is inherited from XmlRelationshipContract:
        GET /categories/:id/<relationship>  test_get_related_items_as_xml
        GET /categories/:id                 test_relationship_ids_appear_inside_parent_xml
        POST /categories/:id/<relationship> test_post_xml_body_without_id_creates_and_links_a_new_object
        POST /categories/:id/<relationship> test_post_xml_body_creates_relationship_as_documented (BUG-06, xfail)
        POST /categories/:id/<relationship> test_post_xml_body_cannot_find_existing_child_actual (BUG-06)
    """

    PARENT = "categories"
