#!/usr/bin/env bash
# Clone (or update) NIDS repositories into one parent directory -- the shared root the
# assignment setup tooling then works against.
#
#   scripts/clone-nids-repos.sh --release r1        the four v1 modules, from the registry
#   scripts/clone-nids-repos.sh --modules ASN,DNS   named modules, from the registry
#   scripts/clone-nids-repos.sh --root /path        every nids-* repo in the org
#
# Two modes, differing only in where the repo list comes from. REGISTRY MODE (--release /
# --modules) reads a known list out of assignments/registry.toml, so it makes no GitHub
# listing call and needs no token; a repo the user cannot read is reported and skipped.
# ORG MODE (the default) enumerates the organisation. A registry is used rather than git
# submodules so a module can be cloned, skipped or pinned without touching this repo.
#
# Org mode requires authentication and deliberately does not make it optional: most
# nids-* repos are private, and an unauthenticated listing returns a plausible-looking
# subset with all of them missing, which is worse than a clear failure.
#
# Student repos are excluded by default. GitHub Classroom names them
# <assignment>-<github-username> (there are dozens of nids-asn-introduction-* alone), so
# a bare prefix match would clone every student's submitted work. Only the -key suffix is
# treated as a real repo; --include-students opts back in.
#
# Full walkthrough: the quickstart in README.md
set -euo pipefail

ORG="CAIDA"
PREFIX="nids-"
ROOT=""
PROTO=""            # resolved after parsing: ssh in org mode, https in registry mode
DRY_RUN=0
INCLUDE_STUDENTS=0
INCLUDE_KEY=0
RELEASE=""
MODULES=""
JOBS=4

usage() {
    sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//;$d'
    cat <<'USAGE'
Options:
  --release TIER       registry mode: clone the modules in a release tier, e.g. r1
  --modules A,B        registry mode: clone these assignment codes
  --include-key        registry mode: also clone the answer-key repos (needs auth)
  --root DIR           where the repos go (default: $NIDS_ROOT, else the parent of this
                       checkout)
  --org NAME           GitHub organisation (default: CAIDA)
  --prefix STR         repository name prefix to match (default: nids-)
  --ssh | --https      clone protocol (default: ssh)
  --include-students   also clone GitHub Classroom student repos
  --jobs N             parallel clones (default: 4)
  --dry-run            print what would happen, change nothing
  -h, --help           this text

Authentication, in the order tried:
  $GITHUB_TOKEN or $GH_TOKEN, else `gh auth token` if the gh CLI is installed.
  Required in org mode and for --include-key. Optional in registry mode, where it is
  used if present (so private modules clone for the team) and its absence is not an error.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --release) RELEASE="$2"; shift 2 ;;
        --modules) MODULES="$2"; shift 2 ;;
        --include-key) INCLUDE_KEY=1; shift ;;
        --root) ROOT="$2"; shift 2 ;;
        --org) ORG="$2"; shift 2 ;;
        --prefix) PREFIX="$2"; shift 2 ;;
        --ssh) PROTO="ssh"; shift ;;
        --https) PROTO="https"; shift ;;
        --include-students) INCLUDE_STUDENTS=1; shift ;;
        --jobs) JOBS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

# --- mode ----------------------------------------------------------------------
REGISTRY_MODE=0
if [[ -n "$RELEASE" || -n "$MODULES" ]]; then
    REGISTRY_MODE=1
fi
if [[ $INCLUDE_KEY -eq 1 && $REGISTRY_MODE -eq 0 ]]; then
    echo "--include-key needs --release or --modules" >&2; exit 2
fi

# --- where ---------------------------------------------------------------------
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname -- "$SCRIPT_DIR")"
if [[ -z "$ROOT" ]]; then
    ROOT="${NIDS_ROOT:-$(dirname -- "$REPO_ROOT")}"
fi
mkdir -p "$ROOT"
ROOT="$(cd -- "$ROOT" && pwd)"

# --- auth ----------------------------------------------------------------------
TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
if [[ -z "$TOKEN" ]] && command -v gh >/dev/null 2>&1; then
    TOKEN="$(gh auth token 2>/dev/null || true)"
fi
# Registry mode names its repos rather than discovering them, so a missing token costs
# only the private ones -- reported per repo, not fatal. --include-key still needs it.
if [[ -z "$TOKEN" && $REGISTRY_MODE -eq 1 && $INCLUDE_KEY -eq 1 ]]; then
    echo "error: --include-key needs a GitHub token; every *-key repo is private" >&2
    exit 3
fi
if [[ -z "$PROTO" ]]; then
    # https is anonymous, so it is the right default only when we have no credentials.
    if [[ $REGISTRY_MODE -eq 1 && -z "$TOKEN" ]]; then PROTO="https"; else PROTO="ssh"; fi
fi

if [[ -z "$TOKEN" && $REGISTRY_MODE -eq 0 ]]; then
    cat >&2 <<'NOAUTH'
error: no GitHub token.

Most nids-* repositories are private -- nids-setup, every *-key repo, and
nids-module-creator among them. Listing the organisation without a token silently
returns only the public subset, so this script refuses to run rather than clone
half the repos and look like it succeeded.

Set one of:
  export GITHUB_TOKEN=ghp_...        # a PAT with `repo` scope
  gh auth login                      # then this script reads `gh auth token`
NOAUTH
    exit 3
fi

# --- list ----------------------------------------------------------------------
# Paginated because the org has well over 100 repos.
list_repos() {
    local page=1 body
    while :; do
        body="$(curl -sSf \
            -H "Authorization: Bearer $TOKEN" \
            -H "Accept: application/vnd.github+json" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            "https://api.github.com/orgs/${ORG}/repos?per_page=100&page=${page}&type=all")"
        [[ "$(jq 'length' <<<"$body")" -eq 0 ]] && break
        jq -r '.[] | [.name, (.archived|tostring), (.private|tostring), .ssh_url, .clone_url] | @tsv' <<<"$body"
        page=$((page + 1))
    done
}

# A student repo is <known-assignment>-<suffix> where the suffix is not "key".
# Matching on the known assignment list rather than on a name shape keeps a
# genuinely new repo (say nids-ip-data-plane) from being mistaken for a fork.
ASSIGNMENT_REPOS=(
    nids-asn-introduction nids-bgp-control-plane nids-irr-rpki-whois
    nids-irr-rpki-whois-local nids-itdk nids-dns-ecosystem nids-telescope-traffic
    nids-iyp nids-ucsdnt-expanse nids-geolocation nids-ip-data-plane
)

is_student_repo() {
    local name="$1" base
    for base in "${ASSIGNMENT_REPOS[@]}"; do
        [[ "$name" == "$base" || "$name" == "${base}-key" ]] && return 1
        [[ "$name" == "${base}-"* ]] && return 0
    done
    return 1
}

# --- registry mode: the repo list comes from assignments/registry.toml ------------
registry_repos() {
    local args=(--repos)
    [[ -n "$RELEASE" ]] && args+=(--release "$RELEASE")
    [[ -n "$MODULES" ]] && args+=(--modules "$MODULES")
    [[ $INCLUDE_KEY -eq 1 ]] && args+=(--include-key)
    "${PYTHON:-python3}" "$SCRIPT_DIR/nids_registry.py" "${args[@]}"
}

repo_url() {
    if [[ "$PROTO" == "ssh" ]]; then
        echo "git@github.com:${ORG}/$1.git"
    else
        echo "https://github.com/${ORG}/$1.git"
    fi
}

if [[ $REGISTRY_MODE -eq 1 ]]; then
    echo "source: assignments/registry.toml (${RELEASE:-modules $MODULES})"
    echo "root:   $ROOT"
    echo "proto:  $PROTO"
    [[ -n "$TOKEN" ]] || echo "auth:   none -- private modules will be reported and skipped"
    [[ $DRY_RUN -eq 0 ]] || echo "mode:   dry run"
    echo

    WANTED=()
    while IFS=$'\t' read -r code role name ref; do
        [[ -n "$name" ]] || continue
        WANTED+=("${name}"$'\t'"$(repo_url "$name")"$'\t'"${ref}")
    done < <(registry_repos)

    if [[ ${#WANTED[@]} -eq 0 ]]; then
        echo "no modules matched" >&2; exit 1
    fi
fi

# --- org mode: enumerate the organisation ----------------------------------------
if [[ $REGISTRY_MODE -eq 0 ]]; then
echo "org:    $ORG (prefix '$PREFIX')"
echo "root:   $ROOT"
echo "proto:  $PROTO"
[[ $DRY_RUN -eq 0 ]] || echo "mode:   dry run"
echo

WANTED=()
SKIPPED_STUDENT=0
SKIPPED_ARCHIVED=()
while IFS=$'\t' read -r name archived private ssh_url clone_url; do
    [[ "$name" == "$PREFIX"* ]] || continue
    if [[ $INCLUDE_STUDENTS -eq 0 ]] && is_student_repo "$name"; then
        SKIPPED_STUDENT=$((SKIPPED_STUDENT + 1))
        continue
    fi
    if [[ "$archived" == "true" ]]; then
        SKIPPED_ARCHIVED+=("$name")
        continue
    fi
    if [[ "$PROTO" == "ssh" ]]; then
        WANTED+=("${name}"$'\t'"${ssh_url}"$'\t')
    else
        WANTED+=("${name}"$'\t'"${clone_url}"$'\t')
    fi
done < <(list_repos)

if [[ ${#WANTED[@]} -eq 0 ]]; then
    echo "no repositories matched '$PREFIX' in $ORG" >&2
    exit 1
fi
fi

# --- clone or update -----------------------------------------------------------
# Idempotent: an existing checkout is fetched and fast-forwarded, never reset. A repo
# with local changes or a diverged branch is reported and left exactly as it is --
# this script must be safe to re-run in a directory someone is working in.
sync_one() {
    local name="$1" url="$2" ref="${3:-}"
    local dest="$ROOT/$name"     # separate statement: `local a=.. b=$a` does not see $a
    if [[ ! -d "$dest" ]]; then
        if [[ $DRY_RUN -eq 1 ]]; then
            printf '%-42s would clone\n' "$name"; return
        fi
        local err
        if err="$(git clone --quiet "$url" "$dest" 2>&1)"; then
            [[ -n "$ref" ]] && git -C "$dest" checkout --quiet "$ref"
            printf '%-42s cloned%s\n' "$name" "${ref:+ at $ref}"
        elif grep -qiE 'not found|denied|authentication|could not read Username' <<<"$err"; then
            printf '%-42s no access (private, or no token)\n' "$name"
        else
            printf '%-42s CLONE FAILED: %s\n' "$name" "$(head -1 <<<"$err")"
        fi
        return
    fi
    if [[ ! -d "$dest/.git" ]]; then
        printf '%-42s skipped (not a git checkout)\n' "$name"; return
    fi
    if [[ -n "$(git -C "$dest" status --porcelain)" ]]; then
        printf '%-42s skipped (uncommitted changes)\n' "$name"; return
    fi
    if [[ $DRY_RUN -eq 1 ]]; then
        printf '%-42s would fetch\n' "$name"; return
    fi
    git -C "$dest" fetch --quiet --all --prune 2>/dev/null || true
    if git -C "$dest" merge --ff-only --quiet '@{u}' 2>/dev/null; then
        printf '%-42s updated\n' "$name"
    else
        printf '%-42s left alone (diverged or no upstream)\n' "$name"
    fi
}
export GIT_TERMINAL_PROMPT=0     # a private repo must fail, not hang asking for a password

# Run the syncs in batches of $JOBS, each writing to a numbered file so the report comes
# out in registry order rather than finish order.
#
# Deliberately not `xargs -I{}`: BSD xargs (macOS) treats tabs as argument separators and
# rejoins them with spaces, so a tab-separated record arrives as one field and every
# clone gets an empty URL. GNU xargs preserves the tab, which is why that only ever broke
# on a Mac. A plain loop is portable and needs no `export -f` either.
OUTDIR="$(mktemp -d)"
trap 'rm -rf "$OUTDIR"' EXIT

i=0
for record in "${WANTED[@]}"; do
    IFS=$'\t' read -r name url ref <<<"$record"
    sync_one "$name" "$url" "$ref" > "$OUTDIR/$(printf '%04d' "$i")" 2>&1 &
    i=$((i + 1))
    if [[ $((i % JOBS)) -eq 0 ]]; then wait; fi
done
wait
cat "$OUTDIR"/*

# Counted with `if grep -q` rather than a `grep | wc -l` pipeline: `pipefail` is on, and
# grep exiting 1 on no-match would take the whole script down with it.
FAILED=0
NOACCESS=0
for report in "$OUTDIR"/*; do
    if grep -q 'CLONE FAILED' "$report"; then FAILED=$((FAILED + 1)); fi
    if grep -q 'no access' "$report"; then NOACCESS=$((NOACCESS + 1)); fi
done

echo
echo "${#WANTED[@]} repositories in $ROOT"
if [[ $REGISTRY_MODE -eq 0 ]]; then
    [[ $SKIPPED_STUDENT -eq 0 ]] || echo "$SKIPPED_STUDENT student repos skipped (--include-students to fetch them)"
    [[ ${#SKIPPED_ARCHIVED[@]} -eq 0 ]] || echo "${#SKIPPED_ARCHIVED[@]} archived repos skipped: ${SKIPPED_ARCHIVED[*]}"
fi
# `no access` is an expected outcome for someone without CAIDA membership, so it is not a
# failure. A clone that broke for any other reason is.
[[ $NOACCESS -eq 0 ]] || echo "$NOACCESS repository/ies you cannot read were skipped"
if [[ $FAILED -gt 0 ]]; then
    echo "$FAILED clone(s) FAILED -- nothing downstream will work until they succeed" >&2
    exit 1
fi
exit 0
