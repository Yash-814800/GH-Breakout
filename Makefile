.PHONY: setup lint fmt test info

setup:
	uv sync --all-groups && uv run pre-commit install

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy src

fmt:
	uv run ruff check --fix . && uv run ruff format .

test:
	uv run pytest -q

info:
	uv run breakout info
