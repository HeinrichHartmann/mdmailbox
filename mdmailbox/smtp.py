"""SMTP client for sending emails."""

import smtplib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .authinfo import Credential, find_credential_by_email
from .email import Email


@dataclass
class SendResult:
    """Result of sending an email."""

    success: bool
    message: str
    message_id: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_response: str | None = None
    sent_at: datetime | None = None
    log: list[str] = field(default_factory=list)


def send_email(
    email: Email,
    credential: Credential | None = None,
    authinfo_path: Path | None = None,
    port: int = 587,
    use_tls: bool = True,
) -> SendResult:
    """Send an email via SMTP.

    Args:
        email: The Email object to send
        credential: SMTP credential. If None, looks up by email.from_addr in .authinfo
        authinfo_path: Path to .authinfo file (uses default if None)
        port: SMTP port (default 587 for submission with STARTTLS)
        use_tls: Whether to use STARTTLS (default True)

    Returns:
        SendResult with success status, message, and audit log
    """
    log: list[str] = []

    def log_msg(msg: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        log.append(f"[{timestamp}] {msg}")

    # Look up credential if not provided
    if credential is None:
        email_to_lookup = email.from_email  # Extract plain email address
        log_msg(f"Looking up credentials for {email_to_lookup}")
        credential = find_credential_by_email(email_to_lookup, authinfo_path)
        if credential is None:
            log_msg(f"ERROR: No credentials found for {email_to_lookup}")
            return SendResult(
                success=False,
                message=f"No credentials found for {email_to_lookup} in .authinfo",
                log=log,
            )
        log_msg(f"Found credentials: {credential.login} via {credential.machine}")

    # Convert to MIME message
    log_msg("Converting to MIME message")
    mime_msg = email.to_mime()

    # Collect all recipients
    recipients = list(email.to)
    recipients.extend(email.cc)
    recipients.extend(email.bcc)
    log_msg(f"Recipients: {', '.join(recipients)}")

    sent_at = datetime.now().astimezone()
    smtp_response = None

    try:
        log_msg(f"Connecting to {credential.machine}:{port}")
        with smtplib.SMTP(credential.machine, port) as server:
            server.ehlo()
            log_msg("EHLO sent")

            if use_tls:
                server.starttls()
                server.ehlo()  # Re-identify after STARTTLS
                log_msg("STARTTLS established")

            # Only login if server supports AUTH
            if server.has_extn("auth"):
                server.login(credential.login, credential.password)
                log_msg(f"Authenticated as {credential.login}")
            else:
                log_msg("Server does not require authentication")

            log_msg(f"Sending message to {len(recipients)} recipient(s)")
            send_errors = server.send_message(mime_msg, to_addrs=recipients)

            # send_message returns {} on success, dict of failed recipients on partial failure
            if send_errors:
                smtp_response = f"Partial failure: {send_errors}"
            else:
                smtp_response = "250 OK"
            log_msg(f"Server response: {smtp_response}")
            log_msg(f"Message-ID: {mime_msg['Message-ID']}")

            if send_errors:
                # send_errors contains failed recipients
                log_msg(f"WARNING: Some recipients failed: {send_errors}")

        return SendResult(
            success=True,
            message="Email sent successfully",
            message_id=mime_msg["Message-ID"],
            smtp_host=credential.machine,
            smtp_port=port,
            smtp_response=smtp_response,
            sent_at=sent_at,
            log=log,
        )

    except smtplib.SMTPAuthenticationError as e:
        log_msg(f"ERROR: Authentication failed: {e}")
        return SendResult(
            success=False,
            message=f"Authentication failed: {e}",
            smtp_host=credential.machine,
            smtp_port=port,
            sent_at=sent_at,
            log=log,
        )
    except smtplib.SMTPException as e:
        log_msg(f"ERROR: SMTP error: {e}")
        return SendResult(
            success=False,
            message=f"SMTP error: {e}",
            smtp_host=credential.machine,
            smtp_port=port,
            sent_at=sent_at,
            log=log,
        )
    except Exception as e:
        log_msg(f"ERROR: Failed to send: {e}")
        return SendResult(
            success=False,
            message=f"Failed to send: {e}",
            smtp_host=credential.machine if credential else None,
            smtp_port=port,
            sent_at=sent_at,
            log=log,
        )
