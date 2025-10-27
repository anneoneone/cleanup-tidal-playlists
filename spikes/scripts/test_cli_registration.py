#!/usr/bin/env python3
"""Test script to debug CLI command registration."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Test imports
try:
    print("1. Testing main CLI import...")
    from tidal_cleanup.cli.main import cli

    print(f"   ✅ Main CLI imported, commands: {list(cli.commands.keys())}")
except Exception as e:
    print(f"   ❌ Failed to import main CLI: {e}")
    sys.exit(1)

try:
    print("2. Testing rekordbox command import...")
    from tidal_cleanup.cli.rekordbox import sync_playlist

    print(f"   ✅ sync_playlist imported: {type(sync_playlist)}")
except Exception as e:
    print(f"   ❌ Failed to import sync_playlist: {e}")
    sys.exit(1)

try:
    print("3. Testing manual command registration...")
    cli.add_command(sync_playlist, name="sync-playlist")
    print(f"   ✅ Command registered, commands: {list(cli.commands.keys())}")
except Exception as e:
    print(f"   ❌ Failed to register command: {e}")
    sys.exit(1)

print("4. Testing CLI help...")
try:
    import click

    ctx = click.Context(cli)
    help_text = cli.get_help(ctx)
    if "sync-playlist" in help_text:
        print("   ✅ sync-playlist found in help text")
    else:
        print("   ❌ sync-playlist not found in help text")
        print("   Available commands in help:")
        for line in help_text.split("\n"):
            if line.strip() and not line.startswith(" ") and "Commands:" not in line:
                print(f"     {line}")
except Exception as e:
    print(f"   ❌ Failed to get help: {e}")

print("\n✅ All tests completed!")
