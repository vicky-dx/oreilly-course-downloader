from typing import Optional, Any
from .locator import Locator

class Element:
    def __init__(self, browser, locator: Locator, parent: Optional["Element"] = None, cached_handle: Any = None):
        self.browser = browser
        self.locator = locator
        self.parent = parent
        self.cached_handle = cached_handle

    def pin(self) -> "Element":
        """Resolves the element immediately and returns a locked-identity static Element."""
        handle = self.browser.actions._resolve_raw_handle(self)
        return Element(self.browser, self.locator, self.parent, cached_handle=handle)

    def find(self, locator: Locator) -> "Element":
        """Dynamic nested element search (natural locator chains)"""
        return Element(self.browser, locator, parent=self)

    def click(self):
        self.browser.actions.click(self)

    def fill(self, text: str):
        self.browser.actions.fill(self, text)

    def send_keys(self, keys: str):
        self.browser.actions.fill(self, keys)

    def clear(self):
        self.browser.actions.clear(self)

    def is_selected(self) -> bool:
        return self.browser.actions.is_selected(self)

    def is_displayed(self) -> bool:
        return self.browser.actions.is_displayed(self)

    def get_attribute(self, name: str) -> Optional[str]:
        return self.browser.actions.get_attribute(self, name)

    @property
    def text(self) -> str:
        return self.browser.actions.get_text(self)
