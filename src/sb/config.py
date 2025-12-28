from dataclasses import dataclass
from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel, Field
import yaml

config_path = Path.home() / ".config/sb/config.yaml"


class ClientConfig(BaseModel):
    url: str
    username: str
    password: str


class QBittorrentConfig(BaseModel):
    clients: dict[str, ClientConfig]


@dataclass
class BTBackupTorrentTuple:
    torrent_path: Path
    fastresume_path: Path


class Config(BaseModel):
    qb: QBittorrentConfig
    download_roots: list[Path] = Field(default_factory=list)
    local_qb_config_dir: Path | None = None

    @classmethod
    def load_from_file(cls):
        with config_path.open("r", encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f)
        return cls(**yaml_config)

    @property
    def qb_conf_file_path(self) -> Path | None:
        if self.local_qb_config_dir:
            return self.local_qb_config_dir / "qBittorrent.conf"
        return None

    @property
    def qb_bt_backup_dir_path(self) -> Path | None:
        if self.local_qb_config_dir:
            return self.local_qb_config_dir / "BT_backup"
        return None

    def qb_bt_backup_torrent_tuples(self) -> Iterator[BTBackupTorrentTuple]:
        bt_backup_dir = self.qb_bt_backup_dir_path
        if not bt_backup_dir or not bt_backup_dir.is_dir():
            return iter(())
        for fastresume_path in bt_backup_dir.glob("*.fastresume"):
            torrent_path = fastresume_path.with_suffix(".torrent")
            if torrent_path.exists():
                yield BTBackupTorrentTuple(
                    torrent_path=torrent_path,
                    fastresume_path=fastresume_path,
                )


if __name__ == "__main__":
    config = Config.load_from_file()
    print(config)
