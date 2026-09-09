# nids-setup

Instructions and tooling for running NIDS ([CAIDA NIDS project](https://www.caida.org/projects/nids/)) on the NRP (National Research Platform) Nautilus Kubernetes cluster: namespace setup, JupyterHub deployment, and data staging for the NIDS assignments.

## Directory structure

- `setup.sh` / `setup.cmd` — the launchers, for Unix and Windows respectively. **Neither holds any logic**: both call `scripts/nids-setup.py setup` and pass every argument through, so there is one implementation of setup shared by all platforms. Add options to the subcommand, never to a launcher, and never let the two diverge.
- `docs/` — setup guides, numbered in reading order: `1_kubectl_install.md`, `2_nrp_namespace.md`, `3_kubectl_config.md`, `4_nrp_jupyterhub.md`, `5_verify_hub.md`. Plus `0_build_images.md`, which sits *outside* that chain: it is maintainer-only (build and publish the image), and the reader path starts at doc 1 because the image is already published.
- `image/` — container image for the hub: `Dockerfile` + `requirements.txt` (union of the assignment deps).
- `configs/` — configuration files: `values.yaml` (Helm values for the JupyterHub deployment).
- `datasets/` — one directory per dataset, each holding a `README.md` (prose) and a `dataset.toml` (machine-readable coordinates), plus the inventory `README.md` and `SCHEMA.md` documenting both registries. **No dataset path is written twice:** the checkers and the setup tooling resolve every coordinate from `dataset.toml`, so a stale path is fixed in exactly one place. The README records provenance (CAIDA or external), whether the public version is usable or a NIDS administrator must build a NIDS-specific version, the access path, and how to validate it. It is deliberately cross-assignment: most datasets are shared, and the per-assignment `Datasets.md` / `00-environment-check.ipynb` copies drift. A dataset marked ❌ in the inventory has no recoverable setup procedure — its `## Setup` section is a stub naming what must be recovered, and **must not** be filled in with a guessed procedure.
- `notebooks/` — `test.ipynb`, the hub environment check run inside a spawned server (see `docs/5_verify_hub.md`), and `check-datasets.ipynb`, the all-datasets reachability pass (see `datasets/README.md`). Their per-assignment counterparts, `00-environment-check.ipynb`, live in the assignment answer-key repos, not here — but **not all of them actually exist**: `nids-asn-introduction-key` and `nids-bgp-control-plane-key` have never held one, on any branch or commit, though `assignments/registry.toml` names one for each. `nids-setup.py verify` reports that discrepancy and falls back to the module's own key notebook, which is why it is not blocked by it. All of them duplicate the same small check runner on purpose — they are handed around as single files, so nothing may be imported from a shared module. That runner is byte-identical everywhere; keep it that way when editing.
- `assignments/` — `registry.toml`, one block per assignment: repos, environment (with an `[X.environment.key]` overlay for the answer-key repo), and the pins it supplies for each dataset it reads. Assignments pin placeholders, never URLs.
- `setup.sh` — the one command a first-time user runs: `--local` (public data, builds a venv) or `--nrp` (in-cluster mirror, hub supplies the environment). A thin wrapper over the three steps below, each of which also stands alone.
- `env/` — `base.txt`, the packages every module needs, and the generated `requirements-<tier>.txt` that `nids-setup.py env` writes by unioning it with each module's `[<CODE>.environment].extra`. Only the release tiers are committed; ad-hoc subsets are gitignored.
- `scripts/` — `build-push.sh`, which builds `image/` with `docker buildx` and pushes both tags (see `docs/0_build_images.md`), `check-datasets.py`, the laptop-side counterpart to `check-datasets.ipynb`, `nids_registry.py`, the loader for both registries (`--validate` cross-checks them, `--repos` lists a release's repos for the cloner), `clone-nids-repos.sh`, which enumerates the whole CAIDA org and clones what matches (token required) — a maintainer tool, not part of anyone's setup path — `check-wheels.py`, which reports whether each dependency ships wheels for Windows, macOS and Linux (run it when **adding** a dependency: a source-only package installs fine here and fails on a machine with no compiler), and `nids-setup.py`, the setup entry point (`setup`, `clone`, `discover`, `doctor`, `env`, `data`, `verify`).

## Conventions

- Docs are numbered, step-by-step markdown guides with fenced code blocks for every command.
- **The two-path split.** The reader chose in `README.md` between the *community hub* (NRP's hosted
  jupyterhub-west) and *your own hub* (the Helm deployment). Every doc in the chain states which
  path it serves in a `> **Path: …**` blockquote directly under its `#` title, and any own-hub-only
  section inside an otherwise-shared doc is marked inline. Doc 2 is the only split doc (Steps 1–3
  everyone, Steps 4–5 own hub); docs 1, 3, and 4 are own-hub-only; doc 5 is both, in two versions.
  Keep the banner and the README's step table in sync when adding or resequencing a doc.
- Docs with dependencies carry a breadcrumb nav line at both the very top and the very bottom showing the chain (`Install kubectl | NRP & Namespace | Configure kubectl | JupyterHub`), with the current page bolded. Keep it consistent when adding docs. `0_build_images.md` deliberately carries **no** nav line — it is not part of the reader chain, and neither is anything under `datasets/`.
- **Venue (`venue` in `assignments/registry.toml`, added 2026-09-09).** Every module is supported on the NRP hub; `venue = ["local", "nrp"]` is an admission a module earns by having a wheels-only environment and wholly public data. It defaults to `["nrp"]`, so a module is hub-only by omission and opts in to the laptop. `nids_registry.py --validate` enforces the data half. It is a *support* statement: `setup --local` warns on a hub-bound module and proceeds, and no file here may say a module "only runs on NRP" unless that has actually been measured.
- Assignments are referred to by the codes published in [assignments.json](https://www.caida.org/projects/nids/assignments/assignments.json) — `ASN`, `BGP`, `IRR`, `ITDK`, `DNS`, `TELESCOPE`, plus `IYP` and `UCSDNT`. `datasets/README.md` carries the code/name table.
- Files or directories prefixed with `z-` (e.g. `z-plan.md`) are scratch/working material — ignore them; they are not shipped repo content.

This is a docs/ops repo, not an application codebase — there are no lint commands and no test suite.
The nearest things to one are `scripts/nids_registry.py --validate`, which cross-checks the two
registries offline and exits non-zero on a dangling reference (run it after touching either), and
`scripts/check-datasets.py`, which checks dataset reachability and exits non-zero if a *required*
dataset is unreachable. The other executables are `scripts/build-push.sh`, which builds and
publishes the container image, and `scripts/clone-nids-repos.sh`, which enumerates the org.
