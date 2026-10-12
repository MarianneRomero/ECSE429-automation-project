"""Projects endpoints with JSON payloads (exploratory session 2).

Endpoint behaviour shared with todos and categories comes from contracts.py;
this module adds what is specific to projects.

Where each documented endpoint is tested:

    GET/HEAD/POST /projects                     TestProjectsCollection
    GET /projects?field=value                   TestProjectQueryFilters
    GET/HEAD/POST/PUT/DELETE /projects/:id      TestProjectInstance, TestProjectDeleteSideEffects
    GET/HEAD/POST /projects/:id/tasks           TestProjectRelationships[tasks-todos],
                                                TestProjectRelationshipVisibility
    DELETE /projects/:id/tasks/:id              TestProjectRelationships[tasks-todos]
    GET/HEAD/POST /projects/:id/categories      TestProjectRelationships[categories-categories]
    DELETE /projects/:id/categories/:id         TestProjectRelationships[categories-categories]

Each class docstring lists the tests it inherits from contracts.py. The first line
of a class docstring is used as its header in the test output (see reporting.py).
"""

import pytest

from contracts import CollectionContract, InstanceContract, RelationshipContract, relationships_of
from support import bug, call, get_one, ids, items, link, related_ids, snapshot


class TestProjectsCollection(CollectionContract):
    """/projects

    Inherited from CollectionContract:
        GET /projects                   test_get_lists_created_objects
        HEAD /projects                  test_head_returns_headers_without_body
        POST /projects                  test_post_returns_201_and_location_header
        POST /projects                  test_post_with_client_supplied_id_returns_400
        PUT/PATCH/DELETE /projects      test_unsupported_methods_return_405_without_side_effects
        OPTIONS /projects               test_options_lists_allowed_methods
    """

    PARENT = "projects"

    def test_post_creates_project_with_defaults(self, create):
        """POST /projects: a project created with only a title is inactive, not completed, with an empty description."""
        project = create("projects", title="launch")
        assert project["title"] == "launch"
        assert (project["active"], project["completed"], project["description"]) == ("false", "false", "")
        assert get_one("projects", project["id"]) == project

    def test_post_without_title_is_allowed(self, create):
        """POST /projects: unlike todos, a project can be created without a title."""
        project = create("projects")
        assert project["title"] == ""

    def test_post_accepts_all_documented_fields(self, create):
        """POST /projects: title, description, active and completed are all stored."""
        project = create("projects", title="full", description="d", active=True, completed=True)
        assert (project["active"], project["completed"]) == ("true", "true")

    @pytest.mark.parametrize("field", ["completed", "active"])
    def test_non_boolean_flag_returns_400_without_side_effects(self, field):
        """POST /projects: a non-boolean active/completed is rejected with 400 and nothing is created."""
        before = snapshot()
        response = call("POST", "/projects", {"title": "t", field: "yes"})
        assert response.status_code == 400
        assert f"{field} should be BOOLEAN" in response.json()["errorMessages"][0]
        assert snapshot() == before


class TestProjectInstance(InstanceContract):
    """/projects/:id

    Inherited from InstanceContract:
        GET /projects/:id               test_get_returns_the_object
        GET /projects/:id               test_get_one_returns_a_bare_object_as_documented (BUG-05, xfail)
        GET /projects/:id               test_get_one_returns_a_single_item_list_actual (BUG-05)
        HEAD /projects/:id              test_head_returns_headers_without_body
        POST /projects/:id              test_post_amends_only_the_given_fields
        POST /projects/:id              test_amend_does_not_change_other_objects
        PUT /projects/:id               test_put_with_title_returns_200
        DELETE /projects/:id            test_delete_removes_the_object
        DELETE /projects/:id            test_delete_twice_returns_404_the_second_time
        DELETE /projects/:id            test_delete_leaves_other_objects_untouched
        PATCH /projects/:id             test_patch_returns_405_without_side_effects
        OPTIONS /projects/:id           test_options_lists_allowed_methods
        GET/HEAD/POST/PUT/DELETE        test_nonexistent_id_returns_404
    """

    PARENT = "projects"

    def test_post_can_mark_project_completed(self, obj):
        """POST /projects/:id: amending completed to true marks the project completed."""
        assert call("POST", f"/projects/{obj['id']}", {"completed": True}).status_code == 200
        assert get_one("projects", obj["id"])["completed"] == "true"

    def test_amend_with_non_boolean_flag_returns_400_without_side_effects(self, obj):
        """POST /projects/:id: a non-boolean completed is rejected with 400 and the project is unchanged."""
        response = call("POST", f"/projects/{obj['id']}", {"completed": "yes"})
        assert response.status_code == 400
        assert get_one("projects", obj["id"]) == obj

    @bug("BUG-04", documented=True)
    def test_put_amends_given_fields_as_documented(self, obj):
        """PUT /projects/:id: per the docs, PUT amends only the given fields, so the description survives."""
        assert call("PUT", f"/projects/{obj['id']}", {"title": "replaced"}).status_code == 200
        assert get_one("projects", obj["id"])["description"] == "original"

    @bug("BUG-04")
    def test_put_replaces_and_clears_missing_fields_actual(self, obj):
        """PUT /projects/:id: in reality PUT is a full replace, so the description is cleared."""
        assert call("PUT", f"/projects/{obj['id']}", {"title": "replaced"}).status_code == 200
        replaced = get_one("projects", obj["id"])
        assert (replaced["title"], replaced["description"]) == ("replaced", "")


class TestProjectQueryFilters:
    """GET /projects?field=value"""

    @pytest.mark.parametrize("field", ["active", "completed"])
    def test_filter_by_boolean_flag(self, create, field):
        """GET /projects?active=true / ?completed=true returns only projects with that flag set."""
        flagged = create("projects", title="flagged", **{field: True})
        plain = create("projects", title="plain")
        result = items(call("GET", "/projects", params={field: "true"}), "projects")
        assert flagged["id"] in ids(result)
        assert plain["id"] not in ids(result)
        assert all(p[field] == "true" for p in result)

    def test_filter_by_title(self, create):
        """GET /projects?title=... returns only the project with that exact title."""
        match = create("projects", title="unique-project-title")
        create("projects", title="another project")
        result = items(call("GET", "/projects", params={"title": "unique-project-title"}), "projects")
        assert ids(result) == {match["id"]}


@pytest.mark.parametrize("relationship, child_collection", relationships_of("projects"))
class TestProjectRelationships(RelationshipContract):
    """/projects/:id/<relationship> and /projects/:id/<relationship>/:id

    Runs once for tasks (project -> todos) and once for categories (project -> categories).
    Every test is inherited from RelationshipContract:

    /projects/:id/<relationship>
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

    /projects/:id/<relationship>/:id
        DELETE                  test_delete_item_removes_only_the_link
        DELETE                  test_delete_missing_item_returns_404
        PUT/PATCH               test_item_put_and_patch_return_405
        OPTIONS                 test_item_options_lists_only_delete
        GET/HEAD/POST           test_item_get_head_post_return_405_as_documented (BUG-01, xfail)
        GET/HEAD/POST           test_item_get_head_post_return_404_actual (BUG-01)
    """

    PARENT = "projects"


class TestProjectRelationshipVisibility:
    """POST /projects/:id/tasks, seen from the todo side"""

    def test_tasks_link_is_visible_from_the_todo(self, project, todo):
        """POST /projects/:id/tasks: the project then appears under GET /todos/:id/tasksof."""
        assert link("projects", project["id"], "tasks", todo["id"]).status_code == 201
        assert related_ids(get_one("todos", todo["id"]), "tasksof") == {project["id"]}
        assert project["id"] in ids(items(call("GET", f"/todos/{todo['id']}/tasksof"), "projects"))


class TestProjectDeleteSideEffects:
    """DELETE /projects/:id on a project that has tasks"""

    def test_deleting_a_project_removes_it_from_its_todos(self, project, todo):
        """DELETE /projects/:id: the todo survives but no longer lists the project in tasksof."""
        assert link("projects", project["id"], "tasks", todo["id"]).status_code == 201
        assert call("DELETE", f"/projects/{project['id']}").status_code == 200
        survivor = get_one("todos", todo["id"])
        assert related_ids(survivor, "tasksof") == set()
        assert survivor["title"] == todo["title"]
