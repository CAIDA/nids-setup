# nids-setup

Instructions and tooling for running NIDS ([CAIDA NIDS project](https://www.caida.org/projects/nids/)) on the NRP (National Research Platform) Nautilus Kubernetes cluster: namespace setup, JupyterHub deployment, and data staging for the NIDS assignments.

## Directory structure

- `docs/` — setup guides, numbered in reading order: `1_kubectl_install.md`, `2_nrp_namespace.md`, `3_kubectl_config.md`, `4_nrp_gitlab.md`, `5_nrp_jupyterhub.md`.
- `DESIGN.md` — the standing design brief: what is being built, the decisions and their rationale, assignment coverage, and open questions. See below for when to read it.
- `image/` — container image for the hub: `Dockerfile` + `requirements.txt` (union of the assignment deps).
- `.gitlab-ci.yml` — the Kaniko pipeline that builds `image/` on NRP GitLab CI/CD and pushes it to the registry (see `docs/4_nrp_gitlab.md`).
- `configs/` — configuration files: `values.yaml` (Helm values for the JupyterHub deployment).
- `scripts/` — setup/automation scripts (currently empty).

## When to read DESIGN.md

`DESIGN.md` holds the *why* that the guides deliberately leave out. Read it before acting when a
task touches any of:

- **The container image** — adding or removing a dependency, changing the base image, or splitting
  the image. It records which deps belong to which assignment, why one combined image was chosen,
  and what is already known to be duplicated or unpinned.
- **Spawner profiles or memory envelopes** — it marks which numbers are authoritative and which are
  inferences, so you don't "correct" a value that came from an assignment's own README.
- **The build pipeline or registry path** — the second-remote arrangement, the Kaniko choice, and
  the digest pin all have reasons that are non-obvious from the files alone.
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
- Docs with dependencies carry a breadcrumb nav line at both the very top and the very bottom showing the chain (`Install kubectl | NRP & Namespace | Configure kubectl | NRP GitLab | JupyterHub`), with the current page bolded. Keep it consistent when adding docs.
- Files or directories prefixed with `z-` (e.g. `z-plan.md`) are scratch/working material — ignore them; they are not shipped repo content.

This is a docs/ops repo, not an application codebase — there are no build, test, or lint commands.
