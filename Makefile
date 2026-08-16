.PHONY: audit format format-fix hygiene lint publication-sweep sync test typecheck verify

SAFETY_MODULES := src/contextsafe/models.py,src/contextsafe/validation.py,src/contextsafe/evaluator.py,src/contextsafe/receipt.py,src/contextsafe/contract_validation.py,src/contextsafe/jsonio.py,src/contextsafe/pack.py,src/contextsafe/plan.py,src/contextsafe/evidence.py,src/contextsafe/preflight.py,src/contextsafe/evidence_store.py

verify: sync lint format typecheck test audit hygiene publication-sweep

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

# Keeps the publication-readiness sweep true as commits land, instead of true
# as of the day somebody ran it by hand. Stdlib only, so it costs `verify`
# nothing and needs no tool a clean clone does not already have.
publication-sweep:
	uv run python tools/publication_sweep.py

hygiene:
	! rg -n '(TODO|FIXME|HACK)' src tests
	! find . -maxdepth 2 -type f \( -name 'ruff.toml' -o -name 'pytest.ini' -o -name 'mypy.ini' -o -name 'setup.cfg' -o -name 'setup.py' -o -name 'tox.ini' -o -name '.flake8' -o -name 'requirements.txt' \) | grep .
