"""Import emails from Maildir (RFC822) to mdmail YAML format."""

import re
import hashlib
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime, parseaddr
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

from .email import Email


@dataclass
class ImportedEmail:
    """Email with import metadata."""
    email: Email
    original_hash: str
    source_path: Path


def sanitize_filename(text: str, max_len: int = 40) -> str:
    """Sanitize text for use in filename.

    - Lowercase
    - Replace spaces/special chars with hyphens
    - Collapse multiple hyphens
    - Strip leading/trailing hyphens
    - Truncate to max_len
    """
    if not text:
        return "unknown"

    # Lowercase and replace non-alphanumeric with hyphens
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)

    # Collapse multiple hyphens and strip edges
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')

    # Truncate (try to break at hyphen)
    if len(text) > max_len:
        text = text[:max_len]
        if '-' in text[max_len-10:]:
            text = text[:text.rfind('-')]

    return text or "unknown"


def generate_filename(
    date: datetime | None,
    from_addr: str,
    subject: str,
    message_id: str | None = None,
    existing_names: set[str] | None = None,
) -> str:
    """Generate a sanitized filename for an email.

    Format: YYYY-MM-DD-from-subject[-id].md
    Total length kept under 120 chars.
    """
    # Date part
    if date:
        date_str = date.strftime("%Y-%m-%d")
    else:
        date_str = "0000-00-00"

    # From part (extract name or email local part)
    _, email_addr = parseaddr(from_addr)
    if email_addr:
        from_part = email_addr.split('@')[0]
    else:
        from_part = from_addr.split('@')[0] if '@' in from_addr else from_addr
    from_part = sanitize_filename(from_part, max_len=20)

    # Subject part
    subject_part = sanitize_filename(subject, max_len=40)

    # Base filename (without potential id suffix)
    base = f"{date_str}-{from_part}-{subject_part}"

    # Check if we need disambiguation
    if existing_names is None:
        existing_names = set()

    filename = f"{base}.md"
    if filename not in existing_names:
        return filename

    # Add short hash from message-id for uniqueness
    if message_id:
        id_hash = hashlib.sha1(message_id.encode()).hexdigest()[:6]
    else:
        # Fallback: hash from content
        id_hash = hashlib.sha1(f"{from_addr}{subject}{date_str}".encode()).hexdigest()[:6]

    filename = f"{base}-{id_hash}.md"
    return filename


def parse_rfc822(path: Path) -> ImportedEmail:
    """Parse an RFC822 email file into an Email object with metadata."""
    raw_bytes = path.read_bytes()

    # Compute hash of original file
    original_hash = hashlib.sha256(raw_bytes).hexdigest()

    msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)

    # Extract headers - convert to plain strings
    from_addr = str(msg['From'] or "")

    # To can be multiple
    to_header = str(msg['To'] or "")
    to = [addr.strip() for addr in to_header.split(',') if addr.strip()]

    # CC
    cc_header = str(msg.get('Cc', "") or "")
    cc = [addr.strip() for addr in cc_header.split(',') if addr.strip()]

    subject = str(msg['Subject'] or "(no subject)")
    message_id = str(msg['Message-ID']) if msg['Message-ID'] else None

    # Parse date
    date_str = msg['Date']
    date = None
    if date_str:
        try:
            date = parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            pass

    in_reply_to = str(msg['In-Reply-To']) if msg.get('In-Reply-To') else None
    references_header = str(msg.get('References', "") or "")
    references = references_header.split() if references_header else []

    # Extract body (prefer plain text)
    body = ""
    if msg.is_multipart():
        # Try to get plain text part
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain':
                try:
                    body = part.get_content()
                    break
                except Exception:
                    pass
        # Fallback to HTML if no plain text
        if not body:
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    try:
                        body = part.get_content()
                        body = f"[HTML content]\n\n{body}"
                        break
                    except Exception:
                        pass
    else:
        try:
            body = msg.get_content()
        except Exception:
            body = ""

    # Clean up body
    if isinstance(body, bytes):
        body = body.decode('utf-8', errors='replace')
    body = body.strip() if body else ""

    email = Email(
        from_addr=from_addr,
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        message_id=message_id,
        date=date.isoformat() if date else None,
        in_reply_to=in_reply_to,
        references=references,
        original_hash=original_hash,
    )

    return ImportedEmail(
        email=email,
        original_hash=original_hash,
        source_path=path,
    )


def find_maildir_emails(maildir_root: Path) -> list[Path]:
    """Find all email files in a Maildir structure.

    Looks in */cur/* and */new/* directories.
    """
    emails = []

    for folder in maildir_root.iterdir():
        if not folder.is_dir():
            continue

        # Check cur and new subdirs
        for subdir in ['cur', 'new']:
            subpath = folder / subdir
            if subpath.exists():
                for email_file in subpath.iterdir():
                    if email_file.is_file():
                        emails.append(email_file)

        # Also check nested folders (e.g., gmail-hhartmann1729/INBOX/cur/)
        for subfolder in folder.iterdir():
            if subfolder.is_dir():
                for subdir in ['cur', 'new']:
                    subpath = subfolder / subdir
                    if subpath.exists():
                        for email_file in subpath.iterdir():
                            if email_file.is_file():
                                emails.append(email_file)

    return emails


def import_maildir(
    maildir_root: Path,
    output_dir: Path,
    account: str | None = None,
    limit: int | None = None,
) -> list[Path]:
    """Import emails from Maildir to mdmail format.

    Args:
        maildir_root: Path to Maildir root (e.g., ~/mail)
        output_dir: Where to write .md files (e.g., ~/.mdmail/inbox)
        account: Account name to set in headers (auto-detected from path if None)
        limit: Max number of emails to import (None for all)

    Returns:
        List of created file paths
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    email_files = find_maildir_emails(maildir_root)
    if limit:
        email_files = email_files[:limit]

    existing_names: set[str] = {f.name for f in output_dir.iterdir() if f.is_file()}
    created: list[Path] = []

    for email_path in email_files:
        try:
            imported = parse_rfc822(email_path)
            email = imported.email

            # Auto-detect account from path
            detected_account = account
            if not detected_account:
                # Try to extract from path like ~/mail/gmail-hhartmann1729/INBOX/cur/...
                parts = email_path.parts
                for i, part in enumerate(parts):
                    if part == 'mail' and i + 1 < len(parts):
                        detected_account = parts[i + 1]
                        break

            email.account = detected_account

            # Parse date for filename
            date = None
            if email.date:
                try:
                    date = datetime.fromisoformat(email.date)
                except ValueError:
                    pass

            filename = generate_filename(
                date=date,
                from_addr=email.from_addr,
                subject=email.subject,
                message_id=email.message_id,
                existing_names=existing_names,
            )

            existing_names.add(filename)
            output_path = output_dir / filename

            email.save(output_path)
            created.append(output_path)

        except Exception as e:
            # Skip problematic emails, continue with others
            print(f"Warning: Failed to import {email_path}: {e}")
            continue

    return created
