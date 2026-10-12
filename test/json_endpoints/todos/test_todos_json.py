"""Todos endpoints with JSON payloads (exploratory session 1).

Endpoint behaviour shared with projects and categories (status codes, OPTIONS,
404s, relationships, BUG-01/03/04, BUG-05) comes from contracts.py; this module
adds what is specific to todos.

Where each documented endpoint is tested:

    GET/HEAD/POST /todos                        TestTodosCollection, TestTodoMalformedJson
    GET /todos?field=value                      TestTodoQueryFilters
    GET/HEAD/POST/PUT/DELETE /todos/:id         TestTodoInstance, TestTodoDeleteSideEffects
    GET/HEAD/POST /todos/:id/tasksof            TestTodoRelationships[tasksof-projects],
                                                TestTodoRelationshipDirection
    DELETE /todos/:id/tasksof/:id               TestTodoRelationships[tasksof-projects]
    GET/HEAD/POST /todos/:id/categories         TestTodoRelationships[categories-categories],
                                                TestTodoRelationshipDirection
    DELETE /todos/:id/categories/:id            TestTodoRelationships[categories-categories]

Each class docstring lists the tests it inherits from contracts.py. The first line
of a class docstring is used as its header in the test output (see reporting.py).
"""

import pytest

from contracts import CollectionContract, InstanceContract, RelationshipContract, relationships_of
from support import JSON, bug, call, content_type, get_one, ids, items, link, related_ids, snapshot


class TestTodosCollection(CollectionContract):
    """/todos

    Inherited from CollectionContract:
        GET /todos                  test_get_lists_created_objects
        HEAD /todos                 test_head_returns_headers_without_body
        POST /todos                 test_post_returns_201_and_location_header
        POST /todos                 test_post_with_client_supplied_id_returns_400
        PUT/PATCH/DELETE /todos     test_unsupported_methods_return_405_without_side_effects
        OPTIONS /todos              test_options_lists_allowed_methods
    """

    PARENT = "todos"

    def test_post_creates_todo_with_defaults(self, create):
        """POST /todos: a todo created with only a title gets doneStatus false and an empty description."""
        todo = create("todos", title="buy milk")
        assert (todo["title"], todo["doneStatus"], todo["description"]) == ("buy milk", "false", "")
        assert get_one("todos", todo["id"]) == todo

    def test_post_accepts_all_documented_fields(self, create):
        """POST /todos: title, description and doneStatus are all stored."""
        todo = create("todos", title="full", description="all fields", doneStatus=True)
        assert (todo["title"], todo["description"], todo["doneStatus"]) == ("full", "all fields", "true")

    @pytest.mark.parametrize("body, message", [
        ({"title": ""}, "title : can not be empty"),
        ({"description": "no title"}, "title : field is mandatory"),
        ({"title": "t", "doneStatus": "banana"}, "doneStatus should be BOOLEAN"),
    ], ids=["empty-title", "missing-title", "non-boolean-doneStatus"])
    def test_invalid_create_returns_400_without_side_effects(self, body, message):
        """POST /todos: an invalid body is rejected with 400 and nothing is created."""
        before = snapshot()
        response = call("POST", "/todos", body)
        assert response.status_code == 400
        assert message in response.json()["errorMessages"][0]
        assert snapshot() == before


class TestTodoInstance(InstanceContract):
    """/todos/:id

    Inherited from InstanceContract:
        GET /todos/:id              test_get_returns_the_object
        GET /todos/:id              test_get_one_returns_a_bare_object_as_documented (BUG-05, xfail)
        GET /todos/:id              test_get_one_returns_a_single_item_list_actual (BUG-05)
        HEAD /todos/:id             test_head_returns_headers_without_body
        POST /todos/:id             test_post_amends_only_the_given_fields
        POST /todos/:id             test_amend_does_not_change_other_objects
        PUT /todos/:id              test_put_with_title_returns_200
        DELETE /todos/:id           test_delete_removes_the_object
        DELETE /todos/:id           test_delete_twice_returns_404_the_second_time
        DELETE /todos/:id           test_delete_leaves_other_objects_untouched
        PATCH /todos/:id            test_patch_returns_405_without_side_effects
        OPTIONS /todos/:id          test_options_lists_allowed_methods
        GET/HEAD/POST/PUT/DELETE    test_nonexistent_id_returns_404
    """

    PARENT = "todos"

    def test_post_can_mark_todo_done(self, obj):
        """POST /todos/:id: amending doneStatus to true marks the todo done."""
        assert call("POST", f"/todos/{obj['id']}", {"doneStatus": True}).status_code == 200
        assert get_one("todos", obj["id"])["doneStatus"] == "true"

    def test_put_clears_fields_not_supplied(self, obj):
        """PUT /todos/:id: fields left out of the body are reset (description becomes empty)."""
        assert call("PUT", f"/todos/{obj['id']}", {"title": "replaced"}).status_code == 200
        assert get_one("todos", obj["id"])["description"] == ""

    @bug("BUG-04", documented=True)
    def test_put_amends_given_fields_as_documented(self, obj):
        """PUT /todos/:id: per the docs, PUT amends only the given fields, so the title survives."""
        response = call("PUT", f"/todos/{obj['id']}", {"description": "only description"})
        assert response.status_code == 200
        assert get_one("todos", obj["id"])["title"] == "instance under test"

    @bug("BUG-04")
    def test_put_without_title_is_rejected_actual(self, obj):
        """PUT /todos/:id: in reality PUT is a full replace, so a body without a title gets 400."""
        response = call("PUT", f"/todos/{obj['id']}", {"description": "only description"})
        assert response.status_code == 400
        assert "title : field is mandatory" in response.json()["errorMessages"][0]
        assert get_one("todos", obj["id"]) == obj


class TestTodoQueryFilters:
    """GET /todos?field=value

    URL query parameters filter the collection on any field.
    """

    def test_filter_by_done_status_true(self, create):
        """GET /todos?doneStatus=true returns only done todos."""
        done = create("todos", title="done one", doneStatus=True)
        open_ = create("todos", title="open one")
        result = items(call("GET", "/todos", params={"doneStatus": "true"}), "todos")
        assert done["id"] in ids(result)
        assert open_["id"] not in ids(result)
        assert all(t["doneStatus"] == "true" for t in result)

    def test_filter_by_done_status_false(self, create):
        """GET /todos?doneStatus=false returns only todos that are not done."""
        done = create("todos", title="done one", doneStatus=True)
        open_ = create("todos", title="open one")
        result = items(call("GET", "/todos", params={"doneStatus": "false"}), "todos")
        assert open_["id"] in ids(result)
        assert done["id"] not in ids(result)
        assert all(t["doneStatus"] == "false" for t in result)

    def test_filter_by_title(self, create):
        """GET /todos?title=... returns only the todo with that exact title."""
        match = create("todos", title="unique-filter-title")
        create("todos", title="something else")
        result = items(call("GET", "/todos", params={"title": "unique-filter-title"}), "todos")
        assert ids(result) == {match["id"]}

    def test_combined_filters_must_all_match(self, create):
        """GET /todos?title=...&doneStatus=...: a todo must match every filter to be returned."""
        match = create("todos", title="combo", doneStatus=True)
        create("todos", title="combo")
        result = items(call("GET", "/todos", params={"title": "combo", "doneStatus": "true"}), "todos")
        assert ids(result) == {match["id"]}

    def test_filter_with_no_match_returns_empty_list(self):
        """GET /todos?title=...: a filter nothing matches gives 200 and an empty list."""
        response = call("GET", "/todos", params={"title": "no todo has this title 8c1f"})
        assert response.status_code == 200
        assert items(response, "todos") == []


class TestTodoMalformedJson:
    """POST /todos with a malformed JSON body

    BUG-02: the 400 for malformed JSON is labelled text/html.
    """

    BROKEN = '{"title":"broken"'

    def test_malformed_json_returns_400_without_side_effects(self):
        """POST /todos: a malformed JSON body gets 400 and nothing is created."""
        before = snapshot()
        assert call("POST", "/todos", self.BROKEN, content_type=JSON).status_code == 400
        assert snapshot() == before

    @bug("BUG-02", documented=True)
    def test_malformed_json_error_is_labelled_json_as_expected(self):
        """POST /todos: the 400 error should have Content-Type application/json."""
        response = call("POST", "/todos", self.BROKEN, content_type=JSON)
        assert content_type(response) == JSON

    @bug("BUG-02")
    def test_malformed_json_error_is_labelled_html_actual(self):
        """POST /todos: the 400 error is actually labelled text/html, though its body is JSON."""
        response = call("POST", "/todos", self.BROKEN, content_type=JSON)
        assert content_type(response) == "text/html"
        # The body is really JSON, and it leaks a Java exception name.
        assert "java.io.EOFException" in response.json()["errorMessages"][0]


@pytest.mark.parametrize("relationship, child_collection", relationships_of("todos"))
class TestTodoRelationships(RelationshipContract):
    """/todos/:id/<relationship> and /todos/:id/<relationship>/:id

    Runs once for tasksof (todo -> projects) and once for categories (todo -> categories).
    Every test is inherited from RelationshipContract:

    /todos/:id/<relationship>
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

    /todos/:id/<relationship>/:id
        DELETE                  test_delete_item_removes_only_the_link
        DELETE                  test_delete_missing_item_returns_404
        PUT/PATCH               test_item_put_and_patch_return_405
        OPTIONS                 test_item_options_lists_only_delete
        GET/HEAD/POST           test_item_get_head_post_return_405_as_documented (BUG-01, xfail)
        GET/HEAD/POST           test_item_get_head_post_return_404_actual (BUG-01)
    """

    PARENT = "todos"


class TestTodoRelationshipDirection:
    """POST /todos/:id/tasksof and /todos/:id/categories, seen from the other side

    tasks/tasksof is two-way, categories is one-way (as the /docs Relationships section says).

    /docs: "tasks/tasksof : project =(tasks)=> todo / todo =(tasksof)=> project"
    and "categories : todo => category".
    """

    def test_tasksof_link_is_visible_from_the_project(self, todo, project):
        """POST /todos/:id/tasksof: the todo then appears under GET /projects/:id/tasks."""
        assert link("todos", todo["id"], "tasksof", project["id"]).status_code == 201
        assert todo["id"] in ids(items(call("GET", f"/projects/{project['id']}/tasks"), "todos"))
        assert todo["id"] in related_ids(get_one("projects", project["id"]), "tasks")

    def test_categories_link_is_one_way(self, todo, category):
        """POST /todos/:id/categories: the todo does not appear under GET /categories/:id/todos."""
        assert link("todos", todo["id"], "categories", category["id"]).status_code == 201
        assert related_ids(get_one("todos", todo["id"]), "categories") == {category["id"]}
        assert items(call("GET", f"/categories/{category['id']}/todos"), "todos") == []
        assert related_ids(get_one("categories", category["id"]), "todos") == set()


class TestTodoDeleteSideEffects:
    """DELETE /todos/:id on a todo that has relationships"""

    def test_deleting_a_linked_todo_removes_it_from_the_project(self, todo, project):
        """DELETE /todos/:id: the todo disappears from its project's tasks."""
        assert link("todos", todo["id"], "tasksof", project["id"]).status_code == 201
        assert call("DELETE", f"/todos/{todo['id']}").status_code == 200
        assert todo["id"] not in related_ids(get_one("projects", project["id"]), "tasks")
        assert todo["id"] not in ids(items(call("GET", f"/projects/{project['id']}/tasks"), "todos"))

    def test_deleting_a_linked_todo_keeps_the_category(self, todo, category):
        """DELETE /todos/:id: the linked category is left unchanged."""
        assert link("todos", todo["id"], "categories", category["id"]).status_code == 201
        assert call("DELETE", f"/todos/{todo['id']}").status_code == 200
        assert get_one("categories", category["id"]) == category
