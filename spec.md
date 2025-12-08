# mdmail - Email as Files with YAML Frontmatter

## Overview

**mdmail** is a command-line tool and Python library for managing email as local files with YAML frontmatter headers. It provides bidirectional sync between IMAP servers and a local filesystem, treating emails as plain text files that can be edited, version-controlled, and processed by scripts or LLMs.

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

Can include **markdown** formatting if content-type is text/markdown.
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

### Attachments

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
~/mdmail/                     # or configured location
├── config.yaml               # account configuration
├── accounts/
│   ├── gmail/
│   │   ├── inbox/            # received emails
│   │   ├── sent/             # successfully sent
│   │   └── archive/          # archived emails
│   └── migadu/
│       ├── inbox/
│       ├── sent/
│       └── archive/
├── drafts/                   # work in progress (not account-specific)
├── outbox/                   # queued for sending
└── templates/                # reusable email templates
```

## Configuration

### config.yaml

```yaml
# ~/mdmail/config.yaml

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

  migadu:
    email: heinrich@signals.io
    name: Heinrich Hartmann

    imap:
      host: imap.migadu.com
      port: 993
      ssl: true

    smtp:
      host: smtp.migadu.com
      port: 587
      starttls: true

    password_file: ~/secrets/migadu.key
```

## Command-Line Interface

### Fetching Email

```bash
# Fetch from all accounts
mdmail fetch

# Fetch from specific account
mdmail fetch --account gmail

# Fetch with options
mdmail fetch --account gmail --folder INBOX --limit 50

# Fetch and convert to markdown (extract plain text, convert HTML)
mdmail fetch --format markdown
```

### Sending Email

```bash
# Send a specific file
mdmail send drafts/meeting-followup.md

# Send all files in outbox
mdmail send --all

# Dry run (validate without sending)
mdmail send drafts/meeting.md --dry-run

# Send and specify account (overrides file header)
mdmail send drafts/meeting.md --account migadu
```

### Managing Email Lifecycle

```bash
# Create new draft from template
mdmail new                           # interactive
mdmail new --to alice@example.com --subject "Hello"
mdmail new --template meeting-invite

# Move draft to outbox (ready to send)
mdmail queue drafts/meeting.md       # moves to outbox/

# List emails by status
mdmail list inbox
mdmail list drafts
mdmail list outbox
mdmail list sent --account gmail --limit 10

# Search across all emails
mdmail search "from:alice subject:meeting"
mdmail search --query "project update" --folder inbox

# Archive email
mdmail archive inbox/msg-12345.md    # moves to archive/

# Reply to email (creates draft with headers pre-filled)
mdmail reply inbox/msg-12345.md
mdmail reply inbox/msg-12345.md --all  # reply-all
```

### Sync Operations

```bash
# Full bidirectional sync
mdmail sync

# Sync specific account
mdmail sync --account gmail

# One-way sync
mdmail sync --pull-only              # IMAP -> local
mdmail sync --push-only              # local -> SMTP (send outbox)
```

### Utility Commands

```bash
# Validate email file format
mdmail validate drafts/meeting.md

# Convert between formats
mdmail convert inbox/msg.md --to html > msg.html
mdmail convert inbox/msg.md --to rfc822 > msg.eml

# Import existing email file
mdmail import message.eml --to inbox/

# Show configuration
mdmail config show
mdmail config accounts
```

## Email Lifecycle

### Composing and Sending

```
                    ┌─────────┐
                    │ drafts/ │  ← mdmail new, manual editing
                    └────┬────┘
                         │ mdmail queue
                         ▼
                    ┌─────────┐
                    │ outbox/ │  ← ready to send
                    └────┬────┘
                         │ mdmail send
                         ▼
              ┌──────────┴──────────┐
              │                     │
         [SMTP OK]            [SMTP Error]
              │                     │
              ▼                     ▼
         ┌─────────┐          stays in outbox
         │  sent/  │          (error logged in header)
         └─────────┘
```

### Receiving

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

**Received emails:**
```
inbox/2025-12-08-143052-meeting-followup-abc123.md
      └─────┬─────┘ └──────┬───────┘ └──┬──┘
          date        subject slug    msg-id hash
```

**Drafts and sent:**
```
drafts/meeting-followup.md           # user-chosen name
sent/2025-12-08-143052-meeting-followup.md  # timestamped on send
```

## Python API

### Installation

```bash
pip install mdmail
```

### Basic Usage

```python
from mdmail import Email, Account, Config

# Load configuration
config = Config.load("~/mdmail/config.yaml")

# Parse email file
email = Email.from_file("drafts/meeting.md")

# Access headers
print(email.from_addr)    # "me@example.com"
print(email.to)           # ["recipient@example.com"]
print(email.subject)      # "Subject line"

# Access body
print(email.body)         # raw content
print(email.body_html)    # converted to HTML if markdown

# Modify email
email.subject = "Updated subject"
email.save()              # write back to file

# Send email
account = config.get_account("gmail")
result = account.send(email)
if result.success:
    email.move_to("sent/")
```

### Fetching Emails

```python
from mdmail import Config, fetch_emails

config = Config.load()
account = config.get_account("gmail")

# Fetch recent emails
emails = account.fetch(folder="INBOX", limit=50)

for email in emails:
    email.save_to("inbox/")
```

### Low-Level SMTP/IMAP

```python
from mdmail.smtp import SMTPClient
from mdmail.imap import IMAPClient

# Direct SMTP access
with SMTPClient(host, port, user, password) as smtp:
    smtp.send(email.to_rfc822())

# Direct IMAP access
with IMAPClient(host, port, user, password) as imap:
    messages = imap.fetch_folder("INBOX", limit=100)
```

## Conversion Details

### RFC822 to mdmail Format

When fetching from IMAP:

1. Parse RFC822 headers into YAML frontmatter
2. Extract plain text body (prefer `text/plain` part)
3. If only HTML, convert to markdown (optional)
4. Save attachments to `attachments/` subfolder (optional)
5. Generate filename from date + subject + message-id hash

### mdmail Format to RFC822

When sending via SMTP:

1. Parse YAML frontmatter into RFC822 headers
2. Generate `Message-ID` if not present
3. Set `Date` to current time if not present
4. Convert markdown body to HTML if content-type is `text/markdown`
5. Encode as MIME multipart if attachments present
6. Submit to SMTP server

## Error Handling

### Send Failures

When SMTP submission fails, the email stays in `outbox/` with error info added:

```yaml
---
from: me@example.com
to: recipient@example.com
subject: Meeting
status: outbox
last_error: "SMTP 550: Recipient rejected"
last_attempt: 2025-12-08T15:30:00+01:00
attempts: 3
---
```

### Validation Errors

```bash
$ mdmail validate drafts/bad-email.md
Error: Missing required header 'to'
Error: Invalid email address format in 'from': 'not-an-email'
```

## Integration Examples

### Git Workflow

```bash
cd ~/mdmail
git init
echo "*.key" >> .gitignore

# Commit sent emails
mdmail send outbox/important-msg.md
git add sent/
git commit -m "Sent: important-msg"
```

### LLM Integration

```python
# Generate email with LLM
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
email.save_to("drafts/llm-followup.md")
```

### Cron/Systemd Automation

```bash
# Periodic sync
*/15 * * * * mdmail sync --quiet

# Auto-send outbox
*/5 * * * * mdmail send --all --quiet
```

## Implementation Notes

### Dependencies

**Required (Python stdlib):**
- `smtplib` - SMTP client
- `imaplib` - IMAP client
- `email` - RFC822 parsing/generation

**Optional:**
- `pyyaml` - YAML parsing (or use stdlib `tomllib` for TOML config)
- `markdown` - Markdown to HTML conversion
- `html2text` - HTML to markdown conversion
- `keyring` - System keyring integration

### Security Considerations

1. **Credentials:** Never store passwords in config.yaml directly. Use:
   - File references (`password_file`)
   - Environment variables (`password_env`)
   - Command output (`password_cmd`)
   - System keyring (`password_keyring`)

2. **Permissions:** Config and password files should be 600 (owner-only)

3. **TLS:** Always use SSL/TLS or STARTTLS for IMAP/SMTP

### Future Extensions

- **PGP/GPG:** Sign and encrypt emails
- **Filters:** Auto-archive, auto-label based on rules
- **Search index:** Local full-text search (sqlite FTS)
- **Web UI:** Simple local web interface
- **Notmuch integration:** Use notmuch for indexing instead of custom

## License

MIT License
