# nids-setup

Instructions and tooling for running NIDS ([CAIDA NIDS project](https://www.caida.org/projects/nids/)) on the NRP (National Research Platform) Nautilus Kubernetes cluster: namespace setup, JupyterHub deployment, and data staging for the NIDS modules.

## Directory structure

- `docs/` — setup guides. Start with `Namespace.md`, then `JupyterHub.md`.
- `scripts/` — setup/automation scripts (currently empty).
- `configs/` — configuration files, e.g. Helm `values.yaml` (currently empty).

## Conventions

- Docs are numbered, step-by-step markdown guides with fenced code blocks for every command.
- New docs should link to their prerequisite docs (e.g. `JupyterHub.md` depends on `Namespace.md`).
- Files or directories prefixed with `z-` (e.g. `z-plan.md`) are scratch/working material — ignore them; they are not shipped repo content.

This is a docs/ops repo, not an application codebase — there are no build, test, or lint commands.
