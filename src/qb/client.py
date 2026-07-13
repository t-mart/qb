import time
from types import TracebackType
from qbittorrentapi import Client
from qbittorrentapi.exceptions import APIConnectionError
from qbittorrentapi.torrents import TorrentStatusesT, TorrentFilesT
from typing import Literal, cast, Iterable, get_args

from qb.config import ClientConfig

type AddResponse = Literal["Ok.", "Fails."]
type HashList = str | Iterable[str] | None


type QBTorrentStatus = (
    TorrentStatusesT | Literal["stopped_complete"] | Literal["stopped_downloading"]
)
# ugh, get_args does not work nicely on Literal unions
qb_torrent_statuses = list(get_args(TorrentStatusesT)) + [
    "stopped_complete",
    "stopped_downloading",
]


class FailedAddException(Exception):
    pass


class QBConnectionError(Exception):
    """Raised when a client cannot be reached."""

    pass


class QBittorrentClient:
    def __init__(self, host: str, username: str, password: str):
        self.host = host
        self.client = Client(host=host, username=username, password=password)

    @classmethod
    def from_config(cls, config: ClientConfig) -> QBittorrentClient:
        return cls(
            host=config.url,
            username=config.username,
            password=config.password,
        )

    def login(self):
        try:
            self.client.auth_log_in()
        except APIConnectionError as e:
            raise QBConnectionError(
                f"Could not connect to qBittorrent at {self.host}. "
                "Check that the URL (including port) in your config is correct "
                "and that the client is reachable."
            ) from e

    def logout(self):
        self.client.auth_log_out()

    def __enter__(self):
        self.login()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        self.logout()

    def _add_paused_torrent(self, path_or_data: TorrentFilesT, category: str | None):
        response = cast(
            AddResponse,
            self.client.torrents_add(
                torrent_files=path_or_data,
                category=category,
                is_paused=True,
            ),
        )
        if response == "Fails.":
            raise FailedAddException("Failed to add torrent.")

    def add_and_wait(
        self,
        path_or_data: TorrentFilesT,
        expected_hash: str,
        category: str | None,
        *,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """
        Add a paused torrent, then block until the client has registered it.

        qBittorrent's add is fire-and-forget: it returns immediately and
        materializes the torrent asynchronously. Waiting for the hash to appear
        before we act on it (e.g. rechecking) avoids operating on a torrent the
        client does not yet know about.

        Returns True if the torrent appeared within `timeout`, False otherwise.

        Raises:
            - FailedAddException: If the client rejected the add outright.
        """
        self._add_paused_torrent(path_or_data, category)

        deadline = time.monotonic() + timeout
        while True:
            if self.client.torrents_info(torrent_hashes=expected_hash):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(poll_interval)

    def list_torrents(
        self,
        *,
        status_filter: QBTorrentStatus | None = None,
        category_filter: str | None = None,
        hashes: HashList = None,
    ):
        stopped_complete = False
        stopped_downloading = False
        if status_filter == "stopped_complete":
            stopped_complete = True
            status_filter = None
        elif status_filter == "stopped_downloading":
            stopped_downloading = True
            status_filter = None

        torrents = self.client.torrents_info(
            category=category_filter,
            status_filter=status_filter,
            torrent_hashes=hashes,
        )

        if stopped_complete:
            torrents = [t for t in torrents if t.state == "stoppedUP"]
        elif stopped_downloading:
            torrents = [t for t in torrents if t.state == "stoppedDL"]

        return torrents

    def start_recheck(self, hashes: HashList):
        """
        Start a recheck for the torrents with the given hashes.

        Note that this does not wait for the recheck to complete.
        """
        self.client.torrents_recheck(torrent_hashes=hashes)

    def export(self, torrent_hash: str) -> bytes:
        """Export the raw torrent data for the torrent with the given hash."""
        return self.client.torrents_export(torrent_hash=torrent_hash)

    def start(self, hashes: HashList):
        """Start the torrents with the given hashes."""
        self.client.torrents_start(torrent_hashes=hashes)
