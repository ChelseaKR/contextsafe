.PHONY: a11y a11y-full a11y-install audit format format-fix hygiene i18n lint mutants publication-sweep scope secret-scan sync test typecheck verify

SAFETY_MODULES := src/contextsafe/identifiers.py,src/contextsafe/models.py,src/contextsafe/validation.py,src/contextsafe/evaluator.py,src/contextsafe/receipt.py,src/contextsafe/contract_validation.py,src/contextsafe/jsonio.py,src/contextsafe/pack.py,src/contextsafe/plan.py,src/contextsafe/evidence.py,src/contextsafe/preflight.py,src/contextsafe/evidence_store.py,src/contextsafe/safe_value.py,src/contextsafe/diagnostics.py,src/contextsafe/eventlog.py

verify: sync lint format typecheck test audit hygiene scope publication-sweep i18n a11y

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

audit:
	uv run pip-audit --skip-editable --cache-dir .cache/pip-audit

# Deliberately not part of `verify`: it needs a pinned gitleaks on PATH, which a
# clean clone does not have, and `verify` must stay the byte-for-byte gate that
# ci.yml runs. The security workflow and the release workflow both call this
# target directly, so CI and a maintainer run the identical scan.
secret-scan:
	./tools/secret-scan-full-history.sh

# Evidence that the suite would notice a change, not just execute the line.
# Deliberately not part of `verify`: every mutant is a separate test run, so
# this takes minutes against the second the rest of `verify` costs. It needs no
# tool a clean clone lacks, and it writes nothing into the working tree: the
# package is copied to a temporary directory, mutated there, and put in front of
# the editable install with PYTHONPATH.
mutants:
	uv run python tools/mutation_gate.py

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

# Every other gate can say "I looked and found nothing" and "I could not look".
# None of them can say "nobody ever pointed me at that tree", which is what
# `tools/` was for the marker scan and the coverage floor until 2026-08-27. This
# reads each analysis's claimed scope from the configuration that makes the
# claim and compares it against the tracked Python that exists.
scope:
	uv run python tools/scope_gate.py
