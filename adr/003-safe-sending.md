# ADR 003: Safe Sending Experience

## Status
Accepted

## Problem Statement

Email sending is a high-stakes, irreversible action. A sloppy or premature email can:
- Damage professional reputation
- Embarrass the sender
- Harm relationships with important contacts
- Be impossible to recall once sent

The current mdmailbox sending experience has several risks:

### 1. Ambiguity about what gets sent
- Markdown files are loose/freeform
- YAML frontmatter parsing may silently fail or behave unexpectedly
- Invalid header fields could be silently ignored
- No preview of the final rendered email

### 2. Easy to send prematurely
- Single command `mdmailbox send` fires immediately
- No confirmation step
- Typo in recipient field could send to wrong person

### 3. No semantic validation
- Header fields not validated against schema
- Email addresses not checked for valid format
- No verification against address book
- Threading headers (in-reply-to) not validated against known messages

## Design Constraints

1. **Zero ambiguity**: User must know exactly what will be sent
2. **Explicit confirmation**: No accidental sends
3. **Clear feedback**: Unambiguous success/failure status
4. **Recoverable**: Ability to review before committing
5. **Auditable**: Full trace of what was sent
6. **Mu integration**: mdmailbox is an LLM-friendly view on a Maildir indexed by [mu](https://www.djcbsoftware.nl/code/mu/). We rely on mu for address book lookups, message-id corpus searches, and contact validation. The Maildir is the source of truth; mdmailbox provides a markdown interface for reading/writing emails.

## Decision

### Default Behavior: Preview + Validation + Confirmation

`mdmailbox send <file>` will:

1. **Parse and validate** the email file semantically
2. **Display a preview** of exactly what will be sent
3. **Show validation results** with emoji-style feedback
4. **Prompt for confirmation** before sending

### Validation Checks

All header fields are semantically parsed and validated:

| Check | Status | Description |
|-------|--------|-------------|
| Required fields | ✓/✗ | from, to, subject present and non-empty |
| Header schema | ✓/✗ | Only valid header names (reject `cert`, `bcc` typos, etc.) |
| Email format | ✓/✗ | All addresses match email format |
| Credentials | ✓/✗ | From address has SMTP credentials configured |
| Address book | ✓/○ | Recipients found in address book (warning if unknown) |
| In-Reply-To | ✓/○ | Message-ID exists in our message corpus (if present) |
| Body | ✓/✗ | Non-empty body |

Legend: ✓ = pass, ✗ = error (blocks send), ○ = warning (informational)

### Preview Display

Validation feedback is **inline** with the field being validated, not in a separate section:

```
══════════════════════════════════════════════════════════════
 From:       me@example.com ✓ credentials found
 To:         alice@example.com ✓
             bob@example.com ○ not in address book
 Cc:         team@example.com ✓
 Subject:    Q4 Planning Meeting ✓
 In-Reply-To: <abc123@mail.example.com> ✓ found in inbox
──────────────────────────────────────────────────────────────

Hey team,

Let's sync on Q4 priorities tomorrow at 2pm.

--
Best regards,
Heinrich

══════════════════════════════════════════════════════════════
✓ Body: 15 words
✓ All headers valid

Send this email? [y/N]:
```

**Error example:**

```
══════════════════════════════════════════════════════════════
 From:       me@example.com ✗ no credentials found
 To:         alice@example.com ✓
             bobexample.com ✗ invalid email format
 Cc:         team@example.com ✓
 Subject:    ✗ empty
 Cert:       ✗ unknown header (did you mean Cc?)
──────────────────────────────────────────────────────────────

Hey team,
...

══════════════════════════════════════════════════════════════
✗ 4 errors - cannot send

```

The validation is **co-located** with each field:
- Each email address shows its own status
- Each header shows if it's recognized
- Credentials status next to From
- Message-ID lookup status next to In-Reply-To
- Only body/summary validations appear at the end

### CLI Flags

| Flag | Short | Behavior |
|------|-------|----------|
| `--yes` | `-y` | Auto-confirm, but still validate. Fails on errors. |
| `--force` | `-f` | Skip all validation, send as-is. For emergency use. |
| `--dry-run` | | Show preview and validation only, don't send. |

### Error Behavior

- **Validation errors** (✗): Send is blocked, user must fix the file
- **Validation warnings** (○): Send proceeds after confirmation
- **With `--yes`**: Errors still block, warnings are logged but don't block
- **With `--force`**: No validation, send raw file contents

## Audit Logging

### Change from ADR 002

Instead of appending audit trail to sent email files, we write separate log files:

```
~/Mdmailbox/
├── sent/                    # Clean sent emails (no audit data)
│   └── 2025-01-23-meeting.md
└── logs/                    # Detailed audit logs
    └── 2025-01-23T10-30-05-meeting.log
```

### Log File Contents

Each send operation creates a log file with:
- Timestamp
- Source file path
- Validation results (full detail)
- SMTP connection log
- Server responses
- Final status (success/failure)
- Message-ID assigned

### Benefits

1. **Clean sent folder** - Emails remain human-readable without audit clutter
2. **Detailed debugging** - Logs can be verbose without affecting email files
3. **Log lifecycle** - Can implement rotation/cleanup separately
4. **Git-friendly** - Sent emails diff cleanly, logs can be gitignored

## Implementation Notes

### Header Validators

Single source of truth: a mapping of header names to validator classes.

```python
# mdmailbox/validate.py

class HeaderValidator:
    """Base class for header validators."""
    required: bool = False

    def validate(self, value: Any, context: ValidationContext) -> ValidationResult:
        raise NotImplementedError

class FromValidator(HeaderValidator):
    """Validates from address: email format + credentials lookup."""
    required = True

    def validate(self, value, ctx):
        # Check email format, lookup credentials
        ...

class RecipientsValidator(HeaderValidator):
    """Validates to/cc/bcc: email format + address book lookup."""

    def validate(self, value, ctx):
        # Check each address, warn if not in address book
        ...

HEADER_VALIDATORS: dict[str, HeaderValidator] = {
    "from":        FromValidator(),
    "to":          RecipientsValidator(required=True),
    "cc":          RecipientsValidator(),
    "bcc":         RecipientsValidator(),
    "subject":     SubjectValidator(required=True),
    "reply-to":    EmailValidator(),
    "in-reply-to": MessageIdValidator(),
    "references":  ReferencesValidator(),
    "message-id":  MessageIdValidator(),
    "date":        DateValidator(),
    "account":     MetadataValidator(),
    "original-hash": HashValidator(),
}
```

**Unknown headers are errors** - any header not in this mapping is rejected (unless `--force`). Custom headers are too unusual; 99% of the time it's a typo.

### Mu Integration

Address book and message corpus queries use mu:

```bash
# Address book lookup
mu cfind alice@example.com

# Message-ID lookup (for in-reply-to validation)
mu find msgid:abc123@example.com
```

This keeps mdmailbox simple - mu already indexes the Maildir and provides fast lookups. We shell out to mu commands rather than maintaining our own indexes.

## Consequences

### Positive
- Zero ambiguity about what gets sent
- Catches common mistakes before sending
- Professional-grade email workflow
- Clean separation of emails and debug logs

### Negative
- More friction for quick sends (mitigated by `--yes`)
- Need to implement validation infrastructure
- Address book feature adds complexity

### Trade-offs Accepted
- We accept the friction for safety
- `--force` exists for emergency bypass
- Validation is opinionated (strict header schema)
