"""Categories endpoints with XML payloads (exploratory session 3).

Generic XML behaviour (and DOC-02 / BUG-06) comes from contracts.py; this module
adds what is specific to categories.
"""

import pytest

from contracts import XmlContract, XmlRelationshipContract, relationships_of
from support import XML, call, content_type, snapshot, to_xml, xml_root


class TestCategoriesXml(XmlContract):
    PARENT = "categories"

    def test_category_xml_has_only_id_title_description(self, obj):
        element = xml_root(call("GET", f"/categories/{obj['id']}", accept=XML)).find("category")
        assert {child.tag for child in element} == {"id", "title", "description"}

    @pytest.mark.parametrize("fields, message", [
        ({"title": ""}, "title : can not be empty"),
        ({"description": "no title"}, "title : field is mandatory"),
    ], ids=["empty-title", "missing-title"])
    def test_validation_errors_are_xml_without_side_effects(self, fields, message):
        before = snapshot()
        response = call("POST", "/categories", to_xml("category", fields), accept=XML)
        assert response.status_code == 400
        assert content_type(response) == XML
        assert message in xml_root(response).findtext("errorMessage")
        assert snapshot() == before


@pytest.mark.parametrize("relationship, child_collection", relationships_of("categories"))
class TestCategoryRelationshipsXml(XmlRelationshipContract):
    PARENT = "categories"
