#!/usr/bin/env bash
# Full-history secret scan (SEC-19).
#
# The two secret scans this repository had before this script were both
# diff-scoped: the pre-commit gitleaks hook (SEC-17) sees only staged changes,
# and the CI gitleaks job (SEC-18) sees only the pull request's commit range.
# Neither of them can ever say anything about the history as a whole, so the
# claim "no secret has ever been committed to this repository" rested on a
# sweep someone ran by hand once, with nothing keeping it true. This script is
# that sweep, made repeatable, and it is wired into CI on a schedule and into
# the release pipeline.
#
# Three phases, deliberately overlapping:
#
#   1. every reachable commit on every ref  (`--log-opts="--all --full-history"`)
#   2. every object in the object database  — every blob, every commit message,
#      every tree listing AND every annotated tag message, including objects
#      that no ref reaches: an orphaned blob from an
#      amended commit, or a commit left behind by a rebase, is still served by
#      `git clone` in some configurations and is trivially recoverable from a
#      published repository until it is garbage-collected. Phase 1 cannot see
#      these; phase 2 can.
#   3. the working tree, including untracked files, which no committed history
#      covers at all.
#
# ---------------------------------------------------------------------------
# Why gitleaks and not TruffleHog, recorded deliberately
# ---------------------------------------------------------------------------
# SEC-19 in the portfolio security standard names TruffleHog with live-
# credential verification. This script uses gitleaks instead, on purpose.
#
# TruffleHog's Lob detector has been reported to match
# `\b((live|test)_[a-zA-Z0-9_]{35})\b`. Underscores are word characters, so
# that pattern matches ordinary pytest function names: `test_` plus a
# thirty-five-character snake_case tail is an unremarkable test name, and this
# repository contains five distinct ones today. TruffleHog then verifies a
# candidate by sending it to Lob and reading the rejection as evidence the key
# is live, which is how test names become "verified" findings — a failure mode
# other repositories in this portfolio have hit.
#
# Measured here on 2026-08-15 against TruffleHog 3.97.0, that specific defect
# does not reproduce: at that version the detector fired on `live_` followed by
# thirty-five hex characters and on nothing else tried — not on `test_` with
# the same tail, not on `live_` with non-hex characters — and a full TruffleHog
# scan of this repository returned zero results from every detector. That is a
# fact about one upstream version, not a property anyone here controls. The
# official action's `version` input defaults to `latest`, so SHA-pinning the
# action does not pin what actually scans, and a detector pattern can widen
# again in any release. gitleaks has no Lob detector and makes no network call
# to a third party while scanning, so this gate cannot be turned red by another
# project's regex, and it cannot turn a scan into an outbound request carrying
# this repository's contents.
#
# If TruffleHog is ever added here, it must be pinned to an exact version and
# run with `--exclude-detectors=Lob`.
#
# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
#   tools/secret-scan-full-history.sh
#
# Exit 0 when clean, 1 when gitleaks finds something, and 2 when this script
# could not perform the scan it claims to: gitleaks absent, gitleaks at an
# unpinned version, an object database it could not enumerate, an object it
# enumerated and could not read, an object of a type it does not materialize,
# or zero blobs enumerated. That is the same three-state contract every other gate here uses
# (ADR 0008), so "the scanner was not installed" can never be read as "the
# scanner found nothing". It used to exit 127 for an absent gitleaks and 1 for
# every other failure to scan, which put a damaged object database at the same
# exit code as a real leaked credential.
#
# Findings are redacted in output: this script must be safe to run in a public
# log.
#
# Environment:
#   GITLEAKS_BIN             gitleaks executable to use. Defaults to whatever is
#                            on PATH; CI passes the verified binary that
#                            .github/actions/setup-gitleaks just installed.
#   GITLEAKS_PINNED_VERSION  expected `gitleaks version` output (default below).
#                            The version is pinned because a scanner that
#                            silently changes its ruleset is not a gate.
#   ALLOW_GITLEAKS_VERSION_DRIFT=1
#                            run anyway on a mismatch, and say so. For a local
#                            developer who has a newer gitleaks; never in CI.

set -euo pipefail

GITLEAKS_PINNED_VERSION="${GITLEAKS_PINNED_VERSION:-8.30.1}"
GITLEAKS_BIN="${GITLEAKS_BIN:-gitleaks}"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# Passed explicitly to every phase. gitleaks discovers a config beside its
# --source, and phase 2's source is a temporary directory of object blobs, so
# discovery would apply the allowlist to two phases out of three and silently
# not to the one that reads unreachable objects.
gitleaks_config="${GITLEAKS_CONFIG:-$repo_root/.gitleaks.toml}"
if [ ! -f "$gitleaks_config" ]; then
  echo "secret-scan: no gitleaks config at '${gitleaks_config}'." >&2
  echo "  The allowlist is part of this gate; running without it would change" >&2
  echo "  what the gate can see without saying so." >&2
  echo "secret-scan: this is a failure to run the scan, not a clean result." >&2
  exit 2
fi

if ! command -v "$GITLEAKS_BIN" >/dev/null 2>&1; then
  echo "secret-scan: gitleaks not found (looked for '${GITLEAKS_BIN}')." >&2
  echo "  macOS:  brew install gitleaks" >&2
  echo "  other:  https://github.com/gitleaks/gitleaks/releases/tag/v${GITLEAKS_PINNED_VERSION}" >&2
  echo "secret-scan: this is a failure to run the scan, not a clean result." >&2
  exit 2
fi

installed_version="$("$GITLEAKS_BIN" version 2>/dev/null | tr -d '[:space:]')"
if [ "$installed_version" != "$GITLEAKS_PINNED_VERSION" ]; then
  if [ "${ALLOW_GITLEAKS_VERSION_DRIFT:-0}" = "1" ]; then
    echo "secret-scan: WARNING — gitleaks ${installed_version} is not the pinned ${GITLEAKS_PINNED_VERSION}; continuing because ALLOW_GITLEAKS_VERSION_DRIFT=1." >&2
  else
    echo "secret-scan: gitleaks ${installed_version} is installed, but this gate is pinned to ${GITLEAKS_PINNED_VERSION}." >&2
    echo "  A secret scan whose ruleset can change underneath it is not a gate." >&2
    echo "  Install the pinned version, or set ALLOW_GITLEAKS_VERSION_DRIFT=1 locally." >&2
    echo "secret-scan: this is a failure to run the scan, not a clean result." >&2
    exit 2
  fi
fi

echo "secret-scan: gitleaks ${installed_version}, three phases over $(git rev-parse --short HEAD)"

# --- phase 1: every reachable commit on every ref ---------------------------
echo "secret-scan: [1/3] all reachable commits on all refs"
"$GITLEAKS_BIN" detect \
  --source . \
  --log-opts="--all --full-history" \
  --config "$gitleaks_config" \
  --redact \
  --exit-code 1 \
  --no-banner

# --- phase 2: every object in the object database, reachable or not ---------
# `git cat-file --batch-all-objects` enumerates loose and packed objects alike,
# including unreachable ones. Blobs are written out with their object id as the
# filename; commit objects contribute their full message, because a secret
# pasted into a commit message is not in any blob and phase 1 does not read
# messages.
echo "secret-scan: [2/3] every object in the object database (including unreachable)"
objects_dir="$(mktemp -d)"
enumeration="$(mktemp)"
trap 'rm -rf "$objects_dir"; rm -f "$enumeration"' EXIT

# The enumeration is written to a file and its exit status checked, rather than
# piped straight into `while read` through process substitution. Neither `set
# -e` nor `pipefail` covers a process substitution, so a `git cat-file` that
# died halfway through used to end the loop quietly and this phase reported
# clean over the objects it never got to.
if ! git cat-file --batch-all-objects --batch-check='%(objectname) %(objecttype)' \
    >"$enumeration" 2>/dev/null; then
  echo "secret-scan: could not enumerate the object database." >&2
  echo "  Refusing to report a scan over an object list that is incomplete." >&2
  exit 2
fi

# An object that cannot be read is an object this scan did not cover. It used
# to be `|| true`, which counted it as materialized anyway and let the phase
# report clean over content nobody looked at. A failure here means the object
# database is damaged or unreadable, and that is a reason to stop, not to skip.
#
# The `case` had branches for `blob` and `commit` and no default, which is the
# same hole one level down. `git cat-file --batch-check` reports the type of an
# object it cannot read as `missing`, so the dominant corruption mode fell
# through: never counted, never materialized, never an error. `tree` and `tag`
# fell through too, so an annotated tag's message was never scanned despite the
# line above claiming every object. All four types are handled and anything
# else stops the scan.
materialize() {
  # $1 object id, $2 object type, $3 filename prefix
  if ! git cat-file "$2" "$1" >"$objects_dir/$3-$1" 2>/dev/null; then
    echo "secret-scan: could not read $2 object $1 from the object database." >&2
    echo "  Refusing to report a scan that skipped an object it enumerated." >&2
    exit 2
  fi
}

blob_count=0
commit_count=0
tree_count=0
tag_count=0
while read -r oid otype; do
  case "$otype" in
    blob)
      materialize "$oid" blob blob
      blob_count=$((blob_count + 1))
      ;;
    commit)
      materialize "$oid" commit commit
      commit_count=$((commit_count + 1))
      ;;
    tree)
      # Path names, which are content in an unreachable tree no other phase
      # reads.
      materialize "$oid" -p tree
      tree_count=$((tree_count + 1))
      ;;
    tag)
      # An annotated tag carries a message, and no other phase reads one.
      materialize "$oid" tag tag
      tag_count=$((tag_count + 1))
      ;;
    *)
      echo "secret-scan: object ${oid} enumerated with type '${otype}'." >&2
      echo "  'missing' means the object database could not read an object it" >&2
      echo "  listed; any other type is one this script does not materialize." >&2
      echo "  Either way this phase did not cover it, so it has no clean result." >&2
      exit 2
      ;;
  esac
done <"$enumeration"

echo "secret-scan: materialized ${blob_count} blobs, ${commit_count} commit objects, ${tree_count} trees and ${tag_count} tags"
if [ "$blob_count" -eq 0 ]; then
  echo "secret-scan: refusing to report success after enumerating zero blobs." >&2
  exit 2
fi

"$GITLEAKS_BIN" detect \
  --source "$objects_dir" \
  --no-git \
  --config "$gitleaks_config" \
  --redact \
  --exit-code 1 \
  --no-banner

# --- phase 3: the working tree, tracked and untracked -----------------------
echo "secret-scan: [3/3] working tree, including untracked files"
"$GITLEAKS_BIN" detect \
  --source . \
  --no-git \
  --config "$gitleaks_config" \
  --redact \
  --exit-code 1 \
  --no-banner

echo "secret-scan: clean — no findings in history, in the object database, or in the working tree"
