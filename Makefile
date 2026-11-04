.PHONY: help install test lint fmt check policy sample demo clean all

PY ?= python3
PKG := supermido
SAMPLE := $(shell mktemp -d)/sample.nes

help:            ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk -F':.*?## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:         ## Install the package with dev extras
	$(PY) -m pip install -e ".[dev]"

test:            ## Run the test suite
	$(PY) -m pytest -v

lint:            ## Lint with ruff
	$(PY) -m ruff check src tests tools

fmt:             ## Auto-format and fix imports
	$(PY) -m ruff format src tests tools
	$(PY) -m ruff check --fix src tests tools

policy:          ## Verify the content policy (no game data, no binaries)
	$(PY) tools/check_policy.py

sample:          ## Build a synthetic cartridge outside the repository
	$(PY) tools/make_sample.py --out $(SAMPLE)
	@echo "sample at $(SAMPLE)"

demo: sample     ## Full walkthrough against the synthetic cartridge
	$(PY) -m $(PKG).cli inspect $(SAMPLE)
	$(PY) -m $(PKG).cli disasm $(SAMPLE) --detect-tables | head -40
	$(PY) -m $(PKG).cli verify $(SAMPLE)
	$(PY) -m $(PKG).cli chr $(SAMPLE) --tiles 4

check: lint test policy   ## Everything CI runs

clean:           ## Remove caches and build artefacts
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

all: check       ## Lint + test + policy
