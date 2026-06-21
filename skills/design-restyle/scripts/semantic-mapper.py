#!/usr/bin/env python3
"""
Semantic Mapper — reads design-audit output and maps hardcoded values
to a reference design system's tokens based on CSS property semantics.

This is the bridge between "what the project has" (audit) and "what it should
look like" (reference system).

Usage:
    python3 semantic-mapper.py <project-path> --reference tailwind [--output FILE] [--dry-run] [--verbose]
    python3 semantic-mapper.py <project-path> --reference antd --output mapping.json
    python3 semantic-mapper.py <project-path> --list               # list available refs
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ──────────────────────────── Config ────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
REFERENCES_DIR = SCRIPT_DIR / "references"
DEFAULT_REF_FILE = REFERENCES_DIR / "default.json"

# CSS property → semantic role group mapping
# This determines WHAT a value is used for in the UI
PROPERTY_TO_ROLE: Dict[str, str] = {
    # ── Color properties ──
    'color': 'color/text',
    'fill': 'color/text',
    'stroke': 'color/text',
    'background-color': 'color/background',
    'background': 'color/background',
    'bg': 'color/background',
    'border-color': 'color/border',
    'outline-color': 'color/border',
    'outline': 'color/border',
    'accent-color': 'color/accent',
    'caret-color': 'color/text',
    'placeholder-color': 'color/text',
    'text-decoration-color': 'color/text',
    'box-shadow': 'shadow',
    'text-shadow': 'shadow/text',
    'border-top-color': 'color/border',
    'border-bottom-color': 'color/border',
    'border-left-color': 'color/border',
    'border-right-color': 'color/border',
}

# More specific role determination based on property + surrounding context
PROPERTY_TO_EXACT_ROLE: Dict[str, str] = {
    # Text foreground
    'color': 'text-primary',
    'fill': 'text-primary',
    'stroke': 'text-primary',
    'caret-color': 'text-primary',
    'placeholder-color': 'text-tertiary',
    # Backgrounds
    'background-color': 'bg-page',
    'background': 'bg-page',
    # Borders
    'border-color': 'border-default',
    'outline-color': 'border-default',
    # Shadow
    'box-shadow': 'shadow',
    'text-shadow': 'shadow',
}

# For exact role, we refine based on value heuristics
# e.g., white/light backgrounds → bg-card, slightly darker → bg-page, even darker → bg-surface
VALUE_HEURISTICS: Dict[str, Dict[str, str]] = {
    'color/background': {
        '#ffffff': 'bg-card',
        '#fff': 'bg-card',
        'white': 'bg-card',
        '#fafafa': 'bg-surface',
        '#f9fafb': 'bg-page',
        '#f5f5f5': 'bg-page',
        '#f0f2f5': 'bg-page',
        '#f3f4f6': 'bg-surface',
        '#f0f0f0': 'bg-surface',
        '#e8e8e8': 'bg-active',
        '#e5e7eb': 'bg-active',
    },
    'color/text': {
        '#ffffff': 'text-inverse',
        '#fff': 'text-inverse',
        'white': 'text-inverse',
    },
    'color/border': {
        '#ffffff': 'border-light',
        '#fff': 'border-light',
        'white': 'border-light',
    }
}

# Spacing properties
SPACING_PROPERTIES = {
    'margin', 'padding', 'gap', 'grid-gap',
    'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
    'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'column-gap', 'row-gap',
}

# ──────────────────────────── Reference Loader ────────────────────────────

def list_references() -> Dict[str, str]:
    """List available reference presets with descriptions."""
    refs = {}
    if DEFAULT_REF_FILE.is_file():
        data = json.loads(DEFAULT_REF_FILE.read_text(encoding='utf-8'))
        for key, val in data.items():
            if key.startswith('_'):
                continue
            if isinstance(val, dict):
                refs[key] = val.get('description', val.get('name', key))
    return refs


def load_reference(name: str) -> Optional[Dict[str, Any]]:
    """Load a reference design system by name."""
    if not DEFAULT_REF_FILE.is_file():
        print(f"Error: Reference file not found at {DEFAULT_REF_FILE}", file=sys.stderr)
        return None

    data = json.loads(DEFAULT_REF_FILE.read_text(encoding='utf-8'))
    ref = data.get(name)
    if not ref:
        available = [k for k in data if not k.startswith('_')]
        print(f"Error: Unknown reference '{name}'. Available: {', '.join(available)}", file=sys.stderr)
        return None

    css = ref.get('css', {})
    return {
        'name': ref.get('name', name),
        'token_map': {
            # Flatten colors
            'colors': css.get('colors', {}),
            # Spacing
            'spacing': css.get('spacing', {}),
            # Typography
            'typography': css.get('typography', {}),
            'font_sizes': {k: v for k, v in css.get('typography', {}).items() if k.startswith('font-size')},
            'font_weights': {k: v for k, v in css.get('typography', {}).items() if k.startswith('font-weight')},
            # Radius
            'radius': css.get('radius', {}),
            # Shadow
            'shadow': css.get('shadow', {}),
        },
        'raw': css,
    }


# ──────────────────────────── Audit Data Loader ────────────────────────────

def load_audit(root: Path) -> Optional[Dict[str, Any]]:
    """Load the value-map.json from .design-audit/."""
    paths = [
        root / '.design-audit' / '06-value-map.json',
        root / '.design-audit' / 'value-map.json',
    ]
    for p in paths:
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                continue

    print(f"Error: No value-map.json found in {root / '.design-audit/'}.", file=sys.stderr)
    print("  Run `design-audit` first.", file=sys.stderr)
    return None


def get_usage_examples(data: Dict[str, Any], value_type: str, value: str) -> List[dict]:
    """Get usage examples for a specific value from the audit data."""
    category = data.get(value_type, {})
    entry = category.get(value, {})
    return entry.get('usage', [])


# ──────────────────────────── Semantic Classification ────────────────────────────

def classify_color_value(property_name: str, value: str, properties_used: Counter) -> str:
    """
    Classify a color value to its most likely semantic role.
    Uses CSS property + value heuristics + usage frequency.
    """
    # Step 1: Determine broad category from property
    prop_lower = property_name.lower()
    role_category = PROPERTY_TO_ROLE.get(prop_lower, 'color/other')

    # Step 2: For background colors, use value heuristics
    if role_category == 'color/background':
        hex_val = value.lower().strip()
        if hex_val in VALUE_HEURISTICS.get('color/background', {}):
            return VALUE_HEURISTICS['color/background'][hex_val]

        # Heuristic: very light → likely page bg or card bg
        if value.startswith('#'):
            try:
                r = int(value[1:3], 16) if len(value) >= 7 else 255
                g = int(value[3:5], 16) if len(value) >= 7 else 255
                b = int(value[5:7], 16) if len(value) >= 7 else 255
                brightness = (r * 299 + g * 587 + b * 114) / 1000

                if brightness > 250:
                    return 'bg-card'       # Near white
                elif brightness > 240:
                    return 'bg-page'       # Very light gray
                elif brightness > 220:
                    return 'bg-surface'    # Light gray
                elif brightness > 180:
                    return 'bg-hover'      # Medium gray
                else:
                    return 'bg-active'     # Darker
            except ValueError:
                pass

    # Step 3: For text colors, use brightness heuristic
    if role_category == 'color/text':
        if value.startswith('#'):
            try:
                r = int(value[1:3], 16) if len(value) >= 7 else 0
                g = int(value[3:5], 16) if len(value) >= 7 else 0
                b = int(value[5:7], 16) if len(value) >= 7 else 0
                brightness = (r * 299 + g * 587 + b * 114) / 1000

                if brightness > 200:
                    return 'text-inverse'
                elif brightness > 150:
                    return 'text-tertiary'
                elif brightness > 100:
                    return 'text-secondary'
                else:
                    return 'text-primary'
            except ValueError:
                pass

    # Step 4: For border colors
    if role_category == 'color/border':
        if value.lower() in ('transparent', 'currentColor'):
            return 'border-default'
        if value.startswith('#'):
            try:
                r = int(value[1:3], 16) if len(value) >= 7 else 0
                g = int(value[3:5], 16) if len(value) >= 7 else 0
                b = int(value[5:7], 16) if len(value) >= 7 else 0
                brightness = (r * 299 + g * 587 + b * 114) / 1000
                if brightness > 230:
                    return 'border-light'
                elif brightness > 180:
                    return 'border-default'
                else:
                    return 'border-hover'
            except ValueError:
                pass

    # Step 5: Fallback — use the most common property usage
    if properties_used:
        most_common_prop = properties_used.most_common(1)[0][0]
        return PROPERTY_TO_EXACT_ROLE.get(most_common_prop, role_category)

    return role_category


def classify_size_value(property_name: str, value: str) -> str:
    """Classify a size/spacing value to its semantic role."""
    prop_lower = property_name.lower()

    if prop_lower in ('font-size',):
        return 'typography/font-size'
    if prop_lower in ('font-weight',):
        return 'typography/font-weight'
    if prop_lower in ('line-height',):
        return 'typography/line-height'
    if prop_lower in SPACING_PROPERTIES:
        return 'spacing'
    if prop_lower in ('border-radius', 'border-top-left-radius',
                      'border-top-right-radius', 'border-bottom-left-radius',
                      'border-bottom-right-radius'):
        return 'radius'
    if prop_lower in ('border-width', 'border-top-width', 'border-bottom-width',
                      'border-left-width', 'border-right-width'):
        return 'border-width'
    if 'width' in prop_lower or 'height' in prop_lower:
        return 'dimension'
    if 'letter-spacing' in prop_lower or 'word-spacing' in prop_lower:
        return 'typography/letter-spacing'

    return 'sizing/other'


# ──────────────────────────── Mapping Generator ────────────────────────────

def generate_color_mapping(
    audit_data: Dict[str, Any],
    ref_tokens: Dict[str, Any],
    verbose: bool = False
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Generate color value mapping.
    Returns (flat_mapping, analysis_report).
    """
    colors_data = audit_data.get('colors', {})
    ref_colors = ref_tokens.get('colors', {})
    ref_spacing = ref_tokens.get('spacing', {})

    mapping: Dict[str, str] = {}
    analysis: Dict[str, Any] = {
        'grouped_by_role': defaultdict(list),
        'role_recommendations': {},
    }

    # For each unique color value in the audit
    for value, info in colors_data.items():
        # Skip very rare values (likely noise, < 3 occurrences)
        count = info.get('count', 0)
        usage = info.get('usage', [])

        if not usage:
            continue

        # Collect all properties this value is used with
        properties_used = Counter(u.get('property', '') for u in usage)

        # Determine primary property and semantic role
        primary_property = properties_used.most_common(1)[0][0] if properties_used else 'color'

        # Get file examples
        example_files = list(set(u.get('file', '') for u in usage))[:3]

        role = classify_color_value(primary_property, value, properties_used)

        # Group by role
        role_key = role.replace('/', '-')
        analysis['grouped_by_role'][role_key].append({
            'value': value,
            'count': count,
            'properties': dict(properties_used.most_common(5)),
            'primary_property': primary_property,
            'example_files': example_files,
        })

    # For each role group, recommend the best reference token
    for role_key, items in analysis['grouped_by_role'].items():
        # Sort by frequency
        items.sort(key=lambda x: -x['count'])

        # Find the most frequent value for this role
        most_frequent = items[0]['value'] if items else None

        # Find the matching reference token
        ref_token_name = f"--color-{role_key}"
        ref_value = find_reference_value(role_key, ref_colors)

        analysis['role_recommendations'][role_key] = {
            'most_frequent_value': most_frequent,
            'reference_token': ref_token_name,
            'reference_value': ref_value,
            'total_occurrences': sum(i['count'] for i in items),
            'unique_values': len(items),
            'candidates': [i['value'] for i in items[:5]],
        }

        # Build the flat mapping: each old value → reference value
        if ref_value:
            for item in items:
                mapping[item['value']] = ref_value

    return mapping, dict(analysis)


def find_reference_value(role_key: str, ref_colors: Dict[str, str]) -> Optional[str]:
    """Find the reference value for a given semantic role key."""
    # Direct match
    if role_key in ref_colors:
        return ref_colors[role_key]

    # Try with underscores
    alt = role_key.replace('-', '_')
    if alt in ref_colors:
        return ref_colors[alt]

    # Try various prefix patterns
    for pattern in ['', 'color-', 'bg-', 'text-', 'border-']:
        for ref_key in ref_colors:
            if ref_key.replace('_', '-').endswith(role_key):
                return ref_colors[ref_key]

    return None


def generate_spacing_mapping(
    audit_data: Dict[str, Any],
    ref_tokens: Dict[str, Any],
    verbose: bool = False
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Generate spacing/size value mapping.
    Maps to the nearest named spacing token from the reference.
    """
    sizes_data = audit_data.get('sizes', {})
    ref_spacing = ref_tokens.get('spacing', {})
    ref_font_sizes = ref_tokens.get('font_sizes', {})
    ref_radius = ref_tokens.get('radius', {})

    grid = ref_spacing.get('grid', 4)

    mapping: Dict[str, str] = {}
    analysis = {
        'grid': grid,
        'spacing_map': {},
        'font_size_map': {},
        'radius_map': {},
    }

    # Build named spacing tokens lookup (value → token name)
    spacing_tokens = {}
    for k, v in ref_spacing.items():
        if k == 'grid':
            continue
        spacing_tokens[v] = f'var(--spacing-{k})'

    # Build font size tokens lookup
    font_size_tokens = {}
    for k, v in ref_font_sizes.items():
        # k is like 'font-size-xs', extract just 'xs'
        suffix = k.replace('font-size-', '').replace('font_', '')
        font_size_tokens[v] = f'var(--{k.replace("_", "-")})'

    # Build radius tokens
    radius_tokens = {}
    for k, v in ref_radius.items():
        radius_tokens[v] = f'var(--radius-{k})'

    # Map each unique size value
    for value, info in sizes_data.items():
        usage = info.get('usage', [])
        if not usage:
            continue

        properties_used = Counter(u.get('property', '') for u in usage)
        primary_prop = properties_used.most_common(1)[0][0] if properties_used else ''
        role = classify_size_value(primary_prop, value)

        if role == 'typography/font-size':
            # Map to nearest font size
            nearest = find_nearest_font_size(value, font_size_tokens)
            if nearest:
                mapping[value] = nearest
                analysis['font_size_map'][value] = nearest

        elif role == 'radius':
            # Map to nearest radius
            nearest = find_nearest_radius(value, radius_tokens)
            if nearest:
                mapping[value] = nearest
                analysis['radius_map'][value] = nearest

        elif role == 'spacing':
            # Map to nearest spacing token (snap to grid)
            nearest = find_nearest_spacing(value, spacing_tokens, grid)
            if nearest:
                mapping[value] = nearest
                analysis['spacing_map'][value] = nearest

    return mapping, analysis


def parse_px(value_str: str) -> Optional[float]:
    """Extract numeric px value from a string like '16px' or '1rem'."""
    m = re.match(r'(\d+(?:\.\d+)?)\s*(px|rem|em)', str(value_str).lower())
    if m:
        num = float(m.group(1))
        unit = m.group(2)
        if unit == 'rem':
            return num * 16
        if unit == 'em':
            return num * 16  # Rough approximation
        return num
    try:
        return float(value_str)
    except (ValueError, TypeError):
        return None


def find_nearest_spacing(value: str, token_map: Dict[str, str], grid: int) -> Optional[str]:
    """Find the nearest named spacing token for a px value."""
    px = parse_px(value)
    if px is None:
        return None

    # Snap to grid first
    snapped = round(px / grid) * grid

    # Try exact match first
    for token_val, token_name in token_map.items():
        token_px = parse_px(token_val)
        if token_px is not None and abs(token_px - snapped) < 0.5:
            return token_name

    # Find closest
    best_diff = float('inf')
    best_token = None
    for token_val, token_name in token_map.items():
        token_px = parse_px(token_val)
        if token_px is not None:
            diff = abs(token_px - snapped)
            if diff < best_diff:
                best_diff = diff
                best_token = token_name

    return best_token


def find_nearest_font_size(value: str, token_map: Dict[str, str]) -> Optional[str]:
    """Find the nearest font size token."""
    px = parse_px(value)
    if px is None:
        return None

    best_diff = float('inf')
    best_token = None
    for token_val, token_name in token_map.items():
        token_px = parse_px(token_val)
        if token_px is not None:
            diff = abs(token_px - px)
            if diff < best_diff:
                best_diff = diff
                best_token = token_name

    return best_token


def find_nearest_radius(value: str, token_map: Dict[str, str]) -> Optional[str]:
    """Find the nearest radius token."""
    px = parse_px(value)
    if px is None:
        return None

    best_diff = float('inf')
    best_token = None
    for token_val, token_name in token_map.items():
        token_px = parse_px(token_val)
        if token_px is not None:
            diff = abs(token_px - px)
            if diff < best_diff:
                best_diff = diff
                best_token = token_name

    return best_token


# ──────────────────────────── Output Generators ────────────────────────────

def write_mapping_json(mapping: Dict[str, str], path: Path, analysis: Dict[str, Any] = None):
    """Write the flat mapping as JSON."""
    output = {
        '_generated_by': 'semantic-mapper.py',
        '_reference': analysis.get('_reference', 'unknown') if analysis else 'unknown',
        '_note': 'Old values → new token values for apply-value-mapping.py',
        '_role_recommendations': analysis.get('role_recommendations', {}) if analysis else {},
        'mapping': mapping,
    }

    # Also write a separate analysis report
    path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding='utf-8')
    return path


def write_analysis_report(analysis: Dict[str, Any], path: Path):
    """Write a human-readable analysis report."""
    lines = []
    lines.append("# Semantic Mapping Analysis\n")

    ref_name = analysis.get('_reference', 'Unknown')
    lines.append(f"**Reference system**: {ref_name}\n")

    # Color roles
    role_recs = analysis.get('role_recommendations', {})
    if role_recs:
        lines.append("## Color Token Mapping\n")
        lines.append("| Semantic Role | Most Frequent | → Reference Token | Reference Value | Total |")
        lines.append("|---------------|---------------|-------------------|-----------------|-------|")
        for role_key, info in sorted(role_recs.items()):
            lines.append(f"| `{role_key}` | `{info.get('most_frequent_value', '-')}` | "
                        f"`{info.get('reference_token', '-')}` | `{info.get('reference_value', '-')}` | "
                        f"{info.get('total_occurrences', 0)} |")
        lines.append("")

        # Values per role
        lines.append("## Grouped Values\n")
        grouped = analysis.get('grouped_by_role', {})
        for role_key in sorted(grouped.keys()):
            items = grouped[role_key]
            rec = role_recs.get(role_key, {})
            lines.append(f"### {role_key} → `{rec.get('reference_value', '?')}`\n")
            lines.append("| Old Value | Count | Primary Property |")
            lines.append("|-----------|-------|-----------------|")
            for item in sorted(items, key=lambda x: -x['count'])[:10]:
                lines.append(f"| `{item['value']}` | {item['count']} | {item.get('primary_property', '-')} |")
            lines.append("")

    # Spacing
    spacing_map = analysis.get('spacing_map', {})
    if spacing_map:
        lines.append("## Spacing Mapping\n")
        lines.append(f"**Grid**: {analysis.get('grid', 4)}px\n")
        lines.append("| Old Value | → New Token |")
        lines.append("|-----------|------------|")
        for old_val, new_token in sorted(spacing_map.items(), key=lambda x: parse_px(x[0]) or 0):
            lines.append(f"| `{old_val}` | `{new_token}` |")
        lines.append("")

    # Font sizes
    font_map = analysis.get('font_size_map', {})
    if font_map:
        lines.append("## Font Size Mapping\n")
        lines.append("| Old Value | → New Token |")
        lines.append("|-----------|------------|")
        for old_val, new_token in sorted(font_map.items(), key=lambda x: parse_px(x[0]) or 0):
            lines.append(f"| `{old_val}` | `{new_token}` |")
        lines.append("")

    # Radius
    radius_map = analysis.get('radius_map', {})
    if radius_map:
        lines.append("## Border Radius Mapping\n")
        lines.append("| Old Value | → New Token |")
        lines.append("|-----------|------------|")
        for old_val, new_token in sorted(radius_map.items(), key=lambda x: parse_px(x[0]) or 0):
            lines.append(f"| `{old_val}` | `{new_token}` |")
        lines.append("")

    path.write_text("\n".join(lines), encoding='utf-8')
    return path


# ──────────────────────────── Main ────────────────────────────

def main(args):
    root = Path(args.project).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory.", file=sys.stderr)
        return 1

    # ── List references ──
    if args.list:
        refs = list_references()
        if not refs:
            print("No reference presets found.")
            return 1
        print("Available reference presets:\n")
        for key, desc in sorted(refs.items()):
            print(f"  {key:<12} {desc}")
        return 0

    # ── Load reference ──
    if not args.reference:
        print("Error: --reference is required (use --list to see available).", file=sys.stderr)
        return 1

    ref = load_reference(args.reference)
    if not ref:
        return 1

    print(f"📖 Reference: {ref['name']}")
    ref_tokens = ref['token_map']

    # ── Load audit data ──
    audit_data = load_audit(root)
    if not audit_data:
        return 1

    print(f"📊 Audit data loaded ({sum(len(v) for v in audit_data.values() if isinstance(v, dict))} unique values)")

    # ── Generate color mapping ──
    print("\n🎨 Classifying colors...")
    color_mapping, color_analysis = generate_color_mapping(audit_data, ref_tokens, args.verbose)
    print(f"   {len(color_mapping)} old colors → reference tokens")

    # ── Generate spacing/size mapping ──
    print("📏 Classifying spacing & sizes...")
    spacing_mapping, size_analysis = generate_spacing_mapping(audit_data, ref_tokens, args.verbose)
    print(f"   {len(spacing_mapping)} old sizes → reference tokens")

    # ── Merge mappings ──
    full_mapping = {}
    full_mapping.update(color_mapping)
    full_mapping.update(spacing_mapping)

    analysis = {
        '_reference': ref['name'],
        'role_recommendations': color_analysis.get('role_recommendations', {}),
        'grouped_by_role': color_analysis.get('grouped_by_role', {}),
        'spacing_map': size_analysis.get('spacing_map', {}),
        'font_size_map': size_analysis.get('font_size_map', {}),
        'radius_map': size_analysis.get('radius_map', {}),
        'grid': size_analysis.get('grid', 4),
    }

    # ── Output ──
    output_dir = root / '.design-audit'

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = output_dir / 'semantic-mapping.json'

    report_path = output_dir / 'semantic-mapping-report.md'

    if args.dry_run:
        print(f"\n{'='*50}")
        print(f"  🏃 DRY RUN — Summary only")
        print(f"{'='*50}")
        print(f"  Total mappings:  {len(full_mapping)}")
        print(f"    Colors:        {len(color_mapping)}")
        print(f"    Spacing/sizes: {len(spacing_mapping)}")
        print(f"  Output would go to:")
        print(f"    {output_path}")
        print(f"    {report_path}")
        if args.verbose:
            print(f"\n  Sample mappings:")
            for old_val, new_val in list(full_mapping.items())[:15]:
                print(f"    {old_val:<30} → {new_val}")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_mapping_json(full_mapping, output_path, analysis)
        write_analysis_report(analysis, report_path)

        print(f"\n{'='*50}")
        print(f"  ✅ Semantic Mapping Complete")
        print(f"{'='*50}")
        print(f"  {len(full_mapping)} total mappings")
        print(f"  Output:")
        print(f"    📄 {output_path}   (for apply-value-mapping.py)")
        print(f"    📄 {report_path}    (human-readable analysis)")

        # Color roles summary
        roles = analysis.get('role_recommendations', {})
        if roles:
            print(f"\n  Color roles mapped:")
            for role_key, info in sorted(roles.items()):
                ref_val = info.get('reference_value', '?')
                count = info.get('total_occurrences', 0)
                print(f"    {role_key:<20} → {ref_val:<20} ({count} occurrences)")

        print(f"\n  Next: run `apply-value-mapping.py` with {output_path}")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Semantic Mapper — map audit values to reference design tokens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 semantic-mapper.py /path/to/project --reference tailwind
  python3 semantic-mapper.py /path/to/project --reference antd --output mapping.json
  python3 semantic-mapper.py /path/to/project --reference catppuccin --dry-run -v
  python3 semantic-mapper.py /path/to/project --list
        """
    )
    parser.add_argument("project", help="Path to the frontend project")
    parser.add_argument("--reference", "-r", help="Reference design system name (use --list to see available)")
    parser.add_argument("--output", "-o", help="Custom output path for mapping JSON")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be mapped without writing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed classification info")
    parser.add_argument("--list", "-l", action="store_true", help="List available reference presets")
    args = parser.parse_args()
    sys.exit(main(args))
