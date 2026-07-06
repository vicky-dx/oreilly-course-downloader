from .browser import Browser

class IBrowser:
    def start(self) -> Browser:
        pass

    def stop(self) -> None:
        pass

