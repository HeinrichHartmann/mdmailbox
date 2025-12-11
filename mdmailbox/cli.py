"""Command-line interface for mdmailbox."""

from pathlib import Path
from datetime import datetime
import os
import click

from .email import Email
from .importer import sanitize_filename
from .smtp import send_email, SendResult
from .authinfo import parse_authinfo, find_credential_by_email
from .importer import import_maildir


def _save_with_audit_trail(email: Email, path: Path, result: SendResult) -> None:
    """Save email to file with audit trail appended.

    The audit trail is a second YAML section at the end of the file
    containing send metadata and a verbose log.
    """
    # First save the email normally
    email.save(path)

    # Now append the audit trail
    audit_lines = [
        "",
        "---",
        "# Send Log",
    ]

    if result.sent_at:
        audit_lines.append(f"sent-at: {result.sent_at.isoformat()}")
    if result.smtp_host:
        audit_lines.append(f"smtp-host: {result.smtp_host}")
    if result.smtp_port:
        audit_lines.append(f"smtp-port: {result.smtp_port}")
    if result.smtp_response:
        # Quote the response in case it has special chars
        audit_lines.append(f'smtp-response: "{result.smtp_response}"')

    audit_lines.append("---")
    audit_lines.append("")

    # Add the log entries
    for log_line in result.log:
        audit_lines.append(log_line)

    # Append to file
    with open(path, "a") as f:
        f.write("\n".join(audit_lines))
        f.write("\n")


def _get_readme_content() -> str:
    """Load README content from package."""
    try:
        from ._docs import README_CONTENT
        if README_CONTENT:
            return README_CONTENT
    except ImportError:
        pass

    return "README not found"


def _get_format_guide() -> str:
    """Return the email format documentation."""
    return """## Email Format Guide

Every mdmailbox email is a plain text file with YAML frontmatter:

```yaml
---
from: sender@example.com
to: recipient@example.com
subject: Subject line
cc: optional@example.com
date: 2025-12-08T15:30:00+01:00
message-id: <abc123@mail.example.com>
attachments:
  - ./report.pdf
  - ~/documents/data.xlsx
---

Body content goes here.
```

### Fields

**Required:**
- `from` - Sender email address (can include display name: "John Doe <john@example.com>")
- `to` - Recipient(s), can be string or list
- `subject` - Email subject

**Optional:**
- `cc` - Carbon copy recipient(s)
- `bcc` - Blind carbon copy recipient(s)
- `date` - ISO 8601 or RFC 2822 format
- `message-id` - Unique message identifier
- `in-reply-to` - Message-ID being replied to
- `references` - List of message-IDs for threading
- `reply-to` - Reply-to address
- `attachments` - File paths (see below)

### Multiple Recipients

```yaml
---
to:
  - alice@example.com
  - bob@example.com
cc: team@example.com
---
```

### Attachments

Files to attach to the email. Paths support:
- Relative paths: `./report.pdf`
- Home directory: `~/documents/data.xlsx`
- Absolute paths: `/abs/path/file.pdf`

Single attachment (scalar):
```yaml
attachments: ./report.pdf
```

Multiple attachments (list):
```yaml
attachments:
  - ./report.pdf
  - ~/documents/data.xlsx
  - /tmp/image.png
```

**Validation:**
- Files must exist (error if not found)
- Cannot attach directories (error if path is directory)
- Empty files are rejected (0 bytes = error)
- Large files (>10MB) trigger warnings
- MIME type is auto-detected

### Display Names

The `from` field supports RFC 5322 display names:

```yaml
from: John Doe <john@example.com>
```

Display names are preserved through save/load cycles.
"""


@click.group()
@click.version_option()
def main():
    """mdmailbox - Email as plain text files with YAML frontmatter."""
    pass


@main.command()
def help():
    """Show README documentation."""
    content = _get_readme_content()
    click.echo(content)


def _format_validation_preview(email: Email, validation_result) -> str:
    """Format the email preview with inline validation feedback."""
    from pathlib import Path as PathlibPath

    lines = ["═" * 66]

    # Group validation items by field for inline display
    items_by_field: dict[str, list] = {}
    for item in validation_result.items:
        items_by_field.setdefault(item.field, []).append(item)

    def format_field(
        name: str, value: str | None, items: list | None = None
    ) -> list[str]:
        """Format a single field with its validation status."""
        result_lines = []
        display_name = f" {name.capitalize()}:"
        padding = " " * (12 - len(display_name))

        if items:
            # First item on same line as field
            first = items[0]
            val_display = value if value else ""
            result_lines.append(
                f"{display_name}{padding}{val_display} {first.symbol} {first.message}"
            )
            # Additional items on separate lines
            for item in items[1:]:
                result_lines.append(
                    f"             {item.value or ''} {item.symbol} {item.message}"
                )
        elif value:
            result_lines.append(f"{display_name}{padding}{value}")

        return result_lines

    # Format header fields with inline validation
    if email.from_addr:
        lines.extend(format_field("from", email.from_addr, items_by_field.get("from")))

    if email.to:
        to_items = items_by_field.get("to", [])
        lines.append(
            f" To:         {email.to[0]} {to_items[0].symbol if to_items else ''} {to_items[0].message if to_items else ''}"
        )
        for i, addr in enumerate(email.to[1:], 1):
            item = to_items[i] if i < len(to_items) else None
            if item:
                lines.append(f"             {addr} {item.symbol} {item.message}")
            else:
                lines.append(f"             {addr}")

    if email.cc:
        cc_items = items_by_field.get("cc", [])
        lines.append(
            f" Cc:         {email.cc[0]} {cc_items[0].symbol if cc_items else ''} {cc_items[0].message if cc_items else ''}"
        )
        for i, addr in enumerate(email.cc[1:], 1):
            item = cc_items[i] if i < len(cc_items) else None
            if item:
                lines.append(f"             {addr} {item.symbol} {item.message}")
            else:
                lines.append(f"             {addr}")

    if email.subject is not None:
        subj_items = items_by_field.get("subject", [])
        if subj_items:
            lines.append(
                f" Subject:    {email.subject} {subj_items[0].symbol} {subj_items[0].message}"
            )
        else:
            lines.append(f" Subject:    {email.subject}")

    if email.in_reply_to:
        reply_items = items_by_field.get("in-reply-to", [])
        if reply_items:
            lines.append(
                f" In-Reply-To: {email.in_reply_to} {reply_items[0].symbol} {reply_items[0].message}"
            )
        else:
            lines.append(f" In-Reply-To: {email.in_reply_to}")

    if email.attachments:
        att_items = items_by_field.get("attachments", [])
        lines.append(f" Attachments: {len(email.attachments)} file(s)")
        for i, path in enumerate(email.attachments):
            display_name = PathlibPath(path).expanduser().name
            item = att_items[i] if i < len(att_items) else None
            if item:
                lines.append(f"             {display_name} {item.symbol} {item.message}")
            else:
                lines.append(f"             {display_name}")

    lines.append("─" * 66)
    lines.append("")

    # Body preview
    body_preview = email.body[:500] if email.body else ""
    if len(email.body or "") > 500:
        body_preview += "..."
    lines.append(body_preview)

    lines.append("")
    lines.append("═" * 66)

    # Summary at bottom
    body_items = items_by_field.get("body", [])
    if body_items:
        lines.append(f"{body_items[0].symbol} Body: {body_items[0].message}")

    # Count errors and warnings
    error_count = len(validation_result.errors)
    warning_count = len(validation_result.warnings)

    if error_count > 0:
        lines.append(
            f"✗ {error_count} error{'s' if error_count > 1 else ''} - cannot send"
        )
    elif warning_count > 0:
        lines.append(
            f"✓ Valid with {warning_count} warning{'s' if warning_count > 1 else ''}"
        )
    else:
        lines.append("✓ All headers valid")

    return "\n".join(lines)


@main.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--authinfo",
    type=click.Path(exists=True, path_type=Path),
    help="Path to .authinfo file (default: ~/.authinfo or $AUTHINFO_FILE)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate and show preview only, don't send",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Auto-confirm, but still validate. Fails on errors.",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip all validation, send as-is. For emergency use.",
)
@click.option(
    "--port",
    type=int,
    default=587,
    help="SMTP port (default: 587)",
)
@click.option(
    "--no-tls",
    is_flag=True,
    help="Disable STARTTLS (for testing only)",
)
def send(
    file: Path,
    authinfo: Path | None,
    dry_run: bool,
    yes: bool,
    force: bool,
    port: int,
    no_tls: bool,
):
    """Send an email file.

    FILE is a path to an email file with YAML frontmatter.

    By default, validates and shows a preview before prompting for confirmation.
    Use --yes to auto-confirm (still validates), or --force to skip validation.
    """
    from .validate import validate_email_string, ValidationContext

    # Load file content
    content = file.read_text()

    # Load and parse email
    try:
        email = Email.from_file(file)
    except Exception as e:
        raise click.ClickException(f"Failed to parse email: {e}")

    # Skip validation if --force
    if force:
        click.echo("⚠ Skipping validation (--force)", err=True)
    else:
        # Run validation
        ctx = ValidationContext(authinfo_path=authinfo)
        validation_result = validate_email_string(content, ctx)

        # Show preview with validation
        preview = _format_validation_preview(email, validation_result)
        click.echo(preview)

        # Check for errors
        if validation_result.has_errors:
            click.echo("", err=True)
            for item in validation_result.errors:
                click.echo(f"✗ {item.field}: {item.message}", err=True)
            raise click.ClickException("Cannot send - fix errors above")

        if dry_run:
            return

        # Prompt for confirmation unless --yes
        if not yes:
            if not click.confirm("Send this email?", default=False):
                click.echo("Cancelled.")
                return

    # Send
    result = send_email(email, authinfo_path=authinfo, port=port, use_tls=not no_tls)

    if result.success:
        # Update email with message-id and date from send
        email.message_id = result.message_id
        if not email.date:
            email.date = datetime.now().astimezone().isoformat()

        # Move to sent folder
        sent_dir = Path.home() / "Mdmailbox" / "sent"
        sent_dir.mkdir(parents=True, exist_ok=True)

        # Generate sent filename with timestamp
        now = datetime.now()
        subject_slug = sanitize_filename(email.subject, max_len=40)
        sent_filename = f"{now.strftime('%Y-%m-%d')}-{subject_slug}.md"
        sent_path = sent_dir / sent_filename

        # Avoid overwriting
        if sent_path.exists():
            i = 1
            stem = sent_path.stem
            while sent_path.exists():
                sent_path = sent_dir / f"{stem}-{i}.md"
                i += 1

        # Save email with audit trail appended
        _save_with_audit_trail(email, sent_path, result)
        file.unlink()

        click.echo(f"Sent: {email.subject}")
        click.echo(f"Message-ID: {result.message_id}")
        click.echo(f"Moved to: {sent_path}")
    else:
        # Show the log on failure for debugging (to stderr)
        if result.log:
            click.echo("Send log:", err=True)
            for line in result.log:
                click.echo(f"  {line}", err=True)
        raise click.ClickException(result.message)


@main.command(name="import")
@click.option(
    "--maildir",
    type=click.Path(exists=True, path_type=Path),
    default=Path.home() / "mail",
    help="Path to Maildir root (default: ~/mail)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: ~/Mdmailbox/inbox)",
)
@click.option(
    "--limit",
    "-n",
    type=int,
    default=None,
    help="Max number of emails to import (default: all)",
)
@click.option(
    "--account",
    help="Account name (auto-detected from path if not specified)",
)
def import_cmd(
    maildir: Path, output: Path | None, limit: int | None, account: str | None
):
    """Import emails from Maildir to mdmailbox format."""
    if output is None:
        output = Path.home() / "Mdmailbox" / "inbox"

    click.echo(f"Importing from: {maildir}")
    click.echo(f"Output to: {output}")
    if limit:
        click.echo(f"Limit: {limit}")

    created = import_maildir(
        maildir_root=maildir,
        output_dir=output,
        account=account,
        limit=limit,
    )

    click.echo(f"Imported {len(created)} emails")
    if created:
        click.echo("Recent imports:")
        for p in created[-5:]:
            click.echo(f"  {p.name}")


@main.command()
@click.option(
    "--to",
    "-t",
    help="Recipient email address",
)
@click.option(
    "--from",
    "-f",
    "from_addr",
    help="Sender email address",
)
@click.option(
    "--subject",
    "-s",
    help="Email subject",
)
@click.option(
    "--cc",
    help="CC recipient(s), comma-separated",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file path (default: ~/Mdmailbox/drafts/<subject>.md)",
)
def new(
    to: str | None,
    from_addr: str | None,
    subject: str | None,
    cc: str | None,
    output: Path | None,
):
    """Create a new email draft."""
    drafts_dir = Path.home() / "Mdmailbox" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    # Build email body with signature if available
    body = "\n"
    signature_path = Path.home() / ".signature.md"
    if signature_path.exists():
        signature = signature_path.read_text()
        body = f"\n\n{signature}"

    # Build email
    to_list = [to] if to else []
    cc_list = [c.strip() for c in cc.split(",")] if cc else []

    email = Email(
        from_addr=from_addr or "",
        to=to_list,
        subject=subject or "",
        body=body,
        cc=cc_list,
    )

    # Determine output path
    if output is None:
        if subject:
            # Sanitize subject for filename
            from .importer import sanitize_filename

            filename = sanitize_filename(subject, max_len=50) + ".md"
        else:
            filename = "new-draft.md"
        output = drafts_dir / filename

        # Avoid overwriting
        if output.exists():
            i = 1
            stem = output.stem
            while output.exists():
                output = drafts_dir / f"{stem}-{i}.md"
                i += 1

    output.parent.mkdir(parents=True, exist_ok=True)
    email.save(output)

    click.echo(f"Created: {output}")


@main.command()
@click.option(
    "--authinfo",
    type=click.Path(exists=True, path_type=Path),
    help="Path to .authinfo file (default: ~/.authinfo or $AUTHINFO_FILE)",
)
@click.option(
    "--email",
    help="Look up credentials for specific email address",
)
def credentials(authinfo: Path | None, email: str | None):
    """Show configured credentials (passwords masked)."""
    # Resolve authinfo path
    if authinfo is None:
        if env_path := os.environ.get("AUTHINFO_FILE"):
            authinfo = Path(env_path).expanduser()
        else:
            authinfo = Path.home() / ".authinfo"

    if not authinfo.exists():
        raise click.ClickException(f"Authinfo file not found: {authinfo}")

    click.echo(f"Reading: {authinfo}")
    click.echo()

    if email:
        # Look up specific email
        cred = find_credential_by_email(email, authinfo)
        if cred:
            click.echo(f"  Email: {cred.login}")
            click.echo(f"  Host:  {cred.machine}")
            click.echo(f"  Pass:  {'*' * len(cred.password)}")
        else:
            raise click.ClickException(f"No credentials found for: {email}")
    else:
        # List all
        creds = parse_authinfo(authinfo)
        if not creds:
            click.echo("No credentials found.")
            return

        for cred in creds:
            click.echo(f"  {cred.login}")
            click.echo(f"    Host: {cred.machine}")
            click.echo(f"    Pass: {'*' * len(cred.password)}")
            click.echo()


@main.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file path (default: ~/Mdmailbox/drafts/re-<subject>.md)",
)
def reply(file: Path, output: Path | None):
    """Create a reply draft to an email.

    FILE is a path to an email file to reply to.
    """
    # Load original email
    try:
        original = Email.from_file(file)
    except Exception as e:
        raise click.ClickException(f"Failed to parse email: {e}")

    drafts_dir = Path.home() / "Mdmailbox" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    # Build reply subject
    subject = original.subject or ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    # Reply to sender
    reply_to = original.from_addr

    # Build reply body with quoted original
    body_lines = ["\n\n"]

    # Add signature if available
    signature_path = Path.home() / ".signature.md"
    if signature_path.exists():
        body_lines.append(signature_path.read_text())
        body_lines.append("\n\n")

    # Quote original message
    if original.date:
        body_lines.append(f"On {original.date}, {original.from_addr} wrote:\n")
    else:
        body_lines.append(f"{original.from_addr} wrote:\n")

    # Quote each line of original body
    for line in original.body.splitlines():
        body_lines.append(f"> {line}")

    body = "\n".join(body_lines)

    # Build references for threading
    references = []
    if original.message_id:
        references.append(original.message_id)

    email = Email(
        from_addr="",  # User fills in
        to=[reply_to] if reply_to else [],
        subject=subject,
        body=body,
        in_reply_to=original.message_id,
    )

    # Determine output path
    if output is None:
        subject_slug = sanitize_filename(subject, max_len=50)
        filename = f"{subject_slug}.md"
        output = drafts_dir / filename

        # Avoid overwriting
        if output.exists():
            i = 1
            stem = output.stem
            while output.exists():
                output = drafts_dir / f"{stem}-{i}.md"
                i += 1

    output.parent.mkdir(parents=True, exist_ok=True)
    email.save(output)

    click.echo(f"Created reply: {output}")


if __name__ == "__main__":
    main()
