from .browsers.locator import Locator

class LoginSelectors:
    SIGN_IN_BUTTONS = Locator.xpath(
        "//a[contains(@href, 'login') or contains(translate(text(), 'SIGN', 'sign'), 'sign in')]"
    )
    EMAIL_FIELD = Locator.id("email")
    CONTINUE_BTN = Locator.css(
        "button[data-testid='EmailSubmit'], button[type='submit']"
    )
    PASSWORD_FIELD = Locator.id("password")
    SIGNIN_BTN = Locator.css("button[data-testid='SignInBtn']")

class RegistrationSelectors:
    FIRST_NAME = Locator.id("first-name")
    LAST_NAME = Locator.id("last-name")
    EMAIL_INPUT = Locator.id("email-address")
    PASSWORD_INPUT = Locator.id("password")
    TERMS_CHECKBOX = Locator.id("terms-agreement")
    SUBMIT_BTN_CSS = Locator.css("button[type='submit']")
    SUBMIT_BTN_XPATH = Locator.xpath(
        "//button[contains(text(), 'Start free trial') or contains(text(), 'Start your free trial')]"
    )
    SUBMIT_BTN_FALLBACK = Locator.xpath("//form//button")
    OTP_INPUTS = Locator.class_name("orm-OneTimePasscode-otpInput")
    OTP_FALLBACK = Locator.xpath(
        "//input[contains(@class, 'otp') or contains(@class, 'OneTimePasscode')]"
    )

class ExtractorSelectors:
    BODY = Locator.tag_name("body")
    IFRAMES = Locator.tag_name("iframe")
    TRANSCRIPT_BODY = Locator.css("div[data-testid='transcript-body']")
    TRANSCRIPT_TOGGLE = Locator.css("button[data-testid='transcript-toggle']")
    TRANSCRIPT_CONTAINER = Locator.css("div[data-testid='transcript']")
    ACCORDION_SUMMARY = Locator.css("button.MuiAccordionSummary-root")
    VIDEO_ANCHORS = Locator.css("a[href*='/videos/']")
    BUTTON_GENERIC = Locator.css("button")

class AudiobookSelectors:
    HEADER = Locator.css("header[class*='_header_']")
    CONTENT_ICON = Locator.css("div[data-testid='contentIcon']")
    AUDIOBOOK_ICON = Locator.css("div[data-testid='contentIcon'] span.orm-icon-audio-book, span.orm-icon-audio-book")
    ICON_LABEL = Locator.css("div[data-testid='contentIcon'] span.orm-IconLabel-label")
    ICON_TITLE = Locator.css("div[data-testid='contentIcon'] span.orm-Icon-title")
    TITLE_HEADER = Locator.css("h1[data-datadog-id='ucv-title-header']")
