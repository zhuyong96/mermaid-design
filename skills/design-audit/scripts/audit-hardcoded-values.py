#!/usr/bin/env python3
"""
Deep Design Audit — Hardcoded Value Scanner
=============================================
Extracts EVERY hardcoded visual value (colors, sizes, radii, shadows, font props)
from a frontend project's source files. Outputs structured audit reports to
.design-audit/ for AI analysis and systematic restyling.

Usage:
    python3 audit-hardcoded-values.py /path/to/project [--output-dir NAME] [--update] [--verbose]
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ──────────────────────── Regex Patterns ────────────────────────

# CSS color patterns — match both hex and functional notations
RE_COLOR = re.compile(
    r'(?<![\w-])'  # Not preceded by word char or dash (avoids matching variable names)
    r'(?:'
    r'#[0-9a-fA-F]{3,8}'                    # Hex: #fff, #ffffff, #ffffffff
    r'|'
    r'rgba?\s*\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(?:,\s*[\d.]+\s*)?\)'  # rgb/rgba
    r'|'
    r'hsla?\s*\(\s*\d{1,3}\s*,\s*\d{1,3}%\s*,\s*\d{1,3}%\s*(?:,\s*[\d.]+\s*)?\)'  # hsl/hsla
    r')',
    re.IGNORECASE
)

# Named CSS colors (most common)
NAMED_COLORS = {
    'red', 'blue', 'green', 'white', 'black', 'gray', 'grey',
    'transparent', 'currentColor', 'inherit', 'initial',
    'aqua', 'black', 'blue', 'fuchsia', 'gray', 'green', 'lime',
    'maroon', 'navy', 'olive', 'orange', 'purple', 'red', 'silver',
    'teal', 'white', 'yellow', 'aliceblue', 'antiquewhite', 'aquamarine',
    'azure', 'beige', 'bisque', 'blanchedalmond', 'blueviolet', 'brown',
    'burlywood', 'cadetblue', 'chartreuse', 'chocolate', 'coral',
    'cornflowerblue', 'cornsilk', 'crimson', 'cyan', 'darkblue', 'darkcyan',
    'darkgoldenrod', 'darkgray', 'darkgreen', 'darkgrey', 'darkkhaki',
    'darkmagenta', 'darkolivegreen', 'darkorange', 'darkorchid', 'darkred',
    'darksalmon', 'darkseagreen', 'darkslateblue', 'darkslategray',
    'darkslategrey', 'darkturquoise', 'darkviolet', 'deeppink', 'deepskyblue',
    'dimgray', 'dimgrey', 'dodgerblue', 'firebrick', 'floralwhite',
    'forestgreen', 'fuchsia', 'gainsboro', 'ghostwhite', 'gold', 'goldenrod',
    'greenyellow', 'honeydew', 'hotpink', 'indianred', 'indigo', 'ivory',
    'khaki', 'lavender', 'lavenderblush', 'lawngreen', 'lemonchiffon',
    'lightblue', 'lightcoral', 'lightcyan', 'lightgoldenrodyellow',
    'lightgray', 'lightgreen', 'lightgrey', 'lightpink', 'lightsalmon',
    'lightseagreen', 'lightskyblue', 'lightslategray', 'lightslategrey',
    'lightsteelblue', 'lightyellow', 'limegreen', 'linen', 'magenta',
    'mediumaquamarine', 'mediumblue', 'mediumorchid', 'mediumpurple',
    'mediumseagreen', 'mediumslateblue', 'mediumspringgreen',
    'mediumturquoise', 'mediumvioletred', 'midnightblue', 'mintcream',
    'mistyrose', 'moccasin', 'navajowhite', 'oldlace', 'olivedrab',
    'orangered', 'orchid', 'palegoldenrod', 'palegreen', 'paleturquoise',
    'palevioletred', 'papayawhip', 'peachpuff', 'peru', 'pink', 'plum',
    'powderblue', 'rebeccapurple', 'rosybrown', 'royalblue', 'saddlebrown',
    'salmon', 'sandybrown', 'seagreen', 'seashell', 'sienna', 'skyblue',
    'slateblue', 'slategray', 'slategrey', 'snow', 'springgreen', 'steelblue',
    'tan', 'thistle', 'tomato', 'turquoise', 'violet', 'wheat', 'whitesmoke',
    'yellowgreen',
}

# CSS property patterns
RE_PX_VALUE = re.compile(r'(\d+(?:\.\d+)?)px')
RE_REM_VALUE = re.compile(r'(\d+(?:\.\d+)?)rem')
RE_EM_VALUE = re.compile(r'(\d+(?:\.\d+)?)em')
RE_PERCENT_VALUE = re.compile(r'(\d+(?:\.\d+)?)%')
RE_VH_VW_VALUE = re.compile(r'(\d+(?:\.\d+)?)(?:vh|vw)')

# CSS property → semantic category mapping
SEMANTIC_SIZE_PROPERTIES = {
    # Font
    'font-size': 'font-size', 'font': 'font-size',
    # Spacing
    'margin': 'margin', 'margin-top': 'margin', 'margin-right': 'margin',
    'margin-bottom': 'margin', 'margin-left': 'margin',
    'padding': 'padding', 'padding-top': 'padding', 'padding-right': 'padding',
    'padding-bottom': 'padding', 'padding-left': 'padding',
    'gap': 'gap', 'grid-gap': 'gap', 'column-gap': 'gap', 'row-gap': 'gap',
    # Border
    'border-width': 'border-width', 'border': 'border-width',
    'border-top-width': 'border-width', 'border-bottom-width': 'border-width',
    'border-left-width': 'border-width', 'border-right-width': 'border-width',
    'outline-width': 'border-width',
    # Radius
    'border-radius': 'border-radius',
    'border-top-left-radius': 'border-radius', 'border-top-right-radius': 'border-radius',
    'border-bottom-left-radius': 'border-radius', 'border-bottom-right-radius': 'border-radius',
    # Shadow
    'box-shadow': 'shadow', 'text-shadow': 'shadow',
    # Layout
    'width': 'size', 'height': 'size',
    'min-width': 'size', 'min-height': 'size',
    'max-width': 'size', 'max-height': 'size',
    'top': 'position', 'right': 'position', 'bottom': 'position', 'left': 'position',
    'inset': 'position',
    # Line
    'line-height': 'line-height',
    'letter-spacing': 'letter-spacing',
    'word-spacing': 'letter-spacing',
    'text-indent': 'text-indent',
}

# CSS-in-JS style property names (camelCase → CSS property mapping)
STYLE_PROP_MAP = {
    'fontSize': 'font-size', 'fontWeight': 'font-weight', 'fontFamily': 'font-family',
    'margin': 'margin', 'marginTop': 'margin-top', 'marginRight': 'margin-right',
    'marginBottom': 'margin-bottom', 'marginLeft': 'margin-left',
    'padding': 'padding', 'paddingTop': 'padding-top', 'paddingRight': 'padding-right',
    'paddingBottom': 'padding-bottom', 'paddingLeft': 'padding-left',
    'gap': 'gap', 'columnGap': 'gap', 'rowGap': 'gap',
    'border': 'border', 'borderWidth': 'border-width', 'borderRadius': 'border-radius',
    'borderTopLeftRadius': 'border-radius', 'borderTopRightRadius': 'border-radius',
    'borderBottomLeftRadius': 'border-radius', 'borderBottomRightRadius': 'border-radius',
    'boxShadow': 'box-shadow', 'textShadow': 'text-shadow',
    'width': 'size', 'height': 'size', 'minWidth': 'size', 'minHeight': 'size',
    'maxWidth': 'size', 'maxHeight': 'size',
    'lineHeight': 'line-height', 'letterSpacing': 'letter-spacing',
    'color': 'color', 'backgroundColor': 'background-color',
    'borderColor': 'border-color', 'outlineColor': 'outline-color',
    'top': 'position', 'right': 'position', 'bottom': 'position', 'left': 'position',
    'inset': 'position',
}

# ──────────────────────── Helpers ────────────────────────


def run_git(cmd: List[str], cwd: Path) -> str:
    """Run a git command and return stdout (silent on error)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=15)
        return r.stdout.strip()
    except Exception:
        return ""


def glob_source_files(root: Path) -> List[Path]:
    """Find all source files that could contain visual values."""
    patterns = [
        "**/*.css", "**/*.scss", "**/*.less",
        "**/*.jsx", "**/*.tsx",
        "**/*.js", "**/*.ts",
        "**/*.vue", "**/*.svelte",
        "**/*.html",
        # Config files
        "tailwind.config.*",
    ]
    excluded_dirs = {
        'node_modules', '.git', 'dist', '.next', '.nuxt', '.output',
        '.cache', '__pycache__', 'build', 'coverage', '.turbo',
        '.design-system', '.design-audit',
    }
    excluded_extensions = {'.d.ts', '.d.tsx', '.min.css', '.min.js'}

    files = []
    for pat in patterns:
        for p in root.rglob(pat):
            rel = p.relative_to(root)
            parts = rel.parts
            if any(seg in parts for seg in excluded_dirs):
                continue
            if any(str(rel).endswith(ext) for ext in excluded_extensions):
                continue
            if p.is_file() and p.stat().st_size <= 500_000:  # Skip files > 500KB
                files.append(p)
    return sorted(set(files))


def read_file_safe(path: Path) -> str:
    """Read a text file safely with error handling."""
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except (UnicodeDecodeError, OSError, IOError):
        return ""


def normalize_color(color: str) -> str:
    """Normalize a color value to a canonical form."""
    c = color.strip()
    # Lowercase hex
    if c.startswith('#'):
        # Expand short hex
        if len(c) == 4:   # #fff → #ffffff
            c = '#' + ''.join(c[i]*2 for i in range(1, 4))
        elif len(c) == 5:  # #ffff → #ffffff? No, that's #ffff = 4 hex = rgba
            pass
        return c.lower()
    # Normalize rgb/rgba spacing
    c = re.sub(r'\s*,\s*', ', ', c)
    c = re.sub(r'\s*\(\s*', '(', c)
    c = re.sub(r'\s*\)\s*', ')', c)
    return c.lower()


def is_visual_value(prop_name: str, value: str) -> bool:
    """Quick check: is this CSS property+value pair visually meaningful?"""
    v = value.strip()
    if not v or v in {'0', 'none', 'normal', 'auto', 'inherit', 'initial', 'unset'}:
        return False
    if prop_name in {
        'visibility', 'display', 'position', 'float', 'clear',
        'overflow', 'overflow-x', 'overflow-y', 'cursor', 'pointer-events',
        'box-sizing', 'resize', 'user-select', 'object-fit', 'object-position',
        'content', 'counter-*', 'list-style', 'list-style-type',
        'order', 'flex', 'flex-grow', 'flex-shrink', 'flex-basis',
        'align-self', 'justify-self', 'place-self',
        'opacity', 'transform', 'transition', 'transition-*', 'animation',
        'clip', 'clip-path', 'filter', 'backdrop-filter', 'mask',
        'will-change', 'contain', 'isolation',
        'break-*', 'orphans', 'widows', 'page-break-*',
        'white-space', 'word-break', 'word-wrap', 'overflow-wrap',
        'text-overflow', 'text-transform', 'text-decoration',
        'direction', 'unicode-bidi', 'writing-mode',
        'tab-size', 'hyphens', 'quotes',
        'empty-cells', 'caption-side', 'table-layout', 'border-collapse',
        'border-spacing',
        'counter-increment', 'counter-reset', 'counter-set',
    }:
        return False
    return True


# ──────────────────────── CSS Value Extraction ────────────────────────

class CSSExtractor:
    """Extract visual values from CSS content."""

    @staticmethod
    def extract_colors(content: str, source: str, file_path: str, line_offset: int = 0) -> List[dict]:
        """Extract color values with context."""
        results = []
        lines = content.split('\n')

        for i, line in enumerate(lines):
            line_num = line_offset + i + 1
            stripped = line.strip()

            # Skip comments and non-style lines
            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            # Extract CSS property: value pattern
            prop_match = re.match(r'\s*([\w-]+)\s*:\s*(.+?)\s*;?\s*$', line)
            if prop_match:
                prop_name, prop_value = prop_match.group(1), prop_match.group(2)

                # Check for color values
                for m in RE_COLOR.finditer(prop_value):
                    color = normalize_color(m.group(0))
                    results.append({
                        'value': color,
                        'file': file_path,
                        'line': line_num,
                        'context': stripped[:120],
                        'type': 'color',
                        'property': prop_name,
                        'category': self._categorize_color_usage(prop_name),
                    })

                # Check for named colors
                for nc in NAMED_COLORS:
                    if nc in prop_value.split():
                        results.append({
                            'value': nc,
                            'file': file_path,
                            'line': line_num,
                            'context': stripped[:120],
                            'type': 'color',
                            'property': prop_name,
                            'category': self._categorize_color_usage(prop_name),
                        })

        return results

    @staticmethod
    def _categorize_color_usage(prop: str) -> str:
        prop_lower = prop.lower()
        if prop_lower in ('color', 'fill', 'stroke'):
            return 'foreground'
        if 'background' in prop_lower or 'bg' == prop_lower:
            return 'background'
        if 'border' in prop_lower or 'outline' in prop_lower:
            return 'border'
        if 'shadow' in prop_lower:
            return 'shadow'
        if 'accent' in prop_lower:
            return 'accent'
        if 'caret' in prop_lower:
            return 'caret'
        if 'placeholder' in prop_lower:
            return 'placeholder'
        return 'other'

    @staticmethod
    def extract_sizes(content: str, source: str, file_path: str, line_offset: int = 0) -> List[dict]:
        """Extract size/spacing values with semantic context."""
        results = []
        lines = content.split('\n')

        for i, line in enumerate(lines):
            line_num = line_offset + i + 1
            stripped = line.strip()

            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            prop_match = re.match(r'\s*([\w-]+)\s*:\s*(.+?)\s*;?\s*$', line)
            if not prop_match:
                continue

            prop_name, prop_value = prop_match.group(1), prop_match.group(2)
            css_prop = prop_name.lower()

            semantic_category = SEMANTIC_SIZE_PROPERTIES.get(css_prop)
            if not semantic_category:
                continue

            # Extract px values
            for m in RE_PX_VALUE.finditer(prop_value):
                val = int(m.group(1))
                results.append({
                    'value': f'{val}px',
                    'numeric': val,
                    'file': file_path,
                    'line': line_num,
                    'context': stripped[:120],
                    'type': 'size',
                    'property': css_prop,
                    'category': semantic_category,
                    'unit': 'px',
                })

            # Extract rem values
            for m in RE_REM_VALUE.finditer(prop_value):
                val = float(m.group(1))
                results.append({
                    'value': f'{val}rem',
                    'numeric': val * 16 if semantic_category == 'font-size' else val,
                    'file': file_path,
                    'line': line_num,
                    'context': stripped[:120],
                    'type': 'size',
                    'property': css_prop,
                    'category': semantic_category,
                    'unit': 'rem',
                })

            # Extract em values
            for m in RE_EM_VALUE.finditer(prop_value):
                val = float(m.group(1))
                results.append({
                    'value': f'{val}em',
                    'numeric': val * 16 if semantic_category == 'font-size' else val * 16,
                    'file': file_path,
                    'line': line_num,
                    'context': stripped[:120],
                    'type': 'size',
                    'property': css_prop,
                    'category': semantic_category,
                    'unit': 'em',
                })

        return results

    @staticmethod
    def extract_font_props(content: str, source: str, file_path: str, line_offset: int = 0) -> List[dict]:
        """Extract font-family and font-weight values."""
        results = []
        lines = content.split('\n')

        for i, line in enumerate(lines):
            line_num = line_offset + i + 1
            stripped = line.strip()

            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            prop_match = re.match(r'\s*([\w-]+)\s*:\s*(.+?)\s*;?\s*$', line)
            if not prop_match:
                continue

            prop_name, prop_value = prop_match.group(1), prop_match.group(2)

            # Font family
            if prop_name.lower() == 'font-family':
                family = prop_value.strip().strip(';"\'')
                results.append({
                    'value': family,
                    'file': file_path,
                    'line': line_num,
                    'context': stripped[:120],
                    'type': 'font-family',
                    'property': 'font-family',
                })

            # Font weight
            if prop_name.lower() == 'font-weight':
                weight = prop_value.strip().strip(';"\'')
                results.append({
                    'value': weight,
                    'file': file_path,
                    'line': line_num,
                    'context': stripped[:120],
                    'type': 'font-weight',
                    'property': 'font-weight',
                })

        return results

    @staticmethod
    def extract_border_shadows(content: str, source: str, file_path: str, line_offset: int = 0) -> List[dict]:
        """Extract border-radius and box-shadow values."""
        results = []
        lines = content.split('\n')

        for i, line in enumerate(lines):
            line_num = line_offset + i + 1
            stripped = line.strip()

            if stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                continue

            prop_match = re.match(r'\s*([\w-]+)\s*:\s*(.+?)\s*;?\s*$', line)
            if not prop_match:
                continue

            prop_name, prop_value = prop_match.group(1), prop_match.group(2)

            # Border radius
            if prop_name.lower() in ('border-radius', 'border-top-left-radius',
                                      'border-top-right-radius', 'border-bottom-left-radius',
                                      'border-bottom-right-radius'):
                for m in RE_PX_VALUE.finditer(prop_value):
                    results.append({
                        'value': f'{m.group(1)}px',
                        'numeric': int(m.group(1)),
                        'file': file_path,
                        'line': line_num,
                        'context': stripped[:120],
                        'type': 'border-radius',
                        'property': prop_name.lower(),
                    })

            # Box shadow — capture full value
            if prop_name.lower() == 'box-shadow':
                shadow_val = prop_value.strip().strip(';"\'')
                if shadow_val and shadow_val != 'none':
                    results.append({
                        'value': shadow_val[:200],
                        'file': file_path,
                        'line': line_num,
                        'context': stripped[:120],
                        'type': 'box-shadow',
                        'property': 'box-shadow',
                    })

            # Text shadow
            if prop_name.lower() == 'text-shadow':
                shadow_val = prop_value.strip().strip(';"\'')
                if shadow_val and shadow_val != 'none':
                    results.append({
                        'value': shadow_val[:200],
                        'file': file_path,
                        'line': line_num,
                        'context': stripped[:120],
                        'type': 'text-shadow',
                        'property': 'text-shadow',
                    })

        return results


# ──────────────────────── JSX/TSX Inline Style Extraction ────────────────────────

def extract_inline_styles(content: str, file_path: str) -> List[dict]:
    """Extract values from JSX/TSX inline style={{...}} objects."""
    results = []

    # Pattern: style={{ key: 'value' }} or style={{ key: value }}
    style_blocks = re.finditer(
        r'style\s*=\s*\{\{\s*([\s\S]*?)\s*\}\}',
        content, re.MULTILINE
    )

    for block in style_blocks:
        block_start = content[:block.start()].count('\n') + 1
        inner = block.group(1)

        # Extract key-value pairs: key: 'value' or key: value
        pairs = re.finditer(
            r'(\w+)\s*:\s*(?:\'([^\']*)\'|"([^"]*)"|`([^`]*)`|(\d+(?:\.\d+)?))',
            inner
        )

        for pair in pairs:
            prop_name = pair.group(1)
            value = pair.group(2) or pair.group(3) or pair.group(4) or pair.group(5)
            if not value:
                continue

            css_prop = STYLE_PROP_MAP.get(prop_name, prop_name)

            # Color values
            if css_prop in ('color', 'background-color', 'border-color', 'outline-color',
                           'backgroundColor', 'borderColor'):
                if RE_COLOR.match(value) or value in NAMED_COLORS:
                    results.append({
                        'value': normalize_color(value),
                        'file': file_path,
                        'line': block_start,
                        'context': inner.strip()[:120],
                        'type': 'color',
                        'property': prop_name,
                        'category': 'foreground' if css_prop == 'color' else 'background' if 'background' in css_prop else 'border',
                    })

            # Size values with px
            px_m = RE_PX_VALUE.search(value)
            if px_m:
                semantic_cat = SEMANTIC_SIZE_PROPERTIES.get(
                    css_prop if '-' in css_prop else prop_name, 'size'
                )
                results.append({
                    'value': f'{px_m.group(1)}px',
                    'numeric': int(px_m.group(1)),
                    'file': file_path,
                    'line': block_start,
                    'context': inner.strip()[:120],
                    'type': 'size',
                    'property': prop_name,
                    'category': semantic_cat,
                    'unit': 'px',
                })

            # Border radius
            if 'radius' in prop_name.lower() or 'radius' in css_prop:
                px_m = RE_PX_VALUE.search(value)
                if px_m:
                    results.append({
                        'value': f'{px_m.group(1)}px',
                        'numeric': int(px_m.group(1)),
                        'file': file_path,
                        'line': block_start,
                        'context': inner.strip()[:120],
                        'type': 'border-radius',
                        'property': prop_name,
                    })

            # Font
            if prop_name == 'fontSize':
                px_m = RE_PX_VALUE.search(value)
                if px_m:
                    results.append({
                        'value': f'{px_m.group(1)}px',
                        'numeric': int(px_m.group(1)),
                        'file': file_path,
                        'line': block_start,
                        'context': inner.strip()[:120],
                        'type': 'size',
                        'property': 'font-size',
                        'category': 'font-size',
                        'unit': 'px',
                    })

            if prop_name == 'fontFamily':
                results.append({
                    'value': value.strip("'\""),
                    'file': file_path,
                    'line': block_start,
                    'context': inner.strip()[:120],
                    'type': 'font-family',
                    'property': 'font-family',
                })

            if prop_name == 'fontWeight':
                results.append({
                    'value': value,
                    'file': file_path,
                    'line': block_start,
                    'context': inner.strip()[:120],
                    'type': 'font-weight',
                    'property': 'font-weight',
                })

            # Border radius prop
            if prop_name == 'borderRadius':
                px_m = RE_PX_VALUE.search(value)
                if px_m:
                    results.append({
                        'value': f'{px_m.group(1)}px',
                        'numeric': int(px_m.group(1)),
                        'file': file_path,
                        'line': block_start,
                        'context': inner.strip()[:120],
                        'type': 'border-radius',
                        'property': 'border-radius',
                    })

            # Box shadow
            if prop_name == 'boxShadow' and value.strip() != 'none':
                results.append({
                    'value': value[:200],
                    'file': file_path,
                    'line': block_start,
                    'context': inner.strip()[:120],
                    'type': 'box-shadow',
                    'property': 'box-shadow',
                })

    # Pattern: styled.xxx`...` (styled-components template literals)
    styled_blocks = re.finditer(
        r'styled\.\w+\s*`([^`]+)`',
        content
    )
    for block in styled_blocks:
        block_line = content[:block.start()].count('\n') + 1
        css_content = block.group(1)
        # Feed CSS content through the CSS extractor
        results.extend(CSSExtractor.extract_colors(
            css_content, 'styled-components', file_path, block_line
        ))
        results.extend(CSSExtractor.extract_sizes(
            css_content, 'styled-components', file_path, block_line
        ))
        results.extend(CSSExtractor.extract_font_props(
            css_content, 'styled-components', file_path, block_line
        ))
        results.extend(CSSExtractor.extract_border_shadows(
            css_content, 'styled-components', file_path, block_line
        ))

    return results


# ──────────────────────── Vue SFC Extraction ────────────────────────

def extract_vue_styles(content: str, file_path: str) -> List[dict]:
    """Extract values from Vue Single File Component style blocks and :style bindings."""
    results = []

    # Extract <style> blocks
    style_blocks = re.finditer(
        r'<style[^>]*>(.*?)</style>',
        content, re.DOTALL
    )
    for block in style_blocks:
        block_line = content[:block.start()].count('\n') + 1
        css_content = block.group(1)

        results.extend(CSSExtractor.extract_colors(css_content, 'vue-style', file_path, block_line))
        results.extend(CSSExtractor.extract_sizes(css_content, 'vue-style', file_path, block_line))
        results.extend(CSSExtractor.extract_font_props(css_content, 'vue-style', file_path, block_line))
        results.extend(CSSExtractor.extract_border_shadows(css_content, 'vue-style', file_path, block_line))

    # Extract :style="..." bindings in templates
    # :style="{ color: 'red', fontSize: '14px' }"
    style_bindings = re.finditer(
        r':style\s*=\s*["\']\{([^}]+)\}["\']',
        content
    )
    for bind in style_bindings:
        bind_line = content[:bind.start()].count('\n') + 1
        inner = bind.group(1)

        pairs = re.finditer(r'(\w+)\s*:\s*[\'"]([^\'"]*)[\'"]', inner)
        for pair in pairs:
            prop_name = pair.group(1)
            value = pair.group(2)
            css_prop = STYLE_PROP_MAP.get(prop_name, prop_name)

            if RE_COLOR.match(value):
                results.append({
                    'value': normalize_color(value),
                    'file': file_path,
                    'line': bind_line,
                    'context': f':style={{ {inner.strip()[:80]} }}',
                    'type': 'color',
                    'property': prop_name,
                })
            elif RE_PX_VALUE.search(value):
                px_m = RE_PX_VALUE.search(value)
                results.append({
                    'value': f'{px_m.group(1)}px',
                    'numeric': int(px_m.group(1)),
                    'file': file_path,
                    'line': bind_line,
                    'context': f':style={{ {inner.strip()[:80]} }}',
                    'type': 'size',
                    'property': prop_name,
                })

    return results


# ──────────────────────── Tailwind Config Extraction ────────────────────────

def extract_tailwind_tokens(content: str) -> Dict[str, Any]:
    """Extract custom tokens from tailwind.config.* content."""
    tokens = {
        'colors': {},
        'fontSize': {},
        'fontFamily': {},
        'spacing': {},
        'borderRadius': {},
        'boxShadow': {},
    }

    # Try to find theme.extend or theme blocks
    # This is regex-based so it won't handle complex JS, but covers common patterns

    # Find theme.extend or theme blocks
    theme_match = re.search(r'theme\s*:\s*\{[^}]*(?:extend\s*:\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\})?',
                            content, re.DOTALL)
    if theme_match:
        extend_block = theme_match.group(1) or content

        # Colors
        color_match = re.search(r'colors\s*:\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', extend_block, re.DOTALL)
        if color_match:
            inner = color_match.group(1)
            # Simple key: value pairs
            for m in re.finditer(r'(\w[\w-]*)\s*:\s*[\'"]([^\'"]+)[\'"]', inner):
                tokens['colors'][m.group(1)] = m.group(2)

        # Font sizes
        font_size_match = re.search(r'fontSize\s*:\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', extend_block, re.DOTALL)
        if font_size_match:
            inner = font_size_match.group(1)
            for m in re.finditer(r'(\w[\w-]*)\s*:\s*[\'"]([^\'"]+(?:px|rem|em))[\'"]', inner):
                tokens['fontSize'][m.group(1)] = m.group(2)

        # Border radius
        br_match = re.search(r'borderRadius\s*:\s*\{([^}]+)\}', extend_block, re.DOTALL)
        if br_match:
            inner = br_match.group(1)
            for m in re.finditer(r'(\w[\w-]*)\s*:\s*[\'"]([^\'"]+(?:px|rem|em))[\'"]', inner):
                tokens['borderRadius'][m.group(1)] = m.group(2)

    return tokens


# ──────────────────────── Data Aggregation ────────────────────────

class AuditData:
    """Aggregate and analyze all extracted values."""

    def __init__(self):
        self.colors: List[dict] = []
        self.sizes: List[dict] = []
        self.font_families: List[dict] = []
        self.font_weights: List[dict] = []
        self.border_radii: List[dict] = []
        self.box_shadows: List[dict] = []
        self.text_shadows: List[dict] = []

    def add(self, item: dict):
        item_type = item.get('type', '')
        if item_type == 'color':
            self.colors.append(item)
        elif item_type == 'size':
            self.sizes.append(item)
        elif item_type == 'font-family':
            self.font_families.append(item)
        elif item_type == 'font-weight':
            self.font_weights.append(item)
        elif item_type == 'border-radius':
            self.border_radii.append(item)
        elif item_type == 'box-shadow':
            self.box_shadows.append(item)
        elif item_type == 'text-shadow':
            self.text_shadows.append(item)

    def build_color_analysis(self) -> Dict[str, Any]:
        """Build per-color frequency + context analysis."""
        by_value: Dict[str, dict] = {}

        for item in self.colors:
            v = item['value']
            if v not in by_value:
                by_value[v] = {
                    'count': 0,
                    'files': set(),
                    'properties': Counter(),
                    'categories': Counter(),
                    'examples': [],
                }
            d = by_value[v]
            d['count'] += 1
            d['files'].add(item['file'])
            d['properties'][item.get('property', '')] += 1
            d['categories'][item.get('category', 'other')] += 1
            if len(d['examples']) < 3:
                d['examples'].append({
                    'file': item['file'],
                    'line': item['line'],
                    'context': item['context'],
                })

        # Sort by count descending
        sorted_colors = sorted(by_value.items(), key=lambda x: -x[1]['count'])

        return {
            'total_unique': len(by_value),
            'total_occurrences': len(self.colors),
            'colors': [
                {
                    'value': v,
                    'count': d['count'],
                    'files': sorted(d['files']),
                    'file_count': len(d['files']),
                    'top_properties': d['properties'].most_common(5),
                    'categories': dict(d['categories'].most_common(3)),
                    'examples': d['examples'],
                }
                for v, d in sorted_colors
            ],
            'top_colors': sorted_colors[:20],
            'single_use_colors': [v for v, d in sorted_colors if d['count'] == 1],
        }

    def build_size_analysis(self) -> Dict[str, Any]:
        """Build per-size frequency analysis, grouped by semantic category."""
        by_category: Dict[str, Counter] = defaultdict(Counter)
        by_value: Dict[str, dict] = {}

        for item in self.sizes:
            v = item['value']
            cat = item.get('category', 'size')

            by_category[cat][v] += 1

            if v not in by_value:
                by_value[v] = {
                    'count': 0,
                    'categories': Counter(),
                    'unit': item.get('unit', 'px'),
                    'files': set(),
                    'examples': [],
                }
            d = by_value[v]
            d['count'] += 1
            d['categories'][cat] += 1
            d['files'].add(item['file'])
            if len(d['examples']) < 3:
                d['examples'].append({
                    'file': item['file'],
                    'line': item['line'],
                    'context': item['context'],
                })

        sorted_sizes = sorted(by_value.items(), key=lambda x: -x[1]['count'])

        return {
            'total_unique': len(by_value),
            'total_occurrences': len(self.sizes),
            'by_category': {
                cat: dict(counter.most_common(30))
                for cat, counter in sorted(by_category.items())
            },
            'sizes': [
                {
                    'value': v,
                    'count': d['count'],
                    'categories': dict(d['categories'].most_common(3)),
                    'unit': d['unit'],
                    'files': sorted(d['files'])[:5],
                    'file_count': len(d['files']),
                    'examples': d['examples'],
                }
                for v, d in sorted_sizes[:50]
            ],
        }

    def build_font_analysis(self) -> Dict[str, Any]:
        """Analyze font families and weights."""
        fam_counter = Counter(item['value'] for item in self.font_families)
        wgt_counter = Counter(item['value'] for item in self.font_weights)

        return {
            'families': dict(fam_counter.most_common(10)),
            'weights': dict(wgt_counter.most_common(10)),
            'total_family_occurrences': len(self.font_families),
            'total_weight_occurrences': len(self.font_weights),
        }

    def build_radius_analysis(self) -> Dict[str, Any]:
        r_counter = Counter(item['value'] for item in self.border_radii)
        return dict(r_counter.most_common(20))

    def build_shadow_analysis(self) -> Dict[str, Any]:
        shadow_counter = Counter(item['value'] for item in self.box_shadows)
        return dict(shadow_counter.most_common(20))

    def build_value_map(self) -> Dict[str, Any]:
        """Build machine-readable value → file mapping JSON."""
        return {
            'colors': self._group_by_value(self.colors),
            'sizes': self._group_by_value(self.sizes),
            'font_families': self._group_by_value(self.font_families),
            'font_weights': self._group_by_value(self.font_weights),
            'border_radii': self._group_by_value(self.border_radii),
            'box_shadows': self._group_by_value(self.box_shadows),
        }

    @staticmethod
    def _group_by_value(items: List[dict]) -> Dict[str, Any]:
        result = {}
        for item in items:
            v = item.get('value', '')
            if v not in result:
                result[v] = {'count': 0, 'usage': []}
            result[v]['count'] += 1
            result[v]['usage'].append({
                'file': item['file'],
                'line': item['line'],
                'context': item['context'],
                'type': item.get('type', ''),
                'property': item.get('property', ''),
            })
        # Sort by count descending
        return dict(sorted(result.items(), key=lambda x: -x[1]['count']))


# ──────────────────────── Inconsistency Detection ────────────────────────

def detect_inconsistencies(audit: AuditData) -> List[dict]:
    """Identify potential inconsistencies in visual values."""
    inconsistencies = []

    # 1. Near-duplicate colors (colors that differ by ≤2 per channel)
    colors_by_value = {}
    for item in audit.colors:
        v = item['value']
        if v not in colors_by_value:
            colors_by_value[v] = {'count': 0, 'properties': set(), 'files': set()}
        colors_by_value[v]['count'] += 1
        colors_by_value[v]['properties'].add(item.get('property', ''))
        colors_by_value[v]['files'].add(item['file'])

    hex_colors = {}
    for v in colors_by_value:
        if v.startswith('#') and len(v) == 7:  # #rrggbb
            try:
                r = int(v[1:3], 16)
                g = int(v[3:5], 16)
                b = int(v[5:7], 16)
                hex_colors[v] = (r, g, b)
            except ValueError:
                pass

    # Find pairs within 2 per channel
    hex_list = list(hex_colors.items())
    for i in range(len(hex_list)):
        for j in range(i + 1, len(hex_list)):
            v1, (r1, g1, b1) = hex_list[i]
            v2, (r2, g2, b2) = hex_list[j]
            diff = abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
            if 0 < diff <= 6:  # Very close
                d1 = colors_by_value[v1]
                d2 = colors_by_value[v2]
                shared_props = d1['properties'] & d2['properties']
                if shared_props:
                    inconsistencies.append({
                        'type': 'near-duplicate-colors',
                        'severity': 'high',
                        'values': [v1, v2],
                        'color_delta': diff,
                        'shared_properties': list(shared_props)[:5],
                        'total_occurrences': d1['count'] + d2['count'],
                        'file_count': len(d1['files'] | d2['files']),
                        'description': (
                            f"Colors {v1} and {v2} differ by only {diff} "
                            f"(delta per channel). They appear in similar CSS properties "
                            f"({', '.join(list(shared_props)[:3])}) — likely intentional "
                            f"difference or drift?"
                        ),
                    })

    # 2. Non-grid spacing values
    all_px_values = []
    for item in audit.sizes:
        if item.get('unit') == 'px':
            all_px_values.append(item['numeric'])

    # Detect the most common grid (4px? 8px?)
    px_counter = Counter(all_px_values)
    top_px = [v for v, c in px_counter.most_common(20)]
    # Try 4px grid first
    grid = 4
    on_grid = sum(1 for v in top_px if v % grid == 0)
    off_grid = sum(1 for v in top_px if v % grid != 0)
    if off_grid > on_grid:
        grid = 8
        on_grid = sum(1 for v in top_px if v % grid == 0)
        off_grid = sum(1 for v in top_px if v % grid != 0)
    if off_grid > on_grid:
        grid = None  # Can't determine

    if grid and off_grid > 2:
        off_grid_values = sorted(v for v, c in px_counter.items() if v % grid != 0 and c >= 2)
        if off_grid_values:
            inconsistencies.append({
                'type': 'non-grid-spacing',
                'severity': 'medium',
                'grid': grid,
                'off_grid_values': off_grid_values[:15],
                'total_off_grid': len(off_grid_values),
                'description': (
                    f"Spacing grid appears to be {grid}px, but {len(off_grid_values)} values "
                    f"don't conform: {', '.join(f'{v}px' for v in off_grid_values[:10])}."
                ),
            })

    # 3. Mixed border-radius
    radii = Counter(item['value'] for item in audit.border_radii)
    if len(radii) > 2:
        inconsistencies.append({
            'type': 'mixed-border-radius',
            'severity': 'medium',
            'values': dict(radii.most_common(8)),
            'description': (
                f"Multiple border-radius values found: "
                f"{', '.join(f'{v} ({c}x)' for v, c in radii.most_common(5))}. "
                f"Consider consolidating to 2-3 values (small, default, large)."
            ),
        })

    # 4. Multiple font families
    fam_counter = Counter(item['value'] for item in audit.font_families)
    if len(fam_counter) > 3:
        inconsistencies.append({
            'type': 'multiple-font-families',
            'severity': 'low',
            'values': dict(fam_counter.most_common(10)),
            'description': (
                f"{len(fam_counter)} different font-family declarations found. "
                f"Consider unifying to 1-2 font stacks."
            ),
        })

    return inconsistencies


# ──────────────────────── Report Generators ────────────────────────

def gen_readme(audit: AuditData, project_name: str, total_files: int, inconsistencies: List[dict]) -> str:
    lines = []
    lines.append(f"# Design Audit: {project_name or 'Unnamed'}\n")
    lines.append(f"Auto-generated by `design-audit` on {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    lines.append("## Summary\n")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Source files scanned | {total_files} |")
    lines.append(f"| Total color occurrences | {len(audit.colors)} |")
    lines.append(f"| Unique colors | {len(set(i['value'] for i in audit.colors))} |")
    lines.append(f"| Size/spacing occurrences | {len(audit.sizes)} |")
    lines.append(f"| Unique size values | {len(set(i['value'] for i in audit.sizes))} |")
    lines.append(f"| Border-radius occurrences | {len(audit.border_radii)} |")
    lines.append(f"| Box-shadow occurrences | {len(audit.box_shadows)} |")
    lines.append(f"| Font-family declarations | {len(audit.font_families)} |")
    lines.append(f"| Font-weight declarations | {len(audit.font_weights)} |")
    lines.append(f"| Inconsistencies found | {len(inconsistencies)} |")
    lines.append("")

    if inconsistencies:
        lines.append("## Top Issues\n")
        for inc in inconsistencies[:5]:
            severity_icon = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(inc['severity'], '⚪')
            lines.append(f"{severity_icon} **{inc['type']}**: {inc['description'][:120]}...\n")

    lines.append("## Output Files\n")
    lines.append("| File | Description |")
    lines.append("|------|-------------|")
    lines.append("| `01-all-colors.md` | All colors with frequency, file locations, usage context |")
    lines.append("| `02-all-typography.md` | Font families, weights, sizes used across the project |")
    lines.append("| `03-all-spacing.md` | Margin, padding, gap values grouped by semantic category |")
    lines.append("| `04-all-borders-shadows.md` | Border widths, radii, box-shadows |")
    lines.append("| `05-inconsistencies.md` | Detected inconsistencies (agent may add AI analysis) |")
    lines.append("| `06-value-map.json` | Machine-readable: every value → file/line/context mapping |")
    lines.append("")

    lines.append("## Next Steps\n")
    lines.append("1. Read `01-all-colors.md` to understand the current palette")
    lines.append("2. Read `05-inconsistencies.md` to identify what needs fixing")
    lines.append("3. Use `design-restyle` skill to apply systematic changes")
    lines.append("4. Or manually: create token mappings → apply layer by layer → verify\n")

    return "\n".join(lines)


def gen_colors_report(analysis: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Color Audit\n")
    lines.append(f"**Total unique colors**: {analysis['total_unique']}  ")
    lines.append(f"**Total occurrences**: {analysis['total_occurrences']}  \n")

    lines.append("## Top Colors by Frequency\n")
    lines.append("| Value | Count | Files | Top Properties | Categories |")
    lines.append("|-------|-------|-------|----------------|------------|")
    for c in analysis['colors'][:40]:
        props = ', '.join(p for p, _ in c['top_properties'][:3])
        cats = ', '.join(f"{k}:{v}" for k, v in list(c['categories'].items())[:3])
        lines.append(f"| `{c['value']}` | {c['count']} | {c['file_count']} | {props} | {cats} |")
    lines.append("")

    if analysis['single_use_colors']:
        lines.append("## Single-Use Colors (Potential Orphans)\n")
        lines.append(f"{len(analysis['single_use_colors'])} colors appear only once. These may be mistakes or special cases.\n")
        # Group them by file
        singles_by_file = defaultdict(list)
        for item in analysis['colors']:
            if item['value'] in analysis['single_use_colors'] and item['examples']:
                singles_by_file[item['examples'][0]['file']].append(item)
        for file_path, items in sorted(singles_by_file.items()):
            items_str = ', '.join(f'`{i["value"]}`' for i in items[:5])
            lines.append(f"- **{file_path}**: {items_str}")
        lines.append("")

    lines.append("## Color Usage by Category\n")
    cat_counter: Counter = Counter()
    for c in analysis['colors']:
        for cat, cnt in c['categories'].items():
            cat_counter[cat] += cnt
    for cat, cnt in cat_counter.most_common():
        lines.append(f"- **{cat}**: {cnt}")
    lines.append("")

    return "\n".join(lines)


def gen_typography_report(font_analysis: Dict[str, Any], size_analysis: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Typography Audit\n")

    # Font families
    lines.append("## Font Families\n")
    if font_analysis['families']:
        lines.append("| Family | Occurrences |")
        lines.append("|--------|-------------|")
        for fam, count in sorted(font_analysis['families'].items(), key=lambda x: -x[1]):
            lines.append(f"| `{fam}` | {count} |")
    else:
        lines.append("No font-family declarations found.\n")

    lines.append("")
    lines.append("## Font Weights\n")
    if font_analysis['weights']:
        lines.append("| Weight | Occurrences |")
        lines.append("|--------|-------------|")
        for wgt, count in sorted(font_analysis['weights'].items(), key=lambda x: -x[1]):
            lines.append(f"| `{wgt}` | {count} |")
    else:
        lines.append("No font-weight declarations found.\n")

    lines.append("")
    lines.append("## Font Sizes\n")
    font_sizes = size_analysis.get('by_category', {}).get('font-size', {})
    if font_sizes:
        lines.append("| Size | Occurrences |")
        lines.append("|------|-------------|")
        for size, count in sorted(font_sizes.items(), key=lambda x: -x[1]):
            lines.append(f"| `{size}` | {count} |")
    else:
        lines.append("No font-size declarations found.\n")

    lines.append("")
    lines.append("## Line Heights\n")
    line_heights = size_analysis.get('by_category', {}).get('line-height', {})
    if line_heights:
        lines.append("| Value | Occurrences |")
        lines.append("|-------|-------------|")
        for lh, count in sorted(line_heights.items(), key=lambda x: -x[1]):
            lines.append(f"| `{lh}` | {count} |")
    else:
        lines.append("No line-height declarations found.\n")

    return "\n".join(lines)


def gen_spacing_report(size_analysis: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Spacing & Sizing Audit\n")
    lines.append(f"**Total size occurrences**: {size_analysis['total_occurrences']}  ")
    lines.append(f"**Unique size values**: {size_analysis['total_unique']}  \n")

    for category_label in [
        ('margin', 'Margin Values'),
        ('padding', 'Padding Values'),
        ('gap', 'Gap Values'),
        ('font-size', 'Font Sizes'),
        ('border-width', 'Border Widths'),
        ('line-height', 'Line Heights'),
        ('size', 'Dimension (width/height) Values'),
    ]:
        cat_key, label = category_label
        values = size_analysis.get('by_category', {}).get(cat_key, {})
        if values:
            lines.append(f"## {label}\n")
            lines.append("| Value | Occurrences |")
            lines.append("|-------|-------------|")
            for v, count in sorted(values.items(), key=lambda x: -x[1]):
                lines.append(f"| `{v}` | {count} |")
            lines.append("")

    # Check grid compliance
    lines.append("## Grid Compliance\n")
    all_px = []
    for size in size_analysis.get('sizes', []):
        if 'px' in size['value']:
            all_px.append(size)
    if all_px:
        px_values = []
        for s in all_px:
            try:
                px_values.append(int(s['value'].replace('px', '')))
            except ValueError:
                pass
        from collections import Counter
        px_counter = Counter(px_values)
        top_px = [v for v, c in px_counter.most_common(30)]

        # Determine dominant grid
        # Try 4px
        grid_4_ok = sum(1 for v in top_px if v % 4 == 0)
        grid_8_ok = sum(1 for v in top_px if v % 8 == 0)
        grid = 4 if grid_4_ok > len(top_px) / 2 else (8 if grid_8_ok > len(top_px) / 2 else None)

        if grid:
            off_grid = [v for v in top_px if v % grid != 0]
            lines.append(f"Grid appears to be **{grid}px** ({grid_4_ok}/{len(top_px)} values on grid).\n")
            if off_grid:
                lines.append("**Off-grid values**: " + ", ".join(f"`{v}px`" for v in off_grid[:15]) + "\n")
            else:
                lines.append("All top spacing values conform to the grid.\n")
        else:
            lines.append("Could not determine a consistent spacing grid.\n")

    return "\n".join(lines)


def gen_borders_shadows_report(radii: Dict[str, int], shadows: Dict[str, int]) -> str:
    lines = []
    lines.append("# Border & Shadow Audit\n")

    lines.append("## Border Radii\n")
    if radii:
        lines.append("| Value | Occurrences |")
        lines.append("|-------|-------------|")
        for v, count in sorted(radii.items(), key=lambda x: -x[1]):
            lines.append(f"| `{v}` | {count} |")
    else:
        lines.append("No border-radius values found.\n")

    lines.append("")
    lines.append("## Box Shadows\n")
    if shadows:
        lines.append("| Value | Occurrences |")
        lines.append("|-------|-------------|")
        for v, count in sorted(shadows.items(), key=lambda x: -x[1]):
            lines.append(f"| `{v}` | {count} |")
    else:
        lines.append("No box-shadow values found.\n")

    return "\n".join(lines)


def gen_inconsistencies_report(inconsistencies: List[dict]) -> str:
    lines = []
    lines.append("# Design Inconsistencies\n")
    lines.append(f"**{len(inconsistencies)} issue(s) detected**\n")

    if not inconsistencies:
        lines.append("No inconsistencies detected. The project appears visually consistent.\n")
        lines.append("\n---\n\n*Note: This is a mechanical analysis. An AI review may find additional semantic inconsistencies.*\n")
        return "\n".join(lines)

    for i, inc in enumerate(inconsistencies, 1):
        severity_icon = {'high': '🔴 High', 'medium': '🟡 Medium', 'low': '🟢 Low'}.get(inc['severity'], '⚪ Unknown')
        lines.append(f"## Issue #{i}: {inc['type'].replace('-', ' ').title()}\n")
        lines.append(f"**Severity**: {severity_icon}\n")
        lines.append(f"{inc['description']}\n")

        if 'values' in inc:
            lines.append("**Values involved**:\n")
            if isinstance(inc['values'], dict):
                for v, c in sorted(inc['values'].items(), key=lambda x: -x[1]):
                    lines.append(f"- `{v}` ({c}x)")
            elif isinstance(inc['values'], list):
                for v in inc['values']:
                    lines.append(f"- `{v}`")
            lines.append("")

        if 'file_count' in inc:
            lines.append(f"**Files affected**: {inc['file_count']}\n")

        if 'off_grid_values' in inc:
            lines.append(f"**Off-grid examples**: {', '.join(f'`{v}px`' for v in inc['off_grid_values'][:10])}\n")

        lines.append("---\n")

    lines.append("\n*Note: This analysis is mechanical. An AI review should follow to identify semantic inconsistencies "
                  "(e.g., two buttons that *look* different but *mean* the same thing).*\n")

    return "\n".join(lines)


# ──────────────────────── Incremental Check ────────────────────────

def get_git_head(root: Path) -> Optional[str]:
    """Get current git HEAD."""
    try:
        import subprocess
        r = subprocess.run(['git', 'log', '-1', '--format=%H'],
                          capture_output=True, text=True, cwd=root, timeout=10)
        return r.stdout.strip() or None
    except Exception:
        return None


AUDIT_STATE_FILE = ".audit-state.json"


def check_update_needed(root: Path, out_root: Path) -> Optional[str]:
    """Check if re-scan is needed. Returns None if up to date, str reason otherwise."""
    state_file = out_root / AUDIT_STATE_FILE
    current_head = get_git_head(root)

    if not out_root.is_dir() or not list(out_root.glob("*.md")):
        return "no existing audit data"

    if not state_file.is_file():
        return "no previous audit state"

    try:
        state = json.loads(state_file.read_text())
        if current_head:
            last_head = state.get('git_head')
            if last_head == current_head:
                return None  # Up to date
            return f"git HEAD changed: {(last_head or 'none')[:8]} → {(current_head or 'none')[:8]}"
        else:
            # No git — check mtime on key files
            last_scan = state.get('last_scan_time', 0)
            pkg = root / 'package.json'
            if pkg.is_file() and pkg.stat().st_mtime > last_scan:
                return "package.json modified"
            return None
    except (json.JSONDecodeError, KeyError):
        return "audit state file corrupted"


def save_audit_state(root: Path, out_root: Path):
    head = get_git_head(root)
    state = {
        'git_head': head or '',
        'last_scan_time': datetime.now().timestamp(),
        'scanned_at': datetime.now().isoformat(),
    }
    (out_root / AUDIT_STATE_FILE).write_text(json.dumps(state, indent=2))


# ──────────────────────── Main ────────────────────────

def audit_project(project_path: str, output_dir: str = ".design-audit",
                  update: bool = False, verbose: bool = False):
    root = Path(project_path).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory.", file=sys.stderr)
        sys.exit(1)

    out_root = root / output_dir

    # Incremental check
    if update:
        reason = check_update_needed(root, out_root)
        if reason is None:
            print(f"✓ Audit data is up to date (last: {get_scan_time(out_root)}).")
            return
        print(f"⟳ Update needed: {reason}")
        print(f"  Re-scanning {root}...\n")

    print(f"🔍 Deep audit: {root}")

    # Phase 1: Find all source files
    if verbose:
        print("  [1/5] Locating source files...")
    files = glob_source_files(root)

    css_files = [f for f in files if f.suffix in ('.css', '.scss', '.less')]
    jsx_files = [f for f in files if f.suffix in ('.jsx', '.tsx', '.js', '.ts')]
    vue_files = [f for f in files if f.suffix == '.vue']
    svelte_files = [f for f in files if f.suffix == '.svelte']
    html_files = [f for f in files if f.suffix == '.html']

    total_files = len(files)
    if verbose:
        print(f"    → {total_files} files: {len(css_files)} CSS, {len(jsx_files)} JS/TS, "
              f"{len(vue_files)} Vue, {len(svelte_files)} Svelte, {len(html_files)} HTML")

    # Phase 2: Extract values
    if verbose:
        print("  [2/5] Extracting visual values...")

    audit = AuditData()
    extractor = CSSExtractor()

    # Process CSS/SCSS/Less files
    for f in css_files:
        content = read_file_safe(f)
        if not content:
            continue
        rel_path = str(f.relative_to(root))
        for item in extractor.extract_colors(content, 'css', rel_path):
            audit.add(item)
        for item in extractor.extract_sizes(content, 'css', rel_path):
            audit.add(item)
        for item in extractor.extract_font_props(content, 'css', rel_path):
            audit.add(item)
        for item in extractor.extract_border_shadows(content, 'css', rel_path):
            audit.add(item)

    # Process JSX/TSX files
    for f in jsx_files:
        content = read_file_safe(f)
        if not content:
            continue
        rel_path = str(f.relative_to(root))
        for item in extract_inline_styles(content, rel_path):
            audit.add(item)

    # Process Vue files
    for f in vue_files:
        content = read_file_safe(f)
        if not content:
            continue
        rel_path = str(f.relative_to(root))
        for item in extract_vue_styles(content, rel_path):
            audit.add(item)

    # Process Svelte files
    for f in svelte_files:
        content = read_file_safe(f)
        if not content:
            continue
        rel_path = str(f.relative_to(root))
        # Svelte uses <style> blocks like Vue
        style_blocks = re.finditer(r'<style[^>]*>(.*?)</style>', content, re.DOTALL)
        for block in style_blocks:
            block_line = content[:block.start()].count('\n') + 1
            css_content = block.group(1)
            for item in extractor.extract_colors(css_content, 'svelte-style', rel_path, block_line):
                audit.add(item)
            for item in extractor.extract_sizes(css_content, 'svelte-style', rel_path, block_line):
                audit.add(item)
            for item in extractor.extract_font_props(css_content, 'svelte-style', rel_path, block_line):
                audit.add(item)
            for item in extractor.extract_border_shadows(css_content, 'svelte-style', rel_path, block_line):
                audit.add(item)

        # Svelte inline style bindings
        inline_style_bindings = re.finditer(
            r'style\s*=\s*"\s*([^"]+?)\s*"',
            content
        )
        for bind in inline_style_bindings:
            bind_line = content[:bind.start()].count('\n') + 1
            style_content = bind.group(1)
            fake_css = style_content.replace(';', '\n')
            for item in extractor.extract_colors(fake_css, 'svelte-inline', rel_path, bind_line):
                audit.add(item)

    if verbose:
        print(f"    → Colors: {len(audit.colors)}, Sizes: {len(audit.sizes)}, "
              f"Fonts: {len(audit.font_families)} fam / {len(audit.font_weights)} wgt, "
              f"Radii: {len(audit.border_radii)}, Shadows: {len(audit.box_shadows)}")

    # Phase 3: Analyze
    if verbose:
        print("  [3/5] Analyzing data...")
    color_analysis = audit.build_color_analysis()
    size_analysis = audit.build_size_analysis()
    font_analysis = audit.build_font_analysis()
    radii = audit.build_radius_analysis()
    shadows = audit.build_shadow_analysis()

    # Phase 4: Detect inconsistencies
    if verbose:
        print("  [4/5] Detecting inconsistencies...")
    inconsistencies = detect_inconsistencies(audit)

    if verbose:
        print(f"    → {len(inconsistencies)} inconsistency(ies) found")

    # Phase 5: Generate reports
    if verbose:
        print("  [5/5] Writing reports...")

    out_root.mkdir(parents=True, exist_ok=True)

    write_file(out_root / "README.md", gen_readme(audit, root.name, total_files, inconsistencies))
    write_file(out_root / "01-all-colors.md", gen_colors_report(color_analysis))
    write_file(out_root / "02-all-typography.md", gen_typography_report(font_analysis, size_analysis))
    write_file(out_root / "03-all-spacing.md", gen_spacing_report(size_analysis))
    write_file(out_root / "04-all-borders-shadows.md", gen_borders_shadows_report(radii, shadows))
    write_file(out_root / "05-inconsistencies.md", gen_inconsistencies_report(inconsistencies))
    write_file(out_root / "06-value-map.json", json.dumps(audit.build_value_map(), indent=2, ensure_ascii=False))

    save_audit_state(root, out_root)

    # Summary
    print(f"\n{'='*50}")
    print(f"✅ Audit complete!")
    print(f"{'='*50}")
    print(f"  Files scanned:  {total_files}")
    print(f"  Colors:         {len(audit.colors)} occurrences, {color_analysis['total_unique']} unique")
    print(f"  Sizes:          {len(audit.sizes)} occurrences, {size_analysis['total_unique']} unique")
    print(f"  Font families:  {font_analysis['total_family_occurrences']} occurrences")
    print(f"  Font weights:   {font_analysis['total_weight_occurrences']} occurrences")
    print(f"  Radii:          {len(audit.border_radii)} occurrences")
    print(f"  Shadows:        {len(audit.box_shadows)} occurrences")
    print(f"  Issues:         {len(inconsistencies)} inconsistency(ies) identified")
    print(f"  Output:         {out_root}/")
    print(f"{'='*50}")

    if inconsistencies:
        print(f"\n⚠️  Top issues:")
        for inc in inconsistencies[:3]:
            icon = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(inc['severity'], '⚪')
            print(f"  {icon} {inc['type']}: {inc['description'][:100]}...")

    print(f"\nNext: load `design-restyle` skill to apply systematic changes.")
    print(f"  Or: read .design-audit/ and create token mappings manually.")


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    status = "✅" if str(path).endswith('.json') else "✅"
    print(f"  {status} {path.name}")


def get_scan_time(out_root: Path) -> str:
    state_file = out_root / AUDIT_STATE_FILE
    if state_file.is_file():
        try:
            state = json.loads(state_file.read_text())
            return state.get('scanned_at', 'unknown')
        except (json.JSONDecodeError, KeyError):
            return 'unknown'
    return 'never'


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deep design audit — extract all hardcoded visual values")
    parser.add_argument("project", help="Path to the frontend project")
    parser.add_argument("--output-dir", default=".design-audit", help="Output directory (default: .design-audit)")
    parser.add_argument("--update", "-u", action="store_true", help="Incremental: only re-scan if git HEAD changed")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print progress details")
    args = parser.parse_args()
    audit_project(args.project, args.output_dir, args.update, args.verbose)
