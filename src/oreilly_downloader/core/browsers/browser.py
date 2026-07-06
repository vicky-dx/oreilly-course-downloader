from .selenium_adapter import SeleniumNavigation, SeleniumActions, SeleniumWait, SeleniumCookies
from .element import Element
from .locator import Locator

class Browser:
    def __init__(self, raw_driver):
        self.raw_driver = raw_driver
        self.navigation = SeleniumNavigation(self, raw_driver)
        self.actions = SeleniumActions(self, raw_driver)
        self.wait = SeleniumWait(self, raw_driver)
        self.cookies = SeleniumCookies(self, raw_driver)

    def find_element(self, locator: Locator) -> Element:
        return Element(self, locator)

    def find_elements(self, locator: Locator) -> list[Element]:
        handles = self.actions._resolve_all_handles(Element(self, locator))
        return [Element(self, locator, cached_handle=h) for h in handles]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()

    def quit(self):
        if self.raw_driver:
            try:
                self.raw_driver.quit()
            except Exception:
                pass
