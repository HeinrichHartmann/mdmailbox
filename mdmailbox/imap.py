"""IMAP client for uploading sent emails to server."""

import imaplib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .authinfo import Credential, find_credential_by_email


@dataclass
class IMAPUploadResult:
    """Result of uploading email via IMAP."""

    success: bool
    message: str
    imap_host: str | None = None
    imap_port: int = 993
    folder: str | None = None
    uid: str | None = None
    log: list[str] = None

    def __post_init__(self):
        if self.log is None:
            self.log = []


def convert_smtp_to_imap(smtp_host: str) -> str:
    """Convert SMTP hostname to IMAP hostname.

    Examples:
        smtp.gmail.com -> imap.gmail.com
        smtp.migadu.com -> imap.migadu.com
    """
    return smtp_host.replace("smtp.", "imap.")


def find_imap_credential(
    email_address: str,
    smtp_host: str,
    authinfo_path: Path | None = None,
) -> Credential | None:
    """Find IMAP credentials by converting SMTP host to IMAP host.

    Args:
        email_address: Email address to look up
        smtp_host: SMTP hostname (will be converted to IMAP)
        authinfo_path: Path to .authinfo file

    Returns:
        Credential object if found, None otherwise
    """
    imap_host = convert_smtp_to_imap(smtp_host)
    return find_credential_by_email(email_address, authinfo_path, machine=imap_host)


def upload_to_sent_folder(
    email_mime: str,
    imap_credential: Credential,
    sent_folder: str = "Sent",
    port: int = 993,
) -> IMAPUploadResult:
    """Upload email to IMAP sent folder via APPEND command.

    Args:
        email_mime: Full RFC822 email message as string
        imap_credential: IMAP credentials (machine, login, password)
        sent_folder: IMAP folder name (default: "Sent")
        port: IMAP port (default: 993 for SSL)

    Returns:
        IMAPUploadResult with success status and details
    """
    log: list[str] = []

    def log_msg(msg: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        log.append(f"[{timestamp}] {msg}")

    try:
        log_msg(f"Connecting to {imap_credential.machine}:{port}")

        # Connect to IMAP server with SSL
        imap = imaplib.IMAP4_SSL(imap_credential.machine, port)
        log_msg(f"Connected to {imap_credential.machine}")

        # Login
        log_msg(f"Logging in as {imap_credential.login}")
        imap.login(imap_credential.login, imap_credential.password)
        log_msg("Logged in successfully")

        # Select sent folder
        log_msg(f"Selecting folder '{sent_folder}'")
        status, count = imap.select(sent_folder)
        if status != "OK":
            log_msg(f"ERROR: Failed to select folder '{sent_folder}'")
            imap.logout()
            return IMAPUploadResult(
                success=False,
                message=f"Failed to select folder '{sent_folder}'",
                imap_host=imap_credential.machine,
                folder=sent_folder,
                log=log,
            )
        log_msg(f"Selected folder '{sent_folder}' ({count[0].decode()} messages)")

        # Append email to folder
        log_msg(f"Appending email to '{sent_folder}'")
        status, response = imap.append(
            sent_folder, None, None, email_mime.encode("utf-8")
        )

        if status != "OK":
            log_msg("ERROR: Failed to append email")
            imap.logout()
            return IMAPUploadResult(
                success=False,
                message=f"Failed to append email to '{sent_folder}'",
                imap_host=imap_credential.machine,
                folder=sent_folder,
                log=log,
            )

        # Extract UID from response
        uid = None
        if response:
            response_str = response[0].decode()
            log_msg(f"Server response: {response_str}")
            # Response format: [APPENDUID 123456789 1] Append completed...
            if "[APPENDUID" in response_str:
                parts = response_str.split()
                if len(parts) >= 3:
                    uid = parts[2]

        log_msg("Email appended successfully")

        # Logout
        imap.logout()
        log_msg("Logged out")

        return IMAPUploadResult(
            success=True,
            message="Email uploaded to sent folder",
            imap_host=imap_credential.machine,
            folder=sent_folder,
            uid=uid,
            log=log,
        )

    except imaplib.IMAP4.error as e:
        log_msg(f"ERROR: IMAP error: {e}")
        return IMAPUploadResult(
            success=False,
            message=f"IMAP error: {e}",
            imap_host=imap_credential.machine,
            folder=sent_folder,
            log=log,
        )
    except Exception as e:
        log_msg(f"ERROR: {type(e).__name__}: {e}")
        return IMAPUploadResult(
            success=False,
            message=f"Error: {e}",
            imap_host=imap_credential.machine,
            folder=sent_folder,
            log=log,
        )
