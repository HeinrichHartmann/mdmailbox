"""SMTP client for sending emails."""

import smtplib
from dataclasses import dataclass
from pathlib import Path

from .authinfo import Credential, find_credential_by_email
from .email import Email


@dataclass
class SendResult:
    """Result of sending an email."""
    success: bool
    message: str
    message_id: str | None = None


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
        SendResult with success status and message
    """
    # Look up credential if not provided
    if credential is None:
        credential = find_credential_by_email(email.from_addr, authinfo_path)
        if credential is None:
            return SendResult(
                success=False,
                message=f"No credentials found for {email.from_addr} in .authinfo",
            )

    # Convert to MIME message
    mime_msg = email.to_mime()

    # Collect all recipients
    recipients = list(email.to)
    recipients.extend(email.cc)
    recipients.extend(email.bcc)

    try:
        with smtplib.SMTP(credential.machine, port) as server:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()  # Re-identify after STARTTLS
            # Only login if server supports AUTH
            if server.has_extn("auth"):
                server.login(credential.login, credential.password)
            server.send_message(mime_msg, to_addrs=recipients)

        return SendResult(
            success=True,
            message="Email sent successfully",
            message_id=mime_msg["Message-ID"],
        )

    except smtplib.SMTPAuthenticationError as e:
        return SendResult(
            success=False,
            message=f"Authentication failed: {e}",
        )
    except smtplib.SMTPException as e:
        return SendResult(
            success=False,
            message=f"SMTP error: {e}",
        )
    except Exception as e:
        return SendResult(
            success=False,
            message=f"Failed to send: {e}",
        )
