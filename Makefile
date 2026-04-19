PYTHON ?= python

.PHONY: install install-dev test lint check-env demo build dist-check

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

lint:
	ruff check src tests

test:
	pytest -q

check-env:
	$(PYTHON) run_checks.py

demo:
	$(PYTHON) run_demo.py --out-dir exports_root

build:
	$(PYTHON) -m build

dist-check:
	$(PYTHON) -m twine check dist/*
