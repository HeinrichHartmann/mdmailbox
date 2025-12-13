"""Integration tests for mdmail using smtpdfix."""

from datetime import datetime
from pathlib import Path

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

    def test_parse_display_name_in_from(self):
        """Test that display names in from field are preserved."""
        text = """---
from: John Doe <john@example.com>
to: recipient@example.com
subject: Display Name Test
---

Body here.
"""
        email = Email.from_string(text)

        assert email.from_addr == "John Doe <john@example.com>"
        assert email.to == ["recipient@example.com"]

    def test_from_email_property_extracts_plain_address(self):
        """Test that from_email property extracts plain email from display name."""
        text = """---
from: Alice Smith <alice@example.com>
to: bob@example.com
subject: Test
---

Body.
"""
        email = Email.from_string(text)

        assert email.from_email == "alice@example.com"
        assert email.from_addr == "Alice Smith <alice@example.com>"

    def test_from_email_property_with_plain_address(self):
        """Test that from_email works with plain addresses too."""
        text = """---
from: bob@example.com
to: alice@example.com
subject: Test
---

Body.
"""
        email = Email.from_string(text)

        assert email.from_email == "bob@example.com"
        assert email.from_addr == "bob@example.com"

    def test_roundtrip_preserves_display_name(self):
        """Test that roundtrip load/save preserves display names."""
        original = """---
from: Charlie Brown <charlie@example.com>
to: recipient@example.com
subject: Roundtrip with Display Name
---

Body content.
"""
        email = Email.from_string(original)
        serialized = email.to_string()
        reparsed = Email.from_string(serialized)

        assert reparsed.from_addr == "Charlie Brown <charlie@example.com>"
        assert reparsed.from_email == "charlie@example.com"


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

    def test_send_with_display_name_in_from(self, smtpd, tmp_path):
        """End-to-end test: send email with display name in from field.

        This verifies the complete flow: email with display name ->
        credential lookup via plain email -> SMTP send -> received by server.
        """
        # Create authinfo pointing to test server
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            f"machine {smtpd.hostname} login sender@example.com password testpass\n"
        )

        # Email with display name in from field
        email = Email.from_string("""---
from: John Smith <sender@example.com>
to: recipient@example.com
subject: Test with Display Name
---

This email has a display name in the from field.
""")

        # Send using authinfo lookup - should extract plain email for credential lookup
        result = send_email(
            email,
            authinfo_path=authinfo,
            port=smtpd.port,
            use_tls=False,
        )

        assert result.success, f"Send failed: {result.message}"
        assert result.message_id is not None

        # Verify message was received by SMTP server with full from address
        assert len(smtpd.messages) == 1
        msg = smtpd.messages[0]
        assert msg["Subject"] == "Test with Display Name"
        assert msg["From"] == "John Smith <sender@example.com>"
        assert msg["To"] == "recipient@example.com"


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
        """Test send --dry-run command with validation preview."""
        # Create authinfo for credential validation
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.example.com login sender@example.com password secret\n"
        )

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
        result = runner.invoke(
            main, ["send", "--dry-run", "--authinfo", str(authinfo), str(email_file)]
        )
        assert result.exit_code == 0
        # Should show validation preview with field status
        assert "sender@example.com" in result.output
        assert "recipient@example.com" in result.output
        assert "Test Subject" in result.output
        assert "✓" in result.output  # Should have success markers

    def test_cli_send_dry_run_with_errors(self, tmp_path):
        """Test send --dry-run shows validation errors."""
        # Create email with invalid sender (no credentials)
        email_file = tmp_path / "test.md"
        email_file.write_text("""---
from: unknown@example.com
to: recipient@example.com
subject: Test Subject
---

Test body.
""")

        runner = CliRunner()
        result = runner.invoke(main, ["send", "--dry-run", str(email_file)])
        assert result.exit_code == 1
        assert "✗" in result.output  # Should have error marker
        assert "no credentials found" in result.output

    def test_cli_send_force_skips_validation(self, smtpd, tmp_path, monkeypatch):
        """Test --force flag skips validation and sends directly."""
        # Create fake home for sent folder
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # Create authinfo pointing to test server
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            f"machine {smtpd.hostname} login sender@example.com password testpass\n"
        )

        email_file = tmp_path / "test.md"
        email_file.write_text("""---
from: sender@example.com
to: recipient@example.com
subject: Force Send Test
---

Sent with --force.
""")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "send",
                "--force",
                "--authinfo",
                str(authinfo),
                "--port",
                str(smtpd.port),
                "--no-tls",
                str(email_file),
            ],
        )

        # Should skip validation warning to stderr
        assert "Skipping validation" in result.output or result.exit_code == 0, (
            f"output: {result.output}"
        )
        # Should have sent
        assert len(smtpd.messages) == 1

    def test_cli_send_yes_autoconfirms(self, smtpd, tmp_path, monkeypatch):
        """Test --yes flag auto-confirms after validation."""
        # Create fake home for sent folder
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # Create authinfo pointing to test server
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            f"machine {smtpd.hostname} login sender@example.com password testpass\n"
        )

        email_file = tmp_path / "test.md"
        email_file.write_text("""---
from: sender@example.com
to: recipient@example.com
subject: Yes Flag Test
---

Sent with --yes.
""")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "send",
                "--yes",
                "--authinfo",
                str(authinfo),
                "--port",
                str(smtpd.port),
                "--no-tls",
                str(email_file),
            ],
        )

        assert result.exit_code == 0, f"output: {result.output}"
        # Should show validation preview
        assert "sender@example.com" in result.output
        assert "✓" in result.output
        # Should have sent without prompting
        assert len(smtpd.messages) == 1

    def test_cli_send_yes_fails_on_errors(self, tmp_path):
        """Test --yes flag still fails on validation errors."""
        email_file = tmp_path / "test.md"
        email_file.write_text("""---
from: unknown@example.com
to: recipient@example.com
subject: Should Fail
---

Should not be sent.
""")

        runner = CliRunner()
        result = runner.invoke(main, ["send", "--yes", str(email_file)])

        assert result.exit_code == 1
        assert "✗" in result.output
        assert "Cannot send" in result.output

    def test_cli_send_unknown_header_error(self, tmp_path):
        """Test that unknown headers are flagged as errors."""
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.example.com login sender@example.com password secret\n"
        )

        email_file = tmp_path / "test.md"
        email_file.write_text("""---
from: sender@example.com
to: recipient@example.com
subject: Test
x-custom-header: should error
---

Body.
""")

        runner = CliRunner()
        result = runner.invoke(
            main, ["send", "--dry-run", "--authinfo", str(authinfo), str(email_file)]
        )
        assert result.exit_code == 1
        assert "unknown header" in result.output.lower()

    def test_cli_send_prompt_cancelled(self, tmp_path):
        """Test that answering 'n' to confirmation cancels send."""
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.example.com login sender@example.com password secret\n"
        )

        email_file = tmp_path / "test.md"
        email_file.write_text("""---
from: sender@example.com
to: recipient@example.com
subject: Test
---

Body.
""")

        runner = CliRunner()
        # Simulate user typing 'n' to cancel
        result = runner.invoke(
            main, ["send", "--authinfo", str(authinfo), str(email_file)], input="n\n"
        )

        assert result.exit_code == 0
        assert "Cancelled" in result.output

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

    def test_cli_new_with_signature(self, tmp_path, monkeypatch):
        """Test new command includes signature from ~/.signature.md."""
        # Create a fake home directory with signature
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        signature_file = fake_home / ".signature.md"
        signature_file.write_text("--\nBest regards,\nTest User")

        # Patch Path.home() to return our fake home
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        runner = CliRunner()
        output_file = tmp_path / "draft.md"
        result = runner.invoke(
            main,
            [
                "new",
                "--to",
                "test@example.com",
                "--subject",
                "Signature Test",
                "-o",
                str(output_file),
            ],
        )
        assert result.exit_code == 0

        # Verify signature is in body
        content = output_file.read_text()
        assert "--" in content
        assert "Best regards," in content
        assert "Test User" in content

    def test_cli_credentials_no_file(self, tmp_path):
        """Test credentials command with missing file."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["credentials", "--authinfo", str(tmp_path / "nonexistent")]
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_cli_reply_command(self, tmp_path, monkeypatch):
        """Test reply command creates draft with quoted original."""
        # Create fake home for drafts
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # Create original email
        original_file = tmp_path / "original.md"
        original_file.write_text("""---
from: alice@example.com
to: me@example.com
subject: Hello there
message-id: <abc123@example.com>
date: '2025-01-23T10:30:00+00:00'
---

How are you doing?

Best,
Alice
""")

        runner = CliRunner()
        output_file = tmp_path / "reply.md"
        result = runner.invoke(
            main,
            ["reply", str(original_file), "-o", str(output_file)],
        )
        assert result.exit_code == 0
        assert output_file.exists()

        # Verify reply content
        content = output_file.read_text()
        assert "Re: Hello there" in content
        assert "alice@example.com" in content  # to field
        assert "in-reply-to: <abc123@example.com>" in content
        assert "> How are you doing?" in content  # quoted
        assert "> Best," in content
        assert "> Alice" in content


class TestValidation:
    """Tests for email validation logic."""

    def test_validate_valid_email(self, tmp_path):
        """Test validation of a valid email with credentials."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.example.com login sender@example.com password secret\n"
        )

        content = """---
from: sender@example.com
to: recipient@example.com
subject: Test Subject
---

This is the body.
"""
        ctx = ValidationContext(authinfo_path=authinfo)
        result = validate_email_string(content, ctx)

        assert not result.has_errors
        assert "from" in [i.field for i in result.items]
        assert "to" in [i.field for i in result.items]
        assert "subject" in [i.field for i in result.items]
        assert "body" in [i.field for i in result.items]

    def test_validate_missing_from(self):
        """Test validation catches missing from address."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        content = """---
to: recipient@example.com
subject: Test Subject
---

Body.
"""
        result = validate_email_string(content, ValidationContext())

        assert result.has_errors
        errors = [
            i for i in result.items if i.field == "from" and i.level.value == "error"
        ]
        assert len(errors) == 1
        assert "required" in errors[0].message

    def test_validate_missing_to(self):
        """Test validation catches missing to address."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        content = """---
from: sender@example.com
subject: Test Subject
---

Body.
"""
        result = validate_email_string(content, ValidationContext())

        assert result.has_errors
        errors = [
            i for i in result.items if i.field == "to" and i.level.value == "error"
        ]
        assert len(errors) == 1
        assert "required" in errors[0].message

    def test_validate_missing_subject(self):
        """Test validation catches missing subject."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        content = """---
from: sender@example.com
to: recipient@example.com
---

Body.
"""
        result = validate_email_string(content, ValidationContext())

        assert result.has_errors
        errors = [
            i for i in result.items if i.field == "subject" and i.level.value == "error"
        ]
        assert len(errors) == 1
        assert "empty" in errors[0].message

    def test_validate_empty_body(self):
        """Test validation catches empty body."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        content = """---
from: sender@example.com
to: recipient@example.com
subject: Test
---

"""
        result = validate_email_string(content, ValidationContext())

        assert result.has_errors
        errors = [
            i for i in result.items if i.field == "body" and i.level.value == "error"
        ]
        assert len(errors) == 1
        assert "empty" in errors[0].message

    def test_validate_invalid_email_format(self):
        """Test validation catches invalid email format."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        content = """---
from: not-an-email
to: also-not-an-email
subject: Test
---

Body.
"""
        result = validate_email_string(content, ValidationContext())

        assert result.has_errors
        errors = [i for i in result.items if "invalid email format" in i.message]
        assert len(errors) >= 2  # Both from and to should fail

    def test_validate_unknown_header(self):
        """Test validation catches unknown headers."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        content = """---
from: sender@example.com
to: recipient@example.com
subject: Test
x-custom-header: should be flagged
---

Body.
"""
        result = validate_email_string(content, ValidationContext())

        assert result.has_errors
        errors = [i for i in result.items if i.field == "x-custom-header"]
        assert len(errors) == 1
        assert "unknown header" in errors[0].message

    def test_validate_no_credentials(self):
        """Test validation catches missing credentials."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        content = """---
from: sender@example.com
to: recipient@example.com
subject: Test
---

Body.
"""
        # No authinfo provided
        result = validate_email_string(content, ValidationContext())

        assert result.has_errors
        errors = [
            i for i in result.items if i.field == "from" and "credentials" in i.message
        ]
        assert len(errors) == 1

    def test_validate_multiple_recipients(self, tmp_path):
        """Test validation of multiple recipients."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.example.com login sender@example.com password secret\n"
        )

        content = """---
from: sender@example.com
to:
  - alice@example.com
  - bob@example.com
cc: charlie@example.com
subject: Test
---

Body.
"""
        ctx = ValidationContext(authinfo_path=authinfo)
        result = validate_email_string(content, ctx)

        assert not result.has_errors
        # Should have validation items for each recipient
        to_items = [i for i in result.items if i.field == "to"]
        cc_items = [i for i in result.items if i.field == "cc"]
        assert len(to_items) == 2  # alice and bob
        assert len(cc_items) == 1  # charlie

    def test_validate_message_id_format(self):
        """Test validation of message-id format."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        content = """---
from: sender@example.com
to: recipient@example.com
subject: Test
in-reply-to: not-in-angle-brackets
---

Body.
"""
        result = validate_email_string(content, ValidationContext())

        # Should have a warning for message-id format
        warnings = [
            i
            for i in result.items
            if i.field == "in-reply-to" and i.level.value == "warning"
        ]
        assert len(warnings) == 1
        assert "angle brackets" in warnings[0].message

    def test_validate_result_to_dict(self, tmp_path):
        """Test ValidationResult.to_dict() serialization."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine smtp.example.com login sender@example.com password secret\n"
        )

        content = """---
from: sender@example.com
to: recipient@example.com
subject: Test
---

Body.
"""
        ctx = ValidationContext(authinfo_path=authinfo)
        result = validate_email_string(content, ctx)

        d = result.to_dict()

        assert "has_errors" in d
        assert "has_warnings" in d
        assert "items" in d
        assert isinstance(d["items"], list)
        assert all("level" in item and "field" in item for item in d["items"])


class TestAttachments:
    """Tests for email attachment functionality."""

    def test_parse_email_with_single_attachment(self):
        """Test parsing email with single attachment (string format)."""
        text = """---
from: sender@example.com
to: recipient@example.com
subject: With Attachment
attachments: ./test.pdf
---

Please see attached.
"""
        email = Email.from_string(text)

        assert email.attachments == ["./test.pdf"]

    def test_parse_email_with_multiple_attachments(self):
        """Test parsing email with multiple attachments (list format)."""
        text = """---
from: sender@example.com
to: recipient@example.com
subject: Multiple Attachments
attachments:
  - ./report.pdf
  - ~/docs/data.xlsx
  - /tmp/image.png
---

Multiple files attached.
"""
        email = Email.from_string(text)

        assert len(email.attachments) == 3
        assert "./report.pdf" in email.attachments
        assert "~/docs/data.xlsx" in email.attachments
        assert "/tmp/image.png" in email.attachments

    def test_roundtrip_with_single_attachment(self):
        """Test that single attachment survives serialization roundtrip."""
        original = """---
from: sender@example.com
to: recipient@example.com
subject: Test
attachments: ./file.pdf
---

Body.
"""
        email = Email.from_string(original)
        serialized = email.to_string()
        reparsed = Email.from_string(serialized)

        assert reparsed.attachments == ["./file.pdf"]

    def test_roundtrip_with_multiple_attachments(self):
        """Test that multiple attachments survive serialization roundtrip."""
        original = """---
from: sender@example.com
to: recipient@example.com
subject: Test
attachments:
  - file1.pdf
  - file2.docx
---

Body.
"""
        email = Email.from_string(original)
        serialized = email.to_string()
        reparsed = Email.from_string(serialized)

        assert len(reparsed.attachments) == 2
        assert reparsed.attachments == email.attachments

    def test_email_without_attachments(self):
        """Test email without attachments field has empty list."""
        text = """---
from: sender@example.com
to: recipient@example.com
subject: No attachments
---

Body.
"""
        email = Email.from_string(text)

        assert email.attachments == []

    def test_to_mime_without_attachments(self):
        """Test MIME conversion without attachments is simple message."""
        text = """---
from: sender@example.com
to: recipient@example.com
subject: Simple
---

Body text.
"""
        email = Email.from_string(text)
        mime = email.to_mime()

        # Should NOT be multipart if no attachments
        assert not mime.is_multipart()
        assert mime["Subject"] == "Simple"

    def test_to_mime_with_attachments_creates_multipart(self, tmp_path):
        """Test MIME conversion with attachments creates multipart message."""
        # Create test files
        file1 = tmp_path / "test.txt"
        file1.write_text("Test content")

        file2 = tmp_path / "data.bin"
        file2.write_bytes(b"\x00\x01\x02\x03")

        text = f"""---
from: sender@example.com
to: recipient@example.com
subject: MIME Test
attachments:
  - {file1}
  - {file2}
---

Body text.
"""
        email = Email.from_string(text)
        mime = email.to_mime()

        # Should be multipart
        assert mime.is_multipart()

        # Check parts (skip container part)
        parts = [p for p in mime.walk() if p.get_filename()]
        assert len(parts) >= 2  # 2 attachments

        # Verify filenames in attachments
        filenames = [part.get_filename() for part in parts]
        assert "test.txt" in filenames
        assert "data.bin" in filenames

    def test_validate_attachments_file_not_found(self):
        """Test validation catches missing attachment files."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        content = """---
from: sender@example.com
to: recipient@example.com
subject: Test
attachments: /nonexistent/file.pdf
---

Body.
"""
        result = validate_email_string(content, ValidationContext())

        assert result.has_errors
        errors = [i for i in result.items if i.field == "attachments"]
        assert any("not found" in e.message for e in errors)

    def test_validate_attachments_is_directory(self, tmp_path):
        """Test validation catches when attachment is a directory."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        content = f"""---
from: sender@example.com
to: recipient@example.com
subject: Test
attachments: {test_dir}
---

Body.
"""
        result = validate_email_string(content, ValidationContext())

        assert result.has_errors
        errors = [i for i in result.items if i.field == "attachments"]
        assert any("directory" in e.message for e in errors)

    def test_validate_attachments_empty_file(self, tmp_path):
        """Test validation catches empty (0 byte) files."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        empty_file = tmp_path / "empty.txt"
        empty_file.write_bytes(b"")

        content = f"""---
from: sender@example.com
to: recipient@example.com
subject: Test
attachments: {empty_file}
---

Body.
"""
        result = validate_email_string(content, ValidationContext())

        assert result.has_errors
        errors = [i for i in result.items if i.field == "attachments"]
        assert any("empty" in e.message for e in errors)

    def test_validate_attachments_with_real_files(self, tmp_path):
        """Test validation passes with real files and shows metadata."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        # Create test files
        small_file = tmp_path / "small.txt"
        small_file.write_text("Small content")

        medium_file = tmp_path / "medium.pdf"
        medium_file.write_bytes(b"PDF" * 1000)

        content = f"""---
from: sender@example.com
to: recipient@example.com
subject: Test
attachments:
  - {small_file}
  - {medium_file}
---

Body.
"""
        result = validate_email_string(content, ValidationContext())

        # Should not have errors for file validation
        file_errors = [
            i for i in result.items
            if i.field == "attachments"
            and i.level.value == "error"
            and "not found" in i.message
        ]
        assert len(file_errors) == 0

        # Should have OK status for the attachments
        att_items = [i for i in result.items if i.field == "attachments"]
        assert len(att_items) > 0

    def test_validate_large_attachment_warning(self, tmp_path):
        """Test validation warns about large attachments (>10MB)."""
        from mdmailbox.validate import validate_email_string, ValidationContext

        # Create 15 MB file
        large_file = tmp_path / "large.bin"
        large_file.write_bytes(b"x" * (15 * 1024 * 1024))

        content = f"""---
from: sender@example.com
to: recipient@example.com
subject: Large File
attachments: {large_file}
---

Body.
"""
        result = validate_email_string(content, ValidationContext())

        # Should have warning for large file
        warnings = [
            i for i in result.items
            if i.field == "attachments" and i.level.value == "warning"
        ]
        assert len(warnings) > 0
        assert any("large" in w.message.lower() for w in warnings)

    def test_send_email_with_attachment_integrates_with_smtp(self, smtpd, tmp_path):
        """Integration test: send email with attachment through SMTP."""
        from mdmailbox.authinfo import Credential

        # Create test file
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"PDF content here")

        email = Email.from_string(f"""---
from: sender@example.com
to: recipient@example.com
subject: With Attachment
attachments: {test_file}
---

See attached.
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
        assert result.message_id is not None

        # Verify message was received and is multipart
        assert len(smtpd.messages) == 1
        msg = smtpd.messages[0]
        assert msg.is_multipart()

        # Verify attachment is in message
        filenames = [
            part.get_filename()
            for part in msg.walk()
            if part.get_filename()
        ]
        assert "test.pdf" in filenames

    def test_send_email_with_multiple_attachments(self, smtpd, tmp_path):
        """Test sending email with multiple attachments."""
        from mdmailbox.authinfo import Credential

        # Create test files
        file1 = tmp_path / "doc.txt"
        file1.write_text("Document")

        file2 = tmp_path / "data.csv"
        file2.write_text("col1,col2\n1,2")

        email = Email.from_string(f"""---
from: sender@example.com
to: recipient@example.com
subject: Multiple Files
attachments:
  - {file1}
  - {file2}
---

Two attachments.
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

        # Verify both attachments received
        msg = smtpd.messages[0]
        filenames = [
            part.get_filename()
            for part in msg.walk()
            if part.get_filename()
        ]
        assert "doc.txt" in filenames
        assert "data.csv" in filenames


class TestAuditTrail:
    """Tests for send audit trail functionality."""

    def test_send_result_has_log(self, smtpd):
        """Test that SendResult includes log entries."""
        email = Email.from_string("""---
from: sender@example.com
to: recipient@example.com
subject: Audit Test
---

Test body.
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
        assert result.log  # Log should not be empty
        assert any("Connecting to" in line for line in result.log)
        assert any("EHLO" in line for line in result.log)
        assert any("Message-ID" in line for line in result.log)

    def test_send_result_has_metadata(self, smtpd):
        """Test that SendResult includes SMTP metadata."""
        email = Email.from_string("""---
from: sender@example.com
to: recipient@example.com
subject: Metadata Test
---

Test body.
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
        assert result.smtp_host == smtpd.hostname
        assert result.smtp_port == smtpd.port
        assert result.smtp_response is not None
        assert result.sent_at is not None
        assert result.message_id is not None

    def test_audit_trail_appended_to_file(self, smtpd, tmp_path):
        """Test that audit trail is appended to sent email file."""
        from mdmailbox.cli import _save_with_audit_trail

        email = Email.from_string("""---
from: sender@example.com
to: recipient@example.com
subject: Audit File Test
---

Test body content.
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

        # Save with audit trail
        output_file = tmp_path / "sent-email.md"
        _save_with_audit_trail(email, output_file, result)

        # Read the file and verify audit trail
        content = output_file.read_text()

        # Should have the original email content
        assert "from: sender@example.com" in content
        assert "subject: Audit File Test" in content
        assert "Test body content." in content

        # Should have the audit trail section
        assert "# Send Log" in content
        assert "sent-at:" in content
        assert "smtp-host:" in content
        assert "smtp-port:" in content
        assert "smtp-response:" in content

        # Should have log entries
        assert "[" in content  # Timestamps in log
        assert "Connecting to" in content
        assert "Message-ID:" in content

    def test_failed_send_has_log(self, tmp_path):
        """Test that failed sends include error log."""
        email = Email.from_string("""---
from: sender@example.com
to: recipient@example.com
subject: Fail Test
---

Test body.
""")

        # Use a non-existent host to force failure
        credential = Credential(
            machine="nonexistent.invalid",
            login="sender@example.com",
            password="testpass",
        )

        result = send_email(
            email,
            credential=credential,
            port=587,
            use_tls=False,
        )

        assert not result.success
        assert result.log  # Log should not be empty even on failure
        assert any("Connecting to" in line for line in result.log)
        assert any("ERROR" in line for line in result.log)

    def test_no_credentials_has_log(self, tmp_path):
        """Test that missing credentials include error log."""
        authinfo = tmp_path / ".authinfo"
        authinfo.write_text("")  # Empty authinfo

        email = Email.from_string("""---
from: unknown@example.com
to: recipient@example.com
subject: No Creds Test
---

Test body.
""")

        result = send_email(email, authinfo_path=authinfo)

        assert not result.success
        assert result.log
        assert any("Looking up credentials" in line for line in result.log)
        assert any("ERROR" in line or "No credentials" in line for line in result.log)


class TestIMAP:
    """Tests for IMAP sent folder upload."""

    def test_convert_smtp_to_imap(self):
        """Test SMTP to IMAP hostname conversion."""
        from mdmailbox.imap import convert_smtp_to_imap

        assert convert_smtp_to_imap("smtp.gmail.com") == "imap.gmail.com"
        assert convert_smtp_to_imap("smtp.migadu.com") == "imap.migadu.com"
        assert convert_smtp_to_imap("smtp.example.com") == "imap.example.com"

    def test_find_imap_credential(self, tmp_path):
        """Test finding IMAP credential from authinfo."""
        from mdmailbox.imap import find_imap_credential

        authinfo = tmp_path / ".authinfo"
        authinfo.write_text(
            "machine imap.gmail.com login user@gmail.com password secret123\n"
        )

        cred = find_imap_credential("user@gmail.com", "smtp.gmail.com", authinfo)

        assert cred is not None
        assert cred.machine == "imap.gmail.com"
        assert cred.login == "user@gmail.com"
        assert cred.password == "secret123"

    def test_find_imap_credential_not_found(self, tmp_path):
        """Test finding IMAP credential when not configured."""
        from mdmailbox.imap import find_imap_credential

        authinfo = tmp_path / ".authinfo"
        authinfo.write_text("machine smtp.gmail.com login user@gmail.com password secret123\n")

        cred = find_imap_credential("user@gmail.com", "smtp.gmail.com", authinfo)

        assert cred is None

    def test_imap_upload_result_structure(self):
        """Test IMAPUploadResult dataclass."""
        from mdmailbox.imap import IMAPUploadResult

        result = IMAPUploadResult(
            success=True,
            message="Test",
            imap_host="imap.example.com",
            folder="Sent",
        )

        assert result.success is True
        assert result.message == "Test"
        assert result.imap_host == "imap.example.com"
        assert result.folder == "Sent"
        assert result.log == []
