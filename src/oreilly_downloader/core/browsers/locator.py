class Locator:
    def __init__(self, steps: list):
        self._steps = steps  # List of tuples: (strategy, value, filter_index)

    @classmethod
    def css(cls, selector: str):
        return cls([("css", selector, None)])

    @classmethod
    def xpath(cls, path: str):
        return cls([("xpath", path, None)])

    @classmethod
    def id(cls, id_: str):
        return cls([("id", id_, None)])

    @classmethod
    def class_name(cls, class_name: str):
        return cls([("class_name", class_name, None)])

    @classmethod
    def tag_name(cls, tag_name: str):
        return cls([("tag_name", tag_name, None)])

    def child(self, selector: str) -> "Locator":
        return Locator(self._steps + [("css", selector, None)])

    def nth(self, index: int) -> "Locator":
        if not self._steps:
            raise ValueError("Cannot apply index to empty locator.")
        last_step = self._steps[-1]
        updated_step = (last_step[0], last_step[1], index)
        return Locator(self._steps[:-1] + [updated_step])

    def first(self) -> "Locator":
        return self.nth(0)

    def __eq__(self, other):
        if not isinstance(other, Locator):
            return False
        return self._steps == other._steps

    def __repr__(self):
        return f"Locator({self._steps})"
