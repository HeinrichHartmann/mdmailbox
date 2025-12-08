.PHONY: test local-install

test:
	uv run pytest tests/ -v

local-install:
	uv tool install --force --reinstall .
