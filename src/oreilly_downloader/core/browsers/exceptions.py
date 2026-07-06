class AutomationError(Exception):
    """Base class for all browser automation exceptions"""
    pass

class NavigationError(AutomationError):
    pass

class InteractionError(AutomationError):
    pass

class WaitTimeout(AutomationError):
    pass
