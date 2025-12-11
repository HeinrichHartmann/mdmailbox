"""Email class - parse and serialize YAML frontmatter emails."""

from dataclasses import dataclass, field
from pathlib import Path
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
import yaml


@dataclass
class Email:
    """An email with YAML frontmatter headers and body content."""

    from_addr: str
    to: list[str]
    subject: str
    body: str

    # Optional fields
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    reply_to: str | None = None
    message_id: str | None = None
    date: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)

    # Import metadata
    account: str | None = None          # Source account (e.g., "gmail-hhartmann1729")
    original_hash: str | None = None    # SHA256 of original RFC822 file (for dedup)

    # Source file path (if loaded from file)
    source_path: Path | None = None

    @property
    def from_email(self) -> str:
        """Extract just the email address from from_addr (handles display names)."""
        display_name, email_addr = parseaddr(self.from_addr)
        return email_addr if email_addr else self.from_addr

    @classmethod
    def from_file(cls, path: Path | str) -> "Email":
        """Load email from a file with YAML frontmatter."""
        path = Path(path)
        text = path.read_text()
        email = cls.from_string(text)
        email.source_path = path
        return email

    @classmethod
    def from_string(cls, text: str) -> "Email":
        """Parse email from string with YAML frontmatter."""
        if not text.startswith("---"):
            raise ValueError("Email must start with YAML frontmatter (---)")

        # Split frontmatter and body
        parts = text.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Invalid frontmatter format")

        frontmatter = parts[1].strip()
        body = parts[2].strip()

        headers = yaml.safe_load(frontmatter)
        if not headers:
            headers = {}

        # Normalize 'to' to list
        to = headers.get("to", [])
        if isinstance(to, str):
            to = [to]

        # Normalize 'cc' to list
        cc = headers.get("cc", [])
        if isinstance(cc, str):
            cc = [cc]

        # Normalize 'bcc' to list
        bcc = headers.get("bcc", [])
        if isinstance(bcc, str):
            bcc = [bcc]

        # Normalize 'references' to list
        references = headers.get("references", [])
        if isinstance(references, str):
            references = [references]

        # Normalize 'attachments' to list
        attachments = headers.get("attachments", [])
        if isinstance(attachments, str):
            attachments = [attachments]

        return cls(
            from_addr=headers.get("from", ""),
            to=to,
            subject=headers.get("subject", ""),
            body=body,
            cc=cc,
            bcc=bcc,
            reply_to=headers.get("reply-to"),
            message_id=headers.get("message-id"),
            date=headers.get("date"),
            in_reply_to=headers.get("in-reply-to"),
            references=references,
            attachments=attachments,
            account=headers.get("account"),
            original_hash=headers.get("original-hash"),
        )

    def to_mime(self) -> EmailMessage:
        """Convert to stdlib EmailMessage for sending."""
        import mimetypes

        msg = EmailMessage()

        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to)
        msg["Subject"] = self.subject

        if self.cc:
            msg["Cc"] = ", ".join(self.cc)

        if self.reply_to:
            msg["Reply-To"] = self.reply_to

        if self.in_reply_to:
            msg["In-Reply-To"] = self.in_reply_to

        if self.references:
            msg["References"] = " ".join(self.references)

        # Generate message-id if not present
        msg["Message-ID"] = self.message_id or make_msgid()

        # Use current date if not specified
        msg["Date"] = self.date or formatdate(localtime=True)

        # Set body text
        msg.set_content(self.body)

        # Add attachments if present
        if self.attachments:
            for attachment_path_str in self.attachments:
                # Resolve path (expanduser for ~)
                attachment_path = Path(attachment_path_str).expanduser()

                # Read file
                content = attachment_path.read_bytes()

                # Guess MIME type
                mime_type, _ = mimetypes.guess_type(str(attachment_path))
                if mime_type:
                    maintype, subtype = mime_type.split('/', 1)
                else:
                    maintype, subtype = 'application', 'octet-stream'

                # Add as attachment
                msg.add_attachment(
                    content,
                    maintype=maintype,
                    subtype=subtype,
                    filename=attachment_path.name
                )

        return msg

    def to_string(self) -> str:
        """Serialize back to YAML frontmatter format."""
        headers = {
            "from": self.from_addr,
            "to": self.to if len(self.to) > 1 else self.to[0] if self.to else "",
            "subject": self.subject,
        }

        if self.cc:
            headers["cc"] = self.cc if len(self.cc) > 1 else self.cc[0]
        if self.bcc:
            headers["bcc"] = self.bcc if len(self.bcc) > 1 else self.bcc[0]
        if self.reply_to:
            headers["reply-to"] = self.reply_to
        if self.message_id:
            headers["message-id"] = self.message_id
        if self.date:
            headers["date"] = self.date
        if self.in_reply_to:
            headers["in-reply-to"] = self.in_reply_to
        if self.references:
            headers["references"] = self.references
        if self.attachments:
            headers["attachments"] = (
                self.attachments if len(self.attachments) > 1
                else self.attachments[0]
            )
        if self.account:
            headers["account"] = self.account
        if self.original_hash:
            headers["original-hash"] = self.original_hash

        frontmatter = yaml.dump(headers, default_flow_style=False, allow_unicode=True)
        return f"---\n{frontmatter}---\n\n{self.body}\n"

    def save(self, path: Path | str | None = None) -> None:
        """Save email to file."""
        path = Path(path) if path else self.source_path
        if not path:
            raise ValueError("No path specified and no source path set")
        path.write_text(self.to_string())
        self.source_path = path
