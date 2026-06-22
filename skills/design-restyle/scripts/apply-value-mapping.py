#!/usr/bin/env python3
"""
Apply Value Mapping — systematically replace old hardcoded visual values
with new token references across a project's source files.

This script handles the mechanical 80% of value replacement. For context-aware
replacements (e.g., replacing #fff as background vs border), use the agent's
patch tool per-file.

Usage:
    python3 apply-value-mapping.py <project-path> <mapping-file> [--dry-run] [--verbose]
    python3 apply-value-mapping.py <project-path> <mapping-file> --include "*.css"
    python3 apply-value-mapping.py <project-path> <mapping-file> --exclude-token-files
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ──────────────────────────── Config ────────────────────────────

EXCLUDED_DIRS: Set[str] = {
    'node_modules', '.git', 'dist', '.next', '.nuxt',
    '.output', '.cache', '__pycache__', 'build', 'coverage',
    '.turbo',
}

# Don't replace values in these dirs (audit/design data stays raw)
ALWAYS_SKIP_DIRS: Set[str] = {
    '.design',
}

EXCLUDED_EXTENSIONS: Set[str] = {
    '.d.ts', '.d.tsx', '.min.css', '.min.js',
    '.png', '.jpg', '.jpeg', '.gif', '.svg',
    '.woff', '.woff2', '.ttf', '.eot',
    '.ico', '.mp4', '.webm', '.pdf',
    '.lock', '.log',
}

CSS_EXTENSIONS = {'.css', '.scss', '.less'}
SOURCE_EXTENSIONS = {'.jsx', '.tsx', '.js', '.ts', '.vue', '.svelte'}

# Patterns that indicate a file is a token definition file (don't touch)
TOKEN_FILE_PATTERNS: List[str] = [
    r':root\s*\{',
    r'theme\s*:\s*\{',
    r'extend\s*:\s*\{',
    r'\$[\w-]+\s*:\s',
    r'--color-',
    r'--spacing-',
    r'--font-',
    r'--border-',
    r'--shadow-',
]


def is_token_file(content: str) -> bool:
    """Check if content looks like a token definition file."""
    for pattern in TOKEN_FILE_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False


# ──────────────────────────── Mapping Reader ────────────────────────────

def read_mapping(path_str: str) -> Dict[str, str]:
    """
    Read a mapping file.
    Supports JSON: {"old_value": "new_value"}
    and YAML-like: old_value: new_value
    """
    path = Path(path_str)
    if not path.is_file():
        print(f"Error: mapping file not found: {path}", file=sys.stderr)
        sys.exit(1)

    content = path.read_text(encoding='utf-8', errors='replace')

    mapping: Dict[str, str] = {}

    if path.suffix == '.json':
        data = json.loads(content)
        # Support nested structure: { "colors": { "#1890ff": "var(--primary)", ... } }
        # and flat: { "#1890ff": "var(--primary)", ... }
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    # Nested — check for "replaces" key
                    if 'replaces' in value and 'value' in value:
                        target = str(value['value'])
                        for old in value['replaces']:
                            mapping[str(old)] = target
                    # Nested but individual entries (like section: { key: val })
                    else:
                        for sub_key, sub_val in value.items():
                            if isinstance(sub_val, dict):
                                if 'replaces' in sub_val and 'value' in sub_val:
                                    target = str(sub_val['value'])
                                    for old in sub_val['replaces']:
                                        mapping[str(old)] = target
                                elif 'value' in sub_val:
                                    mapping[str(sub_val['value'])] = str(sub_val['value'])
                            else:
                                mapping[str(sub_val)] = str(sub_val)
                else:
                    mapping[str(key)] = str(value)
    else:
        # YAML-like: simple key: value lines
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('-'):
                continue
            m = re.match(r'^([^:]+):\s*(.+)$', line)
            if m:
                old_val = m.group(1).strip().strip('"\'')
                new_val = m.group(2).strip().strip('"\'')
                if old_val and new_val:
                    mapping[old_val] = new_val

    return mapping


def expand_mapping(mapping: Dict[str, str], is_css: bool) -> Dict[str, str]:
    """
    Expand mapping to handle different quoting and format variations.
    For CSS files, also match hex without # prefix in some contexts.
    """
    expanded = dict(mapping)

    for old_val, new_val in mapping.items():
        # If it's a hex color, also match single-quoted and double-quoted versions
        if old_val.startswith('#'):
            expanded[f"'{old_val}'"] = f"'{new_val}'"
            expanded[f'"{old_val}"'] = f'"{new_val}"'
            expanded[f"`{old_val}`"] = f"`{new_val}`"

        # If it's a px value, match variations
        if old_val.endswith('px'):
            num = old_val[:-2]
            expanded[f"'{num}px'"] = f"'{new_val}'"
            expanded[f'"{num}px"'] = f'"{new_val}"'

    return expanded


# ──────────────────────────── File Discovery ────────────────────────────

def find_target_files(root: Path, include: Optional[str] = None,
                      exclude_token_files: bool = False) -> List[Path]:
    """Find source files to apply mappings to."""
    patterns = [
        "**/*.css", "**/*.scss", "**/*.less",
        "**/*.jsx", "**/*.tsx",
        "**/*.js", "**/*.ts",
        "**/*.vue", "**/*.svelte",
        "**/*.html",
    ]

    if include:
        patterns = [f"**/{include}"]

    files: List[Path] = []
    for pat in patterns:
        for p in root.rglob(pat):
            rel = p.relative_to(root)
            parts = rel.parts
            if any(seg in parts for seg in EXCLUDED_DIRS):
                continue
            if any(str(rel).startswith(d) for d in ALWAYS_SKIP_DIRS):
                continue
            if any(str(rel).endswith(ext) for ext in EXCLUDED_EXTENSIONS):
                continue
            if p.is_file() and p.stat().st_size <= 500_000:
                if exclude_token_files:
                    content = p.read_text(encoding='utf-8', errors='replace')
                    if is_token_file(content):
                        continue
                files.append(p)

    return sorted(set(files))


# ──────────────────────────── Replacement ────────────────────────────

def replace_in_content(content: str, mapping: Dict[str, str],
                       file_suffix: str, verbose: bool = False) -> Tuple[str, int, Dict[str, int]]:
    """Apply value replacements in content. Returns (new_content, total_replacements, per_key_counts)."""
    new_content = content
    total = 0
    per_key: Dict[str, int] = defaultdict(int)

    # Sort by length (longest first) to avoid partial replacements
    sorted_keys = sorted(mapping.keys(), key=len, reverse=True)

    for old_val in sorted_keys:
        new_val = mapping[old_val]

        # Escape regex special chars in old value
        escaped_old = re.escape(old_val)

        count = new_content.count(old_val)
        if count == 0:
            continue

        if file_suffix in ('.css', '.scss', '.less'):
            # CSS: replace values, not inside CSS variable definitions
            # Only replace when the value appears after a colon (property: value)
            # Pattern: look for old_val as a standalone value (not part of a longer token)
            replaced, n = re.subn(
                rf'(?<=:\s*){escaped_old}(?=\s*;?\s*$|(?:\s+!important)|(?=\s+[#.a-z]))',
                new_val.replace('\\', '\\\\'),
                new_content,
                flags=re.MULTILINE
            )
            if n > 0:
                new_content = replaced
                total += n
                per_key[old_val] += n
        else:
            # JSX/TSX/JS/TS: simple string replacement
            # Only replace if it looks like it's in a style context
            # Heuristic: replace if surrounded by quotes or backticks
            replaced, n = re.subn(
                rf"(['\"`]){escaped_old}(['\"`])",
                rf"\1{new_val}\2",
                new_content
            )
            if n > 0:
                new_content = replaced
                total += n
                per_key[old_val] += n

        # Also do non-quoted replacement for CSS-in-JS numeric values
        if file_suffix in ('.jsx', '.tsx', '.js', '.ts', '.vue'):
            # E.g., fontSize: 14 vs fontSize: '14px' — handle bare numbers
            if old_val.endswith('px') and old_val[:-2].isdigit():
                num = old_val[:-2]
                # Match: number followed by comma or closing brace (no unit)
                replaced2, n2 = re.subn(
                    rf'(?<=:\s*){re.escape(num)}(?=\s*[,}}])',
                    new_val,
                    new_content
                )
                if n2 > 0:
                    new_content = replaced2
                    total += n2
                    per_key[old_val] += n2

    return new_content, total, dict(per_key)


# ──────────────────────────── Main ────────────────────────────

def apply_mapping(project_path: str, mapping_path: str,
                  dry_run: bool = False, verbose: bool = False,
                  include: Optional[str] = None,
                  exclude_token_files: bool = False):
    root = Path(project_path).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory.", file=sys.stderr)
        sys.exit(1)

    # Read mapping
    mapping = read_mapping(mapping_path)
    if not mapping:
        print("Error: No valid mappings found in file.", file=sys.stderr)
        sys.exit(1)

    print(f"📋 Loaded {len(mapping)} value mappings")
    if verbose:
        for old_val, new_val in sorted(mapping.items())[:10]:
            print(f"   {old_val} → {new_val}")
        if len(mapping) > 10:
            print(f"   ... and {len(mapping) - 10} more")

    # Expand mapping (add quoted variants)
    expanded_css = expand_mapping(mapping, is_css=True)
    expanded_source = expand_mapping(mapping, is_css=False)

    print(f"   Expanded to {len(expanded_css)} CSS patterns and {len(expanded_source)} source patterns")

    # Find files
    files = find_target_files(root, include, exclude_token_files)
    css_files = [f for f in files if f.suffix in CSS_EXTENSIONS]
    source_files = [f for f in files if f.suffix in SOURCE_EXTENSIONS]

    print(f"\n📁 Found {len(files)} target files ({len(css_files)} CSS, {len(source_files)} source)")
    if verbose:
        for f in files[:15]:
            print(f"   📄 {f.relative_to(root)}")
        if len(files) > 15:
            print(f"   ... and {len(files) - 15} more")

    if dry_run:
        print(f"\n{'='*50}")
        print(f"  🏃 DRY RUN — no files will be modified")
        print(f"{'='*50}")

    # Apply
    total_replacements = 0
    modified_files = 0
    per_key_totals: Dict[str, int] = defaultdict(int)
    skipped_token_files = 0

    for f in files:
        rel = str(f.relative_to(root))
        suffix = f.suffix

        try:
            original = f.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            if verbose:
                print(f"   ⚠️  Could not read {rel}: {e}")
            continue

        if suffix in CSS_EXTENSIONS:
            new_content, n, per_key = replace_in_content(original, expanded_css, suffix, verbose)
        else:
            new_content, n, per_key = replace_in_content(original, expanded_source, suffix, verbose)

        if n > 0:
            if exclude_token_files and is_token_file(original):
                skipped_token_files += 1
                if verbose:
                    print(f"   ⏭️  {rel}: {n} replacements skipped (token definition file)")
                continue

            if verbose:
                changes = ', '.join(f"'{k}'→'{v}' ({c}x)" for k, v, c in
                                    [(k, mapping.get(k, k), c) for k, c in per_key.items()])
                print(f"   🔄 {rel}: {n} replacement(s) — {changes}")

            if not dry_run:
                f.write_text(new_content, encoding='utf-8')

            total_replacements += n
            modified_files += 1
            for k, c in per_key.items():
                per_key_totals[k] += c

    # Report
    print(f"\n{'='*50}")
    if dry_run:
        print(f"  DRY RUN COMPLETE")
    else:
        print(f"  ✅ Apply Complete")
    print(f"{'='*50}")
    print(f"  Files modified:  {modified_files}")
    print(f"  Total replacements: {total_replacements}")
    if skipped_token_files:
        print(f"  Skipped (token files): {skipped_token_files}")

    if per_key_totals:
        print(f"\n  Top replacements:")
        for k, c in sorted(per_key_totals.items(), key=lambda x: -x[1])[:10]:
            print(f"    '{k}' → '{mapping.get(k, k)}': {c}x")

    if not modified_files:
        print(f"\n  ⚠️  No replacements made. Check:")
        print(f"     - Are the old values actually present in source files?")
        print(f"     - Are they in excluded directories?")
        print(f"     - Different case or spacing?")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Apply old→new value mappings across a project"
    )
    parser.add_argument("project", help="Path to the frontend project")
    parser.add_argument("mapping", help="Path to mapping file (JSON or YAML)")
    parser.add_argument("--dry-run", "-n", action="store_true",
                       help="Show what would be changed without modifying files")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Print per-file replacement details")
    parser.add_argument("--include", help="Only process files matching glob (e.g., '*.css')")
    parser.add_argument("--exclude-token-files", "-e", action="store_true",
                       help="Skip files that look like token definitions")
    args = parser.parse_args()
    sys.exit(apply_mapping(args.project, args.mapping,
                           args.dry_run, args.verbose,
                           args.include, args.exclude_token_files))
