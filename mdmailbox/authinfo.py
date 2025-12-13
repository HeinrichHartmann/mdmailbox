"""Parse .authinfo / .netrc files for email credentials."""

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass
class Credential:
    """SMTP credential entry."""
    machine: str  # SMTP host
    login: str    # username (usually email address)
    password: str


def normalize_gmail(email: str) -> str:
    """Normalize Gmail address for matching.

    Gmail ignores dots and everything after + in the local part.
    e.g., h.hartmann+news@gmail.com -> hhartmann@gmail.com
    """
    if "@" not in email:
        return email

    local, domain = email.rsplit("@", 1)

    # Only normalize gmail addresses
    if domain.lower() not in ("gmail.com", "googlemail.com"):
        return email.lower()

    # Remove everything after +
    if "+" in local:
        local = local.split("+")[0]

    # Remove dots
    local = local.replace(".", "")

    return f"{local}@{domain}".lower()


def parse_authinfo(path: Path) -> list[Credential]:
    """Parse .authinfo file into list of credentials.

    Format: machine <host> login <user> password <pass>
    One entry per line. Lines starting with # are comments.
    """
    credentials = []
    text = path.read_text()

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        entry = {}

        # Parse key-value pairs
        i = 0
        while i < len(parts) - 1:
            key = parts[i]
            if key in ("machine", "login", "password", "port"):
                entry[key] = parts[i + 1]
                i += 2
            else:
                i += 1

        if "machine" in entry and "login" in entry and "password" in entry:
            credentials.append(Credential(
                machine=entry["machine"],
                login=entry["login"],
                password=entry["password"],
            ))

    return credentials


def matches_wildcard(pattern: str, email: str) -> bool:
    """Check if email matches a wildcard pattern like *@domain.com."""
    if not pattern.startswith("*@"):
        return False

    if "@" not in email:
        return False

    pattern_domain = pattern[2:].lower()  # strip "*@"
    email_domain = email.rsplit("@", 1)[1].lower()

    return pattern_domain == email_domain


def find_credential_by_email(
    email: str, path: Path | None = None, machine: str | None = None
) -> Credential | None:
    """Find credential for a given email address.

    Lookup order:
    1. Exact match (with optional machine filter)
    2. Gmail normalized match (dots and +suffix ignored)
    3. Wildcard domain match (*@domain.com)

    Args:
        email: The email address to find credentials for
        path: Path to .authinfo file. Defaults to ~/.authinfo or $AUTHINFO_FILE
        machine: Optional machine/server hostname to filter by (e.g., "imap.gmail.com")

    Returns:
        Credential if found, None otherwise
    """
    if path is None:
        if env_path := os.environ.get("AUTHINFO_FILE"):
            path = Path(env_path).expanduser()
        else:
            path = Path.home() / ".authinfo"

    if not path.exists():
        return None

    credentials = parse_authinfo(path)
    normalized_email = normalize_gmail(email)

    # Filter by machine if provided
    if machine:
        credentials = [c for c in credentials if c.machine == machine]

    # First try exact match
    for cred in credentials:
        if cred.login == email:
            return cred

    # Then try normalized match (for Gmail)
    for cred in credentials:
        if normalize_gmail(cred.login) == normalized_email:
            return cred

    # Then try wildcard domain match (*@domain.com)
    for cred in credentials:
        if matches_wildcard(cred.login, email):
            return cred

    return None
