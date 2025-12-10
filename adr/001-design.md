# mdmailbox - Design Document

This document captures the original vision and future ideas for mdmail.

## Overview

**mdmailbox** is a command-line tool and Python library for managing email as local files with YAML frontmatter headers. It provides bidirectional sync between IMAP servers and a local filesystem, treating emails as plain text files that can be edited, version-controlled, and processed by scripts or LLMs.

## Core Concept

Emails are stored as text files with:
1. **YAML frontmatter** - Structured headers (from, to, subject, date, etc.)
2. **Content body** - The actual message content
3. **File extension** - Hints at content type (.md, .txt, .html)

This format is:
- Human-readable and editable
- Git-friendly (diffable, mergeable)
- LLM-friendly (easy to parse and generate)
- Tool-agnostic (works with any text editor)

## File Format

### Basic Structure

```
---
from: sender@example.com
to: recipient@example.com
subject: Meeting follow-up
---

The message body goes here.
```

### Full Header Schema

```yaml
---
# Required for sending
from: sender@example.com
to: recipient@example.com           # string or list
subject: Subject line

# Optional addressing
cc: cc@example.com                  # string or list
bcc: bcc@example.com                # string or list
reply-to: reply@example.com

# Auto-generated on send/receive
message-id: <uuid@domain>
date: 2025-12-08T15:30:00+01:00     # ISO 8601
in-reply-to: <original-msg-id>      # for replies
references: [<msg1>, <msg2>]        # thread references

# Metadata (managed by mdmail)
account: gmail                      # which account to send from
status: draft | outbox | sent | inbox
content-type: text/plain            # or text/markdown, text/html

# Custom headers (passed through)
x-priority: 1
x-custom: value
---

Message body here.
```

### Multiple Recipients

```yaml
---
from: me@example.com
to:
  - alice@example.com
  - bob@example.com
cc: team@example.com
subject: Team update
---
```

### Attachments (Future)

```yaml
---
from: me@example.com
to: recipient@example.com
subject: Document attached
attachments:
  - path: ./report.pdf
  - path: /absolute/path/to/file.xlsx
  - path: ~/documents/image.png
---

Please find the attached documents.
```

## Directory Structure

```
~/Mdmailbox/
├── inbox/              # imported/received emails
├── drafts/             # work in progress
├── sent/               # successfully sent
└── outbox/             # queued for sending (future)
```

## Configuration

### Credentials via .authinfo

mdmailbox uses the standard `.authinfo` format for SMTP credentials:

```
# ~/.authinfo
machine smtp.gmail.com login you@gmail.com password your-app-password
machine smtp.migadu.com login you@migadu.com password your-password

# Wildcard domain support
machine smtp.migadu.com login *@yourdomain.com password shared-password
```

When sending, mdmailbox looks up credentials by matching the `from:` address to the `login` field.

Features:
- Exact match lookup
- Gmail address normalization (dots and +suffix ignored)
- Wildcard domain matching (*@domain.com)

Set a custom path via environment variable:

```bash
export AUTHINFO_FILE=~/box/secrets/.authinfo
```

### Future: config.yaml

```yaml
# ~/Mdmail/config.yaml

defaults:
  account: gmail              # default account for sending
  content-type: text/plain    # default content type

accounts:
  gmail:
    email: hhartmann1729@gmail.com
    name: Heinrich Hartmann

    imap:
      host: imap.gmail.com
      port: 993
      ssl: true

    smtp:
      host: smtp.gmail.com
      port: 587
      starttls: true

    # Credentials - multiple options
    password_file: ~/secrets/gmail.key        # read from file
    # password_env: GMAIL_PASSWORD            # from environment
    # password_cmd: "pass show gmail"         # from command
    # password_keyring: true                  # from system keyring

    # Sync settings
    sync:
      folders: [INBOX, "[Gmail]/Sent Mail"]
      max_messages: 100                       # per folder
      max_age_days: 30                        # optional time limit
```

## Command-Line Interface

### Implemented

| Command | Description |
|---------|-------------|
| `mdmail send <file>` | Send an email file |
| `mdmail send --dry-run <file>` | Validate without sending |
| `mdmail import` | Import emails from Maildir |
| `mdmail new` | Create a new email draft |
| `mdmail credentials` | Show configured SMTP credentials |

### Future Commands

```bash
# Fetching Email (requires IMAP implementation)
mdmail fetch
mdmail fetch --account gmail
mdmail fetch --account gmail --folder INBOX --limit 50

# Full bidirectional sync
mdmail sync
mdmail sync --account gmail
mdmail sync --pull-only              # IMAP -> local
mdmail sync --push-only              # local -> SMTP (send outbox)

# Managing Email Lifecycle
mdmail queue drafts/meeting.md       # moves to outbox/
mdmail list inbox
mdmail list drafts
mdmail list outbox
mdmail search "from:alice subject:meeting"
mdmail archive inbox/msg-12345.md    # moves to archive/

# Reply to email (creates draft with headers pre-filled)
mdmail reply inbox/msg-12345.md
mdmail reply inbox/msg-12345.md --all  # reply-all

# Utility Commands
mdmail validate drafts/meeting.md
mdmail convert inbox/msg.md --to html > msg.html
mdmail convert inbox/msg.md --to rfc822 > msg.eml
```

## Email Lifecycle

### Composing and Sending

```
                    ┌─────────┐
                    │ drafts/ │  ← mdmail new, manual editing
                    └────┬────┘
                         │ mdmail send
                         ▼
              ┌──────────┴──────────┐
              │                     │
         [SMTP OK]            [SMTP Error]
              │                     │
              ▼                     ▼
         ┌─────────┐          error message
         │  sent/  │
         └─────────┘
```

### Receiving (Future)

```
    [IMAP Server]
          │
          │ mdmail fetch
          ▼
     ┌─────────┐
     │ inbox/  │  ← new emails appear here
     └────┬────┘
          │ mdmail archive
          ▼
     ┌──────────┐
     │ archive/ │
     └──────────┘
```

### File Naming Convention

**Imported/received emails:**
```
inbox/2025-01-23-sender-subject-slug.md
      └────┬────┘└──┬──┘└────┬─────┘
          date    from    subject
```

**Sent emails:**
```
sent/2025-12-08-subject-slug.md  # timestamped on send
```

## Python API

### Current API

```python
from mdmail import Email
from mdmail.authinfo import find_credential_by_email
from mdmail.smtp import send_email

# Parse email file
email = Email.from_file("drafts/meeting.md")

# Access headers
print(email.from_addr)    # "me@example.com"
print(email.to)           # ["recipient@example.com"]
print(email.subject)      # "Subject line"
print(email.body)         # message content

# Modify email
email.subject = "Updated subject"
email.save(Path("drafts/meeting.md"))

# Create new email
email = Email(
    from_addr="me@example.com",
    to=["you@example.com"],
    subject="Hello",
    body="Hi there!"
)
email.save(Path("drafts/hello.md"))

# Send email
result = send_email(email, authinfo_path=Path("~/.authinfo"))
if result.success:
    print(f"Sent! Message-ID: {result.message_id}")
```

### Future API Extensions

```python
from mdmail import Config, Account

# Load configuration
config = Config.load("~/Mdmail/config.yaml")

# Get account and fetch emails
account = config.get_account("gmail")
emails = account.fetch(folder="INBOX", limit=50)

for email in emails:
    email.save_to("inbox/")

# Direct IMAP access
from mdmail.imap import IMAPClient

with IMAPClient(host, port, user, password) as imap:
    messages = imap.fetch_folder("INBOX", limit=100)
```

## Conversion Details

### RFC822 to mdmail Format (Import)

When importing from Maildir:

1. Parse RFC822 headers into YAML frontmatter
2. Extract plain text body (prefer `text/plain` part)
3. If only HTML, convert to markdown (optional)
4. Save attachments to `attachments/` subfolder (optional)
5. Generate filename from date + from + subject
6. Compute SHA256 hash of original file for deduplication

### mdmail Format to RFC822 (Send)

When sending via SMTP:

1. Parse YAML frontmatter into RFC822 headers
2. Generate `Message-ID` if not present
3. Set `Date` to current time if not present
4. Convert markdown body to HTML if content-type is `text/markdown`
5. Encode as MIME multipart if attachments present
6. Submit to SMTP server

## Integration Examples

### Git Workflow

```bash
cd ~/Mdmail
git init
echo "*.key" >> .gitignore

# Commit sent emails
mdmail send drafts/important-msg.md
git add sent/
git commit -m "Sent: important-msg"
```

### LLM Integration

```python
import anthropic
from mdmail import Email

client = anthropic.Anthropic()

# LLM writes the email content
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "Write a follow-up email for..."}]
)

# Parse and save as draft
email = Email.from_string(response.content[0].text)
email.save(Path("drafts/llm-followup.md"))
```

### Cron/Systemd Automation

```bash
# Periodic sync (future)
*/15 * * * * mdmail sync --quiet

# Auto-send outbox (future)
*/5 * * * * mdmail send --all --quiet
```

## Implementation Notes

### Dependencies

**Current:**
- `pyyaml` - YAML parsing
- `click` - CLI framework
- `smtplib` (stdlib) - SMTP client
- `email` (stdlib) - RFC822 parsing/generation

**Future:**
- `imaplib` (stdlib) - IMAP client
- `markdown` - Markdown to HTML conversion
- `html2text` - HTML to markdown conversion
- `keyring` - System keyring integration

### Security Considerations

1. **Credentials:** Never store passwords in config.yaml directly. Use:
   - `.authinfo` files with proper permissions
   - Environment variables (`AUTHINFO_FILE`)
   - Command output (future: `password_cmd`)
   - System keyring (future: `password_keyring`)

2. **Permissions:** Authinfo files should be 600 (owner-only)

3. **TLS:** Always use STARTTLS for SMTP (port 587)

### Future Extensions

- **IMAP fetch:** Download emails from IMAP servers
- **PGP/GPG:** Sign and encrypt emails
- **Attachments:** Support file attachments
- **Filters:** Auto-archive, auto-label based on rules
- **Search index:** Local full-text search (sqlite FTS)
- **Web UI:** Simple local web interface
- **Notmuch integration:** Use notmuch for indexing instead of custom

## License

MIT License
