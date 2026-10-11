"""Todos endpoints with JSON payloads (exploratory session 1).

Endpoint behaviour shared with projects and categories (status codes, OPTIONS,
404s, relationships, BUG-01/03/04, DOC-02) comes from contracts.py; this module
adds what is specific to todos.
"""

import pytest

from contracts import CollectionContract, InstanceContract, RelationshipContract, relationships_of
from support import JSON, bug, call, content_type, get_one, ids, items, link, related_ids, snapshot


class TestTodosCollection(CollectionContract):
    PARENT = "todos"

    def test_post_creates_todo_with_defaults(self, create):
        todo = create("todos", title="buy milk")
        assert (todo["title"], todo["doneStatus"], todo["description"]) == ("buy milk", "false", "")
        assert get_one("todos", todo["id"]) == todo

    def test_post_accepts_all_documented_fields(self, create):
        todo = create("todos", title="full", description="all fields", doneStatus=True)
        assert (todo["title"], todo["description"], todo["doneStatus"]) == ("full", "all fields", "true")

    @pytest.mark.parametrize("body, message", [
        ({"title": ""}, "title : can not be empty"),
        ({"description": "no title"}, "title : field is mandatory"),
        ({"title": "t", "doneStatus": "banana"}, "doneStatus should be BOOLEAN"),
    ], ids=["empty-title", "missing-title", "non-boolean-doneStatus"])
    def test_invalid_create_returns_400_without_side_effects(self, body, message):
        before = snapshot()
        response = call("POST", "/todos", body)
        assert response.status_code == 400
        assert message in response.json()["errorMessages"][0]
        assert snapshot() == before


class TestTodoInstance(InstanceContract):
    PARENT = "todos"

    def test_post_can_mark_todo_done(self, obj):
        assert call("POST", f"/todos/{obj['id']}", {"doneStatus": True}).status_code == 200
        assert get_one("todos", obj["id"])["doneStatus"] == "true"

    def test_put_clears_fields_not_supplied(self, obj):
        assert call("PUT", f"/todos/{obj['id']}", {"title": "replaced"}).status_code == 200
        assert get_one("todos", obj["id"])["description"] == ""

    @bug("DOC-01", documented=True)
    def test_put_amends_given_fields_as_documented(self, obj):
        response = call("PUT", f"/todos/{obj['id']}", {"description": "only description"})
        assert response.status_code == 200
        assert get_one("todos", obj["id"])["title"] == "instance under test"

    @bug("DOC-01")
    def test_put_without_title_is_rejected_actual(self, obj):
        response = call("PUT", f"/todos/{obj['id']}", {"description": "only description"})
        assert response.status_code == 400
        assert "title : field is mandatory" in response.json()["errorMessages"][0]
        assert get_one("todos", obj["id"]) == obj


class TestTodoQueryFilters:
    """URL query parameters filter the collection on any field."""

    def test_filter_by_done_status_true(self, create):
        done = create("todos", title="done one", doneStatus=True)
        open_ = create("todos", title="open one")
        result = items(call("GET", "/todos", params={"doneStatus": "true"}), "todos")
        assert done["id"] in ids(result)
        assert open_["id"] not in ids(result)
        assert all(t["doneStatus"] == "true" for t in result)

    def test_filter_by_done_status_false(self, create):
        done = create("todos", title="done one", doneStatus=True)
        open_ = create("todos", title="open one")
        result = items(call("GET", "/todos", params={"doneStatus": "false"}), "todos")
        assert open_["id"] in ids(result)
        assert done["id"] not in ids(result)
        assert all(t["doneStatus"] == "false" for t in result)

    def test_filter_by_title(self, create):
        match = create("todos", title="unique-filter-title")
        create("todos", title="something else")
        result = items(call("GET", "/todos", params={"title": "unique-filter-title"}), "todos")
        assert ids(result) == {match["id"]}

    def test_combined_filters_must_all_match(self, create):
        match = create("todos", title="combo", doneStatus=True)
        create("todos", title="combo")
        result = items(call("GET", "/todos", params={"title": "combo", "doneStatus": "true"}), "todos")
        assert ids(result) == {match["id"]}

    def test_filter_with_no_match_returns_empty_list(self):
        response = call("GET", "/todos", params={"title": "no todo has this title 8c1f"})
        assert response.status_code == 200
        assert items(response, "todos") == []


class TestTodoMalformedJson:
    """BUG-02: the 400 for malformed JSON is labelled text/html."""

    BROKEN = '{"title":"broken"'

    def test_malformed_json_returns_400_without_side_effects(self):
        before = snapshot()
        assert call("POST", "/todos", self.BROKEN, content_type=JSON).status_code == 400
        assert snapshot() == before

    @bug("BUG-02", documented=True)
    def test_malformed_json_error_is_labelled_json_as_expected(self):
        response = call("POST", "/todos", self.BROKEN, content_type=JSON)
        assert content_type(response) == JSON

    @bug("BUG-02")
    def test_malformed_json_error_is_labelled_html_actual(self):
        response = call("POST", "/todos", self.BROKEN, content_type=JSON)
        assert content_type(response) == "text/html"
        # The body is really JSON, and it leaks a Java exception name.
        assert "java.io.EOFException" in response.json()["errorMessages"][0]


@pytest.mark.parametrize("relationship, child_collection", relationships_of("todos"))
class TestTodoRelationships(RelationshipContract):
    PARENT = "todos"


class TestTodoRelationshipDirection:
    """tasks/tasksof is two-way, categories is one-way (as the /docs Relationships section says).

    /docs: "tasks/tasksof : project =(tasks)=> todo / todo =(tasksof)=> project"
    and "categories : todo => category".
    """

    def test_tasksof_link_is_visible_from_the_project(self, todo, project):
        assert link("todos", todo["id"], "tasksof", project["id"]).status_code == 201
        assert todo["id"] in ids(items(call("GET", f"/projects/{project['id']}/tasks"), "todos"))
        assert todo["id"] in related_ids(get_one("projects", project["id"]), "tasks")

    def test_categories_link_is_one_way(self, todo, category):
        assert link("todos", todo["id"], "categories", category["id"]).status_code == 201
        assert related_ids(get_one("todos", todo["id"]), "categories") == {category["id"]}
        assert items(call("GET", f"/categories/{category['id']}/todos"), "todos") == []
        assert related_ids(get_one("categories", category["id"]), "todos") == set()


class TestTodoDeleteSideEffects:
    def test_deleting_a_linked_todo_removes_it_from_the_project(self, todo, project):
        assert link("todos", todo["id"], "tasksof", project["id"]).status_code == 201
        assert call("DELETE", f"/todos/{todo['id']}").status_code == 200
        assert todo["id"] not in related_ids(get_one("projects", project["id"]), "tasks")
        assert todo["id"] not in ids(items(call("GET", f"/projects/{project['id']}/tasks"), "todos"))

    def test_deleting_a_linked_todo_keeps_the_category(self, todo, category):
        assert link("todos", todo["id"], "categories", category["id"]).status_code == 201
        assert call("DELETE", f"/todos/{todo['id']}").status_code == 200
        assert get_one("categories", category["id"]) == category
