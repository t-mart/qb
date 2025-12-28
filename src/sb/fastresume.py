from pathlib import Path
from dataclasses import dataclass

import bencodepy

@dataclass
class FastResume:
    """Represents the structure of a qBittorrent fastresume file."""

    save_path: str

    @classmethod
    def from_path(cls, file_path: Path):
        bencoded_data = bencodepy.decode(file_path.read_bytes())
        save_path = bencoded_data.get(b"save_path", b"").decode("utf-8")
        return cls(save_path=save_path)