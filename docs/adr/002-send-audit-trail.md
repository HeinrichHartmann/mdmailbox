# ADR 002: Send Audit Trail

## Status
Accepted

## Context

When sending emails, we want a paper trail of what actually happened:
- What was sent and when
- SMTP server details and response
- Debug information for troubleshooting

Options considered:
1. Separate log file (`~/Mdmailbox/logs/send.log`)
2. SQLite database
3. Metadata only in YAML frontmatter
4. Append audit section to the email file itself

## Decision

Append a second YAML section at the end of the sent email file containing the send protocol and debug log.

### Format

```yaml
---
from: me@example.com
to: alice@example.com
subject: Hello
message-id: <abc123@mail.example.com>
date: 2025-01-23T10:30:00+00:00
---

Email body here.

---
# Send Log
sent-at: 2025-01-23T10:30:05+00:00
smtp-host: smtp.gmail.com
smtp-port: 587
smtp-response: "250 2.0.0 OK"
---

[2025-01-23T10:30:05] Connecting to smtp.gmail.com:587
[2025-01-23T10:30:05] STARTTLS established
[2025-01-23T10:30:05] Authenticated as me@example.com
[2025-01-23T10:30:05] Sending to: alice@example.com
[2025-01-23T10:30:05] Server response: 250 2.0.0 OK
[2025-01-23T10:30:05] Message-ID: <abc123@mail.example.com>
```

## Consequences

### Positive
- Self-contained: everything about the email in one file
- Version-controllable with git
- No separate log files to manage
- Human-readable audit trail
- Works with standard tools (grep, cat)

### Negative
- File format is not perfectly clean (body could contain `---`)
- Parsing becomes ambiguous if body has YAML-like content
- File grows slightly larger

### Accepted tradeoffs
- We accept the parsing ambiguity for now. A future version could use a different delimiter or escape mechanism if needed.
- The audit section is append-only and clearly marked with `# Send Log` comment.

## Implementation

1. After successful SMTP send, append the audit section to the email
2. Move the complete file (with audit trail) to `~/Mdmailbox/sent/`
3. The original draft is removed (not copied)
