"""Integration tests for mdmail using smtpdfix."""

import tempfile
from pathlib import Path

import pytest

from mdmail.authinfo import parse_authinfo, find_credential_by_email, Credential
from mdmail.email import Email
from mdmail.smtp import send_email


class TestAuthinfo:
    """Tests for .authinfo parsing."""

    def test_parse_single_entry(self, tmp_path):
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.example.com login user@example.com password secret123\n"
        )

        creds = parse_authinfo(authinfo)

        assert len(creds) == 1
        assert creds[0].machine == "smtp.example.com"
        assert creds[0].login == "user@example.com"
        assert creds[0].password == "secret123"

    def test_parse_multiple_entries(self, tmp_path):
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.gmail.com login alice@gmail.com password pass1\n"
            "machine smtp.migadu.com login bob@migadu.com password pass2\n"
        )

        creds = parse_authinfo(authinfo)

        assert len(creds) == 2
        assert creds[0].login == "alice@gmail.com"
        assert creds[1].login == "bob@migadu.com"

    def test_parse_with_comments(self, tmp_path):
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "# Gmail account\n"
            "machine smtp.gmail.com login user@gmail.com password secret\n"
            "# Work account\n"
        )

        creds = parse_authinfo(authinfo)

        assert len(creds) == 1

    def test_find_credential_by_email(self, tmp_path):
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.gmail.com login alice@gmail.com password alicepass\n"
            "machine smtp.migadu.com login bob@migadu.com password bobpass\n"
        )

        cred = find_credential_by_email("bob@migadu.com", authinfo)

        assert cred is not None
        assert cred.machine == "smtp.migadu.com"
        assert cred.password == "bobpass"

    def test_find_credential_not_found(self, tmp_path):
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.gmail.com login alice@gmail.com password alicepass\n"
        )

        cred = find_credential_by_email("unknown@example.com", authinfo)

        assert cred is None


class TestEmailParsing:
    """Tests for Email YAML frontmatter parsing."""

    def test_parse_minimal_email(self):
        text = """---
from: sender@example.com
to: recipient@example.com
subject: Test Subject
---

This is the body.
"""
        email = Email.from_string(text)

        assert email.from_addr == "sender@example.com"
        assert email.to == ["recipient@example.com"]
        assert email.subject == "Test Subject"
        assert email.body == "This is the body."

    def test_parse_multiple_recipients(self):
        text = """---
from: sender@example.com
to:
  - alice@example.com
  - bob@example.com
cc: charlie@example.com
subject: Group email
---

Hello everyone.
"""
        email = Email.from_string(text)

        assert email.to == ["alice@example.com", "bob@example.com"]
        assert email.cc == ["charlie@example.com"]

    def test_parse_from_file(self, tmp_path):
        email_file = tmp_path / "test.md"
        email_file.write_text("""---
from: me@example.com
to: you@example.com
subject: File test
---

Body from file.
""")

        email = Email.from_file(email_file)

        assert email.from_addr == "me@example.com"
        assert email.source_path == email_file

    def test_to_mime_conversion(self):
        text = """---
from: sender@example.com
to: recipient@example.com
subject: MIME Test
---

Plain text body.
"""
        email = Email.from_string(text)
        mime = email.to_mime()

        assert mime["From"] == "sender@example.com"
        assert mime["To"] == "recipient@example.com"
        assert mime["Subject"] == "MIME Test"
        assert "Message-ID" in mime
        assert "Date" in mime

    def test_roundtrip(self):
        original = """---
from: sender@example.com
to: recipient@example.com
subject: Roundtrip Test
---

Body content here.
"""
        email = Email.from_string(original)
        serialized = email.to_string()
        reparsed = Email.from_string(serialized)

        assert reparsed.from_addr == email.from_addr
        assert reparsed.to == email.to
        assert reparsed.subject == email.subject
        assert reparsed.body == email.body


class TestSMTPIntegration:
    """Integration tests using smtpdfix local SMTP server."""

    def test_send_simple_email(self, smtpd):
        """Send a simple email and verify it's received."""
        email = Email.from_string("""---
from: sender@example.com
to: recipient@example.com
subject: Integration Test
---

This email was sent via smtpdfix.
""")

        # Create a fake credential pointing to the test server
        credential = Credential(
            machine=smtpd.hostname,
            login="sender@example.com",
            password="testpass",
        )

        result = send_email(
            email,
            credential=credential,
            port=smtpd.port,
            use_tls=False,  # smtpdfix doesn't use TLS by default
        )

        assert result.success, f"Send failed: {result.message}"
        assert result.message_id is not None

        # Verify message was received
        assert len(smtpd.messages) == 1
        msg = smtpd.messages[0]
        assert msg["Subject"] == "Integration Test"
        assert msg["From"] == "sender@example.com"
        assert msg["To"] == "recipient@example.com"

    def test_send_to_multiple_recipients(self, smtpd):
        """Send to multiple recipients."""
        email = Email.from_string("""---
from: sender@example.com
to:
  - alice@example.com
  - bob@example.com
cc: charlie@example.com
subject: Multi-recipient Test
---

Hello everyone.
""")

        credential = Credential(
            machine=smtpd.hostname,
            login="sender@example.com",
            password="testpass",
        )

        result = send_email(
            email,
            credential=credential,
            port=smtpd.port,
            use_tls=False,
        )

        assert result.success
        assert len(smtpd.messages) == 1

        msg = smtpd.messages[0]
        assert "alice@example.com" in msg["To"]
        assert "bob@example.com" in msg["To"]
        assert msg["Cc"] == "charlie@example.com"

    def test_send_with_authinfo_lookup(self, smtpd, tmp_path):
        """Test credential lookup from .authinfo file."""
        # Create authinfo pointing to test server
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            f"machine {smtpd.hostname} login testuser@example.com password testpass\n"
        )

        email = Email.from_string("""---
from: testuser@example.com
to: recipient@example.com
subject: Authinfo Lookup Test
---

Testing credential auto-discovery.
""")

        result = send_email(
            email,
            authinfo_path=authinfo,
            port=smtpd.port,
            use_tls=False,
        )

        assert result.success
        assert len(smtpd.messages) == 1

    def test_send_fails_without_credentials(self, tmp_path):
        """Test that send fails gracefully when no credentials found."""
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text("")  # Empty authinfo

        email = Email.from_string("""---
from: unknown@example.com
to: recipient@example.com
subject: Should Fail
---

This should not be sent.
""")

        result = send_email(email, authinfo_path=authinfo)

        assert not result.success
        assert "No credentials found" in result.message
