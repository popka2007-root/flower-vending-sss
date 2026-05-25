.PHONY: install install-dev install-ui install-serial lint typecheck test test-e2e test-coverage clean verify build-windows-portable build-windows-installer build-linux-appimage pre-commit setup

SHELL := /bin/bash
PYTHON := python
PROJECT := flower-vending-system

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev: install
	$(PYTHON) -m pip install -r requirements-dev.txt

install-ui: install
	$(PYTHON) -m pip install -r requirements-ui.txt

install-serial:
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install pyserial>=3.5

install-all: install-dev install-ui install-serial
	$(PYTHON) -m pip install -e ".[dev,ui,serial]"

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

lint-fix:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

typecheck:
	$(PYTHON) -m mypy src tests

test:
	$(PYTHON) -m pytest -v

test-e2e:
	$(PYTHON) -m pytest tests/e2e/ -v

test-coverage:
	$(PYTHON) -m pytest --cov=src --cov-report=term --cov-report=html

verify:
	$(PYTHON) scripts/verify_project.py

clean:
	rm -rf build/ dist/ artifacts/ var/
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

pre-commit:
	pre-commit run --all-files

setup: install-dev install-ui install-serial
	$(PYTHON) -m pip install pre-commit
	pre-commit install
	$(PYTHON) scripts/verify_project.py

build-windows-portable:
	$(PYTHON) packaging/build_release.py windows-portable

build-windows-installer:
	$(PYTHON) packaging/build_release.py windows-installer

build-linux-appimage:
	$(PYTHON) packaging/build_release.py linux-appimage

build-all:
	$(PYTHON) packaging/build_release.py windows-portable windows-installer linux-appimage

.PHONY: check
check: lint typecheck test
