# nids-setup

Instructions for setting up and running NIDS ([CAIDA NIDS project](https://www.caida.org/projects/nids/)) on the National Research Platform (NRP). Covers setting up a namespace, running a JupyterHub from that namespace, and copying data into the namespace for use by the NIDS assignments.

## Guides

- [Install kubectl](docs/1_kubectl_install.md) — install the `kubectl` CLI and `kubelogin` plugin.
- [NRP & Namespace](docs/2_nrp_namespace.md) — get access to NRP and request a namespace.
- [Configure kubectl](docs/3_kubectl_config.md) — point `kubectl` at NRP and your namespace.
- [NRP GitLab](docs/4_nrp_gitlab.md) — create an NRP GitLab project and have GitLab CI/CD build and publish the hub image (no local Docker).
- [JupyterHub](docs/5_nrp_jupyterhub.md) — deploy your own JupyterHub in your namespace.

## Design notes

[DESIGN.md](DESIGN.md) is the standing brief behind these guides: what is being built, the
decisions and their rationale, which assignments the image currently supports, and the open
questions. Read it before changing the image, the profiles, or the build pipeline.

