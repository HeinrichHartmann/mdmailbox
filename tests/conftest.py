"""pytest configuration and fixtures."""

import pytest


@pytest.fixture
def smtpd_use_starttls():
    """Disable STARTTLS for testing."""
    return False


@pytest.fixture
def smtpd_enforce_auth():
    """Disable authentication enforcement for testing."""
    return False
