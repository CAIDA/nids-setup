#!/usr/bin/env bash
# Clone (or update) every NIDS repository from the CAIDA GitHub organisation into one
# parent directory -- the shared root the assignment setup tooling then works against.
#
#   scripts/clone-nids-repos.sh --root /path/to/parent
#
# Authentication is REQUIRED, and deliberately not optional: most nids-* repos are
# private, including nids-setup itself, every answer-key repo, nids-module-creator,
# nids-iyp and nids-geolocation. An unauthenticated listing returns a plausible-looking
# subset with all of those missing, which is far worse than a clear failure.
#
# Student repos are excluded by default. GitHub Classroom names them
# <assignment>-<github-username> (there are dozens of nids-asn-introduction-* alone), so
# a bare prefix match would clone every student's submitted work. Only the -key suffix is
# treated as a real repo; --include-students opts back in.
#
# Full walkthrough: docs/6_assignment_setup.md
set -euo pipefail

ORG="CAIDA"
PREFIX="nids-"
ROOT=""
PROTO="ssh"
DRY_RUN=0
INCLUDE_STUDENTS=0
JOBS=4

usage() {
    sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//;$d'
    cat <<'USAGE'
Options:
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
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
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
if [[ -z "$TOKEN" ]]; then
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

echo "org:    $ORG (prefix '$PREFIX')"
echo "root:   $ROOT"
echo "proto:  $PROTO"
[[ $DRY_RUN -eq 1 ]] && echo "mode:   dry run"
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
        WANTED+=("${name}"$'\t'"${ssh_url}")
    else
        WANTED+=("${name}"$'\t'"${clone_url}")
    fi
done < <(list_repos)

if [[ ${#WANTED[@]} -eq 0 ]]; then
    echo "no repositories matched '$PREFIX' in $ORG" >&2
    exit 1
fi

# --- clone or update -----------------------------------------------------------
# Idempotent: an existing checkout is fetched and fast-forwarded, never reset. A repo
# with local changes or a diverged branch is reported and left exactly as it is --
# this script must be safe to re-run in a directory someone is working in.
sync_one() {
    local name="$1" url="$2" dest="$ROOT/$name"
    if [[ ! -d "$dest" ]]; then
        if [[ $DRY_RUN -eq 1 ]]; then
            printf '%-42s would clone\n' "$name"; return
        fi
        if git clone --quiet "$url" "$dest" 2>/dev/null; then
            printf '%-42s cloned\n' "$name"
        else
            printf '%-42s CLONE FAILED\n' "$name"
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
export -f sync_one
export ROOT DRY_RUN

printf '%s\n' "${WANTED[@]}" \
    | xargs -P "$JOBS" -I{} bash -c 'IFS=$'"'"'\t'"'"' read -r n u <<<"{}"; sync_one "$n" "$u"' \
    | sort

echo
echo "${#WANTED[@]} repositories in $ROOT"
[[ $SKIPPED_STUDENT -gt 0 ]] && echo "$SKIPPED_STUDENT student repos skipped (--include-students to fetch them)"
[[ ${#SKIPPED_ARCHIVED[@]} -gt 0 ]] && echo "${#SKIPPED_ARCHIVED[@]} archived repos skipped: ${SKIPPED_ARCHIVED[*]}"
exit 0
