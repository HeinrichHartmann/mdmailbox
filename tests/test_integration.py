"""Integration tests for mdmail using smtpdfix."""

from datetime import datetime


from click.testing import CliRunner

from mdmailbox.authinfo import parse_authinfo, find_credential_by_email, Credential
from mdmailbox.cli import main
from mdmailbox.email import Email
from mdmailbox.smtp import send_email
from mdmailbox.importer import (
    sanitize_filename,
    generate_filename,
    parse_rfc822,
    import_maildir,
)


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

    def test_find_credential_gmail_normalized(self, tmp_path):
        """Test Gmail address normalization (dots and +suffix ignored)."""
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.gmail.com login hhartmann1729@gmail.com password secret\n"
        )

        # With dots
        cred = find_credential_by_email("h.hartmann.1729@gmail.com", authinfo)
        assert cred is not None
        assert cred.password == "secret"

        # With +suffix
        cred = find_credential_by_email("hhartmann1729+news@gmail.com", authinfo)
        assert cred is not None

        # With both
        cred = find_credential_by_email("h.hartmann.1729+test@gmail.com", authinfo)
        assert cred is not None

        # Non-gmail should NOT normalize
        authinfo.write_text(
            "machine smtp.example.com login user@example.com password pass\n"
        )
        cred = find_credential_by_email("u.ser@example.com", authinfo)
        assert cred is None

    def test_find_credential_wildcard_domain(self, tmp_path):
        """Test wildcard domain matching (*@domain.com)."""
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.migadu.com login *@heinrichhartmann.com password secret\n"
        )

        # Any user at the domain should match
        cred = find_credential_by_email("heinrich@heinrichhartmann.com", authinfo)
        assert cred is not None
        assert cred.password == "secret"
        assert cred.machine == "smtp.migadu.com"

        cred = find_credential_by_email("hello@heinrichhartmann.com", authinfo)
        assert cred is not None

        cred = find_credential_by_email("contact@heinrichhartmann.com", authinfo)
        assert cred is not None

        # Different domain should NOT match
        cred = find_credential_by_email("user@otherdomain.com", authinfo)
        assert cred is None

    def test_find_credential_exact_before_wildcard(self, tmp_path):
        """Test that exact match takes precedence over wildcard."""
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.example.com login specific@example.com password exact\n"
            "machine smtp.example.com login *@example.com password wildcard\n"
        )

        # Exact match should win
        cred = find_credential_by_email("specific@example.com", authinfo)
        assert cred.password == "exact"

        # Other addresses use wildcard
        cred = find_credential_by_email("other@example.com", authinfo)
        assert cred.password == "wildcard"


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


class TestImporter:
    """Tests for Maildir import functionality."""

    def test_sanitize_filename_basic(self):
        """Test basic filename sanitization."""
        assert sanitize_filename("Hello World") == "hello-world"
        assert sanitize_filename("Test@Email.com") == "test-email-com"
        assert sanitize_filename("Re: Meeting Notes!!!") == "re-meeting-notes"

    def test_sanitize_filename_truncation(self):
        """Test filename truncation."""
        long_text = "a" * 100
        result = sanitize_filename(long_text, max_len=40)
        assert len(result) <= 40

    def test_sanitize_filename_empty(self):
        """Test empty input."""
        assert sanitize_filename("") == "unknown"
        assert sanitize_filename("!!!") == "unknown"

    def test_generate_filename_basic(self):
        """Test basic filename generation."""
        date = datetime(2025, 1, 23, 10, 30)
        filename = generate_filename(
            date=date,
            from_addr="sender@example.com",
            subject="Test Subject",
        )
        assert filename == "2025-01-23-sender-test-subject.md"

    def test_generate_filename_no_date(self):
        """Test filename generation without date."""
        filename = generate_filename(
            date=None,
            from_addr="sender@example.com",
            subject="Test",
        )
        assert filename.startswith("0000-00-00-")

    def test_generate_filename_collision(self):
        """Test filename deduplication."""
        date = datetime(2025, 1, 23)
        existing = {"2025-01-23-sender-test.md"}

        filename = generate_filename(
            date=date,
            from_addr="sender@example.com",
            subject="Test",
            message_id="<unique123@example.com>",
            existing_names=existing,
        )

        assert filename != "2025-01-23-sender-test.md"
        assert filename.endswith(".md")
        assert "2025-01-23-sender-test-" in filename

    def test_parse_rfc822(self, tmp_path):
        """Test parsing RFC822 email file."""
        email_file = tmp_path / "test.eml"
        email_file.write_bytes(b"""From: sender@example.com
To: recipient@example.com
Subject: Test Email
Message-ID: <test123@example.com>
Date: Thu, 23 Jan 2025 10:30:00 +0000

This is the body.
""")

        imported = parse_rfc822(email_file)

        assert imported.email.from_addr == "sender@example.com"
        assert imported.email.to == ["recipient@example.com"]
        assert imported.email.subject == "Test Email"
        assert imported.email.message_id == "<test123@example.com>"
        assert "This is the body" in imported.email.body
        assert imported.original_hash is not None
        assert len(imported.original_hash) == 64  # SHA256 hex

    def test_import_maildir(self, tmp_path):
        """Test importing from Maildir structure."""
        # Create Maildir structure
        maildir = tmp_path / "mail"
        account_dir = maildir / "test-account" / "INBOX" / "cur"
        account_dir.mkdir(parents=True)

        # Create test email
        email_file = account_dir / "1234567890.test:2,S"
        email_file.write_bytes(b"""From: alice@example.com
To: bob@example.com
Subject: Hello Bob
Message-ID: <hello123@example.com>
Date: Wed, 22 Jan 2025 15:00:00 +0000

Hi Bob, how are you?
""")

        # Import
        output_dir = tmp_path / "output"
        created = import_maildir(maildir, output_dir)

        assert len(created) == 1
        assert created[0].exists()

        # Verify content
        email = Email.from_file(created[0])
        assert email.from_addr == "alice@example.com"
        assert email.subject == "Hello Bob"
        assert email.account == "test-account"
        assert email.original_hash is not None


class TestCLI:
    """Tests for CLI entry points."""

    def test_cli_entry_point_loads(self):
        """Test that the CLI entry point can be invoked."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "mdmailbox" in result.output

    def test_cli_version(self):
        """Test that --version works."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0

    def test_cli_send_dry_run(self, tmp_path):
        """Test send --dry-run command."""
        # Create a test email file
        email_file = tmp_path / "test.md"
        email_file.write_text("""---
from: sender@example.com
to: recipient@example.com
subject: Test Subject
---

Test body.
""")

        runner = CliRunner()
        result = runner.invoke(main, ["send", "--dry-run", str(email_file)])
        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "sender@example.com" in result.output

    def test_cli_new_command(self, tmp_path):
        """Test new command creates draft."""
        runner = CliRunner()
        output_file = tmp_path / "draft.md"
        result = runner.invoke(
            main,
            [
                "new",
                "--to",
                "test@example.com",
                "--subject",
                "Test Draft",
                "-o",
                str(output_file),
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()

        # Verify content
        email = Email.from_file(output_file)
        assert email.to == ["test@example.com"]
        assert email.subject == "Test Draft"

    def test_cli_credentials_no_file(self, tmp_path):
        """Test credentials command with missing file."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["credentials", "--authinfo", str(tmp_path / "nonexistent")]
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()
