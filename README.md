# nids-setup

Setup and tooling for the **NIDS assignments** — the hands-on modules of CAIDA's
[Network Infrastructure Data Science project](https://www.caida.org/projects/nids/).

Each module is a Jupyter notebook that asks a question about the real Internet and answers it
against real measurement data: which networks does this one buy transit from, how did this prefix
propagate, what does the DNS look like for an entire top-level domain. Students write the analysis;
the data is the production article, not a teaching sample.

This repository holds none of the assignments themselves. It holds the things they have in common —
where each module runs, what environment it needs, which datasets it reads and how to reach them,
and the commands that set all of that up. Each module lives in its own repository, listed below.

## Where the modules run

This is the first thing to understand about the collection, because it decides everything else.

**Two modules run on a student's own laptop: ASN and BGP.** They read only data that CAIDA
publishes openly, and every package they need installs from PyPI as a wheel. Nothing to request,
no account, no allocation — clone, run one command, open the notebook. They are the way in.

**The rest of the collection runs on the [National Research Platform](https://nationalresearchplatform.org/)
(NRP) JupyterHub**, and one — the UCSD Network Telescope module — runs on **SDSC Expanse** under
Slurm. This is not about how much compute a notebook wants. It is about where the data is: a
database that has to be deployed, an archive of captures that is not published, a registry snapshot
no longer re-fetchable from anywhere, a telescope feed governed by a data-use agreement. Moving the
notebook to a bigger laptop does not move the data.

**ASN and BGP are the whole laptop set, and there are no plans to add to it.** A module joins them
only by reading wholly public data and installing from wheels, and nothing else in the collection
does. Treat the two as a sampler: enough to see what these assignments are, before arranging the
access the rest of them need.

| Module | Code | Runs on | Why |
|---|---|---|---|
| [ASN Introduction](https://github.com/CAIDA/nids-asn-introduction) | `ASN` | Laptop or NRP | Public CAIDA data; standard library only |
| [BGP Control Plane](https://github.com/CAIDA/nids-bgp-control-plane) | `BGP` | Laptop or NRP | Public CAIDA data and RouteViews over OSDF; all wheels |
| [DNS Ecosystem](https://github.com/CAIDA/nids-dns-ecosystem) | `DNS` | NRP | Public data, but the queries run under Spark, which needs a JDK |
| [Registries: WHOIS, IRR & RPKI](https://github.com/CAIDA/nids-irr-rpki-whois) | `IRR` | NRP | Pins 2023 snapshots, and no registry archives its dumps |
| [ITDK](https://github.com/CAIDA/nids-itdk) | `ITDK` | NRP | Reads a Postgres database deployed in the namespace |
| [Internet Yellow Pages](https://github.com/CAIDA/nids-iyp) | `IYP` | NRP | Needs a reachable Neo4j; the public endpoint is down |
| [Network Telescope Traffic](https://github.com/CAIDA/nids-telescope-traffic) | `TELESCOPE` | NRP | Capture samples are unpublished; GeoLite2 is account-gated |
| [UCSD Network Telescope](https://github.com/CAIDA/nids-ucsdnt-expanse) | `UCSDNT` | SDSC Expanse | A credentialed archive, governed by a data-use agreement, that stays on Expanse |

The codes are the ones published in
[assignments.json](https://www.caida.org/projects/nids/assignments/assignments.json), and every
command here takes them. `assignments/registry.toml` is the machine-readable version of this table
and is what the tooling actually reads.

ASN and BGP are ready to hand out and are what release 1 covers. The rest are held back on the
reasons above — recorded per module in the registry, so nothing here is "missing" without saying
why. DNS is the nearest of them: it is ready to teach and reads only public data, and what it
waits on is a hub rather than any work on the module.

---

## Running ASN and BGP on your own machine

One command clones the two module repositories, builds a Python environment for them, and
downloads their data.

```bash
git clone https://github.com/CAIDA/nids-setup.git
cd nids-setup
```

Then the line that matches your machine:

| | run this | then activate with |
|---|---|---|
| **macOS / Linux** | `./setup.sh --local` | `source .venv/bin/activate` |
| **Windows** | `.\setup.cmd --local` | `.venv\Scripts\Activate.ps1` |

Finally:

```
jupyter lab ..            # the module repos are cloned beside nids-setup
```

Open either module's notebook and run it. There is no manual download step, and re-running the
setup is safe — each stage skips what is already done.

`--local` selects ASN and BGP because those are the modules that run here; you do not have to name
them. Both launchers call the same `scripts/nids-setup.py setup` and hold no logic of their own, so
every option below behaves identically on all platforms.

### Prerequisites

- **Python 3.11 or newer**, and **git** on your PATH.
- An interpreter with **`venv` support** — some system Python builds ship without it, and
  `--python` is how you point at one that has it.

That is the whole list for ASN and BGP. They install nothing that needs a compiler, which is why
they are the two modules that run here.

Installing Python on Windows: get it from [python.org](https://www.python.org/downloads/windows/)
and tick *Add python.exe to PATH*. `setup.cmd` finds it through the `py` launcher or `python`.

### Useful variations

```
./setup.sh --local --assignment ASN       # just one module
./setup.sh --local --root ~/nids          # put the module repos somewhere specific
./setup.sh --local --python python3.12    # build the environment with a specific interpreter
./setup.sh --local --skip-data            # clone and build the environment only
```

### If something goes wrong

```
python scripts/nids-setup.py discover --venue local   # what is cloned, and its state
python scripts/check-datasets.py --assignment BGP     # is this module's data reachable from here
```

Each stage is also a subcommand you can run alone — `nids-setup.py clone`, `env`, `data` — which is
the quickest way to redo just the part that failed.

### Trying a hub module on a laptop anyway

Nothing stops you: `./setup.sh --local --assignment DNS` sets DNS up and says plainly that it is a hub
module. It may well work — DNS reads public data, and a machine that already has a JDK 17+ has the
one thing `setup` cannot install for you. What you will not get is support, or any promise that the
notebook has ever been run that way. The modules that read in-cluster or credentialed data will
fail at the first read no matter what the laptop has.

---

## For instructors

Before handing a module out, run:

```
python scripts/nids-setup.py prep --assignment ASN
```

`prep` answers the question an instructor actually has — *can I hand this out, and what do I have to
do first?* It reports where the module runs, what the students need to have arranged, whether the
pinned datasets are still reachable, and whether the answer key agrees with the student repo. It
writes nothing.

```
python scripts/nids-setup.py verify --venue local
```

`verify` goes further and executes each module's answer-key notebook, printing one line per module:
which are ready to hand out, and what failed on the ones that are not. It needs the `-key`
repositories, which are private, so it is an instructor-side command; a module whose key is not
cloned is reported as unverified rather than failed. Nothing is written back to the key repos.

**If you are teaching anything past ASN and BGP, start the access conversation early.** An NRP
namespace has to be requested and approved, and an Expanse allocation is a separate process again.
Neither is quick, and both are prerequisites rather than conveniences. See below.

---

## Running on NRP

Everything past ASN and BGP runs here. Two ways in, and the choice is worth making before you
start.

**The community hub** — NRP's hosted service at
[jupyterhub-west.nrp-nautilus.io](https://jupyterhub-west.nrp-nautilus.io). Log in with CILogon,
pick an instance size, go. Nothing to deploy and nothing to maintain.

**Your own hub** — a JupyterHub you deploy into your own NRP namespace with Helm, running the
`nids-hub` image with one spawner profile per module.

|                    | Community hub                                                                   | Your own hub                                                                  |
| ------------------ | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Setup effort       | Log in                                                                          | Namespace admin, a CILogon OAuth app, a Helm release you own                   |
| Environment        | NRP's stock images — each module `%pip install`s its own deps, taking minutes    | The pinned `nids-hub` image with every module's deps already installed         |
| Spark (DNS module) | No JVM; Spark pulls its S3A jars from Maven Central at session start             | Spark-capable image with the S3A jars pre-staged                               |
| Memory             | You pick an instance size per module, by hand, every time                       | One right-sized spawner profile per module                                     |
| Home directory     | Starts at 5 GB (extendable on request)                                          | Whatever you set in `singleuser.storage`                                       |
| Idle culling       | ~1 hour after the browser disconnects, fixed                                    | Yours to set (NRP requires `timeout` ≤ 6 h)                                    |
| Access control     | NRP's                                                                           | Your own: `allowed_idps` / `allowed_domains` / a roster                        |
| Shared datasets    | Each user fetches their own                                                     | A read-only PVC mounted into every server                                      |
| Good for           | A student, or an instructor trying one module out                               | An instructor standing up a managed, reproducible class environment            |

> **If you are unsure, use the community hub.** Switching later costs nothing — no module is
> hub-specific — and it saves you steps 1, 3, and 4 below.

Once you are on a hub, setting a module up is the same one command, in a terminal inside your
notebook server:

```
./setup.sh --nrp --assignment DNS
```

It clones the module and stages its data. It does *not* build an environment: on the hub the image
supplies the packages, and a virtual environment there would only shadow the kernel the notebook
actually runs in.

### The deployment guides

The guides in [docs/](docs/) cover **deploying and operating a hub**. A student running a module
needs none of them, and neither does an instructor on the community hub who is not deploying
anything.

| Step                                                   | Community hub                | Your own hub |
| ------------------------------------------------------ | ---------------------------- | ------------ |
| [1 — Install kubectl](docs/1_kubectl_install.md)       | **Skippable** (optional)     | Required     |
| [2 — NRP & namespace](docs/2_nrp_namespace.md)         | Required (Steps 1–3 only)    | Required     |
| [3 — Configure kubectl](docs/3_kubectl_config.md)      | **Skippable** (optional)     | Required     |
| [4 — Deploy JupyterHub](docs/4_nrp_jupyterhub.md)      | **Skip entirely**            | Required     |
| [5 — Verify](docs/5_verify_hub.md)                     | Required (short version)     | Required (full) |

#### Steps 1–3 — get onto NRP · _step 2 for everyone, steps 1 and 3 for the own-hub path_

Both paths need an NRP identity and a namespace. Only the own-hub path needs a working `kubectl` —
it deploys and operates a hub and nothing else. **No module ever uses it:** every dataset is read
from inside the notebook server over HTTP, S3A, or Postgres, never through Kubernetes.

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

#### Step 4 — deploy the hub · _own-hub path only_

- **[4 — Deploy JupyterHub](docs/4_nrp_jupyterhub.md)** — the Helm release: `values.yaml`, the
  per-module spawner profiles, the mandatory culling and auth policy, shared storage, and the
  egress each module's data needs.

**Community hub: skip this step entirely.** Go to
[jupyterhub-west.nrp-nautilus.io](https://jupyterhub-west.nrp-nautilus.io), log in with CILogon,
and pick an instance sized for the module you are running — the module's README says how much
memory it needs. Then go straight to step 5.

#### Step 5 — verify · _everyone, in two versions_

- **[5 — Verify](docs/5_verify_hub.md)** — run [notebooks/test.ipynb](notebooks/test.ipynb) inside a
  spawned server to prove the things `kubectl` cannot: that the dependencies import, the memory
  limit is real, and each module's data is reachable.

Both paths run the same notebook, but not the same amount of it:

- **Community hub** — spawn a server, upload `notebooks/test.ipynb` (Step 2 of the guide), and
  *Run → Run All Cells*. Expect the `%pip install` cell to install for real and take several
  minutes, and expect the two Spark checks to come back as **warnings** — the stock image has no
  JVM, which only affects the DNS module. Everything above them should pass, including the
  in-cluster Ceph check. Skip the guide's Step 5 (there are no spawner profiles to repeat across)
  and its `kubectl`-based diagnosis in Step 4.
- **Your own hub** — the whole guide, including Step 5: run the notebook once per entry in
  `singleuser.profileList`, because the memory envelope is the one result that changes between
  profiles.

---

## Running on SDSC Expanse

The **UCSD Network Telescope** module (`UCSDNT`) is the one module that is not a JupyterHub module
at all. It runs as a Slurm batch job on [SDSC Expanse](https://www.sdsc.edu/systems/expanse/),
reading the credentialed FlowTuple archive that stays on that machine under CAIDA's data-use
agreement. It needs an Expanse allocation, which an instructor obtains themselves, and it takes no
spawner profile and no hub image.

None of the tooling here provisions Expanse. The module's own repository carries its job scripts;
what this repository records is its coordinates and pins, in
[datasets/ucsdnt-expanse-flowtuple/](datasets/ucsdnt-expanse-flowtuple/).

---

## For maintainers

- [Datasets](datasets/README.md) — every dataset the modules read: who produced it, whether the
  public version can be used or a NIDS administrator has to build a NIDS-specific version first,
  how it is reached, and how to check it is still reachable. Nobody can stand the data up without
  it.
- [Build the images](docs/0_build_images.md) — build the `nids-hub` container image with Docker and
  push it to a registry the hub can pull from. Needed when the image itself changes — a new
  dependency, a new module, a base-image bump — and when standing up a hub that uses it.
- [assignments/registry.toml](assignments/registry.toml) — one block per module: its repositories,
  its venue, its environment, and the pin it supplies for every dataset it reads. Modules pin
  *placeholders*, never URLs, so a path shape lives in exactly one place.
  [datasets/SCHEMA.md](datasets/SCHEMA.md) documents both registries, and
  `python scripts/nids_registry.py --validate` cross-checks them offline.
