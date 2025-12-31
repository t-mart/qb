from dataclasses import dataclass


@dataclass
class Category:
    _parts: list[str]

    @classmethod
    def from_string(cls, category_str: str) -> Category:
        parts = category_str.split("/")
        return cls(parts)

    def __str__(self) -> str:
        return "/".join(self._parts)

    def __repr__(self) -> str:
        return f"Category({str(self)})"

    @property
    def parent(self) -> Category | None:
        if len(self._parts) <= 1:
            return None
        return Category(self._parts[:-1])

    def is_subcategory_of(self, other: Category) -> bool:
        if len(self._parts) < len(other._parts):
            return False
        return self._parts[: len(other._parts)] == other._parts
