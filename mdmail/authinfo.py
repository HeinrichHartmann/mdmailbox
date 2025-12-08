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


def find_credential_by_email(email: str, path: Path | None = None) -> Credential | None:
    """Find SMTP credential for a given email address.

    Looks up by matching the login field to the email address.

    Args:
        email: The email address to find credentials for
        path: Path to .authinfo file. Defaults to ~/.authinfo or $AUTHINFO_FILE

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

    for cred in credentials:
        if cred.login == email:
            return cred

    return None
