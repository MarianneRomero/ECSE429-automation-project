"""Categories endpoints with JSON payloads (exploratory session 3).

Endpoint behaviour shared with todos and projects comes from contracts.py;
this module adds what is specific to categories.
"""

import pytest

from contracts import CollectionContract, InstanceContract, RelationshipContract, relationships_of
from support import bug, call, get_one, ids, items, link, related_ids, snapshot


class TestCategoriesCollection(CollectionContract):
    PARENT = "categories"

    def test_post_creates_category_with_defaults(self, create):
        category = create("categories", title="errands")
        assert category == {"id": category["id"], "title": "errands", "description": ""}
        assert get_one("categories", category["id"]) == category

    def test_duplicate_titles_are_accepted(self, create):
        first, second = create("categories", title="same"), create("categories", title="same")
        assert first["id"] != second["id"]

    @pytest.mark.parametrize("body, message", [
        ({"title": ""}, "title : can not be empty"),
        ({"description": "no title"}, "title : field is mandatory"),
    ], ids=["empty-title", "missing-title"])
    def test_invalid_create_returns_400_without_side_effects(self, body, message):
        before = snapshot()
        response = call("POST", "/categories", body)
        assert response.status_code == 400
        assert message in response.json()["errorMessages"][0]
        assert snapshot() == before


class TestCategoryInstance(InstanceContract):
    PARENT = "categories"

    @bug("DOC-01", documented=True)
    def test_put_amends_given_fields_as_documented(self, obj):
        response = call("PUT", f"/categories/{obj['id']}", {"description": "only description"})
        assert response.status_code == 200
        assert get_one("categories", obj["id"])["title"] == "instance under test"

    @bug("DOC-01")
    def test_put_without_title_is_rejected_actual(self, obj):
        response = call("PUT", f"/categories/{obj['id']}", {"description": "only description"})
        assert response.status_code == 400
        assert "title : field is mandatory" in response.json()["errorMessages"][0]
        assert get_one("categories", obj["id"]) == obj


class TestCategoryQueryFilters:
    def test_filter_by_title(self, create):
        match = create("categories", title="unique-category-title")
        create("categories", title="another category")
        result = items(call("GET", "/categories", params={"title": "unique-category-title"}), "categories")
        assert ids(result) == {match["id"]}

    def test_filter_by_description(self, create):
        match = create("categories", title="c", description="unique-category-description")
        create("categories", title="c", description="other")
        result = items(call("GET", "/categories", params={"description": "unique-category-description"}), "categories")
        assert ids(result) == {match["id"]}


@pytest.mark.parametrize("relationship, child_collection", relationships_of("categories"))
class TestCategoryRelationships(RelationshipContract):
    PARENT = "categories"


class TestCategoryRelationshipDirection:
    """todos and projects are one-way (as the /docs Relationships section says).

    /docs: "todos : category => todo" and "projects : category => project", separate
    from the "categories" relationships of todos and projects.
    """

    def test_todos_link_is_one_way(self, category, todo):
        assert link("categories", category["id"], "todos", todo["id"]).status_code == 201
        assert related_ids(get_one("categories", category["id"]), "todos") == {todo["id"]}
        assert items(call("GET", f"/todos/{todo['id']}/categories"), "categories") == []

    def test_projects_link_is_one_way(self, category, project):
        assert link("categories", category["id"], "projects", project["id"]).status_code == 201
        assert related_ids(get_one("categories", category["id"]), "projects") == {project["id"]}
        assert items(call("GET", f"/projects/{project['id']}/categories"), "categories") == []
        assert related_ids(get_one("projects", project["id"]), "categories") == set()


class TestCategoryDeleteSideEffects:
    def test_deleting_a_linked_category_keeps_its_todos_and_projects(self, category, todo, project):
        assert link("categories", category["id"], "todos", todo["id"]).status_code == 201
        assert link("categories", category["id"], "projects", project["id"]).status_code == 201
        assert call("DELETE", f"/categories/{category['id']}").status_code == 200
        assert get_one("todos", todo["id"])["title"] == todo["title"]
        assert get_one("projects", project["id"])["title"] == project["title"]
