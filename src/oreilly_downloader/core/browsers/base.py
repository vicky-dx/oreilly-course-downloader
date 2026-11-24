from abc import ABC, abstractmethod
from typing import Optional
from .browser import Browser


class IBrowser(ABC):
    """Abstract lifecycle manager for a browser process (LSP).
    Implementations manage the process lifecycle (start/stop) and expose the active Browser driver.
    """
    driver: Optional[Browser] = None

    @abstractmethod
    def start(self) -> Browser:
        """Starts the browser process and returns the active Browser wrapper."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stops and terminates the browser process."""
        pass

