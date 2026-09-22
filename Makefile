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
	@$(PY) -c "import meetlat; from meetlat import console; console.ok(f'meetlat {meetlat.__version__} installed with its dev tools')"

$(VENV):
	python3 -m venv $(VENV)

.PHONY: install-hooks
install-hooks:  ## enable the git hooks in .githooks (commit-msg, pre-commit, pre-push)
	@git config core.hooksPath .githooks
	@$(PY) -c "from meetlat import console; console.ok('git hooks enabled'); \
console.line('commit-msg  keeps attribution out of the history', indent=4); \
console.line('pre-commit  lint, format and the offline gates', indent=4); \
console.line('pre-push    the full preflight, then gitleaks', indent=4)"

.PHONY: clean
clean:  ## remove the venv and every cache
	@rm -rf $(VENV) .pytest_cache .mypy_cache .ruff_cache **/__pycache__ *.egg-info
	@python3 -c "print('  \033[32m✔\033[0m removed the venv and every cache')"

#= Running it

.PHONY: zeef
zeef:  ## run the deterministic checks over a file: make zeef ARGS=response.txt
	@$(VENV)/bin/meetlat zeef $(ARGS)

.PHONY: prompts
prompts:  ## generate an evaluation prompt set: make prompts ARGS="--seed 2026 --per-cell 3"
	@$(VENV)/bin/meetlat prompts $(ARGS)

.PHONY: contexts
contexts:  ## collect the documents that document tasks hand to the model (ADR-0005)
	@$(PY) scripts/collect_contexts.py --all

.PHONY: corpus-sources
corpus-sources:  ## the declared sources the clean corpus may be collected from
	@$(PY) scripts/collect_corpus.py --list

.PHONY: review
review:  ## review collected candidates and append the ones you accept: make review ARGS=batch.jsonl
	@$(PY) scripts/review_corpus.py $(ARGS)

.PHONY: checks
checks:  ## list the registered checks and the ones still designed but unbuilt
	@$(VENV)/bin/meetlat checks

#= Gates (all of these run in CI)

.PHONY: check
check: check-zeef check-taxonomy check-judges check-guard check-commit-msg  ## every offline gate at once

.PHONY: check-zeef
check-zeef:  ## every check has fixtures, exact spans, and no false positives (ADR-0002)
	@$(PY) scripts/check_zeef_contract.py

.PHONY: check-taxonomy
check-taxonomy:  ## every cell is defined, generated or declared empty with a reason (ADR-0005)
	@$(PY) scripts/check_taxonomy.py

.PHONY: check-judges
check-judges:  ## no judge reports a number its own labels do not support (ADR-0004)
	@$(PY) scripts/check_judges.py

.PHONY: check-guard
check-guard:  ## the gold set guard still behaves as recorded (ADR-0006)
	@python3 scripts/check_gold_write.py --selftest

.PHONY: check-commit-msg
check-commit-msg:  ## the commit-message guard still behaves as recorded (ADR-0006)
	@$(PY) scripts/check_commit_msg.py --selftest

# Not in `check` or `preflight`: it needs a binary that is not a Python dev dependency,
# and a gate that fails on a fresh clone for a missing tool gets worked around. CI runs
# the same command, so this is here to reproduce a CI finding locally.
.PHONY: secrets
secrets:  ## scan the full git history for committed secrets (needs gitleaks)
	@command -v gitleaks >/dev/null 2>&1 \
		&& gitleaks detect --source . --redact --verbose \
		|| $(PY) -c "from meetlat import console; console.skip('secrets', 'gitleaks not installed: https://github.com/gitleaks/gitleaks')"

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

# One runner behind `make preflight`, `pre-commit` and `pre-push`, so all three report
# the same battery the same way instead of each printing four tools' raw output.
.PHONY: preflight
preflight:  ## everything CI runs, locally
	@$(PY) scripts/run_checks.py preflight
