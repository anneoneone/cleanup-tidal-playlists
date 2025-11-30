#!/usr/bin/env python3
"""Debug script to check emoji byte representations."""

# Test emojis
test_emojis = {
    "Up Arrow from test": "↗️",
    "Down Arrow from test": "↘️",
    "High from test": "⬆️",
    "Medium from test": "➡️",
}

for name, emoji in test_emojis.items():
    bytes_repr = emoji.encode("utf-8")
    codepoints = " ".join(f"U+{ord(c):04X}" for c in emoji)
    print(f"{name}: {emoji}")
    print(f"  Bytes: {bytes_repr.hex(' ')}")
    print(f"  Codepoints: {codepoints}")
    print()
