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

That's it. Save this as `drafts/meeting.md`, run `mdmail send drafts/meeting.md`, and it's sent.

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

## Quick Start

### 1. Configure your account

```bash
mdmail init
```

Or create `~/.mdmail/config.yaml` manually:

```yaml
accounts:
  gmail:
    email: you@gmail.com
    smtp:
      host: smtp.gmail.com
      port: 587
      starttls: true
    imap:
      host: imap.gmail.com
      port: 993
      ssl: true
    password_file: ~/.mdmail/gmail.key
```

### 2. Fetch your email

```bash
mdmail fetch
```

Emails appear as files in `~/.mdmail/accounts/gmail/inbox/`:

```
inbox/
  2025-12-08-meeting-notes-a1b2c3.md
  2025-12-08-project-update-d4e5f6.md
  2025-12-07-welcome-g7h8i9.md
```

### 3. Read an email

```bash
cat ~/.mdmail/accounts/gmail/inbox/2025-12-08-meeting-notes-a1b2c3.md
```

Or use any text editor, `less`, `grep`, etc.

### 4. Compose and send

Create a file in `drafts/`:

```bash
cat > ~/.mdmail/drafts/hello.md << 'EOF'
---
from: you@gmail.com
to: friend@example.com
subject: Hello!
---

Just wanted to say hi.
EOF
```

Send it:

```bash
mdmail send drafts/hello.md
```

Done. The file moves to `sent/`.

## Commands

| Command | Description |
|---------|-------------|
| `mdmail import` | Import emails from Maildir (e.g., mbsync) |
| `mdmail send <file>` | Send an email |
| `mdmail credentials` | Show configured SMTP credentials |

### Import from Maildir

If you use `mbsync` or similar tools to sync email locally, import them:

```bash
# Import all emails from ~/mail (default)
mdmail import

# Import from custom location
mdmail import --maildir ~/Maildir

# Import to custom output directory
mdmail import -o ~/.mdmail/inbox

# Limit number of emails
mdmail import -n 100
```

Imported emails include metadata:

```yaml
---
from: sender@example.com
to: recipient@example.com
subject: Meeting notes
date: '2025-01-23T10:30:00+00:00'
message-id: <abc123@mail.example.com>
account: gmail-hhartmann1729      # auto-detected from path
original-hash: 5123e59f7de5e2cc... # SHA256 of original file
---
```

## File Format

Every email is a text file with YAML frontmatter:

```yaml
---
from: sender@example.com
to: recipient@example.com
subject: Subject line
cc: optional@example.com
date: 2025-12-08T15:30:00
---

Body content goes here.

Can be plain text, **markdown**, or HTML.
The file extension (.md, .txt, .html) hints at the format.
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

### Attachments

```yaml
---
to: recipient@example.com
subject: Files attached
attachments:
  - ./report.pdf
  - ~/documents/image.png
---
```

## Directory Structure

```
~/.mdmail/
├── config.yaml
├── accounts/
│   └── gmail/
│       ├── inbox/      # received
│       ├── sent/       # sent
│       └── archive/    # archived
├── drafts/             # work in progress
├── outbox/             # ready to send
└── templates/          # reusable templates
```

## Configuration

### Credentials via .authinfo

mdmail uses the standard `.authinfo` format for SMTP credentials:

```
# ~/.authinfo
machine smtp.gmail.com login you@gmail.com password your-app-password
machine smtp.migadu.com login you@migadu.com password your-password
```

When sending, mdmail looks up credentials by matching the `from:` address to the `login` field.

Set a custom path via environment variable:

```bash
export AUTHINFO_FILE=~/box/secrets/.authinfo
```

View configured credentials:

```bash
mdmail credentials --authinfo ~/.authinfo
```

## Examples

### Search emails

```bash
# Find emails from Alice
mdmail search "from:alice"

# Find emails about the project from last week
mdmail search "subject:project date:7d"

# Or just use grep
grep -r "project" ~/.mdmail/accounts/gmail/inbox/
```

### Quick reply

```bash
mdmail reply inbox/question-from-bob.md
# Opens your editor with headers pre-filled
```

### Send from script

```bash
#!/bin/bash
cat > /tmp/alert.md << EOF
---
from: alerts@myserver.com
to: admin@example.com
subject: Server Alert - $(date)
---

Disk usage is above 90%.
EOF

mdmail send /tmp/alert.md
```

### Use with Git

```bash
cd ~/.mdmail
git init
git add sent/
git commit -m "Email archive"
```

## Python API

```python
from mdmail import Email, Config

# Load config
config = Config.load()

# Read an email
email = Email.from_file("inbox/message.md")
print(email.subject)
print(email.body)

# Create and send
email = Email(
    from_addr="me@example.com",
    to=["you@example.com"],
    subject="Hello",
    body="Hi there!"
)
email.save_to("drafts/hello.md")

account = config.get_account("gmail")
account.send(email)
```

## FAQ

**Q: Why not just use Gmail/Outlook/Apple Mail?**

A: Those are great for most people. mdmail is for those who want:
- Email in plain text files they control
- Git version control for email
- Easy scripting and automation
- AI/LLM integration

**Q: Is this secure?**

A: mdmail uses standard TLS/SSL for all server connections. Credentials are stored locally using your choice of secure method (encrypted files, system keyring, password manager).

**Q: Can I use this as my main email client?**

A: You could, but it's designed more as a power-user tool alongside your regular email client. Great for automation, archiving, and scripting.

**Q: What about HTML emails?**

A: HTML emails are converted to plain text by default when fetching. You can also write HTML emails by using a `.html` extension.

## License

MIT
