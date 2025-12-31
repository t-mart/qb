from pathlib import Path
from typing import Iterator
import unicodedata


def iter_variants(path: Path) -> Iterator[Path]:
    for normed in iter_norms(path):
        # for variant in with_and_without_left_to_right_mark(normed):
        if normed != path:
            yield normed


def iter_norms(path: Path) -> Iterator[Path]:
    seen: set[Path] = set()

    for norm in ["NFC", "NFD", "NFKC", "NFKD"]:
        normed = Path(
            *[
                unicodedata.normalize(
                    norm,  # type: ignore[arg-type]
                    part,
                )
                for part in path.parts
            ]
        )
        if normed not in seen:
            seen.add(normed)
            yield normed


# left_to_right_mark = "\u200e"


# def with_and_without_left_to_right_mark(path: Path) -> Iterator[Path]:
#     """
#     Yield the given path as-is. Then, if it contains any left-to-right marks (U+200E),
#     also yield a version with them removed.

#     Somehow, this insidious character sometimes gets inserted into filenames in torrents
#     (have had 5+ torrents affected), and due to some program's agressive normalization
#     (probably syncthing), the character gets removed, causing torrent file mismatches.
#     """
#     yield path

#     without = Path(*[part.replace(left_to_right_mark, "") for part in path.parts])
#     if without != path:
#         yield without
