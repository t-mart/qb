# qb

`qb` is a CLI application for managing seedboxes running qBittorrent. At least,
my seedboxes and my setup. Some consideration has been given to making it more
generally useful, but no guarantees.

## Installation

```sh
uv tool install git+https://github.com/t-mart/qb.git
```

## Config

Config in YAML format is stored in `~/.config/qb/config.yaml`.

```yaml
clients:
  aClient:
    url: "http://localhost:8080"
    username: "admin"
    password: "adminadmin"

  bClient:
    url: "http://otherhost:8080"
    username: "user"
    password: "pass"
```

Clients identify instances of qBittorrent running the web UI. Each client has a
name (like `aClient` or `bClient` above) and connection details. Include the
port in `url` when the client is not on the scheme's default port.

## Statuses

Many commands accept a `--status-filter` (`-s`) option to filter which torrents
to operate on.

The possible statuses are:

- `all`: All torrents, regardless of state. (This is the same as not providing a
  status filter at all.)
- `downloading`: Downloading data
- `seeding`: Uploading data
- `completed`: All data locally present (not necessarily seeding)
- `stopped` or `paused`: Stopped by the user
- `running` or `resumed`: Not stopped by the user
- `active`: Uploading or downloading data
- `inactive`: Neither uploading nor downloading data
- `stalled_uploading`: Not uploading
- `stalled_downloading`: Not downloading
- `stalled`: Not uploading nor downloading
- `checking`: Being checked
- `moving`: Being moved
- `errored`: In an error state
- `stopped_complete`: `stopped` and `completed`
- `stopped_downloading`: `stopped` and not `completed`

Note that many statuses are overlapping. For example, a torrent that is
`seeding` is also `active` and `running`.

## Categories

Many commands accept a `--category-filter` (`-c`) option to filter which
torrents to operate on.

If the client utilizes subcategories, they are selected when specifying the
parent category. For example, `--category-filter movies` will select torrents
with categories `movies`, `movies/foo`, and `movies/bar`.

Providing an empty string to `--category-filter` will select torrents with no
category. To select all torrents regardless of category, do not provide the
option at all.

## Subcommands

Many commands accept a `--dry-run` option to show what would be done without
making any changes.

The best documentation is the help text for each command. Run
`qb COMMAND --help` to see details.

### `add`

Add all torrent files provided to a client in a stopped state and start a
recheck on each newly-added torrent. Client may be a single client or many
separated by commas. One or more torrent files may be provided, and directories
may be provided to add all `.torrent` files found within them recursively.

This is helpful when new torrents are created or downloaded and we want to add
them.

Has a `--category` (`-c`) option to assign a category to the added torrent(s).

Has a `--delete-after` option to delete the torrent file after adding it
successfully to all provided clients.

Examples:

```sh
qb add aClient path/to/a.torrent
```

```sh
qb add aClient,bClient path/to/*.torrent --delete-after
```

```sh
qb add aClient path/to/a.torrent --category movies
```

### `cp`

Add all torrents from FROM_CLIENT to TO_CLIENT that do not already exist on
TO_CLIENT. Just like `add`, the torrents are added in a stopped state and a
recheck is run after adding.

TO_CLIENT may be a single client or many separated by commas.

The category of the torrents on FROM_CLIENT is preserved when adding to
TO_CLIENT.

Example:

```sh
qb cp aClient bClient
```

### `ls`

List all torrents in a given qBittorrent instance as JSON. May provide zero or
more hashes to select particular torrents. Accepts a `--status-filter` option to
filter which torrents to list.

Examples:

```sh
qb ls aClient
```

```sh
qb ls aClient --status-filter seeding
```

```sh
qb ls aClient c5e4ca57a767df5cdda3866f43d224925a2a16ab
```

### `recheck`

Start a recheck on all torrents for client, which can be a single client or many
separated by commas.

Example:

```sh
qb recheck aClient --status-filter stopped_downloading
```

### `start`

Start all torrents for client, which can be a single client or many separated by
commas.

Example:

```sh
qb start aClient --status-filter stopped_complete
```
