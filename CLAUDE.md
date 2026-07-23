# nids-setup

Instructions and tooling for running NIDS ([CAIDA NIDS project](https://www.caida.org/projects/nids/)) on the NRP (National Research Platform) Nautilus Kubernetes cluster: namespace setup, JupyterHub deployment, and data staging for the NIDS assignments.

## Directory structure

- `docs/` — setup guides, numbered in reading order: `1_kubectl_install.md`, `2_nrp_namespace.md`, `3_kubectl_config.md`, `4_nrp_gitlab.md`, `5_nrp_jupyterhub.md`.
- `guides.xml` — admin-facing spec behind `docs/5_nrp_jupyterhub.md` (one hub, one profile per NIDS assignment).
- `image/` — container image for the hub: `Dockerfile` + `requirements.txt` (union of the assignment deps).
- `configs/` — configuration files: `values.yaml` (Helm values for the JupyterHub deployment).
- `scripts/` — setup/automation scripts (currently empty).

## Conventions

- Docs are numbered, step-by-step markdown guides with fenced code blocks for every command.
- Docs with dependencies carry a breadcrumb nav line at both the very top and the very bottom showing the chain (`Install kubectl | NRP & Namespace | Configure kubectl | NRP GitLab | JupyterHub`), with the current page bolded. Keep it consistent when adding docs.
- Files or directories prefixed with `z-` (e.g. `z-plan.md`) are scratch/working material — ignore them; they are not shipped repo content.

This is a docs/ops repo, not an application codebase — there are no build, test, or lint commands.
