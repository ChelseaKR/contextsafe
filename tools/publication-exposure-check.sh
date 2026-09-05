#!/usr/bin/env bash
# Is the removed document still served? Asked of the live host, and dated.
#
# `docs/PUBLICATION-READINESS.md` section 6 records a document that a delete
# commit removed from every branch and that the host still serves by explicit
# commit id. The 2026-08-29 update at the top of that file records what went
# wrong when the question was answered from a clone instead: `git show` fails
# for a reader who only cloned, the finding was briefly written down as closed,
# and it was not. **The direction of that error is the dangerous one — it told a
# reader an exposure was over while it was live.** This script exists so the
# question is answered by asking the host, and so the answer carries the day it
# was given.
#
# It is a probe, not a gate over this tree, which is why it is not a `make`
# target and not part of `make verify`: it needs the network and a specific
# remote host, `make verify` must stay exactly what CI runs, and the answer is a
# fact about the host on one day rather than a property of the repository.
#
# ---------------------------------------------------------------------------
# Why the ref and the path are arguments and not constants
# ---------------------------------------------------------------------------
# The audit already prints the ids by which the blob is addressed, and says that
# printing them is itself part of the exposure surface. This script does not
# restate them: the operator reads them out of section 6 and passes them in, so
# that the checker adds no second pointer to anything. It never prints, stores,
# or transmits any response body either — only HTTP status codes, the ref and
# path it was handed, and a verdict.
#
# ---------------------------------------------------------------------------
# What it probes, and why a 404 alone proves nothing
# ---------------------------------------------------------------------------
# Three content surfaces, unauthenticated, because "served publicly and without
# authentication" is the exposure being measured and a token would answer a
# different question:
#
#   1. the contents API at the ref
#   2. the web blob view at the ref
#   3. the raw host at the ref
#
# and a fourth probe that is corroboration rather than subject: the commit
# object itself, which is what a purge removes. A purge takes the commit with
# the blob, so a commit that still resolves while all three content surfaces
# report absent is either an incomplete purge or a mistyped path, and the script
# says so instead of calling it gone.
#
# A 404 from any of them is also what a private repository, a renamed owner, a
# deleted repository, a rate limit, and a typo in the ref all look like. A
# checker that read those as "gone" would report a clean result over content it
# never examined, which is the defect class `docs/18-ASSURANCE-PROGRAM.md`
# names, and it is the exact error this exposure was already recorded with once.
#
# So each of the three content surfaces carries a positive control: the same
# request shape against a ref and path that must be served (the default branch
# and `README.md`). A negative subject result means "removed" only when its
# surface answered a control correctly in the same run. A failed control is not
# a clean result and not a finding; it is exit 2.
#
# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
#   tools/publication-exposure-check.sh --ref REF --path PATH [options]
#
#     --ref REF            commit id or ref to probe. Required; read it from
#                          docs/PUBLICATION-READINESS.md section 6.
#     --path PATH          repository-relative path to probe. Required, same
#                          source.
#     --repo OWNER/NAME    default: derived from the `origin` remote.
#     --control-ref REF    ref for the positive controls (default: HEAD).
#     --control-path PATH  path for the positive controls (default: README.md).
#     --output FILE        append the record to FILE as well as printing it.
#
# Exit 0 when every content surface answered "absent", the commit answered
# "absent" with them, and every control answered "served"; 1 when any content
# surface found the document still served; 2 when the run could not establish
# either — curl missing, a control that did not answer, a status the script will
# not classify, a redirect it will not follow, a commit that outlived the path,
# or a record it was asked to write and could not. That is the three-state contract
# every gate in this repository uses (ADR 0008): "the probe could not look" can
# never be read as "the content is gone". Exit 64 is a usage error.
#
# ---------------------------------------------------------------------------
# What exit 0 does not mean
# ---------------------------------------------------------------------------
# It means these surfaces did not serve this path at this ref at the printed
# time. It does not reach a fork, a clone somebody already took, a search or
# proxy cache, a third-party mirror, or a web archive, and none of those is
# under the maintainer's control. Re-run it rather than citing an old run: this
# answer is stale the moment it is printed, by construction.

set -euo pipefail

RECORD_VERSION=1
PROBE_TIMEOUT="${PROBE_TIMEOUT:-20}"

repo=""
ref=""
path=""
control_ref="HEAD"
control_path="README.md"
output=""

usage() {
  echo "usage: tools/publication-exposure-check.sh --ref REF --path PATH" >&2
  echo "         [--repo OWNER/NAME] [--control-ref REF] [--control-path PATH]" >&2
  echo "         [--output FILE]" >&2
  echo "  The ref and path are deliberately not defaulted: read them from" >&2
  echo "  docs/PUBLICATION-READINESS.md section 6 rather than from this file." >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ref) [ "$#" -ge 2 ] || usage; ref="$2"; shift 2 ;;
    --path) [ "$#" -ge 2 ] || usage; path="$2"; shift 2 ;;
    --repo) [ "$#" -ge 2 ] || usage; repo="$2"; shift 2 ;;
    --control-ref) [ "$#" -ge 2 ] || usage; control_ref="$2"; shift 2 ;;
    --control-path) [ "$#" -ge 2 ] || usage; control_path="$2"; shift 2 ;;
    --output) [ "$#" -ge 2 ] || usage; output="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "publication-exposure-check: unknown argument '$1'." >&2; usage ;;
  esac
done

[ -n "$ref" ] || usage
[ -n "$path" ] || usage

if ! command -v curl >/dev/null 2>&1; then
  echo "publication-exposure-check: curl not found." >&2
  echo "  This is a failure to run the probe, not evidence the content is gone." >&2
  exit 2
fi

if [ -z "$repo" ]; then
  origin="$(git config --get remote.origin.url 2>/dev/null || true)"
  repo="$(printf '%s' "$origin" | sed -e 's/[[:space:]]*$//' -e 's/\.git$//' \
    -e 's#^.*[:/]\([^/]*/[^/]*\)$#\1#')"
fi

# Checked whether it was derived or passed. A repository that is not exactly
# OWNER/NAME builds a URL that means something else, and every probe against it
# would 404 for a reason that has nothing to do with the content.
case "$repo" in
  */*/*|/*|*/) repo="" ;;
  */*) ;;
  *) repo="" ;;
esac
if [ -z "$repo" ]; then
  echo "publication-exposure-check: no usable OWNER/NAME. It is derived from" >&2
  echo "  the 'origin' remote when --repo is not given; pass --repo OWNER/NAME." >&2
  usage
fi

# Only the status line is ever read. `-o /dev/null` is what keeps a response
# body — the exposed content itself — out of this process, this terminal, and
# any log the operator is capturing. Redirects are deliberately not followed: a
# 3xx is a question about where the host is sending the reader, and answering it
# by chasing the hop would let a redirected 200 stand in for the subject.
probe() {
  local url="$1" code
  code="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H 'Accept: application/vnd.github+json' \
    --max-time "$PROBE_TIMEOUT" --retry 2 "$url" 2>/dev/null)" || code="000"
  [ -n "$code" ] || code="000"
  printf '%s' "$code"
}

# Three states, and everything unrecognized is the third one. 000 is curl's
# "no HTTP response at all"; a 403 is the unauthenticated rate limit as often as
# it is a refusal; a 5xx is the host having a bad minute. None of those is
# evidence of absence.
classify() {
  case "$1" in
    200) printf 'served' ;;
    404|410) printf 'absent' ;;
    *) printf 'unknown' ;;
  esac
}

api="https://api.github.com/repos/${repo}"
web="https://github.com/${repo}"
raw="https://raw.githubusercontent.com/${repo}"

subject_api="$(probe "${api}/contents/${path}?ref=${ref}")"
subject_web="$(probe "${web}/blob/${ref}/${path}")"
subject_raw="$(probe "${raw}/${ref}/${path}")"
subject_commit="$(probe "${api}/commits/${ref}")"

control_api="$(probe "${api}/contents/${control_path}?ref=${control_ref}")"
control_web="$(probe "${web}/blob/${control_ref}/${control_path}")"
control_raw="$(probe "${raw}/${control_ref}/${control_path}")"

# Forks are the half neither option in the decision record can reach: a purge
# does not follow the content into somebody else's copy. Reported, never part of
# the verdict, and "unknown" when the metadata could not be read — a number this
# script guessed would be worse than no number.
forks="unknown"
repo_meta="$(curl -sS --max-time "$PROBE_TIMEOUT" --retry 2 \
  -H 'Accept: application/vnd.github+json' "${api}" 2>/dev/null)" || repo_meta=""
if [ -n "$repo_meta" ]; then
  parsed="$(printf '%s' "$repo_meta" | tr ',' '\n' \
    | sed -n 's/.*"forks_count"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' \
    | head -1)"
  [ -z "$parsed" ] || forks="$parsed"
fi

checked_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# One served content surface settles it, and nothing later can talk the verdict
# back down: a 200 is positive evidence whatever else went wrong in the run.
verdict="NOT SERVED"
exit_code=0
reason=""

inconclusive() {
  if [ "$exit_code" -ne 1 ]; then
    verdict="INCONCLUSIVE"
    exit_code=2
    [ -n "$reason" ] || reason="$1"
  fi
}

for code in "$subject_api" "$subject_web" "$subject_raw"; do
  case "$(classify "$code")" in
    served) verdict="STILL SERVED"; exit_code=1; reason="" ;;
    unknown) inconclusive "a content surface answered with a status this script will not classify" ;;
  esac
done

for code in "$control_api" "$control_web" "$control_raw"; do
  if [ "$(classify "$code")" != "served" ]; then
    inconclusive "a positive control did not answer, so a negative subject result measures nothing"
  fi
done

# The commit probe is not a fourth content surface; it is the corroboration.
# A purge takes the unreachable commit with the blob, so a commit that still
# resolves while all three content surfaces say absent means either that the
# purge did not reach it or that the path being probed is not the path in the
# object. Neither of those is "gone", and the second is the likelier operator
# error: a mistyped path 404s on all three surfaces from a repository that is
# serving everything else perfectly.
if [ "$exit_code" -eq 0 ] && [ "$(classify "$subject_commit")" != "absent" ]; then
  inconclusive "the commit still resolves while the path does not; check the path against section 6"
fi

record="$(cat <<RECORD
publication-exposure-check: record (version ${RECORD_VERSION})
  checked_at_utc:   ${checked_at}
  repo:             ${repo}
  ref:              ${ref}
  path:             ${path}
  subject_api:      ${subject_api} ($(classify "$subject_api"))
  subject_web:      ${subject_web} ($(classify "$subject_web"))
  subject_raw:      ${subject_raw} ($(classify "$subject_raw"))
  subject_commit:   ${subject_commit} ($(classify "$subject_commit"))
  control_ref:      ${control_ref}
  control_path:     ${control_path}
  control_api:      ${control_api} ($(classify "$control_api"))
  control_web:      ${control_web} ($(classify "$control_web"))
  control_raw:      ${control_raw} ($(classify "$control_raw"))
  forks_count:      ${forks}
  verdict:          ${verdict}
RECORD
)"

printf '%s\n' "$record"

if [ -n "$output" ]; then
  if ! printf '%s\n\n' "$record" >>"$output"; then
    echo "publication-exposure-check: could not append the record to '${output}'." >&2
    echo "  The probe ran; no dated record was written, so nothing here is citable." >&2
    exit 2
  fi
fi

case "$exit_code" in
  1)
    echo "publication-exposure-check: the content is STILL SERVED as of ${checked_at}." >&2
    echo "  Section 6 of docs/PUBLICATION-READINESS.md remains open, and the" >&2
    echo "  decision in docs/adr/0016-removed-document-still-served.md is unmade." >&2
    ;;
  2)
    echo "publication-exposure-check: INCONCLUSIVE as of ${checked_at}." >&2
    echo "  Because ${reason}." >&2
    echo "  Record this as 'not established' — never as closed. A 404 from a" >&2
    echo "  repository that is private, renamed, or rate-limiting the caller" >&2
    echo "  looks exactly like a 404 from content that is gone." >&2
    ;;
  *)
    echo "publication-exposure-check: NOT SERVED on these surfaces as of ${checked_at}." >&2
    echo "  Every subject probe was absent and every control was served, so the" >&2
    echo "  negative is a measurement rather than an outage." >&2
    echo "  It does not reach: the ${forks} fork(s) the host reports, any clone" >&2
    echo "  already taken, search or proxy caches, mirrors, or web archives." >&2
    echo "  It ages immediately. Cite the date above, or re-run it." >&2
    ;;
esac

exit "$exit_code"
