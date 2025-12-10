# mdmailbox - Testing Strategy

## Philosophy

This is an integration-heavy tool. We prioritize **end-to-end tests** over unit tests.

### Why End-to-End?

- The value is in the integration: CLI parsing, file I/O, SMTP protocols, credential lookup all working together
- Unit tests can pass while the actual user experience is broken
- We accept the cost in performance and brittleness for tests that mirror real usage
- We don't want to be blindsided by CLI args breaking, file format changes, or protocol issues

### What We Test

We run **actual commands** like a user would and validate **real outcomes**:

- Emails actually get sent (to a local SMTP server)
- Files actually get created/moved/deleted
- Credentials are read from real files
- CLI arguments are parsed correctly

Nothing is mocked away. Side effects are performed and verified.

## Test Infrastructure

### Real Services as Fixtures

| Service | Implementation |
|---------|----------------|
| SMTP server | `smtpdfix` - real local SMTP server |
| IMAP server | (future) real local IMAP server |
| Filesystem | `tmp_path` fixture with real files |
| Credentials | Real `.authinfo` files in temp dirs |

### Observability for Testing

To validate internal behavior without mocking, we use:

1. **Verbose logs** - Events emitted during execution that tests can capture and assert on
2. **Verbose CLI flags** - `--verbose` or similar to expose internal state (e.g., credential lookup details)
3. **Audit trails** - The send log appended to sent emails serves as test evidence

Tests can grep logs/output for expected events rather than mocking internals.

## Running Tests

```bash
make test              # Run all tests
uv run pytest tests/ -v   # Verbose output
```

## Test Structure

```
tests/
├── test_send.py       # End-to-end send with real SMTP
├── test_import.py     # Import from real Maildir fixtures
├── test_cli.py        # CLI integration via CliRunner
├── test_credentials.py # Real authinfo file parsing
└── fixtures/          # Sample emails, Maildir structures
```

## Writing Tests

### Pattern: Real SMTP Send

```python
def test_send_email(smtpd, tmp_path):
    """Send email through real local SMTP server."""
    # Create real authinfo file
    authinfo = tmp_path / ".authinfo"
    authinfo.write_text(
        f"machine {smtpd.hostname} login test@example.com password secret"
    )

    # Create real email file
    email_file = tmp_path / "test.md"
    email_file.write_text("""---
from: test@example.com
to: recipient@example.com
subject: Test
---

Hello!
""")

    # Run actual CLI command
    runner = CliRunner()
    result = runner.invoke(main, [
        "send", str(email_file),
        "--authinfo", str(authinfo),
        "--port", str(smtpd.port),
    ])

    # Verify real outcomes
    assert result.exit_code == 0
    assert not email_file.exists()  # Moved to sent/
    assert len(smtpd.messages) == 1  # Actually received
```

### Pattern: Validate via Logs

```python
def test_credential_lookup_logged(smtpd, tmp_path, capfd):
    """Credential lookup emits log events we can verify."""
    # ... setup ...

    result = runner.invoke(main, ["send", str(email_file), "--verbose"])

    # Check logs for expected events
    assert "Looking up credentials for test@example.com" in result.output
    assert "Found credentials" in result.output
```

## What We Don't Test

- Pure logic in isolation (unless it's complex enough to warrant it)
- Mocked SMTP responses
- Internal data structures without going through CLI

## Trade-offs

| Benefit | Cost |
|---------|------|
| Tests match real usage | Slower execution |
| Catches integration bugs | More setup required |
| No false confidence from mocks | Tests can be flakier |
| Refactor-friendly | Need real fixtures |
