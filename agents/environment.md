# mdmailbox - Development Environment

## Prerequisites

The developer is assumed to have installed:

- **Nix** - Package manager
- **direnv** - Auto-load environment on `cd`

That's it. Everything else comes from the flake.

## How It Works

```
cd mdmailbox/     # direnv triggers automatically
                  # .envrc runs `use flake`
                  # flake.nix provides all dev tools
```

On entering the directory, you get a reproducible dev environment with all dependencies available.

## What the Flake Provides

Defined in `flake.nix`:

| Tool | Purpose |
|------|---------|
| `uv` | Python package management |
| `python313` | Python runtime |
| `ruff` | Linting and formatting |
| `pre-commit` | Git hooks |

The flake also sets:
- `UV_PYTHON_PREFERENCE=only-system` - Use Nix-provided Python
- `UV_PYTHON_DOWNLOADS=never` - Don't download Python, use system

## Secrets Management

Secrets are loaded via `.envrc` from `~/box/secrets/`:

```bash
# Example .envrc additions for secrets:
source ~/box/secrets/pypi.key    # Sets $KEY for PyPI publishing
export AUTHINFO_FILE=~/box/secrets/.authinfo
```

Other developers configure their own secret locations. The pattern is:
1. Secrets live outside the repo (never committed)
2. `.envrc` loads them into environment variables
3. Code reads from environment or well-known paths

## Adding Dependencies

### Dev tools (linting, testing infrastructure)

Add to `flake.nix` in `buildInputs`:

```nix
buildInputs = with pkgs; [
  uv
  python313
  ruff
  pre-commit
  # Add new tools here
];
```

Then run `direnv reload` or re-enter the directory.

### Python packages

Add to `pyproject.toml`:

```toml
# Runtime dependencies
dependencies = [
    "pyyaml>=6.0",
    "click>=8.0",
]

# Dev dependencies
[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "smtpdfix>=0.5.3",
]
```

Then run `uv sync`.

## Environment Variables

| Variable | Purpose | Set By |
|----------|---------|--------|
| `UV_PYTHON_PREFERENCE` | Use system Python | flake.nix |
| `UV_PYTHON_DOWNLOADS` | Disable Python downloads | flake.nix |
| `AUTHINFO_FILE` | Custom credentials path | .envrc (user) |

## Reproducibility

The `flake.lock` file pins exact versions of all Nix dependencies. Commit it to ensure all developers get identical environments.

To update dependencies:
```bash
nix flake update
```
