from .browsers import Logger
import os
import time
from typing import Optional
from colorama import init, Fore, Style
init(autoreset=True)
from .selectors import LoginSelectors, RegistrationSelectors


class AuthService:
    def __init__(self, browser):
        if hasattr(browser, "driver") and browser.driver is not None:
            self.browser = browser.driver
        else:
            self.browser = browser
        self.driver = self.browser

    def is_logged_in(self) -> bool:
        try:
            self.driver.navigation.to("https://learning.oreilly.com/home/")
            time.sleep(3)

            current_url = self.driver.navigation.url.lower()
            if "login" in current_url or "register" in current_url:
                return False

            # Secondary heuristic: if a sign-in button still visibly exists, not logged in
            sign_in_btns = self.driver.find_elements(LoginSelectors.SIGN_IN_BUTTONS)
            if sign_in_btns and any(btn.is_displayed() for btn in sign_in_btns):
                return False

            # If we stayed on /home/ and no login button is visible, we are logged in
            return True
        except Exception:
            return False

    def login(self, email: str, password: str) -> bool:
        if self.is_logged_in():
            Logger.success(" Already logged in using saved profile")
            return True

        Logger.warning("🔐 Attempting automated login...")
        self.driver.navigation.to("https://learning.oreilly.com/accounts/login/")
        try:
            # Step 1: Enter email
            email_field = self.driver.wait.for_visible(self.driver.find_element(LoginSelectors.EMAIL_FIELD), 15)
            email_field.fill(email)

            # Click Continue using explicit wait and data-testid
            continue_btn = self.driver.wait.for_visible(self.driver.find_element(LoginSelectors.CONTINUE_BTN), 10)
            try:
                continue_btn.click()
            except Exception:
                self.driver.actions.execute_js("arguments[0].click();", continue_btn)

            # Step 2: Wait for password field to appear
            password_field = self.driver.wait.for_visible(self.driver.find_element(LoginSelectors.PASSWORD_FIELD), 15)
            # Wait a moment for password field to accept input fully
            time.sleep(1)
            password_field.fill(password)

            # Click Sign In explicitly
            time.sleep(1)
            signin_btn = self.driver.wait.for_visible(self.driver.find_element(LoginSelectors.SIGNIN_BTN), 10)
            try:
                signin_btn.click()
            except Exception:
                self.driver.actions.execute_js("arguments[0].click();", signin_btn)

            time.sleep(5)

            # Check for captchas or errors
            if self.is_logged_in():
                Logger.success(" Successfully logged in!")
                return True
            Logger.error(" Authentication failed or CAPTCHA blocked.")
            return False

        except Exception as e:
            Logger.error(f" Login failed: {e}")
            return False

    def get_ks(self) -> Optional[str]:
        """Fetches the active Kaltura Session (ks) token from the browser cookie or API."""
        try:
            self.driver.actions.set_script_timeout(15)
            script = """
            var callback = arguments[arguments.length - 1];
            fetch('/api/v1/player/kaltura_session/')
                .then(r => r.json())
                .then(d => callback(d.ks || d.kaltura_session || d.session))
                .catch(e => callback(null));
            """
            ks = self.driver.actions.execute_async_js(script)
            return ks
        except Exception as e:
            Logger.error(f" Failed to extract Kaltura session (ks): {e}")
            return None

    def register_account(
        self, email: str, password: str, first_name: str, last_name: str
    ) -> bool:
        """Automates filling the registration form and prompts the user for OTP verification."""
        Logger.warning("📋 Opening O'Reilly registration page...")
        self.driver.navigation.to("https://www.oreilly.com/start-trial/?type=individual")
        
        try:
            # Wait for fields to load
            self.driver.wait.for_present(self.driver.find_element(RegistrationSelectors.FIRST_NAME), 15)
            
            Logger.warning("✍️ Filling registration form details...")
            
            # Fill first name
            first_name_field = self.driver.find_element(RegistrationSelectors.FIRST_NAME)
            first_name_field.clear()
            first_name_field.fill(first_name)
            
            # Fill last name
            last_name_field = self.driver.find_element(RegistrationSelectors.LAST_NAME)
            last_name_field.clear()
            last_name_field.fill(last_name)
            
            # Fill email
            email_field = self.driver.find_element(RegistrationSelectors.EMAIL_INPUT)
            email_field.clear()
            email_field.fill(email)
            
            # Fill password
            password_field = self.driver.find_element(RegistrationSelectors.PASSWORD_INPUT)
            password_field.clear()
            password_field.fill(password)
            
            # Select checkbox
            terms_checkbox = self.driver.find_element(RegistrationSelectors.TERMS_CHECKBOX)
            if not terms_checkbox.is_selected():
                try:
                    terms_checkbox.click()
                except Exception:
                    self.driver.actions.execute_js("arguments[0].click();", terms_checkbox)
                    
            # Click submit button
            submit_btn = None
            for selector in [
                RegistrationSelectors.SUBMIT_BTN_CSS,
                RegistrationSelectors.SUBMIT_BTN_XPATH
            ]:
                try:
                    submit_btn = self.driver.wait.for_visible(self.driver.find_element(selector), 5)
                    if submit_btn:
                        break
                except Exception:
                    pass
                    
            if not submit_btn:
                # Fallback to finding button inside form
                submit_btn = self.driver.find_element(RegistrationSelectors.SUBMIT_BTN_FALLBACK)
                
            try:
                submit_btn.click()
            except Exception:
                self.driver.actions.execute_js("arguments[0].click();", submit_btn)
                
            Logger.info("⏳ Form submitted. Waiting for the OTP Verification page to load...")
            
            # Wait for OTP input boxes to appear
            self.driver.wait.for_present(self.driver.find_element(RegistrationSelectors.OTP_INPUTS), 30)
            
            Logger.success("📬 Verification email sent!")
            code = input("👉 Please check your email inbox and enter the 6-digit verification code: ").strip()
            
            if len(code) != 6 or not code.isalnum():
                Logger.error(" Invalid code format. Must be exactly 6 alphanumeric characters.")
                return False
                
            # Input the code into the boxes
            otp_inputs = self.driver.find_elements(RegistrationSelectors.OTP_INPUTS)
            if not otp_inputs:
                # Fallback selector
                otp_inputs = self.driver.find_elements(RegistrationSelectors.OTP_FALLBACK)
                
            if len(otp_inputs) < 6:
                Logger.error(f" Found only {len(otp_inputs)} OTP fields in browser. Expected 6.")
                return False
                
            for i, digit in enumerate(code):
                otp_inputs[i].fill(digit)
                time.sleep(0.1) # Small delay for focus shifting
                
            # Wait for redirection to complete
            time.sleep(10)
            
            # Verify login status
            if self.is_logged_in():
                return True
                
            return False
            
        except Exception as e:
            Logger.error(f" Registration failed: {e}")
            return False
