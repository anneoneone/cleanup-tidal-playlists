#!/usr/bin/env python3
"""Fix indentation in rekordbox service file."""

SERVICE_FILE = "src/tidal_cleanup/core/rekordbox/service.py"

with open(SERVICE_FILE, "r") as f:
    content = f.read()

# Replace all the malformed patterns
import re

# Pattern 1: year_keys loop (appears twice)
pattern1 = re.compile(
    r"(\s+)with suppress\(ValueError, IndexError\):\s*"
    r'(\s*)metadata\["ReleaseYear"\] = converter\([^)]*# type: ignore[^\n]*\n'
    r"\s*audio_file\[key\]\[0\]\s*\n\s*\)\s*\n"
    r"(\s+)break",
    re.MULTILINE,
)

replacement1 = (
    r"\1with suppress(ValueError, IndexError):\n"
    r"\1    val = audio_file[key][0]\n"
    r'\1    metadata["ReleaseYear"] = converter(val)  # type: ignore\n'
    r"\3break"
)

content = pattern1.sub(replacement1, content)

# Pattern 2: bpm_keys loop (appears twice)
pattern2 = re.compile(
    r"(\s+)with suppress\(ValueError, IndexError, TypeError\):\s*"
    r'(\s*)metadata\["BPM"\] = converter\([^)]*# type: ignore[^\n]*\n'
    r"\s*audio_file\[key\]\[0\]\s*\n\s*\)\s*\n"
    r"(\s+)break",
    re.MULTILINE,
)

replacement2 = (
    r"\1with suppress(ValueError, IndexError, TypeError):\n"
    r"\1    val = audio_file[key][0]\n"
    r'\1    metadata["BPM"] = converter(val)  # type: ignore\n'
    r"\3break"
)

content = pattern2.sub(replacement2, content)

with open(SERVICE_FILE, "w") as f:
    f.write(content)

print("Fixed indentation in service file")
