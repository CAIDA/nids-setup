# nids-setup

Instructions and tooling for running NIDS ([CAIDA NIDS project](https://www.caida.org/projects/nids/)) on the NRP (National Research Platform) Nautilus Kubernetes cluster: namespace setup, JupyterHub deployment, and data staging for the NIDS assignments.

## Directory structure

- `docs/` — setup guides, numbered in reading order: `1_kubectl_install.md`, `2_nrp_namespace.md`, `3_kubectl_config.md`, `4_nrp_jupyterhub.md`, `5_verify_hub.md`. Plus `0_build_images.md`, which sits *outside* that chain: it is maintainer-only (build and publish the image), and the reader path starts at doc 1 because the image is already published.
- `DESIGN.md` — the standing design brief: what is being built, the decisions and their rationale, assignment coverage, and open questions. See below for when to read it.
- `image/` — container image for the hub: `Dockerfile` + `requirements.txt` (union of the assignment deps).
- `configs/` — configuration files: `values.yaml` (Helm values for the JupyterHub deployment).
- `datasets/` — one directory per dataset, each holding a `README.md` (prose) and a `dataset.toml` (machine-readable coordinates), plus the inventory `README.md` and `SCHEMA.md` documenting both registries. **No dataset path is written twice:** the checkers and the setup tooling resolve every coordinate from `dataset.toml`, so a stale path is fixed in exactly one place. The README records provenance (CAIDA or external), whether the public version is usable or a NIDS administrator must build a NIDS-specific version, the access path, and how to validate it. It is deliberately cross-assignment: most datasets are shared, and the per-assignment `Datasets.md` / `00-environment-check.ipynb` copies drift. A dataset marked ❌ in the inventory has no recoverable setup procedure — its `## Setup` section is a stub naming what must be recovered, and **must not** be filled in with a guessed procedure.
- `notebooks/` — `test.ipynb`, the hub environment check run inside a spawned server (see `docs/5_verify_hub.md`), and `check-datasets.ipynb`, the all-datasets reachability pass (see `datasets/README.md`). Their per-assignment counterparts, `00-environment-check.ipynb`, live in the assignment answer-key repos under `nids-module-creator/`, not here. All of them duplicate the same small check runner on purpose — they are handed around as single files, so nothing may be imported from a shared module. That runner is byte-identical everywhere; keep it that way when editing.
- `assignments/` — `registry.toml`, one block per assignment: repos, environment (with an `[X.environment.key]` overlay for the answer-key repo), and the pins it supplies for each dataset it reads. Assignments pin placeholders, never URLs.
- `setup.sh` — the one command a first-time user runs: `--local` (public data, builds a venv) or `--nrp` (in-cluster mirror, hub supplies the environment). A thin wrapper over the three steps below, each of which also stands alone.
- `env/` — `base.txt`, the packages every module needs, and the generated `requirements-<tier>.txt` that `nids-setup.py env` writes by unioning it with each module's `[<CODE>.environment].extra`. Only the release tiers are committed; ad-hoc subsets are gitignored.
- `scripts/` — `build-push.sh`, which builds `image/` with `docker buildx` and pushes both tags (see `docs/0_build_images.md`), `check-datasets.py`, the laptop-side counterpart to `check-datasets.ipynb`, `nids_registry.py`, the loader for both registries (`--validate` cross-checks them, `--repos` lists a release's repos for the cloner), `clone-nids-repos.sh`, which clones module repos either from the registry (`--release` / `--modules`, no token needed) or by enumerating the whole CAIDA org (token required), and `nids-setup.py`, the assignment setup entry point (`discover`, `doctor`, `env`, `data`; `verify` not yet written).

## When to read DESIGN.md

`DESIGN.md` holds the *why* that the guides deliberately leave out. Read it before acting when a
task touches any of:

- **The container image** — adding or removing a dependency, changing the base image, or splitting
  the image. It records which deps belong to which assignment, why one combined image was chosen,
  and what is already known to be duplicated or unpinned.
- **Spawner profiles or memory envelopes** — it marks which numbers are authoritative and which are
  inferences, so you don't "correct" a value that came from an assignment's own README.
- **The build or the registry path** — building locally rather than in CI, the registry being a
  variable rather than a hardcoded path, and the base-image digest pin all have reasons that are
  non-obvious from the files alone.
- **Adding support for another assignment** — the coverage table says what is done, what is
  inferred, and what is blocked (e.g. IYP needs a Neo4j instance that does not exist yet).
- **Anything touching auth, culling, or leaving the hub open** — it lists the mandatory cluster
  policy, where violations can get the namespace locked.
- **A question that starts "why is this like this?"** — if the answer isn't there, that is a gap in
  `DESIGN.md` worth filling.

Two rules when editing it: keep the **[verified]** / **[unverified]** marking on every claim, and
keep it compacted — delete what has stopped being load-bearing instead of appending to it. It is a
design record, not a changelog.

## Conventions

- Docs are numbered, step-by-step markdown guides with fenced code blocks for every command.
- **The two-path split.** The reader chose in `README.md` between the *community hub* (NRP's hosted
  jupyterhub-west) and *your own hub* (the Helm deployment). Every doc in the chain states which
  path it serves in a `> **Path: …**` blockquote directly under its `#` title, and any own-hub-only
  section inside an otherwise-shared doc is marked inline. Doc 2 is the only split doc (Steps 1–3
  everyone, Steps 4–5 own hub); docs 1, 3, and 4 are own-hub-only; doc 5 is both, in two versions.
  Keep the banner and the README's step table in sync when adding or resequencing a doc.
- Docs with dependencies carry a breadcrumb nav line at both the very top and the very bottom showing the chain (`Install kubectl | NRP & Namespace | Configure kubectl | JupyterHub`), with the current page bolded. Keep it consistent when adding docs. `0_build_images.md` deliberately carries **no** nav line — it is not part of the reader chain, and neither is anything under `datasets/`.
- Assignments are referred to by the codes published in [assignments.json](https://www.caida.org/projects/nids/assignments/assignments.json) — `ASN`, `BGP`, `IRR`, `ITDK`, `DNS`, `TELESCOPE`, plus `IYP` and `UCSDNT`. `datasets/README.md` carries the code/name table.
- Files or directories prefixed with `z-` (e.g. `z-plan.md`) are scratch/working material — ignore them; they are not shipped repo content.

This is a docs/ops repo, not an application codebase — there are no lint commands and no test suite.
The nearest things to one are `scripts/nids_registry.py --validate`, which cross-checks the two
registries offline and exits non-zero on a dangling reference (run it after touching either), and
`scripts/check-datasets.py`, which checks dataset reachability and exits non-zero if a *required*
dataset is unreachable. The other executables are `scripts/build-push.sh`, which builds and
publishes the container image, and `scripts/clone-nids-repos.sh`, which fetches the repos.
