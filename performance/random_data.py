"""Random, valid payloads for todos, projects and categories.

Field rules come from Part A and the Swagger:
- todos:      title (mandatory, non-empty), description, doneStatus (bool)
- projects:   title, description, completed (bool), active (bool); nothing mandatory
- categories: title (mandatory, non-empty), description

Every payload gets a non-empty title so the same generator works for all three.
A seeded generator always produces the same sequence of payloads.

Run on its own to preview payloads:
    python performance/random_data.py --resource todos --count 3 --seed 42
"""

import argparse
import json
import random
import string

TITLE_LENGTH = (1, 40)
DESCRIPTION_LENGTH = (0, 200)

_FIRST_CHAR = string.ascii_letters
_CHARS = string.ascii_letters + string.digits + " "


class RandomData:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def text(self, min_len, max_len):
        """A random-length string. Non-empty strings start with a letter, so a
        title is never blank or whitespace only."""
        length = self.rng.randint(min_len, max_len)
        if length == 0:
            return ""
        return self.rng.choice(_FIRST_CHAR) + "".join(self.rng.choices(_CHARS, k=length - 1))

    def boolean(self):
        return self.rng.random() < 0.5

    def payload(self, resource):
        """A complete random body for POST /<resource> or POST /<resource>/:id."""
        body = {
            "title": self.text(*TITLE_LENGTH),
            "description": self.text(*DESCRIPTION_LENGTH),
        }
        if resource == "todos":
            body["doneStatus"] = self.boolean()
        elif resource == "projects":
            body["completed"] = self.boolean()
            body["active"] = self.boolean()
        elif resource != "categories":
            raise ValueError(f"unknown resource {resource!r}")
        return body


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resource", choices=["todos", "projects", "categories"], default="todos")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    data = RandomData(args.seed)
    for _ in range(args.count):
        print(json.dumps(data.payload(args.resource)))


if __name__ == "__main__":
    main()
