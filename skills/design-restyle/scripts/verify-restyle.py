#!/usr/bin/env python3
"""
Restyle Verification — checks that all hardcoded values have been replaced
with token references, and that the project still builds.

Usage:
    python3 verify-restyle.py /path/to/project [--tokens TOKENS_FILE] [--check-remaining] [--build]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ──────────────────────────── Helpers ────────────────────────────

EXCLUDED_DIRS = {'node_modules', '.git', 'dist', '.next', '.nuxt',
                 '.output', '.cache', '__pycache__', 'build', 'coverage',
                 '.turbo', '.design'}

EXCLUDED_EXTENSIONS = {'.d.ts', '.d.tsx', '.min.css', '.min.js',
                       '.png', '.jpg', '.jpeg', '.gif', '.svg',
                       '.woff', '.woff2', '.ttf', '.eot',
                       '.ico', '.mp4', '.webm', '.pdf'}


def glob_sources(root: Path) -> List[Path]:
    """Find source files that could have hardcoded values."""
    patterns = [
        "**/*.css", "**/*.scss", "**/*.less",
        "**/*.jsx", "**/*.tsx",
        "**/*.js", "**/*.ts",
        "**/*.vue", "**/*.svelte",
        "**/*.html",
    ]
    files = []
    for pat in patterns:
        for p in root.rglob(pat):
            rel = p.relative_to(root)
            parts = rel.parts
            if any(seg in parts for seg in EXCLUDED_DIRS):
                continue
            if any(str(rel).endswith(ext) for ext in EXCLUDED_EXTENSIONS):
                continue
            if p.is_file() and p.stat().st_size <= 500_000:
                files.append(p)
    return sorted(set(files))


def read_file(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return ""


# ──────────────────────────── Color Extraction ────────────────────────────

RE_HEX = re.compile(r'#[0-9a-fA-F]{3,8}', re.IGNORECASE)
RE_RGB = re.compile(r'rgba?\s*\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(?:,\s*[\d.]+\s*)?\)', re.IGNORECASE)
RE_HSL = re.compile(r'hsla?\s*\(\s*\d{1,3}\s*,\s*\d{1,3}%\s*,\s*\d{1,3}%\s*(?:,\s*[\d.]+\s*)?\)', re.IGNORECASE)
RE_PX = re.compile(r'(\d+(?:\.\d+)?)px')
RE_SIZE_PROP = re.compile(r'(margin|padding|gap|font-size|border-radius|border-width|width|height|line-height|letter-spacing)\s*:\s*', re.IGNORECASE)
RE_BORDER_RADIUS = re.compile(r'border-radius\s*:\s*(\d+(?:\.\d+)?)px', re.IGNORECASE)


def extract_hex_colors(content: str) -> Set[str]:
    """Extract all unique hex colors from content."""
    colors = set()
    for m in RE_HEX.finditer(content):
        c = m.group(0).lower()
        # Skip if inside var() — already tokenized
        pos = m.start()
        before = content[max(0, pos - 20):pos]
        if 'var(' in before or '$' in before:
            continue
        # Skip if inside a CSS variable definition
        after = content[pos:pos + 50]
        if '--' in content[max(0, pos - 50):pos] and ':' in content[max(0, pos - 50):pos]:
            continue
        colors.add(c)
    return colors


def extract_px_values(content: str) -> Counter:
    """Extract all px values with categories."""
    values: Counter = Counter()
    for m in RE_PX.finditer(content):
        val = int(m.group(1))
        # Common utility values (0 = no style, shouldn't count)
        if val == 0:
            continue
        values[f'{val}px'] += 1
    return values


# ──────────────────────────── Token Parser ────────────────────────────

def parse_tokens_file(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Parse a synthesis-recommendations.yaml or value-mapping.json file."""
    if not path or not path.is_file():
        return None

    content = read_file(path)
    if not content:
        return None

    # Try JSON first
    if path.suffix == '.json':
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None

    # Try YAML-like parsing (simple key: value)
    if path.suffix in ('.yaml', '.yml'):
        result: Dict[str, Any] = {}
        current_section: List[str] = []
        # Parse flat replaces list
        replaces_map: Dict[str, str] = {}

        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            # Comment
            if not stripped or stripped.startswith('#'):
                continue
            # Section header
            if not stripped[0].isalnum() and not stripped[0] == '"' and not stripped[0] == "'":
                continue
            # "replaces:" list
            if stripped.startswith('replaces:'):
                continue
            if stripped.startswith('- "') or stripped.startswith("- '"):
                m = re.match(r'- [\'"]([^\'"]+)[\'"]', stripped)
                if m:
                    replaces_map[m.group(1)] = current_section[0] if current_section else 'unknown'
                continue
            # key: value pair
            m = re.match(r'(\S[\w-]*)\s*:\s*(.+)$', stripped)
            if m:
                key, val = m.group(1), m.group(2).strip().strip("'\"")
                current_section = [key]

        # Build a flat old→new map from the nested structure
        # Walk the whole file looking for "replaces:" lists and their parent value
        parent_value = None
        for line in lines:
            stripped = line.strip()
            m = re.match(r'\s+value\s*:\s*[\'"]([^\'"]+)[\'"]', stripped)
            if m:
                parent_value = m.group(1)
                continue
            m = re.match(r'\s+- [\'"]([^\'"]+)[\'"]', stripped)
            if m and parent_value:
                result[m.group(1)] = parent_value

        return {'flat_map': result} if result else None

    return None


# ──────────────────────────── Main Checks ────────────────────────────

def check_remaining_colors(root: Path, known_old_colors: Set[str]) -> List[dict]:
    """Find files that still use old hardcoded colors."""
    findings = []
    files = glob_sources(root)

    for f in files:
        content = read_file(f)
        if not content:
            continue
        rel = str(f.relative_to(root))
        colors = extract_hex_colors(content)
        remaining = colors & known_old_colors if known_old_colors else colors

        for c in sorted(remaining):
            # Count occurrences
            count = content.count(c)
            findings.append({
                'file': rel,
                'value': c,
                'count': count,
            })

    return findings


def check_spacing_grid(root: Path, grid: int = 4) -> List[dict]:
    """Find spacing values that don't conform to the grid."""
    findings = []
    files = glob_sources(root)

    for f in files:
        content = read_file(f)
        if not content:
            continue
        rel = str(f.relative_to(root))
        values = extract_px_values(content)

        for val_str, count in values.items():
            val = int(val_str.replace('px', ''))
            if val % grid != 0 and val > 0:
                findings.append({
                    'file': rel,
                    'value': val_str,
                    'count': count,
                })

    return findings


def check_radius_consistency(root: Path) -> List[str]:
    """Check how many unique border-radius values exist."""
    files = glob_sources(root)
    radii: Counter = Counter()

    for f in files:
        content = read_file(f)
        if not content:
            continue
        for m in RE_BORDER_RADIUS.finditer(content):
            radii[f'{m.group(1)}px'] += 1

    # Return top values
    return [f'{v} ({c}x)' for v, c in radii.most_common(10)]


def check_font_scale(root: Path) -> Dict[str, int]:
    """Check what font sizes are still in use."""
    files = glob_sources(root)
    font_sizes: Counter = Counter()

    for f in files:
        content = read_file(f)
        if not content:
            continue
        for m in RE_PX.finditer(content):
            # Check if preceded by font-size property
            pos = m.start()
            before = content[max(0, pos - 60):pos]
            if re.search(r'font-size\s*:', before, re.IGNORECASE) or \
               re.search(r'fontSize\s*:', before):
                font_sizes[f'{m.group(1)}px'] += 1

    return dict(font_sizes.most_common(15))


def try_build(root: Path) -> Tuple[bool, str]:
    """Try to build the project."""
    build_commands = [
        (['npm', 'run', 'build'], 'npm'),
        (['yarn', 'build'], 'yarn'),
        (['pnpm', 'build'], 'pnpm'),
        (['npx', 'next', 'build'], 'npx'),
        (['npx', 'vite', 'build'], 'npx'),
    ]

    for cmd, _name in build_commands:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=root, timeout=120)
            if r.returncode == 0:
                return True, f"Build succeeded ({_name})."
            # Try next command
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # Try detecting build script from package.json
    pkg_file = root / 'package.json'
    if pkg_file.is_file():
        try:
            pkg = json.loads(read_file(pkg_file))
            scripts = pkg.get('scripts', {})
            if 'build' in scripts:
                cmd = scripts['build']
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=root, timeout=120)
                if r.returncode == 0:
                    return True, f"Build succeeded (via `{cmd}`)."
                return False, f"Build failed (via `{cmd}`):\n{r.stderr[-500:]}" if r.stderr else "Build failed."
        except Exception:
            pass

    return False, "Could not find a build command."


# ──────────────────────────── Main ────────────────────────────

def verify(project_path: str, tokens_path: Optional[str] = None,
           check_remaining: bool = False, do_build: bool = False):
    root = Path(project_path).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory.", file=sys.stderr)
        sys.exit(1)

    print(f"{'='*55}")
    print(f"  🔍 Restyle Verification for {root.name}")
    print(f"{'='*55}\n")

    results = {
        'colors': {'passed': False, 'details': ''},
        'spacing': {'passed': False, 'details': ''},
        'radius': {'passed': False, 'details': ''},
        'fonts': {'passed': False, 'details': ''},
        'build': {'passed': False, 'details': 'not checked'},
    }

    # ── Parse token file for known old colors ──
    known_old: Set[str] = set()
    flat_map: Dict[str, str] = {}

    if tokens_path:
        parsed = parse_tokens_file(Path(tokens_path))
        if parsed and 'flat_map' in parsed:
            flat_map = parsed['flat_map']
            known_old = set(flat_map.keys())
            # Also look in the synthesis file for old→new mapping
            alt_path = root / '.design/audit' / 'synthesis-recommendations.yaml'
            if alt_path.is_file():
                alt_parsed = parse_tokens_file(alt_path)
                if alt_parsed and 'flat_map' in alt_parsed:
                    flat_map.update(alt_parsed['flat_map'])
                    known_old.update(alt_parsed['flat_map'].keys())

        if known_old:
            print(f"📋 Loaded {len(known_old)} known old values from token file.")
        else:
            print(f"⚠️  Token file found but no replaces list parsed. "
                  f"Checking all colors as potential issues.")
    else:
        print("ℹ️  No token file provided. Checking all hardcoded colors as potential issues.")

    # ── 1. Remaining color check ──
    print("\n📌 1. Remaining Hardcoded Colors...")
    remaining = check_remaining_colors(root, known_old)

    if remaining:
        # Group by file
        by_file = defaultdict(list)
        for r in remaining:
            by_file[r['file']].append(r)

        print(f"   Found {len(remaining)} remaining hardcoded value(s) in {len(by_file)} file(s):")
        for file_path in sorted(by_file)[:15]:
            items = by_file[file_path]
            vals = ', '.join(f"`{i['value']}` ({i['count']}x)" for i in items[:5])
            print(f"   📄 {file_path}")
            print(f"       {vals}")
        if len(by_file) > 15:
            print(f"   ... and {len(by_file) - 15} more file(s)")

        results['colors'] = {
            'passed': False,
            'details': f"{len(remaining)} remain in {len(by_file)} files"
        }
    else:
        print("   ✅ All colors tokenized — no hardcoded values remain.")
        results['colors'] = {'passed': True, 'details': 'clean'}

    # ── 2. Spacing grid compliance ──
    print("\n📌 2. Spacing Grid Compliance...")
    grid = 4

    spacing_issues = check_spacing_grid(root, grid)

    if spacing_issues:
        # Group by value
        by_value = Counter()
        for s in spacing_issues:
            by_value[s['value']] += s['count']

        off_grid = [f"{v} ({c}x)" for v, c in by_value.most_common(10)]
        print(f"   ⚠️  {len(by_value)} off-grid values found (grid: {grid}px):")
        print(f"       {', '.join(off_grid)}")
        results['spacing'] = {
            'passed': len(by_value) < 5,
            'details': f"{len(by_value)} off-grid, top: {', '.join(off_grid[:5])}"
        }
    else:
        print(f"   ✅ All spacing values conform to {grid}px grid.")
        results['spacing'] = {'passed': True, 'details': 'clean'}

    # ── 3. Border-radius consistency ──
    print("\n📌 3. Border-Radius Consistency...")
    radii = check_radius_consistency(root)

    if len(radii) > 3:
        print(f"   ⚠️  {len(radii)} unique border-radius values:")
        for r in radii:
            print(f"       {r}")
        results['radius'] = {
            'passed': False,
            'details': f"{len(radii)} unique radii"
        }
    elif len(radii) > 0:
        print(f"   ✅ {len(radii)} border-radius values (acceptable):")
        for r in radii:
            print(f"       {r}")
        results['radius'] = {'passed': True, 'details': f"{len(radii)} values"}
    else:
        print("   ℹ️  No border-radius values detected.")
        results['radius'] = {'passed': True, 'details': 'none found'}

    # ── 4. Font size scale ──
    print("\n📌 4. Font Size Scale...")
    font_sizes = check_font_scale(root)

    if len(font_sizes) > 7:
        print(f"   ⚠️  {len(font_sizes)} unique font sizes found:")
        for sz, cnt in sorted(font_sizes.items(), key=lambda x: -x[1])[:10]:
            print(f"       {sz}: {cnt}x")
        results['fonts'] = {
            'passed': False,
            'details': f"{len(font_sizes)} unique sizes"
        }
    elif font_sizes:
        print(f"   ✅ {len(font_sizes)} font sizes in use:")
        for sz, cnt in sorted(font_sizes.items(), key=lambda x: -x[1]):
            print(f"       {sz}: {cnt}x")
        results['fonts'] = {'passed': True, 'details': f"{len(font_sizes)} sizes"}
    else:
        print("   ℹ️  No font-size declarations detected in CSS.")
        results['fonts'] = {'passed': True, 'details': 'none found'}

    # ── 5. Build check ──
    if do_build:
        print("\n📌 5. Build Check...")
        success, msg = try_build(root)
        if success:
            print(f"   ✅ {msg}")
            results['build'] = {'passed': True, 'details': msg}
        else:
            print(f"   ❌ {msg}")
            results['build'] = {'passed': False, 'details': msg}
    else:
        print("\n📌 5. Build Check: skipped (use --build to enable)")

    # ── Summary ──
    print(f"\n{'='*55}")
    print(f"  📊 Restyle Verification Summary")
    print(f"{'='*55}")

    all_passed = True
    for check_name, result in results.items():
        icon = '✅' if result['passed'] else ('❌' if not result['passed'] and result['details'] != 'not checked' else '⏭️')
        print(f"  {icon} {check_name.title():<12} {result['details']}")
        if not result['passed'] and result['details'] != 'not checked':
            all_passed = False

    print(f"{'='*55}")
    if all_passed and do_build:
        print(f"  ✅ ALL CHECKS PASSED — restyle is complete!")
    elif all_passed and not do_build:
        print(f"  ⚠️  Visual checks passed. Run --build to confirm build.")
    else:
        print(f"  ⚠️  Some checks failed. Review and fix remaining issues.")
    print(f"{'='*55}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify restyle consistency and completeness")
    parser.add_argument("project", help="Path to the frontend project")
    parser.add_argument("--tokens", help="Path to token mapping file (synthesis-recommendations.yaml or value-mapping.json)")
    parser.add_argument("--check-remaining", "-r", action="store_true", help="Check for remaining hardcoded values")
    parser.add_argument("--build", "-b", action="store_true", help="Try to build the project")
    args = parser.parse_args()
    sys.exit(verify(args.project, args.tokens, args.check_remaining, args.build))
