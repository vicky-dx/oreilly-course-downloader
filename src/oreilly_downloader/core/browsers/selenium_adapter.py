import time
import contextlib
import sys
from typing import List, Dict, Any, Optional
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
    ElementClickInterceptedException,
    ElementNotInteractableException
)
from .exceptions import NavigationError, InteractionError, WaitTimeout
from .element import Element
from .locator import Locator

STRATEGY_MAP = {
    "css": By.CSS_SELECTOR,
    "xpath": By.XPATH,
    "id": By.ID,
    "class_name": By.CLASS_NAME,
    "tag_name": By.TAG_NAME
}

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
        return STRATEGY_MAP.get(strategy, By.CSS_SELECTOR)

    def _clear_cache(self, element: Element):
        curr = element
        while curr is not None:
            curr.cached_handle = None
            curr = curr.parent

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
            except StaleElementReferenceException:
                raise
            except Exception as e:
                 raise InteractionError(f"Failed to resolve element step {strategy}={value}: {e}") from e
        element.cached_handle = context
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
            except StaleElementReferenceException:
                raise
            except Exception as e:
                raise InteractionError(f"Failed to resolve parent steps: {e}") from e

        strategy, value, index = steps[-1]
        by = self._map_strategy(strategy)
        try:
            elements = context.find_elements(by, value)
            if index is not None:
                if 0 <= index < len(elements):
                    return [elements[index]]
                return []
            return elements
        except StaleElementReferenceException:
            raise
        except Exception as e:
            raise InteractionError(f"Failed to resolve elements: {e}") from e

    def _execute_with_retry(self, element: Optional[Element], action_fn, *args, **kwargs):
        last_exc = None
        transient_exceptions = (
            StaleElementReferenceException,
            ElementClickInterceptedException,
            ElementNotInteractableException
        )
        for attempt in range(3):
            try:
                if element is not None:
                    raw_el = self._resolve_raw_handle(element)
                    return action_fn(raw_el, *args, **kwargs)
                else:
                    return action_fn(*args, **kwargs)
            except Exception as e:
                cause = e
                if isinstance(e, InteractionError) and e.__cause__:
                    cause = e.__cause__
                if isinstance(cause, transient_exceptions):
                    last_exc = cause
                    if element is not None:
                        self._clear_cache(element)
                    for arg in args:
                        if isinstance(arg, Element):
                            self._clear_cache(arg)
                    for k, v in kwargs.items():
                        if isinstance(v, Element):
                            self._clear_cache(v)
                    if attempt < 2:
                        time.sleep(0.1 * (2 ** attempt))
                    continue
                raise e
        if last_exc:
            raise last_exc

    def _ensure_actionable(self, raw_el: Any):
        # 1. Attached check
        try:
            _ = raw_el.tag_name
        except StaleElementReferenceException:
            raise

        # 2. Visible check
        if not raw_el.is_displayed():
            raise ElementNotInteractableException("Element is not visible")

        # 3. Enabled check
        if not raw_el.is_enabled():
            raise ElementNotInteractableException("Element is not enabled")

        # 4. Stability check (position stability check)
        try:
            loc1 = raw_el.location
            size1 = raw_el.size
            time.sleep(0.02)
            loc2 = raw_el.location
            size2 = raw_el.size
            if loc1 != loc2 or size1 != size2:
                raise ElementNotInteractableException("Element is not stable (moving/resizing)")
        except Exception:
            pass

    def click(self, element: Element, force: bool = False):
        def _action(raw_el):
            if force:
                self._driver.execute_script("arguments[0].click();", raw_el)
                return

            self._ensure_actionable(raw_el)

            # Strategy 1: Standard Scroll & Click
            try:
                self._driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", raw_el)
                raw_el.click()
                return
            except StaleElementReferenceException:
                raise
            except Exception:
                pass

            # Strategy 2: ActionChains Hover & Click
            try:
                ActionChains(self._driver).move_to_element(raw_el).click().perform()
                return
            except StaleElementReferenceException:
                raise
            except Exception:
                pass

            # Strategy 3: JS fallback click
            try:
                self._driver.execute_script("arguments[0].click();", raw_el)
                return
            except StaleElementReferenceException:
                raise
            except Exception as e:
                raise InteractionError(f"All click strategies failed: {e}") from e

        try:
            self._execute_with_retry(element, _action)
        except Exception as e:
            raise InteractionError(f"Failed to click element: {e}") from e

    def fill(self, element: Element, text: str):
        def _action(raw_el):
            self._ensure_actionable(raw_el)

            # Strategy 1: Standard focus, clear & type
            try:
                try:
                    raw_el.click()
                except Exception:
                    pass
                raw_el.clear()
                raw_el.send_keys(text)
                if raw_el.get_attribute("value") == text:
                    return
            except StaleElementReferenceException:
                raise
            except Exception:
                pass

            # Strategy 2: Keyboard emulation (Control+A, Backspace, Type)
            try:
                cmd_ctrl = Keys.COMMAND if sys.platform == "darwin" else Keys.CONTROL
                try:
                    raw_el.click()
                except Exception:
                    pass
                raw_el.send_keys(cmd_ctrl + "a")
                raw_el.send_keys(Keys.BACKSPACE)
                raw_el.send_keys(text)
                if raw_el.get_attribute("value") == text:
                    return
            except StaleElementReferenceException:
                raise
            except Exception:
                pass

            # Strategy 3: JS value setting & event dispatch (with focus and blur)
            try:
                self._driver.execute_script(
                    "arguments[0].dispatchEvent(new Event('focus', { bubbles: true }));"
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
                    "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));"
                    "arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));",
                    raw_el, text
                )
                if raw_el.get_attribute("value") == text:
                    return
            except StaleElementReferenceException:
                raise
            except Exception:
                pass

            # Fallback assertion check
            if raw_el.get_attribute("value") != text:
                raise InteractionError(f"Verification failed: filled value '{raw_el.get_attribute('value')}' does not match expected '{text}'")

        try:
            self._execute_with_retry(element, _action)
        except Exception as e:
            raise InteractionError(f"Failed to input text: {e}") from e

    def clear(self, element: Element):
        try:
            self._execute_with_retry(element, lambda el: el.clear())
        except Exception as e:
            raise InteractionError(f"Failed to clear input: {e}") from e

    def get_text(self, element: Element) -> str:
        try:
            return self._execute_with_retry(element, lambda el: el.text)
        except Exception as e:
            raise InteractionError(f"Failed to read element text: {e}") from e

    def is_selected(self, element: Element) -> bool:
        try:
            return self._execute_with_retry(element, lambda el: el.is_selected())
        except Exception as e:
            raise InteractionError(f"Failed to check selection: {e}") from e

    def is_displayed(self, element: Element) -> bool:
        try:
            return self._execute_with_retry(element, lambda el: el.is_displayed())
        except Exception as e:
            raise InteractionError(f"Failed to check visibility: {e}") from e

    def get_attribute(self, element: Element, name: str) -> Optional[str]:
        try:
            return self._execute_with_retry(element, lambda el: el.get_attribute(name))
        except Exception as e:
            raise InteractionError(f"Failed to read attribute: {e}") from e

    def execute_js(self, script: str, *args) -> Any:
        def _action(*args_passed):
            unpacked = [self._resolve_raw_handle(arg) if isinstance(arg, Element) else arg for arg in args_passed]
            return self._driver.execute_script(script, *unpacked)

        try:
            return self._execute_with_retry(None, _action, *args)
        except Exception as e:
            raise InteractionError(f"JavaScript execution failed: {e}") from e

    def execute_async_js(self, script: str, *args) -> Any:
        def _action(*args_passed):
            unpacked = [self._resolve_raw_handle(arg) if isinstance(arg, Element) else arg for arg in args_passed]
            return self._driver.execute_async_script(script, *unpacked)

        try:
            return self._execute_with_retry(None, _action, *args)
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

    def _wait_for(self, element: Element, check_fn, timeout: float = 15, error_msg: str = "") -> Element:
        def check_wrapper(d):
            try:
                raw_el = self.browser.actions._resolve_raw_handle(element)
                if check_fn(raw_el):
                    return raw_el
            except StaleElementReferenceException:
                self.browser.actions._clear_cache(element)
            except Exception:
                pass
            return False

        try:
            WebDriverWait(self._driver, timeout).until(check_wrapper)
            return element
        except Exception as e:
            msg = error_msg or f"Timed out waiting for condition ({timeout}s)"
            raise WaitTimeout(f"{msg}: {e}") from e

    def for_visible(self, element: Element, timeout: float = 15) -> Element:
        return self._wait_for(
            element,
            lambda el: el.is_displayed(),
            timeout,
            "Timed out waiting for element visibility"
        )

    def for_present(self, element: Element, timeout: float = 15) -> Element:
        def _check(el):
            if el:
                _ = el.tag_name
                return True
            return False
        return self._wait_for(
            element,
            _check,
            timeout,
            "Timed out waiting for element presence"
        )

    def for_clickable(self, element: Element, timeout: float = 15) -> Element:
        return self._wait_for(
            element,
            lambda el: el.is_displayed() and el.is_enabled(),
            timeout,
            "Timed out waiting for element to be clickable"
        )

    def for_enabled(self, element: Element, timeout: float = 15) -> Element:
        return self._wait_for(
            element,
            lambda el: el.is_enabled(),
            timeout,
            "Timed out waiting for element to be enabled"
        )

    def for_hidden(self, element: Element, timeout: float = 15) -> Element:
        def check_hidden(d):
            try:
                raw_el = self.browser.actions._resolve_raw_handle(element)
                if not raw_el.is_displayed():
                    return True
            except StaleElementReferenceException:
                self.browser.actions._clear_cache(element)
                return True
            except NoSuchElementException:
                self.browser.actions._clear_cache(element)
                return True
            except InteractionError as ie:
                cause = ie.__cause__ or ie
                if isinstance(cause, (NoSuchElementException, StaleElementReferenceException)):
                    self.browser.actions._clear_cache(element)
                    return True
                raise ie
            except Exception as e:
                raise e
            return False

        try:
            WebDriverWait(self._driver, timeout).until(check_hidden)
            return element
        except Exception as e:
            raise WaitTimeout(f"Timed out waiting for element to be hidden ({timeout}s): {e}") from e

    def for_text(self, element: Element, text: str, timeout: float = 15) -> Element:
        return self._wait_for(
            element,
            lambda el: text in el.text,
            timeout,
            f"Timed out waiting for element text '{text}'"
        )

    def for_value(self, element: Element, value: str, timeout: float = 15) -> Element:
        return self._wait_for(
            element,
            lambda el: el.get_attribute("value") == value,
            timeout,
            f"Timed out waiting for element value '{value}'"
        )

    def for_attribute(self, element: Element, attr: str, value: str, timeout: float = 15) -> Element:
        return self._wait_for(
            element,
            lambda el: el.get_attribute(attr) == value,
            timeout,
            f"Timed out waiting for element attribute '{attr}={value}'"
        )

    def for_any(self, elements: List[Element], timeout: float = 15) -> Element:
        def check_any(d):
            for element in elements:
                try:
                    raw_el = self.browser.actions._resolve_raw_handle(element)
                    if raw_el:
                        _ = raw_el.tag_name
                        return element
                except StaleElementReferenceException:
                    self.browser.actions._clear_cache(element)
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
                for raw_child in raw_children:
                    _ = raw_child.tag_name
                if len(raw_children) >= count:
                    return True
            except StaleElementReferenceException:
                self.browser.actions._clear_cache(element)
            except Exception:
                pass
            return False

        try:
            WebDriverWait(self._driver, timeout).until(check_child_count)
        except Exception as e:
            raise WaitTimeout(f"Timed out waiting for children count >= {count} ({timeout}s): {e}") from e


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
