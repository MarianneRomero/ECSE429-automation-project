#!/bin/bash
# ECSE 429 Part A - Session 1 (todos): all 6 todo endpoints x 7 verbs = 42 requests.
# Responses are requested as XML (Accept header), printed, and saved to evidence/xml/<name>.xml
# Run from the repo root (the folder that contains evidence/ and scripts/):
#   bash scripts/todos_xml.sh | tee results_todos.txt
# RESTART THE JAR BEFORE AND AFTER (the run changes data).

# Saves into ./evidence/todos/xml, relative to the folder you run this from (run it from the repo root).
mkdir -p evidence/todos/xml
B=http://localhost:4567

x() {  # usage: x VERB PATH FILENAME [JSON_BODY]
  echo "=== $1 $2"
  if [ "$1" = HEAD ]; then
    curl -s -I -H "Accept: application/xml" $B$2 | tee evidence/todos/xml/$3.xml
  elif [ -n "$4" ]; then
    curl -s -i -X $1 $B$2 -H "Content-Type: application/json" -H "Accept: application/xml" -d "$4" | tee evidence/todos/xml/$3.xml
  else
    curl -s -i -X $1 $B$2 -H "Accept: application/xml" | tee evidence/todos/xml/$3.xml
  fi
  echo
}

# helper: create an object and print its id   usage: mk todos | mk categories | mk projects
mk() { curl -s -X POST $B/$1 -H "Content-Type: application/json" -d '{"title":"probe"}' | grep -o '"id":"[0-9]*"' | head -1 | grep -o '[0-9]*'; }

T=$(mk todos); C=$(mk categories); P=$(mk projects)
echo "Using todo=$T category=$C project=$P"

# ===== 1. /todos (7) =====
x GET     /todos todos_GET
x HEAD    /todos todos_HEAD
x POST    /todos todos_POST '{"title":"probe"}'
x PUT     /todos todos_PUT
x PATCH   /todos todos_PATCH
x DELETE  /todos todos_DELETE
x OPTIONS /todos todos_OPTIONS

# ===== 2. /todos/:id (7) =====
x GET     /todos/$T todos_id_GET
x HEAD    /todos/$T todos_id_HEAD
x POST    /todos/$T todos_id_POST '{"description":"changed"}'
x PUT     /todos/$T todos_id_PUT '{"title":"replaced"}'
x PATCH   /todos/$T todos_id_PATCH
x OPTIONS /todos/$T todos_id_OPTIONS
D=$(mk todos)   # throwaway so the main todo survives
x DELETE  /todos/$D todos_id_DELETE
x DELETE  /todos/$D todos_id_DELETE_again

# ===== 3. /todos/:id/categories (7) =====
x POST    /todos/$T/categories todos_id_categories_POST "{\"id\":\"$C\"}"
x GET     /todos/$T/categories todos_id_categories_GET
x HEAD    /todos/$T/categories todos_id_categories_HEAD
x PUT     /todos/$T/categories todos_id_categories_PUT
x PATCH   /todos/$T/categories todos_id_categories_PATCH
x DELETE  /todos/$T/categories todos_id_categories_DELETE
x OPTIONS /todos/$T/categories todos_id_categories_OPTIONS

# ===== 4. /todos/:id/categories/:id (7)  BUG-01: GET, HEAD, POST should be 405 =====
x GET     /todos/$T/categories/$C todos_id_categories_id_GET
x HEAD    /todos/$T/categories/$C todos_id_categories_id_HEAD
x POST    /todos/$T/categories/$C todos_id_categories_id_POST
x PUT     /todos/$T/categories/$C todos_id_categories_id_PUT
x PATCH   /todos/$T/categories/$C todos_id_categories_id_PATCH
x OPTIONS /todos/$T/categories/$C todos_id_categories_id_OPTIONS
x DELETE  /todos/$T/categories/$C todos_id_categories_id_DELETE

# ===== 5. /todos/:id/tasksof (7) =====
x POST    /todos/$T/tasksof todos_id_tasksof_POST "{\"id\":\"$P\"}"
x GET     /todos/$T/tasksof todos_id_tasksof_GET
x HEAD    /todos/$T/tasksof todos_id_tasksof_HEAD
x PUT     /todos/$T/tasksof todos_id_tasksof_PUT
x PATCH   /todos/$T/tasksof todos_id_tasksof_PATCH
x DELETE  /todos/$T/tasksof todos_id_tasksof_DELETE
x OPTIONS /todos/$T/tasksof todos_id_tasksof_OPTIONS

# ===== 6. /todos/:id/tasksof/:id (7)  BUG-01: GET, HEAD, POST should be 405 =====
x GET     /todos/$T/tasksof/$P todos_id_tasksof_id_GET
x HEAD    /todos/$T/tasksof/$P todos_id_tasksof_id_HEAD
x POST    /todos/$T/tasksof/$P todos_id_tasksof_id_POST
x PUT     /todos/$T/tasksof/$P todos_id_tasksof_id_PUT
x PATCH   /todos/$T/tasksof/$P todos_id_tasksof_id_PATCH
x OPTIONS /todos/$T/tasksof/$P todos_id_tasksof_id_OPTIONS
x DELETE  /todos/$T/tasksof/$P todos_id_tasksof_id_DELETE

# ===== Summary: status line of every saved file =====
echo; echo "--- status of each saved response ---"
for f in evidence/xml/todos_*.xml; do echo "$(basename $f .xml): $(head -1 $f | tr -d '\r')"; done