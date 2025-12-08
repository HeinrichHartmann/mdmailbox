"""Command-line interface for mdmail."""

from pathlib import Path
import os
import click

from .email import Email
from .smtp import send_email
from .authinfo import parse_authinfo, find_credential_by_email
from .importer import import_maildir


@click.group()
@click.version_option()
def main():
    """mdmail - Email as plain text files with YAML frontmatter."""
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
        click.echo(f"---")
        click.echo(email.body[:500] + ("..." if len(email.body) > 500 else ""))
        return

    # Send
    result = send_email(email, authinfo_path=authinfo, port=port)

    if result.success:
        click.echo(f"Sent: {email.subject}")
        click.echo(f"Message-ID: {result.message_id}")
    else:
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
    help="Output directory (default: ~/Mdmail/inbox)",
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
def import_cmd(maildir: Path, output: Path | None, limit: int | None, account: str | None):
    """Import emails from Maildir to mdmail format."""
    if output is None:
        output = Path.home() / "Mdmail" / "inbox"

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
