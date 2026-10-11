"""Readable terminal output for the suite.

Instead of rows of dots, the run prints a header per test module ("JSON · Todos"),
a sub-header per test class (with the endpoint it covers), and one line per test.
Tests that demonstrate a bug say so on their line, and the run ends with a
"Bugs demonstrated" summary.

pytest-randomly shuffles modules, then classes, then tests inside a class, so the
tests under one header always run together. Run with -v to get pytest's standard
output instead.

The hooks are registered by importing them into conftest.py.
"""

import re

import pytest

from support import BUGS

FORMATS = {"json_endpoints": "JSON", "xml_endpoints": "XML"}

# nodeid -> how the test is displayed; filled at collection time.
_layout = {}
_shown = {"section": None, "group": None}
_CONFIG = {}


def pytest_configure(config):
    _CONFIG["config"] = config


def _readable_output(config):
    return config.option.verbose <= 0


def _terminal(config):
    return config.pluginmanager.get_plugin("terminalreporter")


# ---------------------------------------------------------------- labels

def _section(item):
    parts = item.path.relative_to(item.config.rootpath / "test").parts
    if parts[0] in FORMATS:
        return f"{FORMATS[parts[0]]} · {parts[1].capitalize()}"
    return item.path.stem.removeprefix("test_").capitalize()


def _group(item):
    """'Todo Instance — /todos/:id' from the class name and its docstring."""
    cls = getattr(item, "cls", None)
    if cls is None:
        return None
    words = re.findall(r"[A-Z][a-z]*", cls.__name__.removeprefix("Test"))
    title = " ".join(words)
    doc = next((c.__dict__["__doc__"] for c in cls.__mro__[:-1] if c.__dict__.get("__doc__")), None)
    if doc:
        title += " — " + doc.strip().splitlines()[0].replace("<PARENT>", getattr(cls, "PARENT", None) or "")
    return title


def _name(item):
    name = item.originalname.removeprefix("test_").replace("_", " ")
    if hasattr(item, "callspec"):
        name += f" [{item.callspec.id}]"
    return name


def pytest_collection_modifyitems(items):
    for item in items:
        bug = item.get_closest_marker("bug")
        bug_id = bug.args[0] if bug else None
        if bug_id:
            item.user_properties.append(("bug", bug_id))
        _layout[item.nodeid] = {
            "section": _section(item),
            "group": _group(item),
            "name": _name(item),
            "bug": bug_id,
            "documented": item.get_closest_marker("xfail") is not None,
        }


# ---------------------------------------------------------------- per-test lines

def pytest_sessionstart(session):
    if _readable_output(session.config):
        # Stop pytest printing the file path in front of each module's results.
        _terminal(session.config).showfspath = False


@pytest.hookimpl(wrapper=True)
def pytest_report_teststatus(report, config):
    """Drop pytest's one-letter progress marks (., x, F); our lines replace them."""
    category, letter, word = yield
    if _readable_output(config):
        letter = ""
    return category, letter, word


def _status(report):
    if report.when == "call":
        if hasattr(report, "wasxfail"):
            return ("XFAIL", {"yellow": True}) if report.skipped else ("XPASS", {"red": True})
        if report.passed:
            return "PASSED", {"green": True}
        return ("FAILED", {"red": True}) if report.failed else ("SKIPPED", {"yellow": True})
    if report.failed:
        return "ERROR", {"red": True}
    if report.when == "setup" and report.skipped:
        return "SKIPPED", {"yellow": True}
    return None, None


def pytest_runtest_logreport(report):
    config = _CONFIG["config"]
    if not _readable_output(config) or report.nodeid not in _layout:
        return
    word, markup = _status(report)
    if word is None:
        return
    terminal, layout = _terminal(config), _layout[report.nodeid]

    if layout["section"] != _shown["section"]:
        terminal.write("\n")
        terminal.write_sep("=", layout["section"], cyan=True, bold=True)
        _shown.update(section=layout["section"], group=None)
    if layout["group"] and layout["group"] != _shown["group"]:
        terminal.write(f"\n{layout['group']}\n", bold=True)
        _shown["group"] = layout["group"]

    terminal.write(f"  {word:<7}", **markup)
    terminal.write(f" {layout['name']}")
    if layout["bug"]:
        kind = "documented behaviour, fails because of the bug" if layout["documented"] else "actual behaviour"
        terminal.write(f"  ← {layout['bug']} ({kind})", yellow=layout["documented"], cyan=not layout["documented"])
    terminal.write("\n")


# ---------------------------------------------------------------- bug summary

def pytest_terminal_summary(terminalreporter):
    """One entry per bug: how many tests show the documented behaviour failing
    (xfailed) and how many show the actual behaviour (passed)."""
    tally = {}
    for status in ("passed", "xfailed", "failed", "xpassed"):
        for report in terminalreporter.stats.get(status, []):
            for key, bug_id in getattr(report, "user_properties", []):
                if key == "bug":
                    counts = tally.setdefault(bug_id, {})
                    counts[status] = counts.get(status, 0) + 1
    if not tally:
        return
    terminalreporter.write_sep("=", "Bugs demonstrated (documented behaviour = XFAIL, actual behaviour = PASSED)")
    for bug_id in sorted(tally):
        summary = ", ".join(f"{n} {status}" for status, n in sorted(tally[bug_id].items()))
        terminalreporter.write_line(f"{bug_id}: {BUGS[bug_id]}")
        terminalreporter.write_line(f"        {summary}")
