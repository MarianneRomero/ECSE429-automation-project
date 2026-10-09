#!/bin/bash
# ECSE 429 Part A - Session 2 (projects): all 6 projects endpoints x 7 verbs = 42 requests.
# Responses are requested as XML (Accept header), printed, and saved to evidence/xml/<name>.xml
# Run from the repo root (the folder that contains evidence/ and scripts/):
#   bash scripts/projects_xml.sh | tee results_projects.txt
# RESTART THE JAR BEFORE AND AFTER (the run changes data).

# Saves into ./evidence/projects/xml, relative to the folder you run this from (run it from the repo root).
mkdir -p evidence/projects/xml
B=http://localhost:4567

x() {  # usage: x VERB PATH FILENAME [JSON_BODY]
  echo "=== $1 $2"
  if [ "$1" = HEAD ]; then
    curl -s -I -H "Accept: application/xml" $B$2 | tee evidence/projects/xml/$3.xml
  elif [ -n "$4" ]; then
    curl -s -i -X $1 $B$2 -H "Content-Type: application/json" -H "Accept: application/xml" -d "$4" | tee evidence/projects/xml/$3.xml
  else
    curl -s -i -X $1 $B$2 -H "Accept: application/xml" | tee evidence/projects/xml/$3.xml
  fi
  echo
}

# helper: create an object and print its id   usage: mk todos | mk categories | mk projects
mk() { curl -s -X POST $B/$1 -H "Content-Type: application/json" -d '{"title":"probe"}' | grep -o '"id":"[0-9]*"' | head -1 | grep -o '[0-9]*'; }

T=$(mk todos); C=$(mk categories); P=$(mk projects)
echo "Using todo=$T category=$C project=$P"

# ===== 1. /projects (7) =====
x GET     /projects projects_GET
x HEAD    /projects projects_HEAD
x POST    /projects projects_POST '{"title":"probe"}'
x PUT     /projects projects_PUT
x PATCH   /projects projects_PATCH
x DELETE  /projects projects_DELETE
x OPTIONS /projects projects_OPTIONS

# ===== 2. /projects/:id (7) =====
x GET     /projects/$P projects_id_GET
x HEAD    /projects/$P projects_id_HEAD
x POST    /projects/$P projects_id_POST '{"description":"changed"}'
x PUT     /projects/$P projects_id_PUT '{"title":"replaced"}'
x PATCH   /projects/$P projects_id_PATCH
x OPTIONS /projects/$P projects_id_OPTIONS
D=$(mk projects)   # throwaway so the main project survives
x DELETE  /projects/$D projects_id_DELETE
x DELETE  /projects/$D projects_id_DELETE_again

# ===== 3. /projects/:id/categories (7) =====
x POST    /projects/$P/categories projects_id_categories_POST "{\"id\":\"$C\"}"
x GET     /projects/$P/categories projects_id_categories_GET
x HEAD    /projects/$P/categories projects_id_categories_HEAD
x PUT     /projects/$P/categories projects_id_categories_PUT
x PATCH   /projects/$P/categories projects_id_categories_PATCH
x DELETE  /projects/$P/categories projects_id_categories_DELETE
x OPTIONS /projects/$P/categories projects_id_categories_OPTIONS

# ===== 4. /projects/:id/categories/:id (7)  BUG-01: GET, HEAD, POST should be 405 =====
x GET     /projects/$P/categories/$C projects_id_categories_id_GET
x HEAD    /projects/$P/categories/$C projects_id_categories_id_HEAD
x POST    /projects/$P/categories/$C projects_id_categories_id_POST
x PUT     /projects/$P/categories/$C projects_id_categories_id_PUT
x PATCH   /projects/$P/categories/$C projects_id_categories_id_PATCH
x OPTIONS /projects/$P/categories/$C projects_id_categories_id_OPTIONS
x DELETE  /projects/$P/categories/$C projects_id_categories_id_DELETE

# ===== 5. /projects/:id/tasks (7) =====
x POST    /projects/$P/tasks projects_id_tasks_POST "{\"id\":\"$T\"}"
x GET     /projects/$P/tasks projects_id_tasks_GET
x HEAD    /projects/$P/tasks projects_id_tasks_HEAD
x PUT     /projects/$P/tasks projects_id_tasks_PUT
x PATCH   /projects/$P/tasks projects_id_tasks_PATCH
x DELETE  /projects/$P/tasks projects_id_tasks_DELETE
x OPTIONS /projects/$P/tasks projects_id_tasks_OPTIONS

# ===== 6. /projects/:id/tasks/:id (7)  BUG-01: GET, HEAD, POST should be 405 =====
x GET     /projects/$P/tasks/$T projects_id_tasks_id_GET
x HEAD    /projects/$P/tasks/$T projects_id_tasks_id_HEAD
x POST    /projects/$P/tasks/$T projects_id_tasks_id_POST
x PUT     /projects/$P/tasks/$T projects_id_tasks_id_PUT
x PATCH   /projects/$P/tasks/$T projects_id_tasks_id_PATCH
x OPTIONS /projects/$P/tasks/$T projects_id_tasks_id_OPTIONS
x DELETE  /projects/$P/tasks/$T projects_id_tasks_id_DELETE

# ===== Summary: status line of every saved file =====
echo; echo "--- status of each saved response ---"
for f in evidence/xml/projects_*.xml; do echo "$(basename $f .xml): $(head -1 $f | tr -d '\r')"; done