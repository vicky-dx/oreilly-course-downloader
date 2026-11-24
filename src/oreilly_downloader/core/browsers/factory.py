from typing import Optional, Dict, Type, List
from .base import IBrowser
from .stealth import StealthChromeBrowser
from .firefox import FirefoxBrowser
from .chrome import ChromeBrowser


class BrowserFactory:
    """Extensible factory using the Registry pattern (Open/Closed Principle).
    New browser drivers can be registered dynamically without modifying this class.
    """
    _registry: Dict[str, Type[IBrowser]] = {}

    @classmethod
    def register(cls, name: str, browser_cls: Type[IBrowser]) -> None:
        """Registers a browser driver implementation class under a given name."""
        cls._registry[name.strip().lower()] = browser_cls

    @classmethod
    def unregister(cls, name: str) -> None:
        """Unregisters a browser driver implementation class."""
        cls._registry.pop(name.strip().lower(), None)

    @classmethod
    def get_registered_types(cls) -> List[str]:
        """Returns the list of all currently registered browser types."""
        return list(cls._registry.keys())

    @classmethod
    def create(
        cls,
        browser_type: str,
        headless: bool = True,
        clean_session: bool = False,
        browser_binary: Optional[str] = None,
    ) -> IBrowser:
        key = (browser_type or "").strip().lower()
        browser_cls = cls._registry.get(key)
        if not browser_cls:
            available = ", ".join(sorted(cls._registry.keys()))
            raise ValueError(f"Unknown browser type: {browser_type}. Available types: [{available}]")

        return browser_cls(
            headless=headless,
            clean_session=clean_session,
            browser_binary=browser_binary,
        )


# Pre-register built-in browser implementations
BrowserFactory.register("stealth", StealthChromeBrowser)
BrowserFactory.register("firefox", FirefoxBrowser)
BrowserFactory.register("chrome", ChromeBrowser)
