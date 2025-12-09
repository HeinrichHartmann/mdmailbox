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


@click.group()
@click.version_option()
def main():
    """mdmailbox - Email as plain text files with YAML frontmatter."""
    pass


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
    help="Validate and show what would be sent without actually sending",
)
@click.option(
    "--port",
    type=int,
    default=587,
    help="SMTP port (default: 587)",
)
def send(file: Path, authinfo: Path | None, dry_run: bool, port: int):
    """Send an email file.

    FILE is a path to an email file with YAML frontmatter.
    """
    # Load and parse email
    try:
        email = Email.from_file(file)
    except Exception as e:
        raise click.ClickException(f"Failed to parse email: {e}")

    # Validate required fields
    if not email.from_addr:
        raise click.ClickException("Missing required header: from")
    if not email.to:
        raise click.ClickException("Missing required header: to")
    if not email.subject:
        raise click.ClickException("Missing required header: subject")

    if dry_run:
        click.echo("=== Dry run - would send: ===")
        click.echo(f"From: {email.from_addr}")
        click.echo(f"To: {', '.join(email.to)}")
        if email.cc:
            click.echo(f"Cc: {', '.join(email.cc)}")
        click.echo(f"Subject: {email.subject}")
        click.echo("---")
        click.echo(email.body[:500] + ("..." if len(email.body) > 500 else ""))
        return

    # Send
    result = send_email(email, authinfo_path=authinfo, port=port)

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
        # Show the log on failure for debugging
        if result.log:
            click.echo("Send log:")
            for line in result.log:
                click.echo(f"  {line}")
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

    # Build email
    to_list = [to] if to else []
    cc_list = [c.strip() for c in cc.split(",")] if cc else []

    email = Email(
        from_addr=from_addr or "",
        to=to_list,
        subject=subject or "",
        body="\n",
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


if __name__ == "__main__":
    main()
