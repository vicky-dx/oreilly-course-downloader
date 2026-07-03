import os
import time
from typing import Optional
from colorama import init, Fore, Style
init(autoreset=True)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class AuthService:
    def __init__(self, browser):
        self.browser = browser
        self.driver = browser.driver

    def is_logged_in(self) -> bool:
        try:
            self.driver.get("https://learning.oreilly.com/home/")
            time.sleep(3)

            current_url = self.driver.current_url.lower()
            if "login" in current_url or "register" in current_url:
                return False

            # Secondary heuristic: if a sign-in button still visibly exists, not logged in
            sign_in_btns = self.driver.find_elements(
                By.XPATH,
                "//a[contains(@href, 'login') or contains(translate(text(), 'SIGN', 'sign'), 'sign in')]",
            )
            if sign_in_btns and any(btn.is_displayed() for btn in sign_in_btns):
                return False

            # If we stayed on /home/ and no login button is visible, we are logged in
            return True
        except Exception:
            return False

    def login(self, email: str, password: str) -> bool:
        if self.is_logged_in():
            print(Fore.GREEN + "✅ Already logged in using saved profile")
            return True

        print(Fore.YELLOW + "🔐 Attempting automated login...")
        self.driver.get("https://learning.oreilly.com/accounts/login/")
        try:
            # Step 1: Enter email
            email_field = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.ID, "email"))
            )
            email_field.send_keys(email)

            # Click Continue using explicit wait and data-testid
            continue_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (
                        By.CSS_SELECTOR,
                        "button[data-testid='EmailSubmit'], button[type='submit']",
                    )
                )
            )
            try:
                continue_btn.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", continue_btn)

            # Step 2: Wait for password field to appear
            password_field = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.ID, "password"))
            )
            # Wait a moment for password field to accept input fully
            time.sleep(1)
            password_field.send_keys(password)

            # Click Sign In explicitly
            time.sleep(1)
            signin_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "button[data-testid='SignInBtn']")
                )
            )
            try:
                signin_btn.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", signin_btn)

            time.sleep(5)

            # Check for captchas or errors
            if self.is_logged_in():
                print(Fore.GREEN + "✅ Successfully logged in!")
                return True
            print(Fore.RED + "❌ Authentication failed or CAPTCHA blocked.")
            return False

        except Exception as e:
            print(Fore.RED + f"❌ Login failed: {e}")
            return False

    def get_ks(self) -> Optional[str]:
        """Fetches the active Kaltura Session (ks) token from the browser cookie or API."""
        try:
            self.driver.set_script_timeout(15)
            script = """
            var callback = arguments[arguments.length - 1];
            fetch('/api/v1/player/kaltura_session/')
                .then(r => r.json())
                .then(d => callback(d.ks || d.kaltura_session || d.session))
                .catch(e => callback(null));
            """
            ks = self.driver.execute_async_script(script)
            return ks
        except Exception as e:
            print(Fore.RED + f"❌ Failed to extract Kaltura session (ks): {e}")
            return None
