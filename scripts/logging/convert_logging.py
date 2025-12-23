#!/usr/bin/env python3
"""Script to convert f-string logging to %-formatting for lazy evaluation.

This script converts logger calls that use f-strings to use %-formatting instead.
This is important for performance because %-formatting with logging allows for
lazy evaluation - the string interpolation only happens if the log level is enabled.

Examples:
    # Dry-run mode (shows what would change without modifying files)
    python scripts/convert_logging.py --dry-run src/

    # Convert a single file
    python scripts/convert_logging.py src/tidal_cleanup/services/mytag_manager.py

    # Convert all Python files in a directory recursively
    python scripts/convert_logging.py --recursive src/

    # Convert specific files
    python scripts/convert_logging.py file1.py file2.py file3.py

Conversions performed:
    logger.info(f"Found {count} items")
    →
    logger.info("Found %d items", count)  # %d for integers

    logger.info(f"Found {len(items)} elements")
    →
    logger.info("Found %d elements", len(items))  # len() returns int

    logger.error(f"Failed to process {name}: {error}")
    →
    logger.error("Failed to process %s: %s", name, error)  # %s for strings

Type detection:
    - Uses %d for: len(), count variables, num_*, n_*, *_count, *_id, *_num, etc.
    - Uses %s for: most other expressions (safe default)
    - Uses %r for: expressions with !r or = (debug formatting)
"""

import argparse
import re
from pathlib import Path
from typing import List, Tuple


def find_fstring_logs(content: str) -> List[Tuple[int, str, str]]:
    """Find all logger calls with f-strings.

    Returns:
        List of (line_number, full_line, log_level) tuples
    """
    lines = content.split("\n")
    results = []

    for i, line in enumerate(lines, 1):
        # Match logger.level(f"...") or logger.level(f'...')
        # Also match logging.level(f"...") patterns
        match = re.search(
            r'(logger|logging)\.(debug|info|warning|error|critical)\s*\(\s*f["\']',
            line,
        )
        if match:
            results.append((i, line, match.group(2)))

    return results


def infer_format_specifier(expr: str) -> str:
    """Infer the appropriate format specifier for an expression.

    Args:
        expr: The expression inside the f-string (e.g., "count", "len(items)")

    Returns:
        Appropriate format specifier (%s, %d, %r, etc.)
    """
    # Check for explicit format specifiers in the expression
    if "!r" in expr:
        return "%r"

    if "=" in expr:  # Debug format {var=}
        return "%r"

    # Check for f-string format specs
    if re.search(r":\.\d+f", expr):  # Float formatting like {value:.2f}
        return "%f"

    if re.search(r":d", expr):  # Integer formatting like {count:d}
        return "%d"

    # Extract the clean expression without format specs
    clean_expr = re.sub(r"[:!][^}]*$", "", expr).strip()

    # Detect common patterns that suggest integer formatting
    int_patterns = [
        r"^len\(",  # len() returns int
        r"^count$",  # Common variable name for counts
        r"^num_",  # Variable names starting with num_
        r"^n_",  # Variable names starting with n_
        r"_count$",  # Variable names ending with _count
        r"_num$",  # Variable names ending with _num
        r"_id$",  # IDs are typically integers
        r"^id$",  # id variable
        r"^.*_id$",  # Any variable ending with _id
        r"\.count\(",  # .count() method
        r"^sum\(",  # sum() often returns numeric
        r"^int\(",  # explicit int() conversion
        r"^total_",  # total_something variables
        r"_total$",  # something_total variables
        r"^index$",  # index variable
        r"_index$",  # something_index
        r"^size$",  # size variable
        r"_size$",  # something_size
    ]

    for pattern in int_patterns:
        if re.search(pattern, clean_expr, re.IGNORECASE):
            return "%d"

    # Default to %s for safety (works with any type)
    return "%s"


def convert_fstring_to_percent(fstring: str) -> Tuple[str, List[str]]:
    """Convert an f-string to %-formatting.

    Args:
        fstring: The f-string content (without f prefix and quotes)

    Returns:
        Tuple of (format_string, [args])
    """
    args = []
    result = fstring

    # Find all {expression} patterns
    pattern = r"\{([^}]+)\}"
    matches = list(re.finditer(pattern, fstring))

    # Replace from right to left to maintain positions
    for match in reversed(matches):
        expr = match.group(1)

        # Handle debug format {var=} specially
        if "=" in expr and not any(op in expr for op in ["==", "!=", "<=", ">="]):
            # This is debug format like {value=}
            # Remove the = from both expression and clean_expr
            clean_expr = expr.replace("=", "").strip()
        else:
            # Clean the expression (remove format specifiers)
            clean_expr = re.sub(r"[:!][^}]*$", "", expr).strip()

        args.insert(0, clean_expr)

        # Determine the appropriate format specifier
        spec = infer_format_specifier(expr)

        result = result[: match.start()] + spec + result[match.end() :]

    return result, args


def convert_log_line(line: str) -> str:
    """Convert a single log line from f-string to %-formatting.

    Args:
        line: The line containing logger call with f-string

    Returns:
        Converted line with %-formatting
    """
    # Match the full logger call with f-string including closing paren
    # Handles both single and double quotes, multiline not supported here
    pattern = (
        r"(logger|logging)\.(debug|info|warning|error|critical)"
        r'\s*\(\s*f(["\'])(.*?)\3\s*\)'
    )
    match = re.search(pattern, line)

    if not match:
        return line

    logger_obj = match.group(1)
    level = match.group(2)
    quote = match.group(3)
    fstring_content = match.group(4)

    # Convert the f-string content
    format_string, args = convert_fstring_to_percent(fstring_content)

    # Build the new log call
    if args:
        args_str = ", ".join(args)
        new_call = f"{logger_obj}.{level}({quote}{format_string}{quote}, {args_str})"
    else:
        # No variables, just remove the f prefix
        new_call = f"{logger_obj}.{level}({quote}{format_string}{quote})"

    # Replace in the original line
    result = line[: match.start()] + new_call + line[match.end() :]
    return result


def process_file(file_path: Path, dry_run: bool = False) -> Tuple[int, int]:
    """Process a single file and convert f-string logging.

    Args:
        file_path: Path to the file to process
        dry_run: If True, don't write changes back

    Returns:
        Tuple of (total_lines_found, lines_converted)
    """
    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    # Find all f-string logs
    fstring_logs = find_fstring_logs(content)

    if not fstring_logs:
        return 0, 0

    # Convert each line
    converted_count = 0
    new_lines = lines.copy()

    for line_num, original_line, _level in fstring_logs:
        try:
            converted_line = convert_log_line(original_line)
            if converted_line != original_line:
                new_lines[line_num - 1] = converted_line
                converted_count += 1
                if dry_run:
                    print(f"\n{file_path}:{line_num}")
                    print(f"  - {original_line.strip()}")
                    print(f"  + {converted_line.strip()}")
        except Exception as e:
            print(f"Error converting line {line_num} in {file_path}: {e}")
            print(f"  Line: {original_line.strip()}")

    # Write back if not dry run
    if not dry_run and converted_count > 0:
        new_content = "\n".join(new_lines)
        file_path.write_text(new_content, encoding="utf-8")
        print(f"✓ {file_path}: converted {converted_count}/{len(fstring_logs)} lines")

    return len(fstring_logs), converted_count


def collect_files(paths: List[Path], recursive: bool, pattern: str) -> List[Path]:
    """Collect all files to process from given paths.

    Args:
        paths: List of file or directory paths
        recursive: Whether to search directories recursively
        pattern: File pattern to match

    Returns:
        List of file paths to process
    """
    files_to_process = []
    for path in paths:
        if path.is_file():
            files_to_process.append(path)
        elif path.is_dir():
            if recursive:
                files_to_process.extend(path.rglob(pattern))
            else:
                files_to_process.extend(path.glob(pattern))
        else:
            print(f"Warning: Path not found: {path}")
    return files_to_process


def print_summary(
    total_files: int, total_found: int, total_converted: int, dry_run: bool
):
    """Print processing summary."""
    print("\n" + "=" * 60)
    print(f"Files processed: {total_files}")
    print(f"F-string logs found: {total_found}")
    print(f"Lines converted: {total_converted}")

    if dry_run and total_found > 0:
        print("\nRun without --dry-run to apply changes")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Convert f-string logging to %-formatting for lazy evaluation"
    )
    parser.add_argument(
        "paths", nargs="+", type=Path, help="Files or directories to process"
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be changed without making changes",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Process directories recursively",
    )
    parser.add_argument(
        "--pattern",
        "-p",
        default="*.py",
        help="File pattern to match (default: *.py)",
    )

    args = parser.parse_args()

    # Collect all files to process
    files_to_process = collect_files(args.paths, args.recursive, args.pattern)

    if not files_to_process:
        print("No files to process")
        return

    if args.dry_run:
        print("=== DRY RUN MODE - No changes will be made ===\n")

    # Process each file
    total_files = 0
    total_found = 0
    total_converted = 0

    for file_path in sorted(files_to_process):
        try:
            found, converted = process_file(file_path, dry_run=args.dry_run)
            if found > 0:
                total_files += 1
                total_found += found
                total_converted += converted
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    print_summary(total_files, total_found, total_converted, args.dry_run)


if __name__ == "__main__":
    main()
