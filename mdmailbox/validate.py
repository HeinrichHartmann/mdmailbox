"""Email validation for safe sending."""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from email.utils import parseaddr


class ValidationLevel(Enum):
    """Severity level of validation result."""

    OK = "ok"  # ✓
    WARNING = "warning"  # ○
    ERROR = "error"  # ✗


@dataclass
class ValidationItem:
    """Single validation result for a field or check."""

    level: ValidationLevel
    field: str
    value: str | None
    message: str

    @property
    def symbol(self) -> str:
        """Emoji symbol for this level."""
        return {"ok": "✓", "warning": "○", "error": "✗"}[self.level.value]


@dataclass
class ValidationResult:
    """Complete validation result for an email."""

    items: list[ValidationItem] = field(default_factory=list)

    def add(
        self, level: ValidationLevel, field: str, value: str | None, message: str
    ) -> None:
        self.items.append(ValidationItem(level, field, value, message))

    def ok(self, field: str, value: str | None, message: str) -> None:
        self.add(ValidationLevel.OK, field, value, message)

    def warning(self, field: str, value: str | None, message: str) -> None:
        self.add(ValidationLevel.WARNING, field, value, message)

    def error(self, field: str, value: str | None, message: str) -> None:
        self.add(ValidationLevel.ERROR, field, value, message)

    @property
    def has_errors(self) -> bool:
        return any(item.level == ValidationLevel.ERROR for item in self.items)

    @property
    def has_warnings(self) -> bool:
        return any(item.level == ValidationLevel.WARNING for item in self.items)

    @property
    def errors(self) -> list[ValidationItem]:
        return [i for i in self.items if i.level == ValidationLevel.ERROR]

    @property
    def warnings(self) -> list[ValidationItem]:
        return [i for i in self.items if i.level == ValidationLevel.WARNING]

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        return {
            "has_errors": self.has_errors,
            "has_warnings": self.has_warnings,
            "items": [
                {
                    "level": item.level.value,
                    "field": item.field,
                    "value": item.value,
                    "message": item.message,
                }
                for item in self.items
            ],
        }


@dataclass
class ValidationContext:
    """Context passed to validators with shared resources."""

    authinfo_path: Path | None = None
    # Future: mu integration for address book / message-id lookup


class HeaderValidator:
    """Base class for header validators."""

    required: bool = False

    def __init__(self, required: bool = False):
        self.required = required

    def validate(
        self, field: str, value: Any, ctx: ValidationContext, result: ValidationResult
    ) -> None:
        """Validate the field value, adding results to result."""
        raise NotImplementedError


# Email format regex (simplified)
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email_str: str) -> bool:
    """Check if string is a valid email format.

    Supports both plain addresses (user@example.com) and
    addresses with display names (Display Name <user@example.com>).
    """
    # Extract email address from potential display name format
    display_name, email_addr = parseaddr(email_str.strip())

    # If parseaddr found an email address in angle brackets, use that
    if email_addr:
        return bool(EMAIL_REGEX.match(email_addr))

    # Otherwise validate the original string as plain email
    return bool(EMAIL_REGEX.match(email_str.strip()))


class FromValidator(HeaderValidator):
    """Validates from address: email format + credentials lookup."""

    required = True

    def validate(self, field, value, ctx, result):
        if not value:
            result.error(field, None, "required")
            return

        if not is_valid_email(value):
            result.error(field, value, "invalid email format")
            return

        # Extract email address (handles display name format)
        display_name, email_addr = parseaddr(value.strip())
        lookup_email = email_addr if email_addr else value

        # Check credentials
        from .authinfo import find_credential_by_email

        cred = find_credential_by_email(lookup_email, ctx.authinfo_path)
        if cred:
            result.ok(field, value, f"credentials found ({cred.machine})")
        else:
            result.error(field, value, "no credentials found")


class RecipientsValidator(HeaderValidator):
    """Validates to/cc/bcc: email format + address book lookup."""

    def validate(self, field, value, ctx, result):
        if not value:
            if self.required:
                result.error(field, None, "required")
            return

        # Normalize to list
        recipients = value if isinstance(value, list) else [value]

        for addr in recipients:
            if not is_valid_email(addr):
                result.error(field, addr, "invalid email format")
            else:
                # TODO: mu address book lookup
                result.ok(field, addr, "valid")


class SubjectValidator(HeaderValidator):
    """Validates subject: non-empty."""

    required = True

    def validate(self, field, value, ctx, result):
        if not value or not value.strip():
            result.error(field, None, "empty")
        else:
            result.ok(field, value, f"{len(value)} chars")


class EmailValidator(HeaderValidator):
    """Validates a single email address field (reply-to)."""

    def validate(self, field, value, ctx, result):
        if not value:
            return  # Optional field

        if not is_valid_email(value):
            result.error(field, value, "invalid email format")
        else:
            result.ok(field, value, "valid")


class MessageIdValidator(HeaderValidator):
    """Validates message-id format and optionally looks up in corpus."""

    def validate(self, field, value, ctx, result):
        if not value:
            return  # Optional field

        # Message-IDs should be in angle brackets
        if not (value.startswith("<") and value.endswith(">")):
            result.warning(field, value, "should be in <angle brackets>")
        else:
            # TODO: mu lookup for in-reply-to
            result.ok(field, value, "valid format")


class ReferencesValidator(HeaderValidator):
    """Validates references: list of message-ids."""

    def validate(self, field, value, ctx, result):
        if not value:
            return

        refs = value if isinstance(value, list) else [value]
        for ref in refs:
            if not (ref.startswith("<") and ref.endswith(">")):
                result.warning(field, ref, "should be in <angle brackets>")
            else:
                result.ok(field, ref, "valid")


class DateValidator(HeaderValidator):
    """Validates date format."""

    def validate(self, field, value, ctx, result):
        if not value:
            return  # Optional, will be set on send

        # Accept ISO format or RFC 2822
        result.ok(field, str(value), "present")


class MetadataValidator(HeaderValidator):
    """Validates mdmailbox metadata fields (account, original-hash)."""

    def validate(self, field, value, ctx, result):
        if value:
            result.ok(field, str(value), "metadata")


class AttachmentsValidator(HeaderValidator):
    """Validates attachments: file existence, size, type."""

    # Size threshold for warnings (10 MB)
    SIZE_WARNING_THRESHOLD = 10 * 1024 * 1024

    def validate(self, field, value, ctx, result):
        if not value:
            return  # Optional field

        import mimetypes
        from pathlib import Path

        # Normalize to list
        attachments = value if isinstance(value, list) else [value]

        total_size = 0

        for attachment_str in attachments:
            # Resolve path
            try:
                path = Path(attachment_str).expanduser()

                # Check if exists
                if not path.exists():
                    result.error(field, attachment_str, "file not found")
                    continue

                # Check if directory
                if path.is_dir():
                    result.error(field, attachment_str, "is a directory")
                    continue

                # Get file info
                try:
                    stat = path.stat()
                    size = stat.st_size
                except PermissionError:
                    result.error(field, attachment_str, "permission denied")
                    continue

                # Check for empty files
                if size == 0:
                    result.error(field, attachment_str, "file is empty (0 bytes)")
                    continue

                total_size += size

                # Format size for display
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"

                # Detect MIME type
                mime_type, _ = mimetypes.guess_type(str(path))
                type_str = mime_type or "unknown type"

                # Warning for large files
                if size > self.SIZE_WARNING_THRESHOLD:
                    result.warning(
                        field,
                        path.name,
                        f"{size_str}, {type_str} - large file",
                    )
                else:
                    result.ok(field, path.name, f"{size_str}, {type_str}")

            except Exception as e:
                result.error(field, attachment_str, f"error: {e}")

        # Add summary for total size
        if total_size > 0:
            if total_size < 1024 * 1024:
                total_str = f"{total_size / 1024:.1f} KB"
            else:
                total_str = f"{total_size / (1024 * 1024):.1f} MB"

            result.ok(field, None, f"total: {total_str}")


# Single source of truth: header name -> validator
HEADER_VALIDATORS: dict[str, HeaderValidator] = {
    "from": FromValidator(required=True),
    "to": RecipientsValidator(required=True),
    "cc": RecipientsValidator(),
    "bcc": RecipientsValidator(),
    "subject": SubjectValidator(required=True),
    "reply-to": EmailValidator(),
    "in-reply-to": MessageIdValidator(),
    "references": ReferencesValidator(),
    "message-id": MessageIdValidator(),
    "date": DateValidator(),
    "account": MetadataValidator(),
    "original-hash": MetadataValidator(),
    "attachments": AttachmentsValidator(),
}


def validate_email_string(
    content: str, ctx: ValidationContext | None = None
) -> ValidationResult:
    """Validate an email from its markdown string content.

    This is the main entry point for validation - takes raw markdown,
    parses it, and validates all fields.
    """
    from .email import Email

    ctx = ctx or ValidationContext()
    result = ValidationResult()

    # Parse the email
    try:
        email = Email.from_string(content)
    except Exception as e:
        result.error("_parse", None, f"failed to parse: {e}")
        return result

    # Get raw headers from YAML for unknown header detection
    import yaml

    parts = content.split("---", 2)
    if len(parts) >= 3:
        raw_headers = yaml.safe_load(parts[1].strip()) or {}
    else:
        raw_headers = {}

    # Check for unknown headers
    for header in raw_headers.keys():
        if header not in HEADER_VALIDATORS:
            result.error(header, str(raw_headers[header]), "unknown header")

    # Run validators for known headers
    header_values = {
        "from": email.from_addr,
        "to": email.to,
        "cc": email.cc,
        "bcc": email.bcc,
        "subject": email.subject,
        "reply-to": email.reply_to,
        "in-reply-to": email.in_reply_to,
        "references": email.references,
        "message-id": email.message_id,
        "date": email.date,
        "account": email.account,
        "original-hash": email.original_hash,
        "attachments": email.attachments,
    }

    for header, validator in HEADER_VALIDATORS.items():
        value = header_values.get(header)
        validator.validate(header, value, ctx, result)

    # Validate body
    if not email.body or not email.body.strip():
        result.error("body", None, "empty")
    else:
        word_count = len(email.body.split())
        result.ok("body", None, f"{word_count} words")

    return result
