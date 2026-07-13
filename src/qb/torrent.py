from pathlib import Path
from dataclasses import dataclass
import hashlib

import bencodepy


class TorrentException(Exception):
    pass


class UnsupportedTorrentException(TorrentException):
    """Raised when the torrent format is unsupported."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Unsupported torrent format: {reason}")


@dataclass
class Torrent:
    name: Path
    infohash_v1: bytes  # we only support v1 for now

    @classmethod
    def from_path(cls, file_path: Path) -> Torrent:
        torrent_data = bencodepy.decode(file_path.read_bytes())

        info: dict = torrent_data.get(b"info")

        if b"pieces" not in info:
            raise UnsupportedTorrentException("v2-only torrents are not supported.")

        # The info hash is calculated from the raw bencoded bytes of the 'info' dict
        raw_info_bencoded = bencodepy.encode(info)
        infohash_v1 = hashlib.sha1(raw_info_bencoded).digest()

        try:
            name = Path(info.get(b"name").decode("utf-8"))
        except UnicodeDecodeError as ude:
            raise UnsupportedTorrentException(
                f'Torrent name "{info.get(b"name")}" is not valid UTF-8: {ude}'
            ) from ude

        return cls(name=name, infohash_v1=infohash_v1)
