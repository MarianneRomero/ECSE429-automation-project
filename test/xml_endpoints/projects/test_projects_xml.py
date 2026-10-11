"""Projects endpoints with XML payloads (exploratory session 2).

Generic XML behaviour (and DOC-02 / BUG-06) comes from contracts.py; this module
adds what is specific to projects.
"""

import pytest

from contracts import XmlContract, XmlRelationshipContract, relationships_of
from support import XML, call, content_type, snapshot, to_xml, xml_fields, xml_root


class TestProjectsXml(XmlContract):
    PARENT = "projects"

    def test_post_xml_boolean_fields(self):
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
        before = snapshot()
        response = call("POST", "/projects", to_xml("project", {"title": "t", field: "yes"}), accept=XML)
        assert response.status_code == 400
        assert content_type(response) == XML
        assert f"{field} should be BOOLEAN" in xml_root(response).findtext("errorMessage")
        assert snapshot() == before


@pytest.mark.parametrize("relationship, child_collection", relationships_of("projects"))
class TestProjectRelationshipsXml(XmlRelationshipContract):
    PARENT = "projects"
