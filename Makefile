.PHONY: test lint format check install local-install release setup build-docs

build-docs:
	uv run python build_docs.py

test: build-docs
	uv run python -m pytest tests/ -v

lint:
	ruff check .

format:
	ruff format .

check: lint test
	@echo "All checks passed!"

install: build-docs
	uv tool install --force --reinstall .

local-install: install

setup:
	pre-commit install
	@echo "Pre-commit hooks installed!"

release: build-docs check
	@# Check working directory is clean
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "Error: Working directory is not clean"; \
		git status --short; \
		exit 1; \
	fi
	@# Get current version and increment patch
	@CURRENT=$$(grep '^version' pyproject.toml | cut -d'"' -f2); \
	MAJOR=$$(echo $$CURRENT | cut -d. -f1); \
	MINOR=$$(echo $$CURRENT | cut -d. -f2); \
	PATCH=$$(echo $$CURRENT | cut -d. -f3); \
	NEW_PATCH=$$((PATCH + 1)); \
	NEW_VERSION="$$MAJOR.$$MINOR.$$NEW_PATCH"; \
	echo "Bumping version: $$CURRENT -> $$NEW_VERSION"; \
	sed -i "s/version = \"$$CURRENT\"/version = \"$$NEW_VERSION\"/" pyproject.toml; \
	git add pyproject.toml; \
	git commit -m "Release v$$NEW_VERSION"; \
	git tag "v$$NEW_VERSION"; \
	git push && git push --tags; \
	rm -rf dist; \
	uv build; \
	source ~/box/secrets/pypi.key && uv publish --username __token__ --password "$$KEY"; \
	echo "Released v$$NEW_VERSION to PyPI"
