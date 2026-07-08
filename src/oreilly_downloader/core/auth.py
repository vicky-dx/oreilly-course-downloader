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

    def login(self, email: str, password: str, skip_precheck: bool = False) -> bool:
        if not skip_precheck and self.is_logged_in():
            Logger.success(" Already logged in using saved profile")
            return True

        Logger.warning("Attempting automated login...")
        self.driver.navigation.to("https://learning.oreilly.com/accounts/login/")
        try:
            # Step 1: Enter email
            email_field = self.driver.wait.for_visible(self.driver.find_element(LoginSelectors.EMAIL_FIELD), 15)
            email_field.fill(email)
            Logger.info("Email entered")

            # Click Continue using explicit wait and data-testid
            continue_btn = self.driver.wait.for_visible(self.driver.find_element(LoginSelectors.CONTINUE_BTN), 10)
            try:
                continue_btn.click()
                Logger.info("Continue clicked")
            except Exception:
                self.driver.actions.execute_js("arguments[0].click();", continue_btn)
                Logger.info("Continue clicked using JS")

            # Step 2: Wait for password field to appear
            password_field = self.driver.wait.for_visible(self.driver.find_element(LoginSelectors.PASSWORD_FIELD), 15)
            # Wait a moment for password field to accept input fully
            time.sleep(1)
            password_field.fill(password)
            Logger.info("Password entered")

            # Click Sign In explicitly
            time.sleep(1)
            signin_btn = self.driver.wait.for_visible(self.driver.find_element(LoginSelectors.SIGNIN_BTN), 10)
            try:
                signin_btn.click()
                Logger.info("Sign In clicked")
            except Exception:
                self.driver.actions.execute_js("arguments[0].click();", signin_btn)
                Logger.info("Sign In clicked using JS")

            time.sleep(5)

            # Check for captchas or errors
            if self.is_logged_in():
                Logger.success("Successfully logged in!")
                return True
            Logger.error("Authentication failed or CAPTCHA blocked.")
            return False

        except Exception as e:
            Logger.error(f"Login failed: {e}")
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
            
            Logger.warning("Filling registration form details...")
            
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

class HeadlessAutoLoginFailed(Exception):
    """Raised when auto-login (session restore) fails in headless mode, triggering a headed retry."""
    pass

# Import at end to prevent circular imports
from .gmail_trick import GmailTrickState, get_dot_variation
from .config import DownloaderConfig
import random
import string

def authenticate_session(
    auth: AuthService,
    config: DownloaderConfig,
) -> bool:
    """Handles the authentication flow either manually, via credentials, or via existing session."""
    if config.auto_signup:
        state = GmailTrickState(config.output_dir)
        if config.base_email:
            state.set_base_email(config.base_email)

        # Smart Bypass: Check if a non-expired success entry already exists
        active_trial = state.get_active_valid_trial(config.base_email)
        if active_trial:
            Logger.success(f"Active trial account found: {active_trial.get('email')} (Valid until {active_trial.get('expires_at')})")
            if auth.is_logged_in():
                Logger.success("Existing session is already authenticated. Skipping auto-signup.")
                return True
            
            email_cached = active_trial.get("email")
            password_cached = active_trial.get("password")
            if email_cached and password_cached:
                Logger.info("Attempting to restore session using cached credentials...")
                if auth.login(email_cached, password_cached, skip_precheck=True):
                    Logger.success("Successfully restored active session!")
                    return True
                elif config.headless:
                    raise HeadlessAutoLoginFailed()
            Logger.warning("Existing trial login failed. Proceeding with new trial creation...")

        base_email = state.get_base_email()
        if not base_email:
            Logger.error(" Error: Base email is required for auto-signup.")
            Logger.warning("👉 Solution: Run 'uv run oreilly-dl --auto-signup --base-email \"your_email@gmail.com\"'")
            return False

        index = state.get_unused_random_index()
        email_variant = get_dot_variation(base_email, index)

        first_names = ["John", "Jane", "Robert", "Emily", "Michael", "Sarah", "David", "Jessica", "James", "Karen", "Thomas", "Lisa", "Charles", "Sandra"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson"]
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)

        # Generate a strong 16-character password
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        password = "".join(random.choice(chars) for _ in range(16))

        # Show beautiful registration summary panel
        Logger.panel("🆕 AUTOMATIC SIGN UP ACTIVE", [
            f"📧 Base Email:    {base_email}",
            f"📧 Email Variant: {email_variant} (Index: {index})",
            f"👤 Name:          {first_name} {last_name}",
            f"🔑 Password:      {password}"
        ], border_color=Fore.YELLOW)

        success = auth.register_account(email_variant, password, first_name, last_name)
        if success:
            state.add_history(email_variant, index, "success", password=password)
            Logger.success("Confirmed registered and logged in successfully. Profile saved!")
            Logger.panel("📝 Registered Account Details", [
                f"Email:    {email_variant}",
                f"Password: {password}",
                "",
                "✨ You can now close the browser and run standard downloads without credentials."
            ], border_color=Fore.GREEN)
        else:
            state.add_history(email_variant, index, "failed", password=password)
            Logger.error("Registration failed or OTP was incorrect.")
        return False

    if config.manual_login:
        lines = [
            "⏳ Please log in via the newly opened browser window.",
            "⏳ ONCE YOU ARE SUCCESSFULLY ON THE HOMEPAGE:",
            "👉 Press ENTER here in the terminal to continue..."
        ]

        # Retrieve and display active valid cached credentials for copy-paste convenience
        try:
            state = GmailTrickState(config.output_dir)
            active_trial = state.get_active_valid_trial()
            if active_trial:
                email_cached = active_trial.get("email")
                password_cached = active_trial.get("password")
                expires_at = active_trial.get("expires_at")
                if email_cached and password_cached:
                    lines = [
                        "✨ CACHED ACTIVE TRIAL CREDENTIALS AVAILABLE:",
                        f"📧 Email:    {email_cached}",
                        f"🔑 Password: {password_cached}",
                        f"📅 Expires:  {expires_at}",
                        ""
                    ] + lines
        except Exception as e:
            Logger.debug(f"Failed to retrieve active trial details for manual login: {e}")

        _run_manual_login_fallback(auth, "MANUAL LOGIN MODE ACTIVE", lines)
        Logger.success("Manual setup complete. Please close and run the script normally to download courses.")
        return False

    if config.email and config.password:
        if auth.is_logged_in():
            Logger.success("Already logged in. Skipping auto-login.")
            return True
 
        if not auth.login(config.email, config.password, skip_precheck=True):
            if config.headless:
                raise HeadlessAutoLoginFailed()
 
            lines = [
                "⏳ Automatic credentials login failed (possible security challenge or CAPTCHA).",
                "👉 Please complete the login manually in the visible browser window.",
                "⏳ ONCE YOU ARE SUCCESSFULLY ON THE HOMEPAGE:",
                "👉 Press ENTER here in the terminal to continue..."
            ]
            if _run_manual_login_fallback(auth, "⚠️ AUTO-LOGIN FAILED (CAPTCHA/VERIFICATION REQUIRED)", lines):
                return True
            else:
                Logger.error("Authentication failed. (Invalid credentials or manual login not completed)")
                return False
        return True
 
    if not auth.is_logged_in():
        # Check if we have cached active trial credentials to automatically restore the session
        try:
            state = GmailTrickState(config.output_dir)
            active_trial = state.get_active_valid_trial()
            if active_trial:
                email_cached = active_trial.get("email")
                password_cached = active_trial.get("password")
                if email_cached and password_cached:
                    Logger.info("Detected valid active trial account in history. Attempting auto-login...")
                    if auth.login(email_cached, password_cached, skip_precheck=True):
                        Logger.success("Successfully logged in using cached trial credentials!")
                        return True
                    elif config.headless:
                        raise HeadlessAutoLoginFailed()
 
                    lines = [
                        "⏳ Automatic login using cached trial credentials failed.",
                        "👉 Please complete the login manually in the visible browser window.",
                        "⏳ ONCE YOU ARE SUCCESSFULLY ON THE HOMEPAGE:",
                        "👉 Press ENTER here in the terminal to continue..."
                    ]
                    if _run_manual_login_fallback(auth, "⚠️ AUTO-LOGIN FAILED FOR CACHED TRIAL", lines):
                        return True
        except HeadlessAutoLoginFailed:
            raise
        except Exception as e:
            Logger.debug(f"Failed during standard trial restore verification: {e}")
 
        Logger.error("Error: You are NOT logged in.")
        Logger.warning("👉 Solution: pass '--email' and '--password', OR use '--manual-login' / '--auto-signup'")
        return False
 
    return True
 
 
def _run_manual_login_fallback(auth: AuthService, panel_title: str, panel_lines: list) -> bool:
    """Helper method to run a guided manual login fallback flow (follows DRY principle)."""
    Logger.panel(panel_title, panel_lines, border_color=Fore.YELLOW)
    auth.driver.navigation.to("https://learning.oreilly.com/accounts/login/")
    input()
    if auth.is_logged_in():
        Logger.success(" Confirmed logged in manually. Profile saved!")
        return True
    Logger.error(" Warning: Could not detect logged-in state.")
    return False

