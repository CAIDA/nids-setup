# RouteViews BGP RIB (MRT)

Full BGP routing-table snapshots from a RouteViews collector, in MRT format, read over the OSDF
federation.

- **Used by:** BGP, TELESCOPE
- **Produced by:** External — University of Oregon RouteViews, served via the OSDF / OSG data federation
- **Served from:** Both — external egress to `osdf-director.osg-htc.org`
- **Public version usable:** Yes — read directly, no mirror involved
- **Setup:** none needed
- **Credentials:** none (anonymous OSDF)
- **Time-sensitive:** Yes — the path encodes a `YYYY.MM` collection month
- **Licence / governance:** open

## Access

Two steps, and they use two different addressing forms — this is the easiest thing to get wrong.
`OSDFFileSystem.ls()` takes a **bare federation path**, and the returned entries are bare paths too;
the HTTPS host is a separate constant that gets prepended to build a URL the MRT parser can fetch.

```python
import pybgpkit_parser as bgpkit          # the PyPI package is pybgpkit-parser; NOT `import bgpkit`
from pelicanfs.core import OSDFFileSystem

OSDF_BASE = "https://osdf-director.osg-htc.org"
COLLECTOR = "route-views3"
RIB_DIR = f"/routeviews/{COLLECTOR}/bgpdata/2026.05/RIBS"

objects = sorted(OSDFFileSystem().ls(RIB_DIR), key=lambda x: x["name"])
url = OSDF_BASE + objects[0]["name"]      # e.g. .../RIBS/rib.20260501.0000.bz2
parser = bgpkit.Parser(url)
```

- **Dependencies:** `pelicanfs`, `pybgpkit-parser`. Both are in the `nids-hub` image.
- `pybgpkit-parser` ships prebuilt wheels — no `libbgpstream` to compile.
- A RIB is large and parsing one takes minutes. That is the assignment's work, not a check's.

## Concrete values in use today

| assignment | value | source |
|---|---|---|
| BGP | `/routeviews/route-views3/bgpdata/2026.05/RIBS` | `nids-bgp-control-plane-key/00-environment-check.ipynb:181-182` |
| BGP | first object `rib.20260501.0000.bz2` | `nids-bgp-control-plane-key/nids-bgp-control-plane-key.ipynb:45` |
| TELESCOPE | `/routeviews/route-views3/bgpdata/2026.06/RIBS` | `nids-telescope-traffic-key/00-environment-check.ipynb:183` |

The two assignments use **different months** — BGP `2026.05`, TELESCOPE `2026.06`. The access pattern
is identical; only the collection month differs. Neither is more correct than the other, but a change
to one does not apply to the other.

## Validate

Directory listing only. `OSDFFileSystem().ls(RIB_DIR)` returning a non-empty list proves the
federation is reachable and the month directory exists — which is everything a reachability check can
establish without a multi-minute parse.

## See also

- `nids-bgp-control-plane/Datasets.md`, `nids-telescope-traffic/Datasets.md`
- [docs/4_nrp_jupyterhub.md](../../docs/4_nrp_jupyterhub.md#data-access-and-egress) — the
  `osdf-director.osg-htc.org` egress row
