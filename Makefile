.PHONY: a11y a11y-full a11y-install audit claims format format-fix hygiene i18n lint mutants package patterns publication-sweep sast scope secret-scan sync test typecheck verify

SAFETY_MODULES := src/contextsafe/identifiers.py,src/contextsafe/models.py,src/contextsafe/validation.py,src/contextsafe/evaluator.py,src/contextsafe/laboratory.py,src/contextsafe/receipt.py,src/contextsafe/contract_validation.py,src/contextsafe/jsonio.py,src/contextsafe/pack.py,src/contextsafe/plan.py,src/contextsafe/evidence.py,src/contextsafe/preflight.py,src/contextsafe/evidence_store.py,src/contextsafe/safe_value.py,src/contextsafe/diagnostics.py,src/contextsafe/eventlog.py,src/contextsafe/importers/__init__.py,src/contextsafe/importers/base.py,src/contextsafe/importers/canonical_json.py,src/contextsafe/importers/fhir_r4_json.py,src/contextsafe/importers/hl7v2_er7.py,src/contextsafe/importers/lis.py,src/contextsafe/importers/lis_csv.py,src/contextsafe/importers/mapping.py,src/contextsafe/mapping_profile.py,src/contextsafe/divergence.py,src/contextsafe/html_receipt.py,src/contextsafe/receipt_delta.py,src/contextsafe/review.py

verify: sync lint format typecheck test audit hygiene scope patterns publication-sweep i18n a11y claims

sync:
	# --locked fails when uv.lock has drifted from pyproject.toml.
	# --frozen installs the stale lock and exits 0, so it cannot gate drift.
	uv sync --locked

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

format-fix:
	uv run ruff check --fix .
	uv run ruff format .

# No path argument: `[tool.mypy] files` in pyproject.toml is the claim, and
# `make scope` checks it against the tree. A path here would silently win.
typecheck:
	uv run mypy --strict

test:
	uv run pytest --cov --cov-branch --cov-report=term-missing --cov-fail-under=90
	uv run coverage report --include='$(SAFETY_MODULES)' --fail-under=95

# pip-audit answers with two exit codes: clean, and everything else. A dropped
# PyPI connection therefore failed this stage -- and so the whole merge gate --
# with the same code as a real advisory, which is what happened on PR #61. The
# gate program keeps the same audit and separates the third state: exit 1 is an
# advisory the service reported, exit 2 is a service that did not answer, and a
# transient failure is retried with backoff before the gate says so. It still
# needs the network, so `verify` is still not runnable offline; what it no
# longer does is report that as the same failure as a vulnerability.
audit:
	uv run python tools/audit_gate.py

# Deliberately not part of `verify`: it needs a pinned gitleaks on PATH, which a
# clean clone does not have, and `verify` must stay the byte-for-byte gate that
# ci.yml runs. The security workflow and the release workflow both call this
# target directly, so CI and a maintainer run the identical scan.
secret-scan:
	./tools/secret-scan-full-history.sh

# The SAST scan, and the half of it the scanner's exit code never carried. A
# partial parse is a warning that leaves the scan at exit 0, so the gate had
# been reporting clean over the unread remainder of a safety module; whether it
# went red depended on how many files the run happened to include. This target
# runs the scan and then reads its JSON: a finding is exit 1, and a file the
# parser could not finish, a source that was never opened, or a scan that did
# not happen at all is exit 2. Deliberately not part of `verify`, exactly as
# `secret-scan` is not: semgrep is not in uv.lock, a clean clone does not have
# it, and `--config auto` is a network call. `.github/workflows/security.yml`
# runs this same program, and the gate is pinned to the scanner version that
# workflow's container is pinned to -- a shared argv is not a shared scan while
# the parsers differ, which is what #114 was about. A different semgrep is exit
# 2 naming both versions; ALLOW_SEMGREP_VERSION_DRIFT=1 accepts it with a
# warning, exactly as `secret-scan` treats a gitleaks that is not the pinned
# one. See ADR 0012.
sast:
	uv run python tools/sast_gate.py

# Evidence that the suite would notice a change, not just execute the line.
# Deliberately not part of `verify`: every mutant is a separate test run, so
# this takes minutes against the second the rest of `verify` costs. It needs no
# tool a clean clone lacks, and it writes nothing into the working tree: the
# package is copied to a temporary directory, mutated there, and put in front of
# the editable install with PYTHONPATH.
mutants:
	uv run python tools/mutation_gate.py

# Every `pattern` in every `.json` file under `schemas/`, at any depth, against
# the constants the runtime compiles. The published half of a grammar and the
# enforced half were two statements of one rule with nothing holding them
# together, which is what #58 cost. Not a test, because a test pins the patterns
# somebody remembered; this enumerates them and fails on one nothing is behind.
# Recursively and by suffix: a flat glob reports clean over a contract in a
# subdirectory, which is the same false green one level up. Stdlib plus the
# package itself, so it costs `verify` nothing, and it exits 2 rather than 0
# when it read no contract or found a file under `schemas/` it cannot place.
patterns:
	uv run python tools/pattern_gate.py

# Keeps the publication-readiness sweep true as commits land, instead of true
# as of the day somebody ran it by hand. Stdlib only, so it costs `verify`
# nothing and needs no tool a clean clone does not already have.
publication-sweep:
	uv run python tools/publication_sweep.py

# Catalog parity, placeholder parity, review consistency, and the rule that a
# machine-translated string may never reach a surface claiming human review.
# Stdlib plus the package itself, so it belongs in `verify` rather than in a
# job somebody remembers to run.
i18n:
	uv run python tools/i18n_gate.py

# The stdlib half of B-043: structural validity, contrast computed from the
# stylesheet, no colour-only encoding, and print. In `verify` because it needs
# nothing a clean clone does not have. It fails rather than passing when it has
# examined no page, and it refuses to treat a rule axe cannot decide as decided.
a11y:
	uv run python tools/a11y_gate.py --engines builtin

# Adds axe-core in a headless DOM. Separate from `verify` because it needs the
# node harness, which a clean clone does not have; the security workflow runs it
# after `make a11y-install`. A requested engine that cannot run is a failure, so
# this target cannot quietly degrade into the target above.
a11y-full:
	uv run python tools/a11y_gate.py --engines builtin,axe --json .a11y/report.json

a11y-install:
	npm ci --prefix tools/a11y

# Unowned markers and stray tool configs. This was two shell lines, and neither
# could fail on a machine missing the tool it called: `! rg ...` maps "ripgrep
# is not installed" (exit 2) onto success exactly as it maps "ripgrep matched
# nothing" (exit 1), and `! find ... | grep .` takes its status from `grep`, so
# a `find` that never ran produced no output and reported success too. Neither
# tool is in uv.lock or installed by any CI step. Stdlib Python now, like the
# sweep and the i18n gate, so `verify` still needs nothing a clean clone lacks;
# it exits 1 on a finding and 2 when it could not examine anything.
hygiene:
	uv run python tools/hygiene_gate.py

# The artifacts a release would ship, built the way release.yml and package.yml
# build them: a clean dist/, `uv build` for the sdist and wheel, a CycloneDX
# SBOM exported from the locked graph (`--locked` fails on drift; `--no-dev`
# because the artifact carries no dev tool; the graph is the project alone,
# since `[project] dependencies` is empty), and the wheel's contents listed so
# a reviewer can see what shipped -- the reference fixtures were missing from it
# until 2026-09-02 and nothing showed that. Not a gate and not in `verify`: it
# builds, it does not judge. The judgment is `tools/fresh_install_gate.py`,
# which package.yml runs against this output on Ubuntu, macOS and Windows and a
# maintainer runs with `uv run python tools/fresh_install_gate.py --dist dist`.
package:
	rm -rf dist
	uv build --out-dir dist
	uv export --locked --no-dev --format cyclonedx1.5 --preview-features sbom-export --output-file dist/contextsafe-sbom.cdx.json
	uv run python -m zipfile -l dist/*.whl

# Every other gate can say "I looked and found nothing" and "I could not look".
# None of them can say "nobody ever pointed me at that tree", which is what
# `tools/` was for the marker scan and the coverage floor until 2026-08-27. This
# reads each analysis's claimed scope from the configuration that makes the
# claim and compares it against the tracked Python that exists.
scope:
	uv run python tools/scope_gate.py

# The figures and lists the documents state, re-derived from the repository: this
# target list against README.md and CONTRIBUTING.md, the ADR index, the coverage
# floors, the contract count, and the rule that a standard `verify` gates may not
# be declared not applicable. Last in `verify` because it reads what the earlier
# stages are, and stdlib only, so it costs `verify` nothing. Every check fails
# both ways: a wrong value, and a document that stopped stating the value at all.
claims:
	uv run python tools/claims_gate.py
