.PHONY: a11y a11y-full a11y-install audit format format-fix hygiene i18n lint publication-sweep secret-scan sync test typecheck verify

SAFETY_MODULES := src/contextsafe/models.py,src/contextsafe/validation.py,src/contextsafe/evaluator.py,src/contextsafe/receipt.py,src/contextsafe/contract_validation.py,src/contextsafe/jsonio.py,src/contextsafe/pack.py,src/contextsafe/plan.py,src/contextsafe/evidence.py,src/contextsafe/preflight.py,src/contextsafe/evidence_store.py

verify: sync lint format typecheck test audit hygiene publication-sweep i18n a11y

sync:
	uv sync --frozen

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

format-fix:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy --strict src

test:
	uv run pytest --cov=contextsafe --cov-branch --cov-report=term-missing --cov-fail-under=90
	uv run coverage report --include='$(SAFETY_MODULES)' --fail-under=95

audit:
	uv run pip-audit --skip-editable --cache-dir .cache/pip-audit

# Deliberately not part of `verify`: it needs a pinned gitleaks on PATH, which a
# clean clone does not have, and `verify` must stay the byte-for-byte gate that
# ci.yml runs. The security workflow and the release workflow both call this
# target directly, so CI and a maintainer run the identical scan.
secret-scan:
	./tools/secret-scan-full-history.sh

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

hygiene:
	! rg -n '(TODO|FIXME|HACK)' src tests
	! find . -maxdepth 2 -type f \( -name 'ruff.toml' -o -name 'pytest.ini' -o -name 'mypy.ini' -o -name 'setup.cfg' -o -name 'setup.py' -o -name 'tox.ini' -o -name '.flake8' -o -name 'requirements.txt' \) | grep .
