# Every gate a push is measured against is reachable from here, and CI calls the same
# targets rather than re-listing the commands. A check that exists only in a workflow
# file is a check a person cannot run before pushing, and one that exists only here is
# a check nobody runs at all.

VENV := .venv
PY   := $(VENV)/bin/python
ARGS ?=

.DEFAULT_GOAL := help

.PHONY: help
help:  ## this list
	@python3 scripts/help.py

#= Setup

.PHONY: install
install: $(VENV)  ## create .venv and install meetlat with its dev tools
	@$(PY) -m pip install -q --upgrade pip
	@$(PY) -m pip install -q -e ".[dev]"
	@$(PY) -c "import meetlat; print('meetlat', meetlat.__version__, 'installed')"

$(VENV):
	python3 -m venv $(VENV)

.PHONY: clean
clean:  ## remove the venv and every cache
	rm -rf $(VENV) .pytest_cache .mypy_cache .ruff_cache **/__pycache__ *.egg-info

#= Running it

.PHONY: zeef
zeef:  ## run the deterministic checks over a file: make zeef ARGS=response.txt
	@$(VENV)/bin/meetlat zeef $(ARGS)

.PHONY: checks
checks:  ## list the registered checks and the ones still designed but unbuilt
	@$(VENV)/bin/meetlat checks

#= Gates (all of these run in CI)

.PHONY: check
check: check-zeef check-judges check-guard  ## every offline gate at once

.PHONY: check-zeef
check-zeef:  ## every check has fixtures, exact spans, and no false positives (ADR-0002)
	@$(PY) scripts/check_zeef_contract.py

.PHONY: check-judges
check-judges:  ## no judge reports a number its own labels do not support (ADR-0004)
	@$(PY) scripts/check_judges.py

.PHONY: check-guard
check-guard:  ## the gold set guard still behaves as recorded (ADR-0006)
	@python3 scripts/check_gold_write.py --selftest

.PHONY: check-adrs
check-adrs:  ## the ADR index matches the ADRs on disk
	@$(PY) scripts/generate_adr_index.py --check

.PHONY: adr-index
adr-index:  ## regenerate docs/adr/README.md from each ADR's frontmatter
	@$(PY) scripts/generate_adr_index.py

#= Quality

.PHONY: test
test:  ## pytest; make test ARGS="-k agreement" to filter
	@$(PY) -m pytest $(ARGS)

.PHONY: lint
lint:  ## ruff
	@$(PY) -m ruff check .

.PHONY: format
format:  ## reformat in place
	@$(PY) -m ruff format .

.PHONY: format-check
format-check:  ## fail if anything is unformatted
	@$(PY) -m ruff format --check .

.PHONY: typecheck
typecheck:  ## mypy over src, scripts and tests
	@$(PY) -m mypy

.PHONY: preflight
preflight: lint format-check typecheck test check check-adrs  ## everything CI runs, locally
	@$(PY) -c "print()"
	@echo "  preflight green"
