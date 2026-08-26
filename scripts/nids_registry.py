#!/usr/bin/env python3
"""Loader for the NIDS dataset and assignment registries.

Two registries, both plain TOML, both living in this repo:

  datasets/<id>/dataset.toml     one per dataset -- transport, path template, the
                                 placeholders an assignment must pin, and how to check it
  assignments/registry.toml      one block per assignment -- repos, environment, and the
                                 pins it uses for each dataset it reads

The prose companions (datasets/<id>/README.md, DESIGN.md) keep owning provenance, gotchas,
and the setup narrative. This module owns none of that; it only resolves coordinates.

Why central rather than per-assignment: the per-assignment copies already drift -- the
RouteViews RIB month was 2026.05 in BGP and 2026.06 in TELESCOPE. Assignments pin a
*period*, never a URL, so a drift is visible as two different pins on one dataset instead
of two unrelated strings in two repos.

Needs Python 3.11+ for tomllib, or `pip install tomli` on 3.10.
"""

import os
import pathlib
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10 and older
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        raise SystemExit(
            "reading the registry needs TOML support: Python 3.11+ (tomllib) "
            "or `pip install tomli`"
        ) from None

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


class Dataset:
    """One datasets/<id>/dataset.toml, with its template resolvable against pins."""

    def __init__(self, data, path):
        self.path = path
        self.raw = data
        self.id = data["id"]
        self.name = data["name"]
        self.used_by = data.get("used_by", [])
        self.produced_by = data.get("produced_by")
        self.public = data.get("public")
        self.served_from = data.get("served_from")
        self.setup = data.get("setup")
        self.time_sensitive = data.get("time_sensitive")
        self.credentials = data.get("credentials", [])
        self.access = data.get("access", {})
        self.defaults = data.get("defaults", {})
        self.check = data.get("check", {})

    @property
    def transport(self):
        return self.access.get("transport")

    @property
    def pins(self):
        """Placeholder names an assignment is expected to supply."""
        return self.access.get("pins", [])

    @property
    def reachable_offsite(self):
        """False for anything only addressable from inside the NRP cluster."""
        return self.served_from != "ceph-only"

    def resolve(self, **pins):
        """Fill the access template. Assignment pins win over the dataset defaults.

        Raises KeyError naming the missing placeholder rather than emitting a path with
        a literal `{period}` in it, which would 404 in a confusing way much later.
        """
        template = self.access.get("template", "")
        values = dict(self.defaults)
        values.update({k: v for k, v in pins.items() if v is not None})
        values.setdefault("bucket", self.access.get("bucket", ""))
        values.setdefault("prefix", self.access.get("prefix", ""))
        missing = [n for n in _PLACEHOLDER.findall(template) if n not in values]
        if missing:
            raise KeyError(
                f"{self.id}: no value for {', '.join(missing)} "
                f"-- pin it in assignments/registry.toml or datasets/{self.id}/dataset.toml"
            )
        return template.format(**values)

    def url(self, **pins):
        """The full address, including the host for transports that carry one."""
        resolved = self.resolve(**pins)
        host = self.access.get("host") or self.access.get("base")
        if host and not resolved.startswith(("http://", "https://", "s3a://", "neo4j://", "bolt://")):
            return f"{host.rstrip('/')}/{resolved.lstrip('/')}"
        return resolved

    def __repr__(self):
        return f"<Dataset {self.id} {self.transport}>"


class Assignment:
    """One block of assignments/registry.toml."""

    def __init__(self, code, data):
        self.code = code
        self.raw = data
        self.name = data.get("name", code)
        self.repo = data.get("repo")
        self.key_repo = data.get("key_repo")
        self.status = data.get("status", "active")
        self.check_notebook = data.get("check")
        self.memory = data.get("memory", {})
        self.environment = data.get("environment", {})
        self.datasets = data.get("datasets", [])

    def env_for(self, role):
        """Merged environment spec for `assignment` or `key`.

        The key repo's spec is the assignment's with its own overrides layered on top --
        the README's "the environments required for the assignment and key repos might
        differ" case. Same spec means the two roles can share one environment.
        """
        base = {k: v for k, v in self.environment.items() if k != "key"}
        if role == "key":
            for key, value in self.environment.get("key", {}).items():
                if key == "extra":
                    base["extra"] = list(base.get("extra", [])) + list(value)
                else:
                    base[key] = value
        return base

    def pins_for(self, dataset_id):
        """The pins this assignment supplies for one dataset, minus registry bookkeeping."""
        for entry in self.datasets:
            if entry.get("id") == dataset_id:
                return {k: v for k, v in entry.items() if k not in ("id", "required", "note")}
        return {}

    def __repr__(self):
        return f"<Assignment {self.code}>"


def repo_root(start=None):
    """The nids-setup checkout this module lives in, or $NIDS_SETUP_ROOT if set."""
    override = os.environ.get("NIDS_SETUP_ROOT")
    if override:
        return pathlib.Path(override).expanduser().resolve()
    return pathlib.Path(start).resolve() if start else REPO_ROOT


def load_datasets(root=None):
    """Every datasets/<id>/dataset.toml, keyed by id."""
    base = repo_root(root) / "datasets"
    found = {}
    for path in sorted(base.glob("*/dataset.toml")):
        data = tomllib.loads(path.read_text())
        if data.get("schema") != 1:
            raise SystemExit(f"{path}: unsupported schema {data.get('schema')!r}, expected 1")
        if data["id"] != path.parent.name:
            raise SystemExit(f"{path}: id {data['id']!r} does not match directory {path.parent.name!r}")
        found[data["id"]] = Dataset(data, path)
    if not found:
        raise SystemExit(f"no dataset.toml files under {base}")
    return found


def load_assignments(root=None):
    """assignments/registry.toml, keyed by assignment code. Empty dict if absent."""
    path = repo_root(root) / "assignments" / "registry.toml"
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text())
    data.pop("schema", None)
    return {code: Assignment(code, block) for code, block in data.items()}


def checks_in_order(datasets, section):
    """Datasets carrying a check in `section`, in their declared order."""
    picked = [d for d in datasets.values() if d.check.get("section") == section]
    return sorted(picked, key=lambda d: (d.check.get("order", 999), d.id))


def datasets_for(datasets, assignments, code):
    """(dataset, pins, required) for every dataset one assignment reads."""
    assignment = assignments[code]
    out = []
    for entry in assignment.datasets:
        dataset = datasets.get(entry["id"])
        if dataset is None:
            raise SystemExit(
                f"assignments/registry.toml: {code} references unknown dataset {entry['id']!r}"
            )
        out.append((dataset, assignment.pins_for(entry["id"]), entry.get("required", True)))
    return out


def validate(root=None):
    """Cross-check the two registries. Returns a list of problems, empty when clean.

    This is the closest thing the repo has to a unit test: it proves every assignment
    references a dataset that exists, that every placeholder that dataset declares is
    actually pinned somewhere, and that no pin is silently ignored because the template
    has no such placeholder.
    """
    datasets = load_datasets(root)
    assignments = load_assignments(root)
    problems = []

    for dataset in datasets.values():
        declared = set(dataset.pins)
        used = set(_PLACEHOLDER.findall(dataset.access.get("template", "")))
        used -= {"bucket", "prefix"}
        for name in sorted(used - declared):
            problems.append(f"{dataset.id}: template uses {{{name}}} but does not list it in pins")
        for name in sorted(declared - used):
            problems.append(f"{dataset.id}: pins lists {name!r}, which the template never uses")
        if not dataset.check:
            problems.append(f"{dataset.id}: no [check] block")

    for assignment in assignments.values():
        for entry in assignment.datasets:
            dataset = datasets.get(entry["id"])
            if dataset is None:
                problems.append(f"{assignment.code}: unknown dataset {entry['id']!r}")
                continue
            pins = assignment.pins_for(entry["id"])
            for name in sorted(set(pins) - set(dataset.pins)):
                problems.append(
                    f"{assignment.code}/{dataset.id}: pins {name!r}, which the dataset does not declare"
                )
            try:
                dataset.resolve(**pins)
            except KeyError as exc:
                problems.append(f"{assignment.code}/{exc.args[0]}")
    return problems


def _cli():
    """`scripts/nids_registry.py` prints the registry; `--validate` cross-checks it."""
    if "--validate" in sys.argv[1:]:
        problems = validate()
        for problem in problems:
            print(f"  {problem}")
        print(f"\n{len(problems)} problems" if problems else "registry is consistent")
        return 1 if problems else 0
    datasets = load_datasets()
    assignments = load_assignments()
    print(f"{len(datasets)} datasets\n")
    for dataset in datasets.values():
        try:
            resolved = dataset.url()
        except KeyError as exc:
            resolved = f"unresolved ({exc.args[0]})"
        print(f"  {dataset.id:26} {dataset.transport:9} {resolved}")
    print(f"\n{len(assignments)} assignments\n")
    for assignment in assignments.values():
        ids = ", ".join(entry["id"] for entry in assignment.datasets) or "-"
        print(f"  {assignment.code:10} {assignment.status:8} {ids}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
