import time
import contextlib
from typing import List, Dict, Any, Optional
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from .exceptions import NavigationError, InteractionError, WaitTimeout
from .element import Element
from .locator import Locator

class SeleniumNavigation:
    def __init__(self, browser, driver):
        self.browser = browser
        self._driver = driver

    def to(self, url: str) -> None:
        try:
            self._driver.get(url)
        except Exception as e:
            raise NavigationError(f"Failed to navigate to {url}: {e}") from e

    def refresh(self) -> None:
        try:
            self._driver.refresh()
        except Exception as e:
            raise NavigationError(f"Failed to refresh page: {e}") from e

    @contextlib.contextmanager
    def frame(self, frame_element: Element):
        raw_el = self.browser.actions._resolve_raw_handle(frame_element)
        try:
            self._driver.switch_to.frame(raw_el)
            yield
        except Exception as e:
            raise NavigationError(f"Error executing inside frame scope: {e}") from e
        finally:
            try:
                self._driver.switch_to.default_content()
            except Exception:
                pass

    @property
    def url(self) -> str:
        try:
            return self._driver.current_url
        except Exception as e:
            raise NavigationError(f"Failed to retrieve current URL: {e}") from e

    @property
    def title(self) -> str:
        try:
            return self._driver.title
        except Exception as e:
            raise NavigationError(f"Failed to retrieve page title: {e}") from e


class SeleniumActions:
    def __init__(self, browser, driver):
        self.browser = browser
        self._driver = driver

    def _map_strategy(self, strategy: str):
        mapping = {
            "css": By.CSS_SELECTOR,
            "xpath": By.XPATH,
            "id": By.ID,
            "class_name": By.CLASS_NAME,
            "tag_name": By.TAG_NAME
        }
        return mapping.get(strategy, By.CSS_SELECTOR)

    def _resolve_raw_handle(self, element: Element) -> Any:
        if element.cached_handle is not None:
            return element.cached_handle

        context = self._driver
        if element.parent is not None:
            context = self._resolve_raw_handle(element.parent)

        for strategy, value, index in element.locator._steps:
            by = self._map_strategy(strategy)
            try:
                if index is not None:
                    elements = context.find_elements(by, value)
                    if not elements or index >= len(elements):
                        raise InteractionError(f"Index {index} out of bounds for locator {strategy}={value}")
                    context = elements[index]
                else:
                     context = context.find_element(by, value)
            except Exception as e:
                 raise InteractionError(f"Failed to resolve element step {strategy}={value}: {e}") from e
        return context

    def _resolve_all_handles(self, element: Element) -> List[Any]:
        context = self._driver
        if element.parent is not None:
            context = self._resolve_raw_handle(element.parent)

        steps = element.locator._steps
        if not steps:
            return []

        for strategy, value, index in steps[:-1]:
            by = self._map_strategy(strategy)
            try:
                if index is not None:
                    elements = context.find_elements(by, value)
                    context = elements[index]
                else:
                    context = context.find_element(by, value)
            except Exception as e:
                raise InteractionError(f"Failed to resolve parent steps: {e}") from e

        strategy, value, index = steps[-1]
        by = self._map_strategy(strategy)
        try:
            elements = context.find_elements(by, value)
            if index is not None:
                return [elements[index]] if index < len(elements) else []
            return elements
        except Exception as e:
            raise InteractionError(f"Failed to resolve elements: {e}") from e

    def click(self, element: Element, force: bool = False):
        raw_el = self._resolve_raw_handle(element)
        if force:
            self._driver.execute_script("arguments[0].click();", raw_el)
        else:
            try:
                raw_el.click()
            except Exception:
                self._driver.execute_script("arguments[0].click();", raw_el)

    def fill(self, element: Element, text: str):
        raw_el = self._resolve_raw_handle(element)
        try:
            raw_el.clear()
            raw_el.send_keys(text)
        except Exception as e:
            raise InteractionError(f"Failed to input text: {e}") from e

    def clear(self, element: Element):
        raw_el = self._resolve_raw_handle(element)
        try:
            raw_el.clear()
        except Exception as e:
            raise InteractionError(f"Failed to clear input: {e}") from e

    def get_text(self, element: Element) -> str:
        try:
            raw_el = self._resolve_raw_handle(element)
            return raw_el.text
        except Exception as e:
            raise InteractionError(f"Failed to read element text: {e}") from e

    def is_selected(self, element: Element) -> bool:
        try:
            raw_el = self._resolve_raw_handle(element)
            return raw_el.is_selected()
        except Exception as e:
            raise InteractionError(f"Failed to check selection: {e}") from e

    def is_displayed(self, element: Element) -> bool:
        try:
            raw_el = self._resolve_raw_handle(element)
            return raw_el.is_displayed()
        except Exception as e:
            raise InteractionError(f"Failed to check visibility: {e}") from e

    def get_attribute(self, element: Element, name: str) -> Optional[str]:
        try:
            raw_el = self._resolve_raw_handle(element)
            return raw_el.get_attribute(name)
        except Exception as e:
            raise InteractionError(f"Failed to read attribute: {e}") from e

    def execute_js(self, script: str, *args) -> Any:
        try:
            unpacked = [self._resolve_raw_handle(arg) if isinstance(arg, Element) else arg for arg in args]
            return self._driver.execute_script(script, *unpacked)
        except Exception as e:
            raise InteractionError(f"JavaScript execution failed: {e}") from e

    def execute_async_js(self, script: str, *args) -> Any:
        try:
            unpacked = [self._resolve_raw_handle(arg) if isinstance(arg, Element) else arg for arg in args]
            return self._driver.execute_async_script(script, *unpacked)
        except Exception as e:
            raise InteractionError(f"Asynchronous JavaScript execution failed: {e}") from e

    def set_script_timeout(self, timeout: float):
        try:
            self._driver.set_script_timeout(timeout)
        except Exception as e:
            raise InteractionError(f"Failed to set script timeout: {e}") from e


class SeleniumWait:
    def __init__(self, browser, driver):
        self.browser = browser
        self._driver = driver

    def for_visible(self, element: Element, timeout: float = 15) -> Element:
        def check_visible(d):
            try:
                raw_el = self.browser.actions._resolve_raw_handle(element)
                if raw_el.is_displayed():
                    return raw_el
            except Exception:
                pass
            return False

        try:
            WebDriverWait(self._driver, timeout).until(check_visible)
            return element
        except Exception as e:
            raise WaitTimeout(f"Timed out waiting for element visibility ({timeout}s): {e}") from e

    def for_present(self, element: Element, timeout: float = 15) -> Element:
        def check_present(d):
            try:
                raw_el = self.browser.actions._resolve_raw_handle(element)
                if raw_el:
                    return raw_el
            except Exception:
                pass
            return False

        try:
            WebDriverWait(self._driver, timeout).until(check_present)
            return element
        except Exception as e:
            raise WaitTimeout(f"Timed out waiting for element presence ({timeout}s): {e}") from e

    def for_any(self, elements: List[Element], timeout: float = 15) -> Element:
        def check_any(d):
            for element in elements:
                try:
                    raw_el = self.browser.actions._resolve_raw_handle(element)
                    if raw_el:
                        return element
                except Exception:
                    pass
            return False

        try:
            return WebDriverWait(self._driver, timeout).until(check_any)
        except Exception as e:
            raise WaitTimeout(f"Timed out waiting for any of the elements ({timeout}s): {e}") from e

    def for_url_contains(self, text: str, timeout: float = 15) -> None:
        try:
            WebDriverWait(self._driver, timeout).until(
                EC.url_contains(text)
            )
        except Exception as e:
            raise WaitTimeout(f"Timed out waiting for URL to contain '{text}' ({timeout}s): {e}") from e

    def for_child_count(self, element: Element, child: Locator, count: int, timeout: float = 15) -> None:
        def check_child_count(d):
            try:
                child_ref = element.find(child)
                raw_children = self.browser.actions._resolve_all_handles(child_ref)
                if len(raw_children) > count:
                    return True
            except Exception:
                pass
            return False

        try:
            WebDriverWait(self._driver, timeout).until(check_child_count)
        except Exception as e:
            raise WaitTimeout(f"Timed out waiting for children count > {count} ({timeout}s): {e}") from e


class SeleniumCookies:
    def __init__(self, browser, driver):
        self.browser = browser
        self._driver = driver

    def get_all(self) -> List[Dict[str, Any]]:
        try:
            return self._driver.get_cookies()
        except Exception as e:
            raise InteractionError(f"Failed to fetch cookies: {e}") from e

    def clear(self) -> None:
        try:
            self._driver.delete_all_cookies()
        except Exception as e:
            raise InteractionError(f"Failed to clear cookies: {e}") from e
