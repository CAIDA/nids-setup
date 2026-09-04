# nids-setup

Setup for the NIDS assignments ([CAIDA NIDS project](https://www.caida.org/projects/nids/)) —
on your own machine, or on the National Research Platform (NRP).

## Quickstart

One command clones the module repositories, builds a Python environment for them, and downloads
their data.

```bash
git clone https://github.com/CAIDA/nids-setup.git
cd nids-setup
```

Then one line — pick the one that matches where you are:

| | run this | then activate with |
|---|---|---|
| **Windows** | `.\setup.cmd --local` | `.venv\Scripts\Activate.ps1` |
| **macOS / Linux** | `./setup.sh --local` | `source .venv/bin/activate` |
| **NRP JupyterHub** | `./setup.sh --nrp` | nothing — the hub supplies the environment |

Finally:

```
jupyter lab ..                     # the module repos are cloned beside nids-setup
```

Open any module's notebook and run it. There is no manual download step.

Both launchers call the same `scripts/nids-setup.py setup`, so every option below works
identically on all three; only the launcher's name and the activation line differ.

### What the two modes differ on

| | `--local` | `--nrp` |
|---|---|---|
| Data source | `publicdata.caida.org` and other open-web endpoints | NRP's in-cluster mirror |
| Python | a `.venv` this script builds | the hub image, already provisioned |
| Needs a CAIDA account | no | an NRP account |
| Works on Windows | yes | you are in a Linux container already |

`--local` is the one to use if you are not sure. It needs no CAIDA affiliation and no NRP access.

### Useful variations

```
./setup.sh --local --modules ASN,BGP      # just these two modules
./setup.sh --local --root ~/nids          # put the module repos somewhere specific
./setup.sh --local --python python3.12    # build the environment with a specific interpreter
./setup.sh --local --skip-data            # clone and build the environment only
```

On Windows substitute `.\setup.cmd` for `./setup.sh`; the options are the same.

Re-running is safe — each step skips what is already done.

### If something goes wrong

```
python scripts/nids-setup.py discover --release r1   # what is cloned, and its state
python scripts/check-datasets.py --release r1        # is every dataset reachable from here
```

`setup.sh` and `setup.cmd` are launchers and hold no logic. Each step is also a subcommand you
can run alone — `nids-setup.py clone`, `env`, `data` — which is the quickest way to redo just
the part that failed.

**Python 3.11 or newer** is needed to read the registry, and **git** must be on your PATH.
Building the environment additionally needs an interpreter with `venv` support — some system
Python builds ship without it, and `--python` is how you point at one that has it. On Windows,
install Python from [python.org](https://www.python.org/downloads/windows/) and tick *Add
python.exe to PATH*; `setup.cmd` finds it through the `py` launcher or `python`.

## Which modules this covers

Release 1 is **ASN**, **BGP**, **DNS** and **IYP**. The other six modules read data that is not
publicly downloadable, or is pinned to periods that are no longer re-fetchable, and they are
deliberately out of scope for now rather than missing — `assignments/registry.toml` records why
for each one, and `nids-setup.py env --release r1` and friends will not touch them.

---

## Running on NRP: whose hub will you use?

Everything below branches on one decision, so make it first.

**The community hub** — NRP's hosted service at
[jupyterhub-west.nrp-nautilus.io](https://jupyterhub-west.nrp-nautilus.io). Log in with CILogon,
pick an instance size, go. Nothing to deploy and nothing to maintain. This is what the assignment
READMEs themselves assume.

**Your own hub** — a JupyterHub you deploy into your own NRP namespace with Helm, running the
pre-built `nids-hub` image with one spawner profile per assignment.

|                    | Community hub                                                                   | Your own hub                                                                  |
| ------------------ | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Setup effort       | Log in                                                                          | Namespace admin, a CILogon OAuth app, a Helm release you own                   |
| Environment        | NRP's stock images — each assignment `%pip install`s its own deps, taking minutes | The pinned `nids-hub` image with every assignment's deps already installed     |
| Spark (DNS assignment) | No JVM; Spark pulls its S3A jars from Maven Central at session start         | Spark-capable image with the S3A jars pre-staged                               |
| Memory             | You pick an instance size per assignment, by hand, every time                   | One right-sized spawner profile per assignment                                 |
| Home directory     | Starts at 5 GB (extendable on request)                                          | Whatever you set in `singleuser.storage`                                       |
| Idle culling       | ~1 hour after the browser disconnects, fixed                                    | Yours to set (NRP requires `timeout` ≤ 6 h)                                    |
| Access control     | NRP's                                                                           | Your own: `allowed_idps` / `allowed_domains` / a roster                        |
| Shared datasets    | Each user fetches their own                                                     | A read-only PVC mounted into every server                                      |
| Good for           | A student, or an instructor trying one assignment out                           | An instructor standing up a managed, reproducible class environment            |

> **If you are unsure, use the community hub.** Switching later costs nothing — no assignment is
> hub-specific — and it saves you steps 1, 3, and 4 below.

## The steps

The guides in [docs/](docs/) are numbered in reading order. Which ones you need depends on the
choice above:

| Step                                                   | Community hub                | Your own hub |
| ------------------------------------------------------ | ---------------------------- | ------------ |
| [1 — Install kubectl](docs/1_kubectl_install.md)       | **Skippable** (optional)     | Required     |
| [2 — NRP & namespace](docs/2_nrp_namespace.md)         | Required (Steps 1–3 only)    | Required     |
| [3 — Configure kubectl](docs/3_kubectl_config.md)      | **Skippable** (optional)     | Required     |
| [4 — Deploy JupyterHub](docs/4_nrp_jupyterhub.md)      | **Skip entirely**            | Required     |
| [5 — Verify](docs/5_verify_hub.md)                     | Required (short version)     | Required (full) |

### Steps 1–3 — get onto NRP · _step 2 for everyone, steps 1 and 3 for the own-hub path_

Both paths need an NRP identity and a namespace. Only the own-hub path needs a working `kubectl` —
it deploys and operates a hub and nothing else. **No assignment ever uses it:** every dataset is
read from inside the notebook server over HTTP, S3A, or Postgres, never through Kubernetes.

- **[1 — Install kubectl](docs/1_kubectl_install.md)** — install the `kubectl` CLI and the
  `kubelogin` OIDC plugin.
  _Community hub: skippable._ You never run a `kubectl` command against your namespace on that
  path; install it only if you want to inspect the namespace from the command line.

- **[2 — NRP & namespace](docs/2_nrp_namespace.md)** — **required on both paths**, but only its
  first half applies to everyone:
  - _Everyone_ — Step 1 (log into the NRP Portal via CILogon), Step 2 (request a namespace), and
    Step 3 (add teammates). A namespace is what gets you resources on the cluster, hosted hub or
    not, and approval can take a few days — start here.
  - _Own hub only_ — Step 4 ([pinning your `HUB_HOST`](docs/2_nrp_namespace.md#step-4-your-hubs-hostname-hub_host))
    and Step 5 ([registering a CILogon OAuth application](docs/2_nrp_namespace.md#step-5-register-a-cilogon-oauth-application)).
    **Skip both on the community hub** — the hosted hub already has a hostname and its own OAuth
    registration.

- **[3 — Configure kubectl](docs/3_kubectl_config.md)** — point `kubectl` at NRP and default it to
  your namespace.
  _Community hub: skippable_, for the same reason as step 1. It is also the quickest way to confirm
  your namespace is live, if you want that confirmation.

### Step 4 — deploy the hub · _own-hub path only_

- **[4 — Deploy JupyterHub](docs/4_nrp_jupyterhub.md)** — the Helm release: `values.yaml`, the
  per-assignment spawner profiles, the mandatory culling and auth policy, shared storage, and the
  egress each assignment's data needs.

**Community hub: skip this step entirely.** Go to
[jupyterhub-west.nrp-nautilus.io](https://jupyterhub-west.nrp-nautilus.io), log in with CILogon,
and pick an instance sized for the assignment you are running — the assignment's README says how
much memory it needs (the telescope assignment needs ≥ 16 GB, which is the one size you cannot get
wrong). Then go straight to step 5.

The hub image is already built and published, so nothing here requires building anything.

### Step 5 — verify · _everyone, in two versions_

- **[5 — Verify](docs/5_verify_hub.md)** — run [notebooks/test.ipynb](notebooks/test.ipynb) inside a
  spawned server to prove the things `kubectl` cannot: that the dependencies import, the memory
  limit is real, and each assignment's data is reachable.

Both paths run the same notebook, but not the same amount of it:

- **Community hub** — spawn a server, upload `notebooks/test.ipynb` (Step 2 of the guide), and
  *Run → Run All Cells*. Expect the `%pip install` cell to install for real and take several
  minutes, and expect the two Spark checks to come back as **warnings** — the stock image has no
  JVM, which only affects the DNS assignment. Everything above them should pass, including the
  in-cluster Ceph check. Skip the guide's Step 5 (there are no spawner profiles to repeat across)
  and its `kubectl`-based diagnosis in Step 4.
- **Your own hub** — the whole guide, including Step 5: run the notebook once per entry in
  `singleuser.profileList`, because the memory envelope is the one result that changes between
  profiles.

Instructors on either path should run this before handing an assignment out:

```
python scripts/nids-setup.py verify --release r1
```

It executes each module's answer-key notebook headlessly in the environment `env` built and prints
one line per module — which are ready to hand out, and what failed on the ones that are not. It
needs the `-key` repos, which are private, so it is an instructor-side command; a module whose key
is not cloned is reported as unverified rather than failed. Nothing is written back to the key
repos.

## For maintainers

- [Build the images](docs/0_build_images.md) — build the hub's container image with Docker and push
  it to a registry. Outside the numbered chain and needed only when the image itself changes (a new
  dependency, a new assignment, a base-image bump), never to deploy a hub or to use one.
- [Datasets](datasets/README.md) — every dataset the assignments read: who produced it, whether the
  public version can be used or a NIDS administrator has to build a NIDS-specific version first, how
  it is reached, and how to check it is still reachable. Also outside the numbered chain: a reader
  following steps 1–5 never needs it, but nobody can stand the data up without it.

## Design notes

[DESIGN.md](DESIGN.md) is the standing brief behind these guides: what is being built, the
decisions and their rationale, which assignments the image currently supports, and the open
questions. Read it before changing the image, the profiles, or the build.
