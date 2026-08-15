#!/usr/bin/env python3
"""Syncs boilerplate wrapper files from a template directory into the root repository,

replacing JSON metadata placeholders dynamically (including {{key:json}} modifiers,
and dynamic usage snippets generated via readme.py) and validating that no unhandled
placeholders remain.
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

# Import the README usage generator from readme.py
from readme import generate_usage

# Matches remaining {{placeholder_name}} or {{placeholder_name:modifier}} patterns
PLACEHOLDER_PATTERN = re.compile(r"\{\{([a-zA-Z0-9_]+(?::[a-zA-Z0-9_]+)?)\}\}")


def is_binary(file_path: Path) -> bool:
    """Detect binary files by checking for NULL bytes in the first chunk."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except OSError:
        return False


def load_replacements(config_path: Path, lock_path: Path) -> dict[str, str]:
    """Parse JSON metadata, C# usage snippets, and GitHub env vars into placeholder mappings."""
    raw_data = {}

    # 1. Load local .sdk-fabric.json if available
    if config_path.is_file():
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

    # 2. Inject environment metadata automatically if running in GitHub Actions
    server_url = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    repo_slug = os.getenv("GITHUB_REPOSITORY", "")  # e.g., "sdk-fabric/petstore-java"

    if repo_slug and "/" in repo_slug:
        user_name, repo_name = repo_slug.split("/", 1)

        raw_data.setdefault("github_user", user_name)
        raw_data.setdefault("github_repository", repo_name)
        raw_data.setdefault("github_url", f"{server_url}/{repo_slug}")

    # 3. Dynamically generate C# usage snippets via readme.py
    raw_data["usage"] = generate_usage(lock_path)

    replacements = {}
    for key, val in raw_data.items():
        if isinstance(val, (dict, list)):
            continue

        str_val = str(val)

        replacements["{{" + key + "}}"] = str_val
        replacements["{{" + key + ":json}}"] = json.dumps(str_val)[1:-1]

    return replacements


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync template files to repository root.")
    parser.add_argument("--template-dir", type=Path, default=Path(".template_tmp"))
    parser.add_argument("--config-file", type=Path, default=Path(".sdk-fabric.json"))
    parser.add_argument("--lock-file", type=Path, default=Path("sdkgen.lock"))
    args = parser.parse_args()

    template_dir: Path = args.template_dir
    config_file: Path = args.config_file
    lock_file: Path = args.lock_file

    # 1. Validation
    if not config_file.is_file():
        print(f"::error file={config_file}::Config file '{config_file}' not found.")
        sys.exit(1)

    if not template_dir.is_dir():
        print(f"::error::Template directory '{template_dir}' not found.")
        sys.exit(1)

    # 2. Load placeholders
    replacements = load_replacements(config_file, lock_file)

    # 3. Process template files using pathlib
    ignored_parts = {".git", ".sdk-fabric.json", "sync.py", "readme.py", "__pycache__"}
    missing_placeholders_found = False

    for src_file in template_dir.rglob("*"):
        if not src_file.is_file():
            continue

        rel_path = src_file.relative_to(template_dir)

        # Skip ignored root entries and bytecode files
        if any(part in ignored_parts for part in rel_path.parts) or src_file.suffix == ".pyc":
            continue

        # Skip everything under .github/workflows specifically
        if len(rel_path.parts) >= 2 and rel_path.parts[0] == ".github" and rel_path.parts[1] == "workflows":
            continue

        dest_file = Path(rel_path)
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        # 4. Copy binary or render text
        if is_binary(src_file):
            shutil.copy2(src_file, dest_file)
        else:
            try:
                content = src_file.read_text(encoding="utf-8")

                # Replace all known {{key}} and {{key:json}} placeholders
                for placeholder, value in replacements.items():
                    content = content.replace(placeholder, value)

                # Check if any unhandled {{key}} or {{key:json}} placeholders remain
                unhandled_matches = set(PLACEHOLDER_PATTERN.findall(content))
                if unhandled_matches:
                    missing_keys = ", ".join(f"'{{{{{m}}}}}'" for m in sorted(unhandled_matches))
                    print(
                        f"::error file={rel_path}::Missing placeholder value(s) {missing_keys} in '{rel_path}'."
                    )
                    missing_placeholders_found = True

                dest_file.write_text(content, encoding="utf-8")
            except UnicodeDecodeError:
                # Fallback for unexpected encoding issues
                shutil.copy2(src_file, dest_file)

    if missing_placeholders_found:
        print("::error::Template sync failed due to missing placeholders in configuration.")
        sys.exit(1)

    print("Template sync completed successfully.")


if __name__ == "__main__":
    main()