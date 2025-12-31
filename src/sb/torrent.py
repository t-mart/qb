from collections.abc import Iterable
from pathlib import Path
from dataclasses import dataclass
import hashlib

import bencodepy


class TorrentException(Exception):
    pass


class MissingTorrentFileException(TorrentException):
    """Raised when the specified torrent file is missing."""

    def __init__(self, torrent_path: Path):
        self.torrent_path = torrent_path
        super().__init__(f"Torrent file not found: {torrent_path}")


class HashMismatchException(TorrentException):
    """Raised when a piece hash does not match the expected value."""

    def __init__(
        self,
        piece_index: int,
        expected_hash: bytes,
        actual_hash: bytes,
        files: list[Path],
    ):
        self.piece_index = piece_index
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        self.files = files
        super().__init__(
            f"Piece {piece_index} hash mismatch (files: {[str(file) for file in files]}). "
            f"Expected {expected_hash.hex()}, got {actual_hash.hex()}."
        )


class UnsupportedTorrentException(TorrentException):
    """Raised when the torrent format is unsupported."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Unsupported torrent format: {reason}")


@dataclass
class TorrentFile:
    """
    Represents a file within a torrent. The paths are relative to the download root.

    Note: I've seen some weirdness around how left-to-right markers (U+200E) are handled
    in torrent file names. Even though a torrent may specify a file name with such a
    character, the actual downloaded file may not have it. I'm not sure if this is due
    to qbittorrent, the filesystem, or something else. Be cautious when comparing file
    names. (Honestly, it's bad that these characters are in file names at all. This is
    certainly user error of the torrent author.)
    """

    size: int
    path: Path

    @classmethod
    def from_files_dict(cls, file_entry: dict[bytes, int | list[bytes]], root: Path):
        size = file_entry.get(b"length")
        if not isinstance(size, int):
            raise ValueError("Invalid torrent file entry: 'length' is not an integer.")
        path_segments = file_entry.get(b"path")
        if not isinstance(path_segments, list):
            raise ValueError("Invalid torrent file entry: 'path' is not a list.")
        path = root / Path(*[segment.decode("utf-8") for segment in path_segments])
        return cls(size=size, path=path)


@dataclass
class Torrent:
    name: Path
    size: int
    files: list[TorrentFile]
    piece_length: int
    infohash_v1: bytes  # we only support v1 for now
    pieces: list[bytes]

    @classmethod
    def from_path(cls, file_path: Path) -> Torrent:
        torrent_data = bencodepy.decode(file_path.read_bytes())

        info: dict = torrent_data.get(b"info")

        # The info hash is calculated from the raw bencoded bytes of the 'info' dict
        raw_info_bencoded = bencodepy.encode(info)
        if b"pieces" not in info:
            raise UnsupportedTorrentException("v2-only torrents are not supported.")
        infohash_v1 = hashlib.sha1(raw_info_bencoded).digest()

        # Parse the v1 piece hashes
        concatenated_pieces = info.get(b"pieces")
        pieces: list[bytes] = [
            concatenated_pieces[i : i + 20]
            for i in range(0, len(concatenated_pieces), 20)
        ]

        try:
            name = Path(info.get(b"name").decode("utf-8"))
        except UnicodeDecodeError as ude:
            raise UnsupportedTorrentException(
                f'Torrent name "{info.get(b"name")}" is not valid UTF-8: {ude}'
            ) from ude
        size: int = info.get(b"length", 0)
        piece_length = info.get(b"piece length")

        files_value = info.get(b"files")
        if files_value is None:
            # Single-file torrent
            files = [TorrentFile(size=size, path=name)]
        else:
            # Multi-file torrent
            files = [
                TorrentFile.from_files_dict(file, root=name)
                for file in info.get(b"files", [])
            ]

        return cls(
            name=name,
            size=size,
            piece_length=piece_length,
            pieces=pieces,
            files=files,
            infohash_v1=infohash_v1,
        )

    def file_check(self, download_path: Path) -> None:
        """
        Check that all files in the torrent exist at the given download path.

        This is a lesser check than `check`, which verifies piece hashes too.

        Raises:
            - MissingTorrentFileException: If any of the files are missing.
        """
        for torrent_file in self.files:
            file = download_path / torrent_file.path
            if not file.is_file():
                raise MissingTorrentFileException(file)

    def check(self, download_path: Path) -> None:
        """
        Check the integrity of the downloaded files against the torrent pieces.

        To only check for the existence of files, use `file_check`.

        Raises:
            - MissingTorrentFileException: If any of the files are missing.
            - HashMismatchException: If any piece does not match its expected hash.
        """

        @dataclass
        class Piece:
            index: int
            data: bytes
            files: list[TorrentFile]

        def pieces() -> Iterable[Piece]:
            buffer = bytearray()
            current_piece_index = 0
            current_piece_files: list[TorrentFile] = []
            bytes_remaining_in_piece = self.piece_length

            for torrent_file in self.files:
                file = download_path / torrent_file.path
                try:
                    with open(file, "rb") as f:
                        while True:
                            chunk = f.read(bytes_remaining_in_piece)
                            if not chunk:
                                break
                            buffer.extend(chunk)
                            current_piece_files.append(torrent_file)
                            bytes_remaining_in_piece -= len(chunk)

                            if bytes_remaining_in_piece == 0:
                                yield Piece(
                                    index=current_piece_index,
                                    data=bytes(buffer),
                                    files=current_piece_files,
                                )
                                current_piece_index += 1
                                buffer.clear()
                                current_piece_files = []
                                bytes_remaining_in_piece = self.piece_length
                except FileNotFoundError:
                    raise MissingTorrentFileException(file)

            # Handle any remaining data in the buffer (last piece)
            if buffer:
                yield Piece(
                    index=current_piece_index,
                    data=bytes(buffer),
                    files=current_piece_files,
                )

        for piece in pieces():
            expected_hash = self.pieces[piece.index]
            actual_hash = hashlib.sha1(piece.data).digest()
            if actual_hash != expected_hash:
                raise HashMismatchException(
                    piece_index=piece.index,
                    expected_hash=expected_hash,
                    actual_hash=actual_hash,
                    files=[file.path for file in piece.files],
                )
