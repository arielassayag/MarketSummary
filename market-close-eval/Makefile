.PHONY: install test lint typecheck check dry-run help

help:
	@echo "make install   - cria venv e instala dependências (com dev)"
	@echo "make test      - roda pytest"
	@echo "make lint      - roda ruff check ."
	@echo "make typecheck - roda mypy src"
	@echo "make check     - test + lint + typecheck"

install:
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .

typecheck:
	.venv/bin/mypy src

check: test lint typecheck

dry-run:
	.venv/bin/python -m market_eval dry-run
