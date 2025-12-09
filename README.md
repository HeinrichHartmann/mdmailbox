# mdmailbox

Email as plain text files with YAML headers.

## What is this?

mdmail treats email as simple text files:

```yaml
---
from: me@example.com
to: alice@example.com
subject: Quick question
---

Hey Alice,

Are we still on for tomorrow?

Best,
Me
```

Save this as `~/Mdmailbox/drafts/meeting.md`, run `mdmailbox send ~/Mdmailbox/drafts/meeting.md`, and it's sent.

## Why?

- **Plain text** - Edit emails in your favorite editor
- **Git-friendly** - Track your email history with version control
- **Scriptable** - Automate email with simple shell scripts or Python
- **LLM-friendly** - Easy for AI tools to read, search, and compose emails
- **No lock-in** - It's just files. Move them, grep them, back them up

## Installation

```bash
pip install mdmailbox
```

Or with uv:

```bash
uv tool install mdmailbox
```

## Quick Start

### 1. Configure credentials

Create `~/.authinfo` with your SMTP credentials:

```
machine smtp.gmail.com login you@gmail.com password your-app-password
machine smtp.migadu.com login you@migadu.com password your-password
```

### 2. Create a draft

```bash
mdmailbox new --to friend@example.com --subject "Hello" --from you@gmail.com
```

This creates `~/Mdmailbox/drafts/hello.md`.

### 3. Edit and send

Edit the draft in your favorite editor, then:

```bash
mdmailbox send ~/Mdmailbox/drafts/hello.md
```

The email is sent and moved to `~/Mdmailbox/sent/`.

## Commands

| Command | Description |
|---------|-------------|
| `mdmailbox send <file>` | Send an email |
| `mdmailbox send --dry-run <file>` | Validate without sending |
| `mdmailbox import` | Import emails from Maildir |
| `mdmailbox new` | Create a new email draft |
| `mdmailbox credentials` | Show configured SMTP credentials |

### Send

```bash
# Send an email
mdmailbox send ~/Mdmailbox/drafts/hello.md

# Dry run (validate without sending)
mdmailbox send --dry-run ~/Mdmailbox/drafts/hello.md

# Use custom authinfo file
mdmailbox send --authinfo ~/secrets/.authinfo ~/Mdmailbox/drafts/hello.md
```

### Import from Maildir

If you use `mbsync` or similar tools to sync email locally:

```bash
# Import all emails from ~/mail (default)
mdmailbox import

# Import from custom location
mdmailbox import --maildir ~/Maildir

# Import to custom output directory
mdmailbox import -o ~/Mdmailbox/inbox

# Limit number of emails
mdmailbox import -n 100
```

### New Draft

```bash
# Create empty draft
mdmailbox new

# Create with fields pre-filled
mdmailbox new --to alice@example.com --subject "Meeting" --from me@gmail.com

# Specify output path
mdmailbox new -o ~/Mdmailbox/drafts/custom-name.md
```

### Credentials

```bash
# List all configured credentials
mdmailbox credentials

# Look up credentials for specific email
mdmailbox credentials --email you@gmail.com
```

## File Format

Every email is a text file with YAML frontmatter:

```yaml
---
from: sender@example.com
to: recipient@example.com
subject: Subject line
cc: optional@example.com
date: 2025-12-08T15:30:00+01:00
message-id: <abc123@mail.example.com>
---

Body content goes here.
```

### Multiple recipients

```yaml
---
to:
  - alice@example.com
  - bob@example.com
cc: team@example.com
---
```

## Directory Structure

```
~/Mdmailbox/
├── inbox/              # imported emails
├── drafts/             # work in progress
└── sent/               # successfully sent
```

## Configuration

### Credentials via .authinfo

mdmail uses the standard `.authinfo` format:

```
# ~/.authinfo
machine smtp.gmail.com login you@gmail.com password your-app-password
machine smtp.migadu.com login you@migadu.com password your-password

# Wildcard domain support (for aliases)
machine smtp.migadu.com login *@yourdomain.com password shared-password
```

When sending, mdmail looks up credentials by matching the `from:` address.

Features:
- Exact match
- Gmail normalization (dots and +suffix ignored for gmail.com)
- Wildcard domain matching (*@domain.com)

Set a custom path via environment variable:

```bash
export AUTHINFO_FILE=~/secrets/.authinfo
```

## Python API

```python
from mdmailbox import Email
from mdmailbox.smtp import send_email
from pathlib import Path

# Read an email
email = Email.from_file(Path("inbox/message.md"))
print(email.subject)
print(email.body)

# Create and save
email = Email(
    from_addr="me@example.com",
    to=["you@example.com"],
    subject="Hello",
    body="Hi there!"
)
email.save(Path("drafts/hello.md"))

# Send
result = send_email(email)
if result.success:
    print(f"Sent! Message-ID: {result.message_id}")
```

## Development

```bash
# Run tests
make test

# Install locally
make local-install
```

## Future Ideas

See [docs/adr/001-design.md](docs/adr/001-design.md) for the full design document including planned features like IMAP fetch, attachments, and more.

## License

MIT
