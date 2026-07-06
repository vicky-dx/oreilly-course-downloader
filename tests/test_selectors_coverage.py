import pytest
from unittest.mock import MagicMock, patch
from oreilly_downloader.core.auth import AuthService
from oreilly_downloader.core.selectors import LoginSelectors, RegistrationSelectors

def test_auth_service_is_logged_in_uses_selectors():
    browser = MagicMock()
    browser.driver = None
    browser.navigation.url = "https://learning.oreilly.com/home/"
    browser.find_elements.return_value = []
    
    auth = AuthService(browser)
    res = auth.is_logged_in()
    
    assert res is True
    browser.find_elements.assert_any_call(LoginSelectors.SIGN_IN_BUTTONS)

def test_auth_service_login_uses_selectors():
    browser = MagicMock()
    browser.driver = None
    auth = AuthService(browser)
    auth.is_logged_in = MagicMock(side_effect=[False, True])
    
    email_el = MagicMock()
    continue_el = MagicMock()
    pass_el = MagicMock()
    signin_el = MagicMock()
    
    browser.wait.for_visible.side_effect = [email_el, continue_el, pass_el, signin_el]
    
    res = auth.login("test@email.com", "password")
    
    assert res is True
    browser.find_element.assert_any_call(LoginSelectors.EMAIL_FIELD)
    browser.find_element.assert_any_call(LoginSelectors.CONTINUE_BTN)
    browser.find_element.assert_any_call(LoginSelectors.PASSWORD_FIELD)
    browser.find_element.assert_any_call(LoginSelectors.SIGNIN_BTN)

def test_auth_service_register_uses_selectors():
    browser = MagicMock()
    browser.driver = None
    browser.find_elements.return_value = [MagicMock() for _ in range(6)]
    
    auth = AuthService(browser)
    auth.is_logged_in = MagicMock(return_value=True)
    
    # Mock console input
    with patch('builtins.input', return_value="123456"):
        res = auth.register_account("test@gmail.com", "password123456", "John", "Doe")
        
    assert res is True
    browser.find_element.assert_any_call(RegistrationSelectors.FIRST_NAME)
    browser.find_elements.assert_any_call(RegistrationSelectors.OTP_INPUTS)
