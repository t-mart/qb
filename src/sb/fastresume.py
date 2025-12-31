from pathlib import Path
from dataclasses import dataclass

import bencodepy


@dataclass
class FastResume:
    """Represents the structure of a qBittorrent fastresume file."""

    save_path: str
    category: str | None
    tags: list[str]

    @classmethod
    def from_path(cls, file_path: Path) -> FastResume:
        bencoded_data = bencodepy.decode(file_path.read_bytes())

        save_path = bencoded_data.get(b"save_path", b"").decode("utf-8")

        tags = [tag.decode("utf-8") for tag in bencoded_data.get(b"qBt-tags", [])]

        category_data = bencoded_data.get(b"qBt-category", None)
        if category_data is None or category_data == b"":
            category = None
        else:
            category = category_data.decode("utf-8")

        return cls(save_path=save_path, tags=tags, category=category)
