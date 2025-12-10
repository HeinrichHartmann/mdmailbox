# mdmailbox - Coding Guidelines

## Environment

- **Python 3.13+** (see `requires-python` in pyproject.toml)
- **uv** for package management and running
- **hatchling** as build backend

## Language & Style

- Modern type hints (`list[str]`, `str | None`)
- **Dataclasses** for data structures (`Email`, `Credential`, `SendResult`)
- **Type hints** on all function signatures
- **No classes for utilities** - plain functions for stateless operations
- **ruff** for linting and formatting

## Code Organization

```
mdmailbox/
├── __init__.py   # Package metadata only
├── email.py      # Core Email dataclass
├── authinfo.py   # Credential handling (single responsibility)
├── smtp.py       # SMTP operations (single responsibility)
├── importer.py   # Maildir import logic
└── cli.py        # CLI commands (thin wrapper over library)
```

### Principles

1. **Library-first** - Core logic in modules, CLI is just a thin wrapper
2. **Single responsibility** - Each module handles one concern
3. **Minimal dependencies** - Prefer stdlib where possible
4. **Explicit over implicit** - No magic, clear data flow

## Error Handling

- Use `click.ClickException` for CLI errors (user-facing)
- Return result objects (`SendResult`) rather than raising for expected failures
- Log errors to stderr, not stdout
- Include context in error messages

## Make Targets

```bash
make test          # Run pytest
make lint          # Run ruff check
make format        # Run ruff format
make check         # lint + test
make local-install # Install via uv tool
make setup         # Install pre-commit hooks
make release       # Bump version, tag, push, publish to PyPI
```

## CLI Conventions

- Use `click` decorators for commands
- `--dry-run` flag for destructive operations
- Output success to stdout, errors to stderr
- Return non-zero exit code on failure
- Keep CLI thin - delegate to library functions

## Commit Messages

Format: `<type>: <description>`

Types:
- `Add` - New feature
- `Fix` - Bug fix
- `Update` - Enhancement to existing feature
- `Refactor` - Code restructure without behavior change
- `Test` - Test additions/changes
- `Docs` - Documentation only
