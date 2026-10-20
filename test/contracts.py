"""Behaviour shared by /todos, /projects and /categories.

Each class checks one kind of endpoint against the Swagger. A test module reuses
it by subclassing and setting PARENT, e.g.

    class TestProjectsCollection(CollectionContract):
        PARENT = "projects"

Relationship contracts are parametrized by the subclass with
("relationship", "child_collection") pairs taken from support.RELATIONSHIPS.
The class names here don't start with "Test", so pytest only collects them
through the subclasses.
"""

from collections import Counter

import pytest

from support import (
    ALLOW_COLLECTION, ALLOW_INSTANCE, ALLOW_RELATIONSHIP_ITEM, JSON, RELATIONSHIPS, SINGULAR,
    XML, allowed, actual_behaviour, documented_behaviour, call, content_type, get_one, ids,
    items, link, related_ids, snapshot, to_xml, xml_fields, xml_root,
)


def relationships_of(parent):
    """[(relationship, child_collection), ...] for one parent collection."""
    return [(name, child) for owner, name, child in RELATIONSHIPS if owner == parent]


class CollectionContract:
    """/<PARENT>"""

    PARENT = None

    def test_get_lists_created_objects(self, create):
        obj = create(self.PARENT)
        response = call("GET", f"/{self.PARENT}")
        assert response.status_code == 200
        assert content_type(response) == JSON
        assert obj["id"] in ids(items(response, self.PARENT))

    def test_head_returns_headers_without_body(self):
        response = call("HEAD", f"/{self.PARENT}")
        assert response.status_code == 200
        assert response.text == ""

    def test_post_returns_201_and_location_of_the_new_object(self):
        response = call("POST", f"/{self.PARENT}", {"title": "located"})
        created = response.json()
        try:
            assert response.status_code == 201
            location = response.headers["Location"]
            assert location == f"{self.PARENT}/{created['id']}"
            located = call("GET", f"/{location}")
            assert located.status_code == 200
            assert items(located, self.PARENT) == [created]
        finally:
            call("DELETE", f"/{self.PARENT}/{created['id']}")

    def test_post_with_client_supplied_id_returns_400(self):
        before = snapshot()
        response = call("POST", f"/{self.PARENT}", {"title": "t", "id": "123"})
        assert response.status_code == 400
        assert "Not allowed to create with id" in response.json()["errorMessages"][0]
        assert snapshot() == before

    @pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
    def test_unsupported_methods_return_405_without_side_effects(self, method):
        before = snapshot()
        assert call(method, f"/{self.PARENT}").status_code == 405
        assert snapshot() == before

    def test_options_lists_allowed_methods(self):
        response = call("OPTIONS", f"/{self.PARENT}")
        assert response.status_code == 200
        assert allowed(response) == ALLOW_COLLECTION

    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
    def test_read_only_methods_have_no_side_effects(self, create, method):
        create(self.PARENT)
        before = snapshot()
        assert call(method, f"/{self.PARENT}").status_code == 200
        assert snapshot() == before


class InstanceContract:
    """/<PARENT>/:id"""

    PARENT = None

    @pytest.fixture
    def obj(self, create):
        return create(self.PARENT, title="instance under test", description="original")

    def test_get_returns_the_object(self, obj):
        response = call("GET", f"/{self.PARENT}/{obj['id']}")
        assert response.status_code == 200
        assert items(response, self.PARENT)[0] == obj

    def test_head_returns_headers_without_body(self, obj):
        response = call("HEAD", f"/{self.PARENT}/{obj['id']}")
        assert response.status_code == 200
        assert response.text == ""

    def test_post_amends_only_the_given_fields(self, obj):
        response = call("POST", f"/{self.PARENT}/{obj['id']}", {"description": "changed"})
        assert response.status_code == 200
        amended = get_one(self.PARENT, obj["id"])
        assert amended["description"] == "changed"
        assert amended["title"] == obj["title"]

    def test_put_replaces_the_title(self, obj):
        response = call("PUT", f"/{self.PARENT}/{obj['id']}", {"title": "replaced"})
        assert response.status_code == 200
        assert get_one(self.PARENT, obj["id"])["title"] == "replaced"

    def test_delete_removes_the_object(self, obj):
        assert call("DELETE", f"/{self.PARENT}/{obj['id']}").status_code == 200
        assert call("GET", f"/{self.PARENT}/{obj['id']}").status_code == 404

    def test_delete_twice_returns_404_the_second_time(self, obj):
        assert call("DELETE", f"/{self.PARENT}/{obj['id']}").status_code == 200
        response = call("DELETE", f"/{self.PARENT}/{obj['id']}")
        assert response.status_code == 404
        assert f"Could not find any instances with {self.PARENT}/{obj['id']}" in response.json()["errorMessages"][0]

    def test_delete_leaves_other_objects_untouched(self, obj):
        before = snapshot()
        call("DELETE", f"/{self.PARENT}/{obj['id']}")
        del before[self.PARENT][obj["id"]]
        assert snapshot() == before

    def test_amend_does_not_change_other_objects(self, create, obj):
        bystander = create(self.PARENT, title="bystander")
        call("POST", f"/{self.PARENT}/{obj['id']}", {"title": "amended"})
        assert get_one(self.PARENT, bystander["id"]) == bystander

    def test_patch_returns_405_without_side_effects(self, obj):
        before = snapshot()
        assert call("PATCH", f"/{self.PARENT}/{obj['id']}", {"title": "x"}).status_code == 405
        assert snapshot() == before

    def test_options_lists_allowed_methods(self, obj):
        response = call("OPTIONS", f"/{self.PARENT}/{obj['id']}")
        assert response.status_code == 200
        assert allowed(response) == ALLOW_INSTANCE

    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
    def test_read_only_methods_have_no_side_effects(self, obj, method):
        before = snapshot()
        assert call(method, f"/{self.PARENT}/{obj['id']}").status_code == 200
        assert snapshot() == before

    # Each method words its 404 differently.
    @pytest.mark.parametrize("method, body, message", [
        ("GET", None, "Could not find an instance with {parent}/{id}"),
        ("POST", {"title": "x"}, "No such {singular} entity instance with GUID or ID {id} found"),
        ("PUT", {"title": "x"}, "Invalid GUID for {id} entity {singular}"),
        ("DELETE", None, "Could not find any instances with {parent}/{id}"),
    ], ids=["GET", "POST", "PUT", "DELETE"])
    def test_nonexistent_id_returns_404_naming_the_id(self, missing_id, method, body, message):
        absent = missing_id(self.PARENT)
        before = snapshot()
        response = call(method, f"/{self.PARENT}/{absent}", body)
        assert response.status_code == 404
        expected = message.format(parent=self.PARENT, singular=SINGULAR[self.PARENT], id=absent)
        assert response.json()["errorMessages"] == [expected]
        assert snapshot() == before

    def test_head_on_nonexistent_id_returns_404_without_body(self, missing_id):
        response = call("HEAD", f"/{self.PARENT}/{missing_id(self.PARENT)}")
        assert response.status_code == 404
        assert response.text == ""

    @documented_behaviour("BUG-05")
    def test_get_one_returns_a_bare_object_as_documented(self, obj):
        body = call("GET", f"/{self.PARENT}/{obj['id']}").json()
        assert body.get("id") == obj["id"]

    @actual_behaviour("BUG-05")
    def test_get_one_returns_a_single_item_list_actual(self, obj):
        body = call("GET", f"/{self.PARENT}/{obj['id']}").json()
        assert list(body) == [self.PARENT]
        assert [o["id"] for o in body[self.PARENT]] == [obj["id"]]


class RelationshipContract:
    """/<PARENT>/:id/<relationship> and /<PARENT>/:id/<relationship>/:id"""

    PARENT = None

    @pytest.fixture
    def parent(self, create):
        return create(self.PARENT)

    @pytest.fixture
    def linked(self, parent, create, relationship, child_collection):
        """A parent linked to a new child: (parent, child)."""
        child = create(child_collection)
        assert link(self.PARENT, parent["id"], relationship, child["id"]).status_code == 201
        return parent, child

    def path(self, parent, relationship, child=None):
        base = f"/{self.PARENT}/{parent['id']}/{relationship}"
        return f"{base}/{child['id']}" if child else base

    # ---- /<PARENT>/:id/<relationship>

    def test_post_creates_relationship_with_empty_body(self, parent, create, relationship, child_collection):
        child = create(child_collection)
        response = link(self.PARENT, parent["id"], relationship, child["id"])
        assert response.status_code == 201
        assert response.text == ""
        assert related_ids(get_one(self.PARENT, parent["id"]), relationship) == {child["id"]}

    def test_get_lists_related_items(self, linked, relationship, child_collection):
        parent, child = linked
        response = call("GET", self.path(parent, relationship))
        assert response.status_code == 200
        assert ids(items(response, child_collection)) == {child["id"]}

    def test_get_with_no_links_returns_empty_list(self, parent, relationship, child_collection):
        response = call("GET", self.path(parent, relationship))
        assert response.status_code == 200
        assert items(response, child_collection) == []

    def test_head_returns_headers_without_body(self, parent, relationship, child_collection):
        response = call("HEAD", self.path(parent, relationship))
        assert response.status_code == 200
        assert response.text == ""

    @pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
    def test_unsupported_methods_return_405_without_side_effects(self, linked, method, relationship, child_collection):
        parent, _ = linked
        before = snapshot()
        assert call(method, self.path(parent, relationship)).status_code == 405
        assert snapshot() == before

    def test_options_lists_allowed_methods(self, parent, relationship, child_collection):
        response = call("OPTIONS", self.path(parent, relationship))
        assert response.status_code == 200
        assert allowed(response) == ALLOW_COLLECTION

    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
    def test_read_only_methods_have_no_side_effects(self, linked, method, relationship, child_collection):
        parent, _ = linked
        before = snapshot()
        assert call(method, self.path(parent, relationship)).status_code == 200
        assert snapshot() == before

    def test_item_options_has_no_side_effects(self, linked, relationship, child_collection):
        parent, child = linked
        before = snapshot()
        assert call("OPTIONS", self.path(parent, relationship, child)).status_code == 200
        assert snapshot() == before

    def test_duplicate_post_does_not_duplicate_relationship(self, linked, relationship, child_collection):
        parent, child = linked
        assert link(self.PARENT, parent["id"], relationship, child["id"]).status_code == 201
        assert len(items(call("GET", self.path(parent, relationship)), child_collection)) == 1

    @documented_behaviour("BUG-03")
    def test_post_nonexistent_child_returns_400_as_documented(self, parent, missing_id, relationship, child_collection):
        assert link(self.PARENT, parent["id"], relationship, missing_id(child_collection)).status_code == 400

    @actual_behaviour("BUG-03")
    def test_post_nonexistent_child_returns_404_actual(self, parent, missing_id, relationship, child_collection):
        absent = missing_id(child_collection)
        before = snapshot()
        response = link(self.PARENT, parent["id"], relationship, absent)
        assert response.status_code == 404
        assert "Could not find thing matching value for id" in response.json()["errorMessages"][0]
        assert snapshot() == before

    @documented_behaviour("BUG-07")
    def test_get_relationship_of_missing_parent_returns_no_items_as_documented(
            self, linked, missing_id, relationship, child_collection):
        # "return all the ... items related to <parent>, with given id": no such
        # parent, so nothing is related. Either a 404 or an empty list is acceptable.
        response = call("GET", f"/{self.PARENT}/{missing_id(self.PARENT)}/{relationship}")
        assert response.status_code == 404 or items(response, child_collection) == []

    @actual_behaviour("BUG-07")
    def test_get_relationship_of_missing_parent_lists_every_parents_items_actual(
            self, linked, create, missing_id, relationship, child_collection):
        # The items are concatenated per parent, not de-duplicated: link a second
        # parent to the same child so it is guaranteed to appear twice.
        _, child = linked
        other_parent = create(self.PARENT)
        assert link(self.PARENT, other_parent["id"], relationship, child["id"]).status_code == 201
        absent = missing_id(self.PARENT)
        before = snapshot()
        every_parents_items = Counter(
            child_id
            for parent in before[self.PARENT].values()
            for child_id in parent.get(relationship, [])
        )
        response = call("GET", f"/{self.PARENT}/{absent}/{relationship}")
        assert response.status_code == 200
        assert Counter(obj["id"] for obj in items(response, child_collection)) == every_parents_items
        assert every_parents_items[child["id"]] == 2
        assert snapshot() == before

    @actual_behaviour("BUG-06")
    def test_post_numeric_json_id_is_not_matched(self, parent, create, relationship, child_collection):
        # Root cause of BUG-06: ids are strings, and a numeric id is never matched.
        child = create(child_collection)
        before = snapshot()
        response = call("POST", self.path(parent, relationship), {"id": int(child["id"])})
        assert response.status_code == 404
        assert snapshot() == before

    # ---- /<PARENT>/:id/<relationship>/:id

    def test_delete_item_removes_only_the_link(self, linked, relationship, child_collection):
        parent, child = linked
        assert call("DELETE", self.path(parent, relationship, child)).status_code == 200
        assert related_ids(get_one(self.PARENT, parent["id"]), relationship) == set()
        assert get_one(child_collection, child["id"]) == child

    def test_delete_missing_item_returns_404_without_side_effects(self, parent, create, relationship, child_collection):
        child = create(child_collection)
        before = snapshot()
        assert call("DELETE", self.path(parent, relationship, child)).status_code == 404
        assert snapshot() == before

    @pytest.mark.parametrize("method", ["PUT", "PATCH"])
    def test_item_put_and_patch_return_405_without_side_effects(self, linked, method, relationship, child_collection):
        parent, child = linked
        before = snapshot()
        assert call(method, self.path(parent, relationship, child)).status_code == 405
        assert snapshot() == before

    def test_item_options_lists_only_delete(self, linked, relationship, child_collection):
        parent, child = linked
        response = call("OPTIONS", self.path(parent, relationship, child))
        assert response.status_code == 200
        assert allowed(response) == ALLOW_RELATIONSHIP_ITEM

    @documented_behaviour("BUG-01")
    @pytest.mark.parametrize("method", ["GET", "HEAD", "POST"])
    def test_item_get_head_post_return_405_as_documented(self, linked, method, relationship, child_collection):
        parent, child = linked
        assert call(method, self.path(parent, relationship, child)).status_code == 405

    @actual_behaviour("BUG-01")
    @pytest.mark.parametrize("method", ["GET", "HEAD", "POST"])
    def test_item_get_head_post_return_404_actual(self, linked, method, relationship, child_collection):
        parent, child = linked
        before = snapshot()
        assert call(method, self.path(parent, relationship, child)).status_code == 404
        # The link still exists, so this 404 does not mean "relationship missing".
        assert snapshot() == before


class XmlContract:
    """/<PARENT> and /<PARENT>/:id with XML payloads (Accept / Content-Type)."""

    PARENT = None

    @property
    def singular(self):
        return SINGULAR[self.PARENT]

    @pytest.fixture
    def obj(self, create):
        return create(self.PARENT, title="xml under test", description="original")

    def test_get_collection_as_xml(self, obj):
        response = call("GET", f"/{self.PARENT}", accept=XML)
        assert response.status_code == 200
        assert content_type(response) == XML
        root = xml_root(response)
        assert root.tag == self.PARENT
        assert {child.tag for child in root} == {self.singular}
        assert obj["id"] in {child.findtext("id") for child in root}

    def test_post_xml_body_creates_object_and_returns_xml(self):
        body = to_xml(self.singular, {"title": "from xml", "description": "xml body"})
        response = call("POST", f"/{self.PARENT}", body, accept=XML)
        root = xml_root(response)
        new_id = root.findtext("id")
        try:
            assert response.status_code == 201
            assert content_type(response) == XML
            assert response.headers["Location"] == f"{self.PARENT}/{new_id}"
            assert root.tag == self.singular
            assert (root.findtext("title"), root.findtext("description")) == ("from xml", "xml body")
            assert get_one(self.PARENT, new_id)["title"] == "from xml"
        finally:
            call("DELETE", f"/{self.PARENT}/{new_id}")

    def test_json_body_can_be_answered_in_xml(self):
        response = call("POST", f"/{self.PARENT}", {"title": "json in, xml out"}, accept=XML)
        root = xml_root(response)
        try:
            assert response.status_code == 201
            assert root.tag == self.singular
            assert root.findtext("title") == "json in, xml out"
        finally:
            call("DELETE", f"/{self.PARENT}/{root.findtext('id')}")

    def test_post_xml_body_amends_object(self, obj):
        body = to_xml(self.singular, {"description": "changed by xml"})
        response = call("POST", f"/{self.PARENT}/{obj['id']}", body, accept=XML)
        assert response.status_code == 200
        assert xml_fields(xml_root(response))["description"] == "changed by xml"
        amended = get_one(self.PARENT, obj["id"])
        assert (amended["title"], amended["description"]) == (obj["title"], "changed by xml")

    def test_put_xml_body_replaces_object(self, obj):
        body = to_xml(self.singular, {"title": "replaced by xml"})
        response = call("PUT", f"/{self.PARENT}/{obj['id']}", body, accept=XML)
        assert response.status_code == 200
        replaced = get_one(self.PARENT, obj["id"])
        assert (replaced["title"], replaced["description"]) == ("replaced by xml", "")

    def test_not_found_error_is_xml(self, missing_id):
        absent = missing_id(self.PARENT)
        response = call("GET", f"/{self.PARENT}/{absent}", accept=XML)
        assert response.status_code == 404
        assert content_type(response) == XML
        root = xml_root(response)
        assert root.tag == "errorMessages"
        assert f"Could not find an instance with {self.PARENT}/{absent}" in root.findtext("errorMessage")

    def test_filter_query_answered_in_xml(self, obj):
        response = call("GET", f"/{self.PARENT}", accept=XML, params={"title": obj["title"]})
        assert response.status_code == 200
        assert obj["id"] in {child.findtext("id") for child in xml_root(response)}
        assert {child.findtext("title") for child in xml_root(response)} == {obj["title"]}

    @pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
    def test_unsupported_method_returns_405_with_empty_body(self, method):
        response = call(method, f"/{self.PARENT}", accept=XML)
        assert response.status_code == 405
        assert response.text == ""

    @documented_behaviour("BUG-05")
    def test_get_one_returns_a_bare_element_as_documented(self, obj):
        root = xml_root(call("GET", f"/{self.PARENT}/{obj['id']}", accept=XML))
        assert root.tag == self.singular

    @actual_behaviour("BUG-05")
    def test_get_one_returns_a_list_wrapper_actual(self, obj):
        root = xml_root(call("GET", f"/{self.PARENT}/{obj['id']}", accept=XML))
        assert root.tag == self.PARENT
        assert [child.findtext("id") for child in root] == [obj["id"]]


class XmlRelationshipContract:
    """/<PARENT>/:id/<relationship> with XML payloads."""

    PARENT = None

    @pytest.fixture
    def parent(self, create):
        return create(self.PARENT)

    def test_get_related_items_as_xml(self, parent, create, relationship, child_collection):
        child = create(child_collection)
        assert link(self.PARENT, parent["id"], relationship, child["id"]).status_code == 201
        response = call("GET", f"/{self.PARENT}/{parent['id']}/{relationship}", accept=XML)
        assert response.status_code == 200
        assert content_type(response) == XML
        root = xml_root(response)
        assert root.tag == child_collection
        assert [element.findtext("id") for element in root] == [child["id"]]

    def test_relationship_ids_appear_inside_parent_xml(self, parent, create, relationship, child_collection):
        child = create(child_collection)
        assert link(self.PARENT, parent["id"], relationship, child["id"]).status_code == 201
        root = xml_root(call("GET", f"/{self.PARENT}/{parent['id']}", accept=XML))
        assert root.find(SINGULAR[self.PARENT]).findtext(f"{relationship}/id") == child["id"]

    def test_post_xml_body_without_id_creates_and_links_a_new_object(self, parent, relationship, child_collection):
        # Undocumented: a relationship POST without an id creates the child and links it.
        body = to_xml(SINGULAR[child_collection], {"title": "created through relationship"})
        response = call("POST", f"/{self.PARENT}/{parent['id']}/{relationship}", body)
        new_id = response.json()["id"]
        try:
            assert response.status_code == 201
            assert new_id in related_ids(get_one(self.PARENT, parent["id"]), relationship)
        finally:
            call("DELETE", f"/{child_collection}/{new_id}")

    @documented_behaviour("BUG-06")
    def test_post_xml_body_creates_relationship_as_documented(self, parent, create, relationship, child_collection):
        child = create(child_collection)
        body = to_xml(SINGULAR[child_collection], {"id": child["id"]})
        response = call("POST", f"/{self.PARENT}/{parent['id']}/{relationship}", body)
        assert response.status_code == 201
        assert related_ids(get_one(self.PARENT, parent["id"]), relationship) == {child["id"]}

    @actual_behaviour("BUG-06")
    def test_post_xml_body_cannot_find_existing_child_actual(self, parent, create, relationship, child_collection):
        child = create(child_collection)
        body = to_xml(SINGULAR[child_collection], {"id": child["id"]})
        before = snapshot()
        response = call("POST", f"/{self.PARENT}/{parent['id']}/{relationship}", body)
        assert response.status_code == 404
        assert "Could not find thing matching value for id" in response.json()["errorMessages"][0]
        assert snapshot() == before
