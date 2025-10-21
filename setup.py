#!/usr/bin/env python3
"""Setup script for Tidal Playlist Cleanup Tool."""

from pathlib import Path
from setuptools import setup, find_packages

# Read the contents of README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

# Read requirements
requirements = []
with open("requirements.txt") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            requirements.append(line.split(">=")[0])

setup(
    name="tidal-cleanup",
    version="2.0.0",
    author="Anton",
    description="A modern tool for synchronizing Tidal playlists with local audio files",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/anneoneone/cleanup-tidal-playlists",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Sound/Audio",
        "Topic :: Utilities",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "tidal-cleanup=tidal_cleanup.cli.main:cli",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
