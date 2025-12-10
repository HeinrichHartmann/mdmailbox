# mdmailbox - Project Summary

## What It Is

A CLI tool and Python library for managing email as local markdown files with YAML frontmatter headers. Enables bidirectional workflow between IMAP/SMTP servers and a local filesystem.

## Core Concept

Emails stored as plain text files:
```
---
from: sender@example.com
to: recipient@example.com
subject: Meeting follow-up
---

The message body goes here.
```

This format is human-readable, git-friendly, and LLM-friendly.

## Directory Structure

```
~/Mdmailbox/
├── inbox/     # imported/received emails
├── drafts/    # work in progress
├── sent/      # successfully sent (with audit trail)
└── outbox/    # queued for sending (future)
```

## Current Features

| Command | Description |
|---------|-------------|
| `mdmailbox send <file>` | Send an email file via SMTP |
| `mdmailbox send --dry-run <file>` | Validate without sending |
| `mdmailbox import` | Import emails from Maildir |
| `mdmailbox new` | Create a new email draft |
| `mdmailbox reply <file>` | Create reply to an email |
| `mdmailbox credentials` | Show configured SMTP credentials |

## Architecture

```
mdmailbox/
├── email.py      # Email dataclass, YAML parsing/serialization
├── authinfo.py   # Credential lookup from ~/.authinfo
├── smtp.py       # SMTP client with audit logging
├── importer.py   # Maildir import (RFC822 → YAML)
└── cli.py        # Click-based CLI commands
```

## Key Design Decisions

1. **YAML frontmatter format** - Standard, parseable, human-editable
2. **Credentials via .authinfo** - Standard format, supports wildcards and Gmail normalization
3. **Audit trail appended to sent emails** - Self-contained send log in each file (ADR 002)
4. **Signature support** - Reads `~/.signature.md` for new/reply drafts

## Dependencies

- `pyyaml` - YAML parsing
- `click` - CLI framework
- `smtplib` (stdlib) - SMTP client
- `email` (stdlib) - RFC822 parsing/generation

## Future Plans

- IMAP fetch (download emails)
- Bidirectional sync
- Attachments support
- Safe sending experience (ADR 003 - draft)
