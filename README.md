# mdmail

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

Save this as `~/Mdmail/drafts/meeting.md`, run `mdmail send ~/Mdmail/drafts/meeting.md`, and it's sent.

## Why?

- **Plain text** - Edit emails in your favorite editor
- **Git-friendly** - Track your email history with version control
- **Scriptable** - Automate email with simple shell scripts or Python
- **LLM-friendly** - Easy for AI tools to read, search, and compose emails
- **No lock-in** - It's just files. Move them, grep them, back them up

## Installation

```bash
pip install mdmail
```

Or with uv:

```bash
uv tool install mdmail
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
mdmail new --to friend@example.com --subject "Hello" --from you@gmail.com
```

This creates `~/Mdmail/drafts/hello.md`.

### 3. Edit and send

Edit the draft in your favorite editor, then:

```bash
mdmail send ~/Mdmail/drafts/hello.md
```

The email is sent and moved to `~/Mdmail/sent/`.

## Commands

| Command | Description |
|---------|-------------|
| `mdmail send <file>` | Send an email |
| `mdmail send --dry-run <file>` | Validate without sending |
| `mdmail import` | Import emails from Maildir |
| `mdmail new` | Create a new email draft |
| `mdmail credentials` | Show configured SMTP credentials |

### Send

```bash
# Send an email
mdmail send ~/Mdmail/drafts/hello.md

# Dry run (validate without sending)
mdmail send --dry-run ~/Mdmail/drafts/hello.md

# Use custom authinfo file
mdmail send --authinfo ~/secrets/.authinfo ~/Mdmail/drafts/hello.md
```

### Import from Maildir

If you use `mbsync` or similar tools to sync email locally:

```bash
# Import all emails from ~/mail (default)
mdmail import

# Import from custom location
mdmail import --maildir ~/Maildir

# Import to custom output directory
mdmail import -o ~/Mdmail/inbox

# Limit number of emails
mdmail import -n 100
```

### New Draft

```bash
# Create empty draft
mdmail new

# Create with fields pre-filled
mdmail new --to alice@example.com --subject "Meeting" --from me@gmail.com

# Specify output path
mdmail new -o ~/Mdmail/drafts/custom-name.md
```

### Credentials

```bash
# List all configured credentials
mdmail credentials

# Look up credentials for specific email
mdmail credentials --email you@gmail.com
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
~/Mdmail/
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
from mdmail import Email
from mdmail.smtp import send_email
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
