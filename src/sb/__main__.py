from sb.diff import print_string_diff
from sb.category import Category
from pathlib import Path
from typing import get_args, TypeVar, Callable, Any
import json
from functools import cache
import shutil

import click
from qbittorrentapi.torrents import TorrentStatusesT

from sb.config import Config
from sb.norm import iter_variants
from sb.fastresume import FastResume
from sb.torrent import Torrent, MissingTorrentFileException, TorrentException
from sb.client import (
    QBittorrentClient,
    FailedAddException,
    SBTorrentStatus,
    sb_torrent_statuses,
)


@click.group()
def sb():
    """Seedbox management CLI."""
    pass


@sb.group()
def qb():
    """Commands for managing qBittorrent clients."""
    pass


F = TypeVar("F", bound=Callable[..., Any])


def torrent_path_argument(f: F) -> F:
    """
    Argument decorator for one or more torrent file or directory paths.

    Should be typed as `tuple[Path]` in the decorated function.
    """
    return click.argument(
        "torrent_file_or_dir_path",
        type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path),
        required=False,
        nargs=-1,
    )(f)


@qb.command()
@click.argument(
    "client",
)
@torrent_path_argument
@click.option(
    "-c",
    "--category",
    default=None,
    help="Category to assign to the added torrent(s)",
)
@click.option(
    "--delete-after",
    is_flag=True,
    default=False,
    help="Delete torrent file after successfully adding or being skipped due to already existing by all clients",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def add(
    client: str,
    torrent_file_or_dir_path: tuple[Path],
    category: str | None,
    delete_after: bool,
    dry_run: bool,
):
    """
    Add TORRENT to CLIENT. CLIENT may be a single client or many separated by commas. One or more
    TORRENT files may be provided.
    """
    config = Config.load_from_file()

    torrent_paths = []
    for path in torrent_file_or_dir_path:
        if path.is_file():
            torrent_paths.append(path)
        elif path.is_dir():
            for file in path.glob("**/*.torrent"):
                torrent_paths.append(file)

    add_results: dict[Path, bool] = {path: True for path in torrent_paths}

    for client_name in client.split(","):
        client_config = get_qb_client_config(config, client_name)
        with QBittorrentClient.from_config(client_config) as qb_client:
            click.echo(f"Client '{client_name}'", err=True)

            existing_torrents = qb_client.list_torrents()
            existing_hashes = {t.hash for t in existing_torrents}
            recheck_hashes: set[str] = set()

            for torrent_path in torrent_paths:
                click.echo(
                    f"\tAdding torrent {torrent_path}",
                    err=True,
                )
                t = Torrent.from_path(torrent_path)
                torrent_hash = t.infohash_v1.hex()
                if torrent_hash in existing_hashes:
                    click.echo(
                        "\t\t⚠️ Already exists, skipping",
                        err=True,
                    )
                    continue

                if dry_run:
                    click.echo("\t\tℹ️ Dry run, not adding", err=True)
                    continue

                try:
                    qb_client.add_paused_torrent_by_path(
                        torrent_path, category=category
                    )
                except FailedAddException:
                    click.echo("\t\t❌ Failed to add", err=True)
                    add_results[torrent_path] = False
                    continue

                recheck_hashes.add(torrent_hash)

                click.echo("\t\t✅ Added successfully", err=True)

            if not dry_run:
                qb_client.start_recheck(recheck_hashes)

    if delete_after and not dry_run:
        for torrent_path, success in add_results.items():
            if success:
                click.echo(f"🗑️ Deleting {torrent_path}", err=True)
                torrent_path.unlink()
            else:
                click.echo(
                    f"Not deleting {torrent_path} due to previous errors",
                    err=True,
                )


@qb.command()
@click.argument(
    "from_client",
    type=str,
)
@click.argument(
    "to_client",
    type=str,
)
@click.option(
    "-c",
    "--category-filter",
    default=None,
    help="Only select torrents with this category. Subcategories are included by parent categories.",
)
@click.option(
    "-s",
    "--status-filter",
    type=click.Choice(get_args(TorrentStatusesT)),
    default=None,
    help="Only select torrents with this status.",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def cp(
    from_client: str,
    to_client: str,
    category_filter: str | None,
    status_filter: SBTorrentStatus | None,
    dry_run: bool,
):
    """
    Copy all torrents from FROM_CLIENT to TO_CLIENT.

    TO_CLIENT may be a single client or many separated by commas.
    """
    config = Config.load_from_file()
    from_client_config = get_qb_client_config(config, from_client)
    to_client_configs = {
        name: get_qb_client_config(config, name) for name in to_client.split(",")
    }

    from_qb = QBittorrentClient.from_config(from_client_config)
    from_qb.login()

    from_torrents = from_qb.list_torrents(
        category_filter=category_filter, status_filter=status_filter
    )
    from_torrent_map = {t.hash: t for t in from_torrents}
    from_hashes = {t.hash for t in from_torrents}

    @cache
    def get_torrent_data(torrent_hash: str) -> bytes:
        return from_qb.export(torrent_hash=torrent_hash)

    for name, config in to_client_configs.items():
        with QBittorrentClient.from_config(config) as to_qb:
            click.echo(f"Copying torrents from '{from_client}' to '{name}'", err=True)

            to_torrents = to_qb.list_torrents()
            to_hashes = {t.hash for t in to_torrents}
            missing_hashes = from_hashes - to_hashes
            recheck_hashes = set(missing_hashes)

            for missing_hash in missing_hashes:
                torrent_data = get_torrent_data(missing_hash)
                torrent = from_torrent_map[missing_hash]
                category = torrent.category
                click.echo(f"\tAdding torrent: {torrent.name}", err=True)

                if dry_run:
                    click.echo("\t\tℹ️ Dry run, not copying", err=True)
                    continue

                try:
                    to_qb.add_paused_torrent_by_data(
                        torrent_data, category=str(category)
                    )
                except FailedAddException:
                    click.echo("\t\t❌ Failed to copy", err=True)
                    recheck_hashes.remove(missing_hash)
                    continue

                click.echo("\t\t✅ Copied successfully", err=True)

            if not dry_run:
                to_qb.start_recheck(hashes=recheck_hashes)

    from_qb.logout()


@qb.command()
@click.argument(
    "client",
    type=str,
)
@click.argument(
    "hashes",
    type=str,
    required=False,
    nargs=-1,
)
@click.option(
    "-s",
    "--status-filter",
    type=click.Choice(get_args(TorrentStatusesT)),
    default=None,
    help="Only select torrents with this status",
)
@click.option(
    "-c",
    "--category-filter",
    default=None,
    help="Only select torrents with this category. Subcategories are included by parent categories.",
)
def ls(
    client: str,
    hashes: tuple[str],
    status_filter: TorrentStatusesT | None,
    category_filter: str | None,
):
    """List all torrents in CLIENT. May provide zero or more HASHES to select specific torrents."""
    config = Config.load_from_file()
    client_config = get_qb_client_config(config, client)

    with QBittorrentClient.from_config(client_config) as qb_client:
        torrents = qb_client.list_torrents(
            status_filter=status_filter, hashes=hashes, category_filter=category_filter
        )
        json_list = [dict(t) for t in torrents]
        click.echo(json.dumps(json_list, indent=4))


@qb.command()
@click.argument(
    "client",
)
@click.option(
    "-s",
    "--status-filter",
    type=click.Choice(sb_torrent_statuses),
    default=None,
    help="Only select torrents with this status",
)
@click.option(
    "-c",
    "--category-filter",
    default=None,
    help="Only select torrents with this category. Subcategories are included by parent categories.",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def recheck(
    client: str,
    status_filter: SBTorrentStatus | None,
    category_filter: str | None,
    dry_run: bool,
):
    """
    Recheck all torrents in specified CLIENT. CLIENT may be a single client or many
    separated by commas.
    """
    config = Config.load_from_file()

    for client_name in client.split(","):
        client_config = get_qb_client_config(config, client_name)

        with QBittorrentClient.from_config(client_config) as qb_client:
            click.echo(f"Client '{client_name}'", err=True)

            torrents = qb_client.list_torrents(
                status_filter=status_filter, category_filter=category_filter
            )

            if not dry_run:
                qb_client.start_recheck(torrent.hash for torrent in torrents)

            for torrent in torrents:
                if not dry_run:
                    click.echo(f"\t🔍 Started recheck of {torrent.name}", err=True)
                else:
                    click.echo(f"\tℹ️ Dry run, would recheck {torrent.name}", err=True)


@qb.command()
@click.argument(
    "client",
)
@click.option(
    "-s",
    "--status-filter",
    type=click.Choice(sb_torrent_statuses),
    default=None,
    help="Only select torrents with this status",
)
@click.option(
    "-c",
    "--category-filter",
    default=None,
    help="Only select torrents with this category. Subcategories are included by parent categories.",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def start(
    client: str,
    status_filter: SBTorrentStatus | None,
    category_filter: str | None,
    dry_run: bool,
):
    """
    Start all torrents in specified CLIENT. CLIENT may be a single client or many
    separated by commas.
    """
    config = Config.load_from_file()

    for client_name in client.split(","):
        client_config = get_qb_client_config(config, client_name)

        with QBittorrentClient.from_config(client_config) as qb_client:
            click.echo(f"Client '{client_name}'", err=True)

            torrents = qb_client.list_torrents(
                status_filter=status_filter, category_filter=category_filter
            )

            if not dry_run:
                qb_client.start(torrent.hash for torrent in torrents)

            for torrent in torrents:
                if not dry_run:
                    click.echo(f"\t🏃‍➡️ Started torrent {torrent.name}", err=True)
                else:
                    click.echo(
                        f"\tℹ️ Dry run, would start torrent {torrent.name}", err=True
                    )


def get_qb_client_config(config: Config, client_name: str):
    try:
        return config.qb.clients[client_name]
    except KeyError:
        raise click.ClickException(
            f"Client '{client_name}' not found in configuration."
        )


@sb.command()
@click.argument(
    "torrent_path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.argument(
    "download_path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=False,
)
def check(torrent_path: Path, download_path: Path | None):
    """
    Check the integrity of the files downloaded for the torrent at TORRENT_PATH
    against the torrent pieces. DOWNLOAD_PATH is the root path where the files
    are downloaded.

    If DOWNLOAD_PATH is not provided, each download root from the configuration
    will be checked. If the files are valid in any of the download roots, the
    check is considered successful.
    """
    t = Torrent.from_path(torrent_path)

    click.echo(f"Checking files for torrent: {t.name}", err=True)

    if download_path is None:
        config = Config.load_from_file()
        for root in config.download_roots:
            try:
                t.check(root)
                click.echo(f"✅ Torrent check OK in {root}", err=True)
                break
            except TorrentException:
                continue
        else:
            raise click.ClickException(
                "❌ Torrent check failed: files not found or files invalid in all download roots"
            )
        return

    try:
        t.check(download_path)
    except MissingTorrentFileException as e:
        raise click.ClickException(f"❌ Torrent check failed: {e}")

    click.echo("✅ Torrent check OK", err=True)


@sb.command("file-check")
@click.argument(
    "torrent_path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.argument(
    "download_path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=False,
)
def file_check(torrent_path: Path, download_path: Path):
    """
    Check that all files for the torrent at TORRENT_PATH exist in DOWNLOAD_PATH.

    If DOWNLOAD_PATH is not provided, each download root from the configuration
    will be checked. If the files are found in any of the download roots, the
    check is considered successful.
    """
    t = Torrent.from_path(torrent_path)

    click.echo(f"Checking files for torrent: {t.name}", err=True)

    if download_path is None:
        config = Config.load_from_file()
        for root in config.download_roots:
            try:
                t.file_check(root)
                click.echo(f"✅ File check OK in {root}", err=True)
                break
            except MissingTorrentFileException:
                continue
        else:
            raise click.ClickException(
                "❌ File check failed: files not found in all download roots"
            )
        return

    try:
        t.file_check(download_path)
    except MissingTorrentFileException as e:
        raise click.ClickException(f"❌ File check failed: {e}")

    click.echo("✅ File check OK", err=True)


@sb.command()
@click.argument(
    "file_or_dir_path",
    type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path),
    required=True,
    nargs=-1,
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
@click.option(
    "--min-size",
    type=int,
    default=1,
    help="Minimum file size in bytes to consider for linking",
)
@click.option(
    "--interactive",
    is_flag=True,
    default=False,
    help="Prompt before linking each set of duplicates",
)
def linkup(file_or_dir_path: Path, dry_run: bool, min_size: int, interactive: bool):
    """
    Hardlink all files under FILE_OR_DIR_PATH that are duplicates.

    Duplicates are determined by matching file size and xxhash hashes.

    Warning: this may take a long time because all files need to be read and hashed.

    Warning: this is an agressive space-saving operation that will connect files that
    may not have been previously related. Therefore, modifications to one file will
    affect all linked files. Use with caution.
    """
    raise NotImplementedError("linkup command is not yet implemented.")


@sb.command("fix-norm")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
@click.option(
    "--interactive", is_flag=True, default=False, help="Prompt before fixing each file"
)
@click.option(
    "-c",
    "--category-filter",
    default=None,
    help="Only select torrents with this category. Subcategories are included by parent categories.",
)
def fix_bad_normalization(
    dry_run: bool, interactive: bool, category_filter: str | None
):
    """
    From torrents in config's `local_qb_config_dir`, fix downloaded files' paths that
    have errantly been Unicode-normalized by other software (e.g. syncthing).
    """
    config = Config.load_from_file()

    if category_filter is not None:
        only_category = Category.from_string(category_filter)

    for bt_backup_tuple in config.qb_bt_backup_torrent_tuples():
        fast_resume = FastResume.from_path(bt_backup_tuple.fastresume_path)
        category = (
            Category.from_string(fast_resume.category) if fast_resume.category else None
        )

        # skip if:
        # - category filter is set, and the fast resume category is None
        # - category filter is set, and the fast resume category is not a subcategory of it
        if category_filter is not None and (
            category is None or not category.is_subcategory_of(only_category)
        ):
            continue

        try:
            torrent = Torrent.from_path(bt_backup_tuple.torrent_path)
        except TorrentException as e:
            click.secho(f"Failed to load torrent: {e}", err=True, fg="red")
            continue

        printed_torrent = False

        def print_torrent_once():
            nonlocal printed_torrent
            if not printed_torrent:
                printed_torrent = True
                click.secho(f"{bt_backup_tuple.torrent_path}: {torrent.name}", err=True)

        save_path = fast_resume.save_path

        torrent_fixed = True

        for file in sorted(torrent.files, key=lambda f: f.path):
            # This is weird, but some quirk in my stack names files on disk without LTR
            # markers even though the torrent specifies them. So, just strip them out
            # for the purposes of this check.
            file_path = Path(*[part.replace("\u200e", "") for part in file.path.parts])

            expected_path = save_path / file_path

            fixed = False

            if expected_path.is_file():
                fixed = True

            for normed_file_path in iter_variants(file_path):
                normed_full_path = save_path / normed_file_path
                if not normed_full_path.is_file():
                    continue

                print_torrent_once()

                if fixed:
                    click.secho(
                        "\tVariant found even though expected file exists",
                        err=True,
                    )
                    print_string_diff(
                        str(expected_path),
                        str(normed_full_path),
                        headings=(
                            "\tExpected",
                            "\tFound   ",
                        ),
                        file=click.get_text_stream("stderr"),
                    )
                    if dry_run:
                        click.secho("\tDry run, not deleting", err=True)
                        continue
                    if interactive:
                        confirm = click.confirm("\tDelete variant?")
                        if not confirm:
                            click.secho("\tSkipping", err=True)
                            continue
                    normed_full_path.unlink()
                    click.secho("\tDeleted", err=True, fg="green")

                else:
                    click.secho(
                        "\tVariant found that can fix missing file",
                        err=True,
                    )
                    print_string_diff(
                        str(expected_path),
                        str(normed_full_path),
                        headings=(
                            "\tExpected",
                            "\tFound   ",
                        ),
                        file=click.get_text_stream("stderr"),
                    )

                    if dry_run:
                        click.secho("\tDry run, not fixing", err=True)
                        continue
                    if interactive:
                        confirm = click.confirm("\tRename to expected?")
                        if not confirm:
                            click.secho("\tSkipping", err=True)
                            continue

                    expected_path.parent.mkdir(parents=True, exist_ok=True)
                    normed_full_path.rename(expected_path)
                    fixed = True
                    click.secho("\t✅ Fixed", err=True, fg="green")

            if not fixed:
                print_torrent_once()
                click.secho(
                    f"\tExpected path {expected_path} not found nor any variant",
                    err=True,
                    fg="red",
                )
                torrent_fixed = False

        if torrent_fixed:
            # now we can go through any variant directories and remove them
            torrent_root = save_path / Path(
                *[part.replace("\u200e", "") for part in torrent.name.parts]
            )

            for variant_root in iter_variants(torrent_root):
                if variant_root == torrent_root:
                    continue
                if not variant_root.exists():
                    continue

                if not dry_run:
                    if interactive:
                        confirm = click.confirm(
                            f"\tDelete variant directory {variant_root}?"
                        )
                        if not confirm:
                            click.secho("\tSkipping", err=True)
                            continue
                    shutil.rmtree(variant_root)
                    click.secho(
                        f"\tDeleted variant directory {variant_root}",
                        err=True,
                        fg="green",
                    )
                else:
                    click.secho(
                        f"\tDry run, would delete variant directory {variant_root}",
                        err=True,
                    )
