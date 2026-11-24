import pytest
from unittest.mock import MagicMock, patch
from oreilly_downloader.core.auth import (
    authenticate_session,
    HeadlessAutoLoginFailed,
    AuthService,
    IdentityGenerator,
    IOtpHandler,
    ConsoleOtpHandler,
)
from oreilly_downloader.core.config import DownloaderConfig

@pytest.fixture
def mock_auth():
    auth = MagicMock(spec=AuthService)
    auth.driver = MagicMock()
    return auth

def test_authenticate_session_already_logged_in_credentials(mock_auth):
    config = DownloaderConfig(
        url="https://learning.oreilly.com/course/test-course/123/",
        email="test@example.com",
        password="password",
        headless=True
    )
    mock_auth.is_logged_in.return_value = True
    
    assert authenticate_session(mock_auth, config) is True
    # Verify pre-check bypass avoids calling auth.login
    mock_auth.login.assert_not_called()

def test_authenticate_session_credentials_headless_failure(mock_auth):
    config = DownloaderConfig(
        url="https://learning.oreilly.com/course/test-course/123/",
        email="test@example.com",
        password="password",
        headless=True
    )
    mock_auth.is_logged_in.return_value = False
    mock_auth.login.return_value = False
    
    with pytest.raises(HeadlessAutoLoginFailed):
        authenticate_session(mock_auth, config)
    
    mock_auth.login.assert_called_once_with("test@example.com", "password", skip_precheck=True)

@patch("oreilly_downloader.core.auth._run_manual_login_fallback")
def test_authenticate_session_credentials_headed_manual_fallback(mock_fallback, mock_auth):
    config = DownloaderConfig(
        url="https://learning.oreilly.com/course/test-course/123/",
        email="test@example.com",
        password="password",
        headless=False
    )
    mock_auth.is_logged_in.return_value = False
    mock_auth.login.return_value = False
    mock_fallback.return_value = True
    
    assert authenticate_session(mock_auth, config) is True
    mock_fallback.assert_called_once()

@patch("oreilly_downloader.core.auth._run_manual_login_fallback")
def test_authenticate_session_manual_login(mock_fallback, mock_auth, tmp_path):
    config = DownloaderConfig(
        url=None,
        manual_login=True,
        output_dir=str(tmp_path)
    )
    mock_fallback.return_value = True
    
    assert authenticate_session(mock_auth, config) is False
    mock_fallback.assert_called_once()


def test_identity_generator():
    first, last = IdentityGenerator.generate_name()
    assert len(first) >= 2
    assert len(last) >= 2
    pwd = IdentityGenerator.generate_password()
    assert len(pwd) >= 12
    assert any(c.isupper() for c in pwd)
    assert any(c.islower() for c in pwd)
    assert any(c.isdigit() for c in pwd)
    assert any(c in "!@#$%^&*" for c in pwd)


def test_console_otp_handler_prompts():
    handler = ConsoleOtpHandler()
    with patch("builtins.input", return_value="123456"):
        assert handler.prompt_otp() == "123456"

    with patch("builtins.input", return_value=""):
        handler.prompt_manual_login()


def test_auth_service_custom_otp_handler():
    mock_driver = MagicMock()
    custom_handler = MagicMock(spec=IOtpHandler)
    service = AuthService(mock_driver, otp_handler=custom_handler)
    assert service.otp_handler == custom_handler


