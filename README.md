# ECSE429-automation-project

Unit tests (pytest + requests) for the Todo Manager REST API, written from the
findings of exploratory sessions 1–3.

## Running

1. Start the API: `java -jar runTodoManagerRestAPI-1.5.5.jar` (listens on `http://localhost:4567`).
2. Install dependencies and run:

   ```sh
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/pytest
   ```

Set `TODO_API_URL` to test a server on another address. Tests run in a random
order on every run (pytest-randomly); reproduce an order with `-p randomly --randomly-seed=<n>`,
or use `-p no:randomly` to run in file order (each documented/actual pair then sits together).

Output is grouped under a header per format and resource (e.g. `JSON · Todos`) and a
sub-header per endpoint (`test/reporting.py`). Use `-v` for pytest's standard output.

## Layout

| Path | Contents |
|---|---|
| `test/support.py` | HTTP helpers, bug registry (`BUGS`) and the `@bug` decorator |
| `test/conftest.py` | Readiness check, `create` / `missing_id` fixtures with cleanup, bug summary |
| `test/contracts.py` | Behaviour shared by todos, projects and categories |
| `test/json_endpoints/<resource>/` | JSON tests per resource |
| `test/xml_endpoints/<resource>/` | XML tests per resource |
| `test/test_docs.py` | `/docs` and `/docs/swagger` |

`/shutdown` is not tested, since it stops the server.

## How bugs are reported

Every behaviour that differs from the documentation has two tests:

- `..._as_documented` / `..._as_expected` asserts the documented behaviour. It is
  a strict `xfail`, so it shows as **XFAIL** with the bug ID as the reason.
- `..._actual` asserts what the server really does and **passes**.

The run ends with a "Bugs demonstrated" section listing each bug ID. If a bug is
fixed, its documented test starts passing, which strict xfail reports as a
failure, so the pair gets updated.

| ID | Summary |
|---|---|
| BUG-01 | GET/HEAD/POST on relationship item URLs return 404 instead of the documented 405 |
| BUG-02 | 400 errors for malformed JSON/XML bodies are labelled `Content-Type: text/html` |
| BUG-03 | POST to a relationship with a nonexistent id returns 404, Swagger documents 400 |
| BUG-04 | `GET /:id/<relationship>` for a nonexistent `:id` returns every parent's related items |
| BUG-06 | XML relationship POST cannot link an existing object: `<id>` is read as a number, 404 |
| DOC-01 | `PUT /:id` is a full replace, but the docs describe it as an amend like POST |
| DOC-02 | `GET /:id` wraps the single object in a list; the docs example shows a bare object |
