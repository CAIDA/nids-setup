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
        # `public` says the upstream data is openly published. `public_access` says the
        # artifact *this dataset reads* can be downloaded by anyone from the open web,
        # with no account, allocation, or vetting. They differ -- caida-as2org is public
        # upstream while its mirror is in-cluster -- and only the second one is the v1
        # test. Defaults to `public` so an unmarked dataset is not silently admitted.
        self.public_access = data.get("public_access", data.get("public"))
        self.served_from = data.get("served_from")
        self.setup = data.get("setup")
        self.time_sensitive = data.get("time_sensitive")
        self.credentials = data.get("credentials", [])
        self.access = data.get("access", {})
        self.defaults = data.get("defaults", {})
        self._check = data.get("check", {})
        self.stage = data.get("stage", {})

    @property
    def public_coordinate(self):
        """The open-web `[access.public]` block, or {} when there is no separate one.

        Present only where `[access]` points somewhere not everyone can reach -- today
        the two Ceph-mirrored CAIDA datasets, whose real artifacts are on
        publicdata.caida.org.
        """
        return self.access.get("public", {})

    @property
    def coordinate(self):
        """The block to resolve against: the public one when this dataset has one.

        v1 targets machines with no NRP access, so the open-web address is the answer to
        "where is this dataset". `mirror_*` reaches the in-cluster copy explicitly.
        """
        return self.public_coordinate or self.access

    @property
    def check(self):
        """The check to run -- `[check.public]` when present, else `[check]`."""
        return self._check.get("public") or self._check

    @property
    def mirror_check(self):
        """The in-cluster check, when a public one supersedes it. Not run today."""
        return self._check if self._check.get("public") else {}

    @property
    def transport(self):
        return self.coordinate.get("transport")

    @property
    def pins(self):
        """Placeholder names an assignment is expected to supply."""
        return self.coordinate.get("pins", [])

    @property
    def reachable_offsite(self):
        """False for anything only addressable from inside the NRP cluster.

        A public coordinate settles this on its own: `served_from` records where the
        *mirror* lives, and is irrelevant once we are resolving publicdata instead.
        """
        return bool(self.public_coordinate) or self.served_from != "ceph-only"

    def staged_name(self, **pins):
        """Filename this dataset takes in a repo's data/ directory, or None."""
        template = self.stage.get("filename")
        if not template:
            return None
        values = dict(self.defaults)
        values.update({k: v for k, v in pins.items() if v is not None})
        try:
            return template.format(**values)
        except KeyError as exc:
            raise KeyError(f"{self.id}: [stage].filename needs a pin for "
                           f"{exc.args[0]!r}") from None

    def resolve(self, **pins):
        """Fill the access template. Assignment pins win over the dataset defaults.

        Resolves the public coordinate when there is one -- see `coordinate`.

        Raises KeyError naming the missing placeholder rather than emitting a path with
        a literal `{period}` in it, which would 404 in a confusing way much later.
        """
        return self._resolve(self.coordinate, pins)

    def resolve_mirror(self, **pins):
        """The in-cluster path, for a dataset whose default coordinate is public."""
        return self._resolve(self.access, pins)

    def _resolve(self, access, pins):
        template = access.get("template", "")
        values = dict(self.defaults)
        values.update({k: v for k, v in pins.items() if v is not None})
        values.setdefault("bucket", access.get("bucket", ""))
        values.setdefault("prefix", access.get("prefix", ""))
        missing = [n for n in _PLACEHOLDER.findall(template) if n not in values]
        if missing:
            raise KeyError(
                f"{self.id}: no value for {', '.join(missing)} "
                f"-- pin it in assignments/registry.toml or datasets/{self.id}/dataset.toml"
            )
        return template.format(**values)

    def url(self, **pins):
        """The full address, including the host for transports that carry one."""
        return self._join(self.coordinate, self.resolve(**pins))

    def mirror_url(self, **pins):
        """The full in-cluster address. Empty when there is no separate mirror."""
        if not self.public_coordinate:
            return ""
        return self._join(self.access, self.resolve_mirror(**pins))

    def _join(self, access, resolved):
        host = access.get("host") or access.get("base")
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
        # Which release this module ships in. Editorial: someone decided IRR waits, and
        # that is not derivable from the dataset fields. Unmarked means not in v1 --
        # a new module has to opt in, never land in the release by omission.
        self.release = data.get("release", "later")
        self.check_notebook = data.get("check")
        # Optional commit pin, honoured by clone-nids-repos.sh. Unset means track the
        # module's default branch. See DESIGN.md.
        self.ref = data.get("ref")
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


def load_assignments(root=None, release=None):
    """assignments/registry.toml, keyed by assignment code. Empty dict if absent.

    `release="r1"` narrows to the modules that ship in v1; None or "all" returns every
    block.
    """
    path = repo_root(root) / "assignments" / "registry.toml"
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text())
    data.pop("schema", None)
    found = {code: Assignment(code, block) for code, block in data.items()}
    if release in (None, "all"):
        return found
    return {code: a for code, a in found.items() if a.release == release}


def datasets_in_release(datasets, assignments, release="r1"):
    """Dataset ids read by the modules in `release`, in registry order.

    The release scopes *modules*; datasets follow from what those modules pin. That is
    why routeviews-prefix2as is out of v1 despite being publicly downloadable -- its only
    reader is IRR.
    """
    wanted = []
    for assignment in load_assignments(release=release).values() if assignments is None else assignments.values():
        if assignment.release != release:
            continue
        for entry in assignment.datasets:
            if entry["id"] not in wanted:
                wanted.append(entry["id"])
    return [datasets[i] for i in wanted if i in datasets]


def requirements_for(assignments, codes=None, role="assignment"):
    """The union of every selected module's `environment.extra`, in registry order.

    Names are returned exactly as spelled: they are pip requirement strings, and
    normalising them here would silently merge `pandas` and `pandas>=2`.
    """
    out = []
    for code, assignment in assignments.items():
        if codes and code not in codes:
            continue
        for name in assignment.env_for(role).get("extra", []):
            if name not in out:
                out.append(name)
    return out


def base_requirements(root=None):
    """env/base.txt -- what every module needs, whichever ones are selected."""
    path = repo_root(root) / "env" / "base.txt"
    if not path.exists():
        return []
    return [
        line.strip() for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


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
        # Both coordinates are checked: a stale placeholder in the mirror block is still
        # a bug, and the public block is the one v1 actually resolves.
        blocks = [("access", dataset.access)]
        if dataset.public_coordinate:
            blocks.append(("access.public", dataset.public_coordinate))
        for label, block in blocks:
            declared = set(block.get("pins", []))
            used = set(_PLACEHOLDER.findall(block.get("template", "")))
            used -= {"bucket", "prefix"}
            for name in sorted(used - declared):
                problems.append(
                    f"{dataset.id}: [{label}] template uses {{{name}}} but does not list it in pins"
                )
            for name in sorted(declared - used):
                problems.append(
                    f"{dataset.id}: [{label}] pins lists {name!r}, which the template never uses"
                )
        if dataset.public_coordinate and not dataset.public_coordinate.get("verified"):
            problems.append(
                f"{dataset.id}: [access.public] has no `verified` date -- record when it was last "
                f"confirmed reachable"
            )
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

    problems.extend(_release_problems(datasets, assignments))
    return problems


def _release_problems(datasets, assignments):
    """The v1 scope guard: nothing non-public may ship in the release.

    Both clauses earn their place. `public_access` catches maxmind-geolite2 and
    ucsd-nt-pcap-samples, which declare no credentials and are still closed; the
    credentials list catches itdk-postgres and ucsdnt-expanse-flowtuple. Either alone
    lets a restricted dataset back into the release through a later edit.
    """
    problems = []
    for assignment in assignments.values():
        if assignment.release != "r1":
            continue
        for entry in assignment.datasets:
            dataset = datasets.get(entry["id"])
            if dataset is None:
                continue                      # already reported above
            if not dataset.public_access:
                problems.append(
                    f"{assignment.code} is release r1 but reads {dataset.id}, which is not "
                    f"publicly accessible -- drop the module from r1 or give the dataset a "
                    f"public coordinate"
                )
            if dataset.credentials:
                problems.append(
                    f"{assignment.code} is release r1 but reads {dataset.id}, which requires "
                    f"{', '.join(dataset.credentials)}"
                )
    return problems


def _repos_cli(argv):
    """`--repos` emits `code<TAB>role<TAB>repo<TAB>ref`, so the shell script never parses TOML."""
    release = None
    codes = None
    for i, arg in enumerate(argv):
        if arg == "--release" and i + 1 < len(argv):
            release = argv[i + 1]
        if arg == "--modules" and i + 1 < len(argv):
            codes = {c.strip().upper() for c in argv[i + 1].split(",") if c.strip()}
    include_key = "--include-key" in argv

    assignments = load_assignments(release=None if release in (None, "all") else release)
    if codes:
        unknown = codes - set(assignments)
        if unknown:
            sys.stderr.write(
                f"unknown assignment code: {', '.join(sorted(unknown))}\n"
                f"known: {', '.join(sorted(assignments))}\n")
            return 2
    emitted = 0
    for code, assignment in assignments.items():
        if codes and code not in codes:
            continue
        roles = [("assignment", assignment.repo)]
        if include_key:
            roles.append(("key", assignment.key_repo))
        for role, name in roles:
            if not name:
                continue
            print(f"{code}\t{role}\t{name}\t{assignment.ref or ''}")
            emitted += 1
    if emitted == 0:
        sys.stderr.write("no modules matched\n")
        return 1
    return 0


def _cli():
    """`scripts/nids_registry.py` prints the registry; `--validate` cross-checks it."""
    if "--repos" in sys.argv[1:]:
        return _repos_cli(sys.argv[1:])
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
