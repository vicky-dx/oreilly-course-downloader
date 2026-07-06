from .logger import Logger
import os
from colorama import Fore, init
import undetected_chromedriver as uc  # type: ignore
from .base import IBrowser

init(autoreset=True)


class StealthChromeBrowser(IBrowser):
    def __init__(self, headless=True, clean_session=False):
        self.headless = headless
        self.clean_session = clean_session
        self.driver = None

    def _get_options(self):
        opts = uc.ChromeOptions()
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--start-maximized")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")

        # NOTE: Do NOT spoof the User-Agent or manually change blink features!
        # undetected_chromedriver patches the chromedriver binary directly.
        if self.headless:
            opts.add_argument("--headless=new")
        return opts

    def _kill_zombie_chrome_processes(self, profile_dir: str):
        import subprocess
        if os.name == "nt":
            try:
                cmd = 'powershell -Command "Get-CimInstance Win32_Process -Filter \\"name = \'chrome.exe\'\\" | Where-Object { $_.CommandLine -like \'*browser_profile_stealth*\' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"'
                subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        else:
            try:
                output = subprocess.check_output(["lsof", "-t", profile_dir], text=True)
                pids = [p.strip() for p in output.split("\n") if p.strip()]
                for pid in pids:
                    subprocess.run(["kill", "-9", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def start(self):
        prof = os.path.join(os.getcwd(), "browser_profile_stealth")
        if self.clean_session:
            import shutil
            if os.path.exists(prof):
                Logger.warning("🧹 Cleaning previous browser session profile to ensure a fresh registration...")
                # Kill zombie processes first to release file locks
                self._kill_zombie_chrome_processes(prof)
                try:
                    shutil.rmtree(prof, ignore_errors=True)
                except Exception as e:
                    Logger.error(f" Could not fully clear session folder: {e}")

        lock_file = os.path.join(prof, "lockfile")

        if os.path.exists(lock_file):
            Logger.warning("🧹 Stale browser profile lock detected. Automatically cleaning up background processes...")
            self._kill_zombie_chrome_processes(prof)
            try:
                if os.path.exists(lock_file):
                    os.remove(lock_file)
            except Exception:
                pass

        Logger.info(f"🚀 Starting True Stealth Chrome (Headless: {self.headless})...")

        def handle_lock_error(exception):
            err_msg = str(exception)
            if "cannot connect to chrome" in err_msg.lower() or "chrome not reachable" in err_msg.lower():
                Logger.error("Browser Profile Lock Detected!")
                Logger.warning("It looks like background Chrome/Chromedriver processes from a previous run are still active and locking the profile directory:")
                Logger.warning(f"   Folder: {prof}")
                Logger.info("👉 Solution:")
                Logger.info("   1. Open Task Manager and terminate any active 'chrome.exe' or 'chromedriver.exe' processes.")
                Logger.info("   2. Alternatively, run the script with '--browser chrome' or '--browser firefox'.")
                return RuntimeError("Chrome profile locked by background processes. Please clean up Task Manager and rerun.")
            return exception

        try:
            raw_driver = uc.Chrome(options=self._get_options(), user_data_dir=prof)
        except Exception as e:
            err_msg = str(e)
            
            # Handle version mismatch first
            if "supports chrome version" in err_msg.lower():
                import re

                match = re.search(r"current browser version is (\d+)", err_msg, re.IGNORECASE)
                if match:
                    ver = int(match.group(1))
                    Logger.warning(f" Chrome version mismatch. Retrying with driver version {ver}...")
                    try:
                        raw_driver = uc.Chrome(
                            options=self._get_options(),
                            user_data_dir=prof,
                            version_main=ver,
                        )
                    except Exception as retry_e:
                        retry_lock_err = handle_lock_error(retry_e)
                        raise retry_lock_err
                else:
                    raise e
            else:
                # Check if it's a lock connection error
                lock_err = handle_lock_error(e)
                raise lock_err

        from .browser import Browser
        self.raw_driver = raw_driver
        self.driver = Browser(raw_driver)
        return self.driver

    def stop(self):
        if hasattr(self, 'raw_driver') and self.raw_driver:
            self.raw_driver.quit()

