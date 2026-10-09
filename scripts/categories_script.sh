#!/bin/bash
# ECSE 429 Part A - Session 3 (categories): all 6 categories endpoints x 7 verbs = 42 requests.
# Responses are requested as XML (Accept header), printed, and saved to evidence/xml/<name>.xml
# Run from the repo root (the folder that contains evidence/ and scripts/):
#   bash scripts/categories_xml.sh | tee results_categories.txt
# RESTART THE JAR BEFORE AND AFTER (the run changes data).

# Saves into ./evidence/xml, relative to the folder you run this from (run it from the repo root).
mkdir -p evidence/categories/xml
B=http://localhost:4567

x() {  # usage: x VERB PATH FILENAME [JSON_BODY]
  echo "=== $1 $2"
  if [ "$1" = HEAD ]; then
    curl -s -I -H "Accept: application/xml" $B$2 | tee evidence/categories/xml/$3.xml
  elif [ -n "$4" ]; then
    curl -s -i -X $1 $B$2 -H "Content-Type: application/json" -H "Accept: application/xml" -d "$4" | tee evidence/categories/xml/$3.xml
  else
    curl -s -i -X $1 $B$2 -H "Accept: application/xml" | tee evidence/categories/xml/$3.xml
  fi
  echo
}

# helper: create an object and print its id   usage: mk todos | mk categories | mk projects
mk() { curl -s -X POST $B/$1 -H "Content-Type: application/json" -d '{"title":"probe"}' | grep -o '"id":"[0-9]*"' | head -1 | grep -o '[0-9]*'; }

T=$(mk todos); C=$(mk categories); P=$(mk projects)
echo "Using todo=$T category=$C project=$P"

# ===== 1. /categories (7) =====
x GET     /categories categories_GET
x HEAD    /categories categories_HEAD
x POST    /categories categories_POST '{"title":"probe"}'
x PUT     /categories categories_PUT
x PATCH   /categories categories_PATCH
x DELETE  /categories categories_DELETE
x OPTIONS /categories categories_OPTIONS

# ===== 2. /categories/:id (7) =====
x GET     /categories/$C categories_id_GET
x HEAD    /categories/$C categories_id_HEAD
x POST    /categories/$C categories_id_POST '{"description":"changed"}'
x PUT     /categories/$C categories_id_PUT '{"title":"replaced"}'
x PATCH   /categories/$C categories_id_PATCH
x OPTIONS /categories/$C categories_id_OPTIONS
D=$(mk categories)   # throwaway so the main category survives
x DELETE  /categories/$D categories_id_DELETE
x DELETE  /categories/$D categories_id_DELETE_again

# ===== 3. /categories/:id/todos (7) =====
x POST    /categories/$C/todos categories_id_todos_POST "{\"id\":\"$T\"}"
x GET     /categories/$C/todos categories_id_todos_GET
x HEAD    /categories/$C/todos categories_id_todos_HEAD
x PUT     /categories/$C/todos categories_id_todos_PUT
x PATCH   /categories/$C/todos categories_id_todos_PATCH
x DELETE  /categories/$C/todos categories_id_todos_DELETE
x OPTIONS /categories/$C/todos categories_id_todos_OPTIONS

# ===== 4. /categories/:id/todos/:id (7)  BUG-01: GET, HEAD, POST should be 405 =====
x GET     /categories/$C/todos/$T categories_id_todos_id_GET
x HEAD    /categories/$C/todos/$T categories_id_todos_id_HEAD
x POST    /categories/$C/todos/$T categories_id_todos_id_POST
x PUT     /categories/$C/todos/$T categories_id_todos_id_PUT
x PATCH   /categories/$C/todos/$T categories_id_todos_id_PATCH
x OPTIONS /categories/$C/todos/$T categories_id_todos_id_OPTIONS
x DELETE  /categories/$C/todos/$T categories_id_todos_id_DELETE

# ===== 5. /categories/:id/projects (7) =====
x POST    /categories/$C/projects categories_id_projects_POST "{\"id\":\"$P\"}"
x GET     /categories/$C/projects categories_id_projects_GET
x HEAD    /categories/$C/projects categories_id_projects_HEAD
x PUT     /categories/$C/projects categories_id_projects_PUT
x PATCH   /categories/$C/projects categories_id_projects_PATCH
x DELETE  /categories/$C/projects categories_id_projects_DELETE
x OPTIONS /categories/$C/projects categories_id_projects_OPTIONS

# ===== 6. /categories/:id/projects/:id (7)  BUG-01: GET, HEAD, POST should be 405 =====
x GET     /categories/$C/projects/$P categories_id_projects_id_GET
x HEAD    /categories/$C/projects/$P categories_id_projects_id_HEAD
x POST    /categories/$C/projects/$P categories_id_projects_id_POST
x PUT     /categories/$C/projects/$P categories_id_projects_id_PUT
x PATCH   /categories/$C/projects/$P categories_id_projects_id_PATCH
x OPTIONS /categories/$C/projects/$P categories_id_projects_id_OPTIONS
x DELETE  /categories/$C/projects/$P categories_id_projects_id_DELETE

# ===== Summary: status line of every saved file =====
echo; echo "--- status of each saved response ---"
for f in evidence/xml/categories_*.xml; do echo "$(basename $f .xml): $(head -1 $f | tr -d '\r')"; done