"""Categories endpoints with JSON payloads (exploratory session 3).

Endpoint behaviour shared with todos and projects comes from contracts.py;
this module adds what is specific to categories.

Where each documented endpoint is tested:

    GET/HEAD/POST /categories                   TestCategoriesCollection
    GET /categories?field=value                 TestCategoryQueryFilters
    GET/HEAD/POST/PUT/DELETE /categories/:id    TestCategoryInstance, TestCategoryDeleteSideEffects
    GET/HEAD/POST /categories/:id/todos         TestCategoryRelationships[todos-todos],
                                                TestCategoryRelationshipDirection
    DELETE /categories/:id/todos/:id            TestCategoryRelationships[todos-todos]
    GET/HEAD/POST /categories/:id/projects      TestCategoryRelationships[projects-projects],
                                                TestCategoryRelationshipDirection
    DELETE /categories/:id/projects/:id         TestCategoryRelationships[projects-projects]

Each class docstring lists the tests it inherits from contracts.py. The first line
of a class docstring is used as its header in the test output (see reporting.py).
"""

import pytest

from contracts import CollectionContract, InstanceContract, RelationshipContract, relationships_of
from support import bug, call, get_one, ids, items, link, related_ids, snapshot


class TestCategoriesCollection(CollectionContract):
    """/categories

    Inherited from CollectionContract:
        GET /categories                 test_get_lists_created_objects
        HEAD /categories                test_head_returns_headers_without_body
        POST /categories                test_post_returns_201_and_location_header
        POST /categories                test_post_with_client_supplied_id_returns_400
        PUT/PATCH/DELETE /categories    test_unsupported_methods_return_405_without_side_effects
        OPTIONS /categories             test_options_lists_allowed_methods
    """

    PARENT = "categories"

    def test_post_creates_category_with_defaults(self, create):
        """POST /categories: a category has only id, title and description (empty by default)."""
        category = create("categories", title="errands")
        assert category == {"id": category["id"], "title": "errands", "description": ""}
        assert get_one("categories", category["id"]) == category

    def test_duplicate_titles_are_accepted(self, create):
        """POST /categories: two categories may share a title; they get different ids."""
        first, second = create("categories", title="same"), create("categories", title="same")
        assert first["id"] != second["id"]

    @pytest.mark.parametrize("body, message", [
        ({"title": ""}, "title : can not be empty"),
        ({"description": "no title"}, "title : field is mandatory"),
    ], ids=["empty-title", "missing-title"])
    def test_invalid_create_returns_400_without_side_effects(self, body, message):
        """POST /categories: an empty or missing title is rejected with 400 and nothing is created."""
        before = snapshot()
        response = call("POST", "/categories", body)
        assert response.status_code == 400
        assert message in response.json()["errorMessages"][0]
        assert snapshot() == before


class TestCategoryInstance(InstanceContract):
    """/categories/:id

    Inherited from InstanceContract:
        GET /categories/:id             test_get_returns_the_object
        GET /categories/:id             test_get_one_returns_a_bare_object_as_documented (BUG-05, xfail)
        GET /categories/:id             test_get_one_returns_a_single_item_list_actual (BUG-05)
        HEAD /categories/:id            test_head_returns_headers_without_body
        POST /categories/:id            test_post_amends_only_the_given_fields
        POST /categories/:id            test_amend_does_not_change_other_objects
        PUT /categories/:id             test_put_with_title_returns_200
        DELETE /categories/:id          test_delete_removes_the_object
        DELETE /categories/:id          test_delete_twice_returns_404_the_second_time
        DELETE /categories/:id          test_delete_leaves_other_objects_untouched
        PATCH /categories/:id           test_patch_returns_405_without_side_effects
        OPTIONS /categories/:id         test_options_lists_allowed_methods
        GET/HEAD/POST/PUT/DELETE        test_nonexistent_id_returns_404
    """

    PARENT = "categories"

    @bug("BUG-04", documented=True)
    def test_put_amends_given_fields_as_documented(self, obj):
        """PUT /categories/:id: per the docs, PUT amends only the given fields, so the title survives."""
        response = call("PUT", f"/categories/{obj['id']}", {"description": "only description"})
        assert response.status_code == 200
        assert get_one("categories", obj["id"])["title"] == "instance under test"

    @bug("BUG-04")
    def test_put_without_title_is_rejected_actual(self, obj):
        """PUT /categories/:id: in reality PUT is a full replace, so a body without a title gets 400."""
        response = call("PUT", f"/categories/{obj['id']}", {"description": "only description"})
        assert response.status_code == 400
        assert "title : field is mandatory" in response.json()["errorMessages"][0]
        assert get_one("categories", obj["id"]) == obj


class TestCategoryQueryFilters:
    """GET /categories?field=value"""

    def test_filter_by_title(self, create):
        """GET /categories?title=... returns only the category with that exact title."""
        match = create("categories", title="unique-category-title")
        create("categories", title="another category")
        result = items(call("GET", "/categories", params={"title": "unique-category-title"}), "categories")
        assert ids(result) == {match["id"]}

    def test_filter_by_description(self, create):
        """GET /categories?description=... returns only the category with that exact description."""
        match = create("categories", title="c", description="unique-category-description")
        create("categories", title="c", description="other")
        result = items(call("GET", "/categories", params={"description": "unique-category-description"}), "categories")
        assert ids(result) == {match["id"]}


@pytest.mark.parametrize("relationship, child_collection", relationships_of("categories"))
class TestCategoryRelationships(RelationshipContract):
    """/categories/:id/<relationship> and /categories/:id/<relationship>/:id

    Runs once for todos (category -> todos) and once for projects (category -> projects).
    Every test is inherited from RelationshipContract:

    /categories/:id/<relationship>
        POST                    test_post_creates_relationship_with_empty_body
        POST                    test_duplicate_post_does_not_duplicate_relationship
        POST                    test_post_nonexistent_child_returns_400_as_documented (BUG-03, xfail)
        POST                    test_post_nonexistent_child_returns_404_actual (BUG-03)
        POST                    test_post_numeric_json_id_is_not_matched (BUG-06)
        GET                     test_get_lists_related_items
        GET                     test_get_with_no_links_returns_empty_list
        GET                     test_get_relationship_of_missing_parent_returns_no_items_as_documented (BUG-07, xfail)
        GET                     test_get_relationship_of_missing_parent_lists_every_parents_items_actual (BUG-07)
        HEAD                    test_head_returns_headers_without_body
        PUT/PATCH/DELETE        test_unsupported_methods_return_405_without_side_effects
        OPTIONS                 test_options_lists_allowed_methods

    /categories/:id/<relationship>/:id
        DELETE                  test_delete_item_removes_only_the_link
        DELETE                  test_delete_missing_item_returns_404
        PUT/PATCH               test_item_put_and_patch_return_405
        OPTIONS                 test_item_options_lists_only_delete
        GET/HEAD/POST           test_item_get_head_post_return_405_as_documented (BUG-01, xfail)
        GET/HEAD/POST           test_item_get_head_post_return_404_actual (BUG-01)
    """

    PARENT = "categories"


class TestCategoryRelationshipDirection:
    """POST /categories/:id/todos and /categories/:id/projects, seen from the other side

    todos and projects are one-way (as the /docs Relationships section says).

    /docs: "todos : category => todo" and "projects : category => project", separate
    from the "categories" relationships of todos and projects.
    """

    def test_todos_link_is_one_way(self, category, todo):
        """POST /categories/:id/todos: the category does not appear under GET /todos/:id/categories."""
        assert link("categories", category["id"], "todos", todo["id"]).status_code == 201
        assert related_ids(get_one("categories", category["id"]), "todos") == {todo["id"]}
        assert items(call("GET", f"/todos/{todo['id']}/categories"), "categories") == []

    def test_projects_link_is_one_way(self, category, project):
        """POST /categories/:id/projects: the category does not appear under GET /projects/:id/categories."""
        assert link("categories", category["id"], "projects", project["id"]).status_code == 201
        assert related_ids(get_one("categories", category["id"]), "projects") == {project["id"]}
        assert items(call("GET", f"/projects/{project['id']}/categories"), "categories") == []
        assert related_ids(get_one("projects", project["id"]), "categories") == set()


class TestCategoryDeleteSideEffects:
    """DELETE /categories/:id on a category that has relationships"""

    def test_deleting_a_linked_category_keeps_its_todos_and_projects(self, category, todo, project):
        """DELETE /categories/:id: the linked todo and project still exist afterwards."""
        assert link("categories", category["id"], "todos", todo["id"]).status_code == 201
        assert link("categories", category["id"], "projects", project["id"]).status_code == 201
        assert call("DELETE", f"/categories/{category['id']}").status_code == 200
        assert get_one("todos", todo["id"])["title"] == todo["title"]
        assert get_one("projects", project["id"])["title"] == project["title"]
