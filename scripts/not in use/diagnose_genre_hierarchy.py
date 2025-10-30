#!/usr/bin/env python3
"""Diagnostic tool to validate genre hierarchy configuration."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from rich.console import Console
from rich.table import Table

from tidal_cleanup.services.genre_hierarchy_manager import GenreHierarchyManager
from tidal_cleanup.services.playlist_name_parser import PlaylistNameParser

console = Console()
logger = logging.getLogger(__name__)


def load_emoji_mapping(config_path: Path) -> Dict:
    """Load emoji to MyTag mapping."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_configuration(
    emoji_config_path: Path, hierarchy_config_path: Path
) -> Tuple[List[str], List[str]]:
    """Validate that emoji mappings match hierarchy configuration.

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    # Load configs
    emoji_config = load_emoji_mapping(emoji_config_path)
    hierarchy_manager = GenreHierarchyManager(hierarchy_config_path)

    # Get all genre tags from emoji mapping
    genre_tags = set(emoji_config["Track-Metadata"]["Genre"].values())
    party_tags = set(emoji_config["Track-Metadata"]["Party"].values())
    all_emoji_tags = genre_tags | party_tags

    # Get all genre tags from hierarchy
    hierarchy_tags = set()
    with open(hierarchy_config_path, "r", encoding="utf-8") as f:
        hierarchy_config = json.load(f)
        for category_tags in hierarchy_config["genre_hierarchy"].values():
            hierarchy_tags.update(category_tags)

    # Check for mismatches
    emoji_only = all_emoji_tags - hierarchy_tags
    hierarchy_only = hierarchy_tags - all_emoji_tags

    if emoji_only:
        for tag in sorted(emoji_only):
            warnings.append(
                f"Tag '{tag}' is in emoji mapping but not in hierarchy "
                f"(will go to '{hierarchy_manager.default_category}')"
            )

    if hierarchy_only:
        for tag in sorted(hierarchy_only):
            warnings.append(
                f"Tag '{tag}' is in hierarchy but has no emoji mapping "
                f"(will never be used)"
            )

    return errors, warnings


def test_playlist_categorization(
    playlists_dir: Path,
    emoji_config_path: Path,
    hierarchy_config_path: Path,
) -> None:
    """Test how playlists would be categorized."""
    console.print("\n[bold cyan]📊 Playlist Categorization Test[/bold cyan]")
    console.print("=" * 80)

    if not playlists_dir.exists():
        console.print(f"[red]❌ Directory not found: {playlists_dir}[/red]")
        return

    # Initialize managers
    name_parser = PlaylistNameParser(emoji_config_path)
    hierarchy_manager = GenreHierarchyManager(hierarchy_config_path)

    # Get all playlist folders
    playlist_folders = sorted([d for d in playlists_dir.iterdir() if d.is_dir()])

    if not playlist_folders:
        console.print("[yellow]⚠️  No playlist folders found[/yellow]")
        return

    # Categorize playlists
    categorization: Dict[str, List[Tuple[str, str, List[str], List[str]]]] = {}

    for playlist_folder in playlist_folders:
        playlist_name = playlist_folder.name

        try:
            # Parse playlist name
            metadata = name_parser.parse_playlist_name(playlist_name)

            # Determine category
            category = hierarchy_manager.get_top_level_category(
                list(metadata.genre_tags), list(metadata.party_tags)
            )

            # Determine subfolder (first genre or party tag)
            subfolder = None
            if metadata.genre_tags:
                subfolder = sorted(metadata.genre_tags)[0]
            elif metadata.party_tags:
                subfolder = sorted(metadata.party_tags)[0]

            if category not in categorization:
                categorization[category] = []

            categorization[category].append(
                (
                    playlist_name,
                    subfolder or "(none)",
                    list(metadata.genre_tags),
                    list(metadata.party_tags),
                )
            )

        except Exception as e:
            console.print(f"[red]❌ Error parsing '{playlist_name}': {e}[/red]")

    # Display results by category
    for category in sorted(categorization.keys()):
        playlists = categorization[category]

        console.print(f"\n[bold yellow]Category: {category}[/bold yellow]")
        console.print(f"  Playlists: {len(playlists)}")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Playlist Name", style="cyan", width=40)
        table.add_column("Subfolder", style="green", width=20)
        table.add_column("Genre Tags", style="blue", width=30)
        table.add_column("Party Tags", style="yellow", width=15)

        for playlist_name, subfolder, genre_tags, party_tags in sorted(playlists):
            table.add_row(
                playlist_name[:40],
                subfolder,
                ", ".join(genre_tags) if genre_tags else "-",
                ", ".join(party_tags) if party_tags else "-",
            )

        console.print(table)

    # Summary statistics
    console.print("\n[bold green]📈 Summary Statistics[/bold green]")
    console.print("=" * 80)

    summary_table = Table(show_header=True, header_style="bold magenta")
    summary_table.add_column("Category", style="cyan")
    summary_table.add_column("Count", style="green", justify="right")
    summary_table.add_column("Percentage", style="yellow", justify="right")

    total = sum(len(playlists) for playlists in categorization.values())

    for category in sorted(categorization.keys()):
        count = len(categorization[category])
        percentage = (count / total * 100) if total > 0 else 0
        summary_table.add_row(category, str(count), f"{percentage:.1f}%")

    console.print(summary_table)
    console.print(f"\n[bold]Total playlists: {total}[/bold]")


def check_empty_categories(
    playlists_dir: Path,
    emoji_config_path: Path,
    hierarchy_config_path: Path,
) -> None:
    """Check which categories have no playlists."""
    console.print("\n[bold cyan]🔍 Empty Category Check[/bold cyan]")
    console.print("=" * 80)

    # Initialize managers
    name_parser = PlaylistNameParser(emoji_config_path)
    hierarchy_manager = GenreHierarchyManager(hierarchy_config_path)

    # Get all playlist folders
    playlist_folders = [d for d in playlists_dir.iterdir() if d.is_dir()]

    # Get used categories
    used_categories = set()
    for playlist_folder in playlist_folders:
        try:
            metadata = name_parser.parse_playlist_name(playlist_folder.name)
            category = hierarchy_manager.get_top_level_category(
                list(metadata.genre_tags), list(metadata.party_tags)
            )
            used_categories.add(category)
        except Exception:
            pass

    # Get all defined categories
    all_categories = hierarchy_manager.get_all_categories()

    # Find empty categories
    empty_categories = all_categories - used_categories

    if empty_categories:
        console.print("[yellow]⚠️  Categories with no playlists:[/yellow]")
        for category in sorted(empty_categories):
            console.print(f"  - {category}")
        console.print(
            "\n[dim]These empty category folders will be created "
            "in Rekordbox but contain no playlists.[/dim]"
        )
    else:
        console.print("[green]✓ All categories have playlists[/green]")


def main():
    """Run diagnostics."""
    console.print("\n[bold green]🔧 Genre Hierarchy Diagnostic Tool[/bold green]")
    console.print("=" * 80)

    # Paths
    project_root = Path(__file__).resolve().parents[1]
    emoji_config_path = project_root / "config" / "rekordbox_mytag_mapping.json"
    hierarchy_config_path = project_root / "config" / "rekordbox_genre_hierarchy.json"

    # Try to get playlists directory from config
    try:
        from tidal_cleanup.config import Config

        config = Config()
        playlists_dir = config.mp3_directory / "Playlists"
    except Exception:
        # Fallback to default
        playlists_dir = Path.home() / "Music" / "Playlists"

    # Check config files exist
    if not emoji_config_path.exists():
        console.print(f"[red]❌ Emoji config not found: {emoji_config_path}[/red]")
        return

    if not hierarchy_config_path.exists():
        console.print(
            f"[red]❌ Hierarchy config not found: {hierarchy_config_path}[/red]"
        )
        return

    console.print(f"[green]✓ Emoji config: {emoji_config_path}[/green]")
    console.print(f"[green]✓ Hierarchy config: {hierarchy_config_path}[/green]")
    console.print(f"[blue]📁 Playlists directory: {playlists_dir}[/blue]")

    # 1. Validate configuration
    console.print("\n[bold cyan]1️⃣  Configuration Validation[/bold cyan]")
    console.print("=" * 80)

    errors, warnings = validate_configuration(emoji_config_path, hierarchy_config_path)

    if errors:
        console.print("[red]❌ Errors found:[/red]")
        for error in errors:
            console.print(f"  - {error}")
    else:
        console.print("[green]✓ No errors found[/green]")

    if warnings:
        console.print("\n[yellow]⚠️  Warnings:[/yellow]")
        for warning in warnings:
            console.print(f"  - {warning}")
    else:
        console.print("[green]✓ No warnings[/green]")

    # 2. Check for empty categories
    if playlists_dir.exists():
        check_empty_categories(playlists_dir, emoji_config_path, hierarchy_config_path)

    # 3. Test playlist categorization
    if playlists_dir.exists():
        test_playlist_categorization(
            playlists_dir, emoji_config_path, hierarchy_config_path
        )
    else:
        console.print(
            f"\n[yellow]⚠️  Playlists directory not found: {playlists_dir}[/yellow]"
        )
        console.print("[dim]Skipping playlist categorization test[/dim]")

    console.print("\n[bold green]✅ Diagnostics complete![/bold green]\n")


if __name__ == "__main__":
    main()
