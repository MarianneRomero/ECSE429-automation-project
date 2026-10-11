"""Projects endpoints with JSON payloads (exploratory session 2).

Endpoint behaviour shared with todos and categories comes from contracts.py;
this module adds what is specific to projects.
"""

import pytest

from contracts import CollectionContract, InstanceContract, RelationshipContract, relationships_of
from support import bug, call, get_one, ids, items, link, related_ids, snapshot


class TestProjectsCollection(CollectionContract):
    PARENT = "projects"

    def test_post_creates_project_with_defaults(self, create):
        project = create("projects", title="launch")
        assert project["title"] == "launch"
        assert (project["active"], project["completed"], project["description"]) == ("false", "false", "")
        assert get_one("projects", project["id"]) == project

    def test_post_without_title_is_allowed(self, create):
        project = create("projects")
        assert project["title"] == ""

    def test_post_accepts_all_documented_fields(self, create):
        project = create("projects", title="full", description="d", active=True, completed=True)
        assert (project["active"], project["completed"]) == ("true", "true")

    @pytest.mark.parametrize("field", ["completed", "active"])
    def test_non_boolean_flag_returns_400_without_side_effects(self, field):
        before = snapshot()
        response = call("POST", "/projects", {"title": "t", field: "yes"})
        assert response.status_code == 400
        assert f"{field} should be BOOLEAN" in response.json()["errorMessages"][0]
        assert snapshot() == before


class TestProjectInstance(InstanceContract):
    PARENT = "projects"

    def test_post_can_mark_project_completed(self, obj):
        assert call("POST", f"/projects/{obj['id']}", {"completed": True}).status_code == 200
        assert get_one("projects", obj["id"])["completed"] == "true"

    def test_amend_with_non_boolean_flag_returns_400_without_side_effects(self, obj):
        response = call("POST", f"/projects/{obj['id']}", {"completed": "yes"})
        assert response.status_code == 400
        assert get_one("projects", obj["id"]) == obj

    @bug("DOC-01", documented=True)
    def test_put_amends_given_fields_as_documented(self, obj):
        assert call("PUT", f"/projects/{obj['id']}", {"title": "replaced"}).status_code == 200
        assert get_one("projects", obj["id"])["description"] == "original"

    @bug("DOC-01")
    def test_put_replaces_and_clears_missing_fields_actual(self, obj):
        assert call("PUT", f"/projects/{obj['id']}", {"title": "replaced"}).status_code == 200
        replaced = get_one("projects", obj["id"])
        assert (replaced["title"], replaced["description"]) == ("replaced", "")


class TestProjectQueryFilters:
    @pytest.mark.parametrize("field", ["active", "completed"])
    def test_filter_by_boolean_flag(self, create, field):
        flagged = create("projects", title="flagged", **{field: True})
        plain = create("projects", title="plain")
        result = items(call("GET", "/projects", params={field: "true"}), "projects")
        assert flagged["id"] in ids(result)
        assert plain["id"] not in ids(result)
        assert all(p[field] == "true" for p in result)

    def test_filter_by_title(self, create):
        match = create("projects", title="unique-project-title")
        create("projects", title="another project")
        result = items(call("GET", "/projects", params={"title": "unique-project-title"}), "projects")
        assert ids(result) == {match["id"]}


@pytest.mark.parametrize("relationship, child_collection", relationships_of("projects"))
class TestProjectRelationships(RelationshipContract):
    PARENT = "projects"


class TestProjectRelationshipVisibility:
    def test_tasks_link_is_visible_from_the_todo(self, project, todo):
        assert link("projects", project["id"], "tasks", todo["id"]).status_code == 201
        assert related_ids(get_one("todos", todo["id"]), "tasksof") == {project["id"]}
        assert project["id"] in ids(items(call("GET", f"/todos/{todo['id']}/tasksof"), "projects"))


class TestProjectDeleteSideEffects:
    def test_deleting_a_project_removes_it_from_its_todos(self, project, todo):
        assert link("projects", project["id"], "tasks", todo["id"]).status_code == 201
        assert call("DELETE", f"/projects/{project['id']}").status_code == 200
        survivor = get_one("todos", todo["id"])
        assert related_ids(survivor, "tasksof") == set()
        assert survivor["title"] == todo["title"]
