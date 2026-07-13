# qb

A CLI for driving one or more remote qBittorrent instances over their Web UI
API. Personal tooling for managing seedboxes.

## Layout

- `src/qb/__main__.py` - Click CLI. A single top-level group `qb` with the
  commands `add`, `cp`, `ls`, `recheck`, `start`. The `qb = "qb.__main__:qb"`
  entry point in `pyproject.toml` exposes it as the `qb` executable.
- `src/qb/client.py` - `QBittorrentClient`, a thin wrapper over the
  `qbittorrent-api` `Client`. Owns login/logout (also a context manager),
  listing, adding, rechecking, starting, and exporting torrents. Also defines
  the status vocabulary.
- `src/qb/config.py` - Pydantic config models and loading.
- `src/qb/torrent.py` - `Torrent.from_path`, which parses a `.torrent` file to
  get its name and v1 infohash. Only v1 torrents are supported.

## Config

Loaded from `~/.config/qb/config.yaml` (or `.yml`). Shape:

```yaml
clients:
  aClient:
    url: "http://localhost:8080"
    username: "admin"
    password: "adminadmin"
```

`Config.clients` is a map of client name to `ClientConfig` (`url`, `username`,
`password`). Commands take a client name (or a comma-separated list) and look it
up here. The port is part of `url` (the `qbittorrent-api` `Client` honors a port
embedded in the host URL), so there is no separate port field.

## Statuses

`--status-filter` / `-s` uses `qb_torrent_statuses` in `client.py`: the stock
`qbittorrent-api` `TorrentStatusesT` values plus two custom ones,
`stopped_complete` and `stopped_downloading`. The custom ones are resolved
client-side in `list_torrents` (qBittorrent has no native "stopped and complete"
filter): it filters on torrent `state` (`stoppedUP` / `stoppedDL`) after
fetching. Everything else is passed straight through to `torrents_info`.

## Adding torrents (the recheck flow)

qBittorrent's add is fire-and-forget: `torrents_add` returns before the torrent
is registered, so rechecking a just-added hash can no-op. `add_and_wait` adds a
torrent paused, then polls `torrents_info` until the expected infohash appears
(or a timeout). `add` and `cp` only add a hash to the recheck set once
`add_and_wait` confirms it registered, then issue one batched `start_recheck`.
`add` dedupes against existing hashes locally (via `Torrent.infohash_v1`) before
submitting; `cp` copies only hashes missing on the target and preserves the
source category.

## Conventions

- Human-readable progress goes to stderr (`click.echo(..., err=True)`); only
  machine output (e.g. `ls` JSON) goes to stdout.
- Most mutating commands accept `--dry-run`.

## Dev

- `uv run qb --help` to run the CLI from source.
- `uv lock` after changing dependencies or the project name.
- No test runner or linter is configured. Sample torrents for manual checks live
  in `test/example-torrents/`.
- Requires Python >= 3.14.
