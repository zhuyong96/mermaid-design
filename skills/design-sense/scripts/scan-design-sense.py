#!/usr/bin/env python3
"""
Project Design System Scanner
=============================
Scans a frontend project and generates structured Markdown documentation
of its design system. Output goes to <project>/.design/sense/.

Usage:
    python3 scan-design-sense.py /path/to/project [--output-dir NAME] [--verbose]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# ──────────────────────────── Helpers ────────────────────────────

def run(cmd: List[str], cwd: Path) -> Tuple[str, str, int]:
    """Run a shell command and return (stdout, stderr, code)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
        return r.stdout, r.stderr, r.returncode
    except FileNotFoundError:
        return "", f"command not found: {cmd[0]}", -1
    except subprocess.TimeoutExpired:
        return "", "timeout", -1


def quiet_run(cmd: List[str], cwd: Path) -> str:
    """Run and return stdout, ignoring errors."""
    out, _, _ = run(cmd, cwd)
    return out


def glob_files(root: Path, patterns: List[str]) -> List[Path]:
    """Find files matching shell glob patterns."""
    found: List[Path] = []
    for pat in patterns:
        for p in root.rglob(pat):
            # Skip node_modules, .git, dist, .next, .nuxt
            parts = p.relative_to(root).parts
            if any(seg in parts for seg in ('node_modules', '.git', 'dist',
                                            '.next', '.nuxt', '.output',
                                            '.cache', '__pycache__')):
                continue
            if p.is_file():
                found.append(p)
    return sorted(found)


def read_file_safe(path: Path, max_size: int = 500_000) -> str:
    """Read file content, with size limit."""
    if not path.is_file():
        return ""
    try:
        if path.stat().st_size > max_size:
            return f"[file too large: {path.stat().st_size} bytes]"
        return path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        return f"[read error: {e}]"


def write_md(path: Path, content: str):
    """Write markdown file, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    print(f"  ✅ {path.name}")


def heading(text: str, level: int = 1) -> str:
    return f"{'#' * level} {text}\n\n"


def table(headers: List[str], rows: List[List[str]]) -> str:
    """Generate a markdown table."""
    if not rows:
        return "*No data.*\n\n"
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))
    lines = []
    sep = "|"
    fmt = " | ".join(f"{{:<{w}}}" for w in col_widths)
    lines.append(f"| {fmt.format(*headers)} |")
    lines.append(f"|{'|'.join('-' * (w + 2) for w in col_widths)}|")
    for row in rows:
        padded = [cell + " " * (w - len(cell)) for cell, w in zip(row, col_widths)]
        lines.append(f"| {' | '.join(padded)} |")
    return "\n".join(lines) + "\n\n"


# ──────────────────────────── Package.json Scanner ────────────────────────────

UI_LIBS = {
    "antd": "Ant Design",
    "ant-design-vue": "Ant Design Vue",
    "element-plus": "Element Plus",
    "element-ui": "Element UI",
    "@mui/material": "Material UI (MUI)",
    "@nextui-org/react": "NextUI",
    "@chakra-ui/react": "Chakra UI",
    "primevue": "PrimeVue",
    "vuetify": "Vuetify",
    "view-ui-plus": "View Design",
    "react-bootstrap": "React Bootstrap",
    "bootstrap": "Bootstrap",
    "@headlessui/react": "Headless UI",
    "@radix-ui/react-accordion": "Radix UI",
    "radix-vue": "Radix Vue",
    "react-virtuoso": "Virtuoso (virtual list)",
    "@tanstack/react-table": "TanStack Table",
    "@tanstack/react-query": "TanStack Query",
    "react-router-dom": "React Router",
    "vue-router": "Vue Router",
    "next": "Next.js",
    "nuxt": "Nuxt.js",
}

CSS_FRAMEWORKS = {
    "tailwindcss": "Tailwind CSS",
    "styled-components": "Styled Components",
    "@emotion/react": "Emotion (React)",
    "@emotion/styled": "Emotion Styled",
    "jss": "JSS",
    "@stitches/react": "Stitches",
    "vanilla-extract": "Vanilla Extract",
    "unocss": "UnoCSS",
    "windicss": "Windi CSS",
}

CSS_PREPROCESSORS = {
    "sass": "Sass/SCSS",
    "less": "Less",
    "stylus": "Stylus",
    "postcss": "PostCSS",
}


def scan_package_json(root: Path) -> dict:
    """Scan package.json and return findings."""
    result = {
        "ui_libs": [],
        "css_frameworks": [],
        "css_preprocessors": [],
        "build_tools": [],
        "other_notable": [],
        "project_name": "",
        "version": "",
    }

    pkg = root / "package.json"
    if not pkg.is_file():
        return result

    data = json.loads(pkg.read_text(encoding='utf-8', errors='replace'))
    result["project_name"] = data.get("name", "")
    result["version"] = data.get("version", "")

    all_deps = {}
    all_deps.update(data.get("dependencies", {}))
    all_deps.update(data.get("devDependencies", {}))

    for pkg_name, label in UI_LIBS.items():
        if pkg_name in all_deps:
            result["ui_libs"].append((label, all_deps[pkg_name]))

    for pkg_name, label in CSS_FRAMEWORKS.items():
        if pkg_name in all_deps:
            result["css_frameworks"].append((label, all_deps[pkg_name]))

    for pkg_name, label in CSS_PREPROCESSORS.items():
        if pkg_name in all_deps:
            result["css_preprocessors"].append((label, all_deps[pkg_name]))

    # Build tools
    build_tool_map = {
        "vite": "Vite", "webpack": "Webpack", "@vitejs/plugin-react": "Vite",
        "next": "Next.js", "nuxt": "Nuxt.js", "@angular/cli": "Angular CLI",
        "react-scripts": "Create React App", "parcel": "Parcel",
        "astro": "Astro", "sveltekit": "SvelteKit",
    }
    for pkg_name, label in build_tool_map.items():
        if pkg_name in all_deps:
            result["build_tools"].append((label, all_deps[pkg_name]))

    return result


# ──────────────────────────── Config Scanner ────────────────────────────

def scan_tailwind_config(root: Path) -> dict:
    """Extract theme extend from Tailwind config."""
    tokens = {"colors": {}, "fontFamily": {}, "spacing": {}, "borderRadius": {}, "boxShadow": {}}
    config_files = glob_files(root, ["tailwind.config.*"])
    for cf in config_files:
        content = read_file_safe(cf)
        # Extract theme.extend
        m = re.search(r"theme\s*:\s*\{[^}]*extend\s*:\s*\{([^}]+)\}", content, re.DOTALL)
        if m:
            extend_block = m.group(1)
            # Colors
            color_m = re.search(r"colors\s*:\s*\{([^}]+)\}", extend_block, re.DOTALL)
            if color_m:
                for line in color_m.group(1).split(","):
                    line = line.strip()
                    if ":" in line:
                        k, v = line.split(":", 1)
                        tokens["colors"][k.strip()] = v.strip().strip("'\";,")
            # Font family
            font_m = re.search(r"fontFamily\s*:\s*\{([^}]+)\}", extend_block, re.DOTALL)
            if font_m:
                for line in font_m.group(1).split(","):
                    line = line.strip()
                    if ":" in line:
                        k, v = line.split(":", 1)
                        tokens["fontFamily"][k.strip()] = v.strip().strip("'\";,")
            # Spacing
            spacing_m = re.search(r"spacing\s*:\s*\{([^}]+)\}", extend_block, re.DOTALL)
            if spacing_m:
                for line in spacing_m.group(1).split(","):
                    line = line.strip()
                    if ":" in line:
                        k, v = line.split(":", 1)
                        tokens["spacing"][k.strip()] = v.strip().strip("'\";,")
    return tokens


def scan_css_tokens(root: Path) -> dict:
    """Extract CSS custom properties and SCSS/Less variables."""
    tokens = {"css_vars": {}, "scss_vars": {}}

    # CSS custom properties (--name: value)
    css_files = glob_files(root, ["**/*.css", "**/*.scss", "**/*.less"])
    for f in css_files:
        content = read_file_safe(f)
        for m in re.finditer(r'--([\w-]+)\s*:\s*([^;]+?)\s*(?:!important)?\s*;', content):
            name, val = m.group(1), m.group(2).strip()
            # Skip if looks like utility or variable reference
            if not val.startswith("var("):
                tokens["css_vars"][f"--{name}"] = val

    # SCSS variables ($name: value)
    scss_files = glob_files(root, ["**/*.scss"])
    for f in scss_files:
        content = read_file_safe(f)
        for m in re.finditer(r'^\s*\$([\w-]+)\s*:\s*([^;]+?)\s*;', content, re.MULTILINE):
            name, val = m.group(1), m.group(2).strip()
            tokens["scss_vars"][f"${name}"] = val

    return tokens


def scan_postcss_config(root: Path) -> List[str]:
    """Extract PostCSS plugins."""
    plugins = []
    config_files = glob_files(root, ["postcss.config.*", ".postcssrc*"])
    for cf in config_files:
        content = read_file_safe(cf)
        # JS config: plugins: { tailwindcss: {}, ... }
        for m in re.finditer(r"(?:require|import)\s*\(\s*['\"]([\w-]+)['\"]", content):
            plugins.append(m.group(1))
        # JSON config
        try:
            data = json.loads(content)
            if "plugins" in data:
                plugins.extend(data["plugins"].keys() if isinstance(data["plugins"], dict) else data["plugins"])
        except json.JSONDecodeError:
            pass
    return list(set(plugins))


# ──────────────────────────── Route Scanner ────────────────────────────

def detect_framework(pkg_info: dict) -> str:
    """Detect frontend framework from package info."""
    for lib_name, _ in pkg_info["build_tools"]:
        if "Next.js" in lib_name: return "next"
        if "Nuxt" in lib_name: return "nuxt"
        if "Vite" in lib_name:
            # Need to check further
            for ul, _ in pkg_info["ui_libs"]:
                if "React" in ul or "NextUI" in ul:
                    return "react"
                if "Vue" in ul:
                    return "vue"
            return "react"  # Default guess
        if "Angular" in lib_name: return "angular"
    # Fallback heuristics
    if any(lib == "react-router-dom" for lib, _ in pkg_info["ui_libs"]):
        return "react"
    if any(lib == "vue-router" for lib, _ in pkg_info["ui_libs"]):
        return "vue"
    if any(lib == "next" for lib, _ in pkg_info["ui_libs"]):
        return "next"
    return "unknown"


def scan_routes(root: Path, framework: str) -> List[dict]:
    """Scan routes and pages in the project."""
    pages = []
    seen_routes = set()

    if framework == "next":
        # Next.js App Router
        page_files = glob_files(root, ["app/**/page.tsx", "app/**/page.jsx", "app/**/page.js", "app/**/page.ts"])
        for pf in page_files:
            rel = pf.relative_to(root).as_posix()
            # Convert 'app/users/page.tsx' → '/users'
            route = "/" + rel.replace("app/", "").replace("/page.tsx", "").replace("/page.jsx", "").replace("/page.js", "").replace("/page.ts", "")
            # Handle dynamic routes [id] → :id
            route = re.sub(r'\[(\w+)\]', r':\1', route)
            # Handle group routes (auth) → ignore in path
            route = re.sub(r'/\([\w-]+\)', '', route)
            # Handle catch-all [...slug] → /*slug
            route = re.sub(r'\[{3}(\w+)\]{3}', r':\1', route)
            if not route: route = "/"
            if route not in seen_routes:
                seen_routes.add(route)
                pages.append({"route": route, "file": rel, "framework": "next-app"})
    elif framework == "react":
        # React Router explicit config
        route_files = glob_files(root, ["src/routes.*", "src/router.*", "src/**/routes.*",
                                        "src/**/router.*", "src/**/*.routes.tsx", "src/**/*.routes.ts"])
        seen = set()
        for rf in route_files:
            content = read_file_safe(rf)
            for m in re.finditer(r"path\s*:\s*['\"]([^'\"]+)['\"]", content):
                path_val = m.group(1)
                if path_val not in seen:
                    seen.add(path_val)
                    pages.append({"route": path_val, "file": rf.relative_to(root).as_posix(), "framework": "react-router"})
    elif framework == "vue":
        route_files = glob_files(root, ["src/router/**/*.{ts,js}", "router/**/*.{ts,js}"])
        seen = set()
        for rf in route_files:
            content = read_file_safe(rf)
            for m in re.finditer(r"path\s*:\s*['\"]([^'\"]+)['\"]", content):
                path_val = m.group(1)
                if path_val not in seen:
                    seen.add(path_val)
                    pages.append({"route": path_val, "file": rf.relative_to(root).as_posix(), "framework": "vue-router"})
    else:
        # Fallback: scan for path definitions in any route-like file
        route_files = glob_files(root, ["**/routes.{ts,tsx,js,jsx}", "**/router.{ts,tsx,js,jsx}",
                                        "**/*.routes.{ts,tsx}", "**/router/index.{ts,js}"])
        seen = set()
        for rf in route_files:
            content = read_file_safe(rf)
            for m in re.finditer(r"path\s*:\s*['\"]([^'\"]+)['\"]", content):
                path_val = m.group(1)
                if path_val not in seen:
                    seen.add(path_val)
                    pages.append({"route": path_val, "file": rf.relative_to(root).as_posix(),
                                  "framework": "explicit"})

    pages.sort(key=lambda p: p["route"])
    return pages


# ──────────────────────────── Layout Pattern Analyzer ────────────────────────────

LAYOUT_COMPONENTS = [
    "PageHeader", "ContentCard", "Card", "SearchForm", "ProTable", "BasicTable",
    "ModalForm", "StepsForm", "DrawerForm", "DescriptionList", "Descriptions",
    "StatCard", "ChartCard", "Timeline", "AppLayout", "Sidebar", "Header",
    "Tabs", "Table", "Form", "Modal", "Drawer", "Tag", "Badge", "Steps",
]

def analyze_page_component(root: Path, file_rel: str) -> Tuple[str, List[str], str]:
    """
    Analyze a page component file.
    Returns (layout_pattern_name, component_names_used, skeleton_description).
    """
    file_path = root / file_rel
    content = read_file_safe(file_path)
    if not content:
        return ("unknown", [], "No content read.")

    # Find which layout components are used
    used = [c for c in LAYOUT_COMPONENTS if re.search(rf'\b{c}\b', content)]
    used = list(set(used))  # dedupe

    # Determine pattern type
    pattern_type = "unknown"
    has_header = any(c in used for c in ["PageHeader"])
    has_search = any(c in used for c in ["SearchForm"])
    has_table = any(c in used for c in ["ProTable", "Table", "BasicTable"])
    has_form = any(c in used for c in ["Form", "ModalForm", "StepsForm", "DrawerForm"])
    has_card = any(c in used for c in ["Card", "ContentCard"])
    has_stat = any(c in used for c in ["StatCard", "ChartCard"])
    has_detail = any(c in used for c in ["Descriptions", "DescriptionList"])
    has_tabs = any(c in used for c in ["Tabs"])
    has_modal = any(c in used for c in ["Modal", "Drawer"])

    if has_header and has_search and has_table:
        pattern_type = "list-page"
    elif has_header and has_card and has_detail:
        pattern_type = "detail-page"
    elif has_header and has_stat:
        pattern_type = "dashboard"
    elif has_header and has_form:
        pattern_type = "form-page"
    elif has_header and has_tabs:
        pattern_type = "tab-page"
    elif has_header and has_table:
        pattern_type = "list-page"

    skeleton = []
    if has_header: skeleton.append("PageHeader(title + actions)")
    if has_search: skeleton.append("SearchForm(filters)")
    if has_stat: skeleton.append("StatCard row (x2-4)")
    if has_card and not has_table and not has_detail: skeleton.append("ContentCard")
    if has_table: skeleton.append("Table/ProTable")
    if has_form: skeleton.append("Form fields")
    if has_detail: skeleton.append("Descriptions/details")
    if has_tabs: skeleton.append("Tabs switch")
    if has_modal: skeleton.append("Modal/Drawer (action trigger)")

    return (pattern_type, used, " → ".join(skeleton) if skeleton else "unstructured")


# ──────────────────────────── Component Inventory ────────────────────────────

def scan_components(root: Path) -> List[dict]:
    """Scan reusable components in the components directory."""
    components = []
    comp_dirs = ["src/components", "components", "app/components", "lib/components"]
    components_dir = None
    for cd in comp_dirs:
        if (root / cd).is_dir():
            components_dir = root / cd
            break

    if not components_dir:
        return components

    # Find all component files (tsx, jsx, vue, svelte)
    files = glob_files(components_dir, ["**/*.tsx", "**/*.jsx", "**/*.vue", "**/*.svelte"])

    for f in files:
        content = read_file_safe(f)
        rel = f.relative_to(components_dir).as_posix()
        name = re.sub(r'\.(tsx|jsx|vue|svelte)$', '', f.name)

        if not content:
            continue

        # Detect if this is actually a component (exports something)
        export_match = re.search(r'export\s+(default\s+)?(function|const|class)\s+(\w+)', content)
        if not export_match:
            continue

        comp_name = export_match.group(3) if export_match.group(3) else name

        # Extract props interface
        props_interfaces = []
        for im in re.finditer(r'(?:interface|type)\s+(\w+Props?)\s*(?:extends\s+\w+\s*)?\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', content, re.DOTALL):
            props_interfaces.append({"name": im.group(1), "body": im.group(2).strip()})

        # Detect if wraps a known UI lib component
        wraps = None
        for lib in ["Button", "Table", "Form", "Modal", "Input", "Select", "Card",
                     "Tag", "Badge", "Tabs", "Menu", "Dropdown"]:
            if re.search(rf'(?:from|extends)\s+["\'].*{lib.lower()}["\']', content, re.IGNORECASE):
                wraps = lib
                break

        # Category hint
        rel_lower = rel.lower()
        if any(x in rel_lower for x in ["layout", "sidebar", "header", "footer", "sider"]):
            category = "layout"
        elif any(x in rel_lower for x in ["form", "input", "select", "upload", "picker"]):
            category = "form"
        elif any(x in rel_lower for x in ["chart", "graph", "stat", "trend"]):
            category = "data-display"
        elif any(x in rel_lower for x in ["button", "modal", "drawer", "tag", "badge"]):
            category = "common"
        else:
            category = "business"

        # Import path (normalized)
        parts = f.relative_to(root).parts
        # Try to find src/ prefix for @/ import pattern
        try:
            src_idx = parts.index("src")
            import_path = "@/" + "/".join(parts[src_idx + 1:])
        except ValueError:
            import_path = f.relative_to(root).as_posix()

        components.append({
            "name": comp_name,
            "file": rel,
            "import_path": import_path,
            "category": category,
            "props": props_interfaces,
            "wraps": wraps,
            "export_type": "default" if export_match.group(1) else "named",
        })

    return components


# ──────────────────────────── Code Conventions ────────────────────────────

def scan_conventions(root: Path) -> dict:
    """Analyze code style conventions."""
    conv = {
        "typescript": False,
        "file_extension": "tsx",
        "import_style": "mixed",
        "export_style": "mixed",
        "indent": "unknown",
        "quotes": "unknown",
        "semicolons": "unknown",
        "line_width": "unknown",
        "naming": "PascalCase (components), camelCase (vars)",
        "css_approach": "unknown",
        "framework": "unknown",
    }

    # Check for TypeScript
    ts_config = root / "tsconfig.json"
    conv["typescript"] = ts_config.is_file()

    # Sample files to determine patterns
    sample_files = glob_files(root, ["src/**/*.tsx", "src/**/*.jsx", "app/**/*.tsx", "pages/**/*.tsx"])[:15]
    if not sample_files:
        sample_files = glob_files(root, ["**/*.tsx", "**/*.jsx"])[:15]

    if not sample_files:
        return conv

    contents = [read_file_safe(f) for f in sample_files if read_file_safe(f)]

    # File extension
    ext_counts = Counter(f.suffix for f in sample_files)
    conv["file_extension"] = ext_counts.most_common(1)[0][0] if ext_counts else "unknown"

    # Import style
    single_quotes = sum(1 for c in contents if re.search(r"""import\s+.*?from\s+['][^']+[']""", c))
    double_quotes = sum(1 for c in contents if re.search(r'''import\s+.*?from\s+["][^"]+["]''', c))
    conv["quotes"] = "single" if single_quotes > double_quotes else "double"

    # Semicolons
    with_semi = sum(1 for c in contents if re.search(r';\s*$', c, re.MULTILINE))
    without_semi = sum(1 for c in contents if re.search(r'^(?!.*[;{])(\s*[\w<>.]+)\s*$', c, re.MULTILINE))
    conv["semicolons"] = "yes" if with_semi > without_semi else "no"

    # Export style
    default_exports = sum(1 for c in contents if "export default" in c)
    named_exports = sum(1 for c in contents if re.search(r"export\s+(const|function|class|interface|type)\s", c))
    if default_exports > named_exports * 1.5:
        conv["export_style"] = "default"
    elif named_exports > default_exports * 1.5:
        conv["export_style"] = "named"
    else:
        conv["export_style"] = "mixed"

    # CSS approach
    css_module_files = glob_files(root, ["src/**/*.module.css", "src/**/*.module.scss", "src/**/*.module.less"])
    styled_usage = sum(1 for c in contents if "styled" in c and ("styled." in c or "styled(" in c))
    tailwind_usage = sum(1 for c in contents if re.search(r'className={\s*["\'`]', c))
    css_in_js = sum(1 for c in contents if re.search(r"(css|styles)\s*:`", c))

    css_module_count = len(css_module_files)
    if tailwind_usage > 10:
        conv["css_approach"] = "Tailwind CSS (utility classes)"
    elif css_module_count > 5 and styled_usage < 3:
        conv["css_approach"] = "CSS Modules"
    elif styled_usage > 5:
        conv["css_approach"] = "Styled Components / CSS-in-JS"
    elif css_in_js > 3:
        conv["css_approach"] = "CSS-in-JS (inline/object)"
    else:
        conv["css_approach"] = "CSS/SCSS files"

    # Prettier/ESLint config
    prettier_files = [root / ".prettierrc", root / ".prettierrc.json", root / ".prettierrc.js"]
    for pf in prettier_files:
        if pf.is_file():
            pc = pf.read_text(encoding='utf-8', errors='replace')
            m = re.search(r'"printWidth"\s*:\s*(\d+)', pc)
            if m: conv["line_width"] = m.group(1)
            m = re.search(r'"semi"\s*:\s*(true|false)', pc)
            if m: conv["semicolons"] = "yes" if m.group(1) == "true" else "no"
            m = re.search(r'"singleQuote"\s*:\s*(true|false)', pc)
            if m: conv["quotes"] = "single" if m.group(1) == "true" else "double"
            m = re.search(r'"useTabs"\s*:\s*(true|false)', pc)
            if m: conv["indent"] = "tabs" if m.group(1) == "true" else "spaces"
            break

    # Editor config
    editorconfig = root / ".editorconfig"
    if editorconfig.is_file():
        ec = read_file_safe(editorconfig)
        m = re.search(r"indent_style\s*=\s*(\w+)", ec)
        if m: conv["indent"] = m.group(1)
        m = re.search(r"indent_size\s*=\s*(\d+)", ec)
        if m and conv["indent"] != "tabs": conv["indent"] = f"spaces ({m.group(1)})"

    return conv


# ──────────────────────────── Generators ────────────────────────────

def generate_01_libraries(root: Path, pkg_info: dict, framework: str) -> str:
    out = heading("Component Libraries & Dependencies")
    out += f"**Project**: {pkg_info['project_name'] or 'Unnamed'}  \n"
    out += f"**Version**: {pkg_info['version'] or 'N/A'}  \n"
    out += f"**Framework**: {framework.capitalize() if framework != 'unknown' else 'Unknown (fallback)'}\n\n"

    if pkg_info["ui_libs"]:
        out += heading("UI Libraries", 2)
        out += table(["Library", "Version"], pkg_info["ui_libs"])
    else:
        out += heading("UI Libraries", 2)
        out += "None detected from package.json (may be custom).\n\n"

    if pkg_info["css_frameworks"]:
        out += heading("CSS Frameworks", 2)
        out += table(["Framework", "Version"], pkg_info["css_frameworks"])

    if pkg_info["css_preprocessors"]:
        out += heading("CSS Preprocessors", 2)
        out += table(["Preprocessor", "Version"], pkg_info["css_preprocessors"])

    if pkg_info["build_tools"]:
        out += heading("Build Tools", 2)
        out += table(["Tool", "Version"], pkg_info["build_tools"])

    out += "\n---\n\n"
    out += "> **Note**: This data is from package.json. Some dependencies may be transitive or unused.\n"
    return out


def generate_02_css_strategy(root: Path, pkg_info: dict, conv: dict, postcss_plugins: List[str]) -> str:
    out = heading("CSS Strategy")

    out += heading("Detected Approach", 2)
    out += f"{conv['css_approach']}\n\n"

    if pkg_info["css_frameworks"]:
        out += heading("CSS Framework Details", 2)
        out += table(["Framework", "Version"], pkg_info["css_frameworks"])

    if postcss_plugins:
        out += heading("PostCSS Plugins", 2)
        for p in postcss_plugins:
            out += f"- `{p}`\n"
        out += "\n"

    # Check for CSS-related config files
    config_files = glob_files(root, ["tailwind.config.*", "postcss.config.*", ".postcssrc*"])
    if config_files:
        out += heading("CSS Config Files", 2)
        for cf in config_files:
            rel = cf.relative_to(root)
            out += f"- `{rel}`\n"
        out += "\n"

    out += "---\n\n"
    out += "> **Usage**: When writing styles, follow the detected approach. "
    out += "Do NOT mix CSS strategies (e.g., Tailwind utility classes + CSS Modules in the same file).\n"
    return out


def categorize_css_var(name: str, value: str) -> str:
    """Assign a category to a CSS variable."""
    nl = name.lower()
    vl = value.lower()
    if "#" in value or vl.startswith("rgb") or vl.startswith("hsl"):
        return "color"
    if any(x in nl for x in ("font", "text", "typography", "font-size", "font-weight", "line-height")):
        return "typography"
    if any(x in nl for x in ("spac", "padding", "margin", "gap", "grid")):
        return "spacing"
    if any(x in nl for x in ("shadow", "box-shadow")):
        return "shadow"
    if any(x in nl for x in ("radius", "round", "corner", "border-radius")):
        return "border-radius"
    if any(x in nl for x in ("border", "outline")):
        return "border"
    if "z-index" in nl or "zindex" in nl:
        return "z-index"
    if any(x in nl for x in ("timing", "transition", "duration", "ease")):
        return "animation"
    if value.endswith("px") or value.endswith("em") or value.endswith("rem") or value.endswith("%"):
        return "sizing"
    return "other"


def generate_03_tokens(root: Path, css_tokens: dict, tailwind_tokens: dict) -> str:
    out = heading("Design Tokens")

    # CSS variables organized by category
    if css_tokens["css_vars"]:
        out += heading("CSS Custom Properties", 2)
        categorized = defaultdict(list)
        for name, value in sorted(css_tokens["css_vars"].items()):
            cat = categorize_css_var(name, value)
            categorized[cat].append((name, value))

        for cat_name in ["color", "typography", "spacing", "shadow", "border-radius", "border", "z-index", "animation", "sizing", "other"]:
            items = categorized.get(cat_name, [])
            if items:
                out += heading(f"{cat_name.title()}", 3)
                out += table(["Variable", "Value"], [[n, v] for n, v in items])

    if css_tokens["scss_vars"]:
        out += heading("SCSS Variables", 2)
        # Filter out color-like values
        color_vars = {k: v for k, v in css_tokens["scss_vars"].items() if "#" in v or v.startswith("rgb")}
        other_vars = {k: v for k, v in css_tokens["scss_vars"].items() if k not in color_vars}

        if color_vars:
            out += heading("Colors", 3)
            out += table(["Variable", "Value"], [[k, v] for k, v in sorted(color_vars.items())])
        if other_vars:
            out += heading("Other SCSS Variables", 3)
            # Show top 30
            items = sorted(other_vars.items())[:30]
            out += table(["Variable", "Value"], [[k, v] for k, v in items])

    # Tailwind theme
    if tailwind_tokens["colors"]:
        out += heading("Tailwind Theme: Colors", 2)
        out += table(["Token", "Value"], [[k, v] for k, v in tailwind_tokens["colors"].items()])
    if tailwind_tokens["fontFamily"]:
        out += heading("Tailwind Theme: Font Families", 2)
        out += table(["Token", "Value"], [[k, v] for k, v in tailwind_tokens["fontFamily"].items()])
    if tailwind_tokens["spacing"]:
        out += heading("Tailwind Theme: Spacing", 2)
        out += table(["Token", "Value"], [[k, v] for k, v in tailwind_tokens["spacing"].items()])

    if not css_tokens["css_vars"] and not css_tokens["scss_vars"] and not tailwind_tokens["colors"]:
        out += "No design tokens detected. The project may use inline values or import tokens from an external package.\n"

    out += "\n---\n\n"
    out += "> **Usage**: When designing new pages, reference these token values. "
    out += "Do NOT introduce new color values or spacing values outside this palette.\n"
    return out


def generate_04_pages(root: Path, pages: List[dict], framework: str) -> str:
    out = heading("Page Patterns & Route Map")

    if not pages:
        out += "No route configuration detected.\n\n"
        out += "> **Possible reasons**: file-based routing (Next.js App Router) with no explicit route config, "
        out += "routes defined dynamically, or project uses hash-based routing.\n"
        return out

    out += heading("Route Overview", 2)
    out += f"**Total pages detected**: {len(pages)}\n"
    out += f"**Routing framework**: {framework}\n\n"

    # Group by depth
    depths = Counter(p["route"].count("/") - 1 for p in pages)
    out += "**Route depth distribution**:\n"
    for d in sorted(depths.keys()):
        out += f"- Depth {d}: {depths[d]} pages\n"
    out += "\n"

    # Page table
    out += heading("All Routes", 2)
    rows = []
    for p in pages:
        # Analyze the component file
        pattern, components_used, skeleton = analyze_page_component(root, p["file"])
        rows.append([
            f"`{p['route']}`",
            pattern,
            ", ".join(components_used[:5]) + ("..." if len(components_used) > 5 else ""),
            skeleton[:60],
        ])

    out += table(["Route", "Pattern", "Key Components", "Layout Skeleton"], rows)

    # Pattern summary
    out += heading("Layout Pattern Summary", 2)
    patterns = Counter(p["route"] for p in pages)
    pattern_groups = defaultdict(list)
    for p in pages:
        pat, _, skel = analyze_page_component(root, p["file"])
        pattern_groups[pat].append(p["route"])

    for pat_name in ["list-page", "detail-page", "dashboard", "form-page", "tab-page", "unknown"]:
        if pat_name in pattern_groups:
            routes = pattern_groups[pat_name]
            label = {"list-page": "📋 List Page (Header + Search + Table)",
                     "detail-page": "📄 Detail Page (Header + Card + Details)",
                     "dashboard": "📊 Dashboard (Summary Cards + Charts)",
                     "form-page": "📝 Form Page (Header + Form)",
                     "tab-page": "📑 Tabbed Page (Tabs + Content)",
                     "unknown": "❓ Unstructured"}.get(pat_name, pat_name)
            out += heading(label, 3)
            for r in routes:
                out += f"- `{r}`\n"
            out += "\n"

    out += "---\n\n"
    out += "> **Usage**: When creating a new page, pick the matching pattern above as a layout template. "
    out += "Use the same component hierarchy.\n"
    return out


def generate_05_components(root: Path, components: List[dict]) -> str:
    out = heading("Component Inventory")

    if not components:
        out += "No reusable components detected in `components/` or `src/components/`.\n\n"
        out += "> The project may use UI library components directly without custom wrappers.\n"
        return out

    out += f"**Total reusable components**: {len(components)}\n\n"

    # Group by category
    categories = defaultdict(list)
    for c in components:
        categories[c["category"]].append(c)

    for cat_name in ["layout", "common", "form", "data-display", "business"]:
        items = categories.get(cat_name, [])
        if not items:
            continue
        label = {"layout": "Layout Components",
                 "common": "Common UI Components",
                 "form": "Form Components",
                 "data-display": "Data Display Components",
                 "business": "Business-Specific Components"}.get(cat_name, cat_name.title())

        out += heading(label, 2)
        rows = []
        for c in items:
            wraps_str = f" (wraps {c['wraps']})" if c['wraps'] else ""
            props_summary = "; ".join(f"{p['name']}: {p['body'][:80]}" for p in c['props'][:2])
            rows.append([
                f"`{c['name']}`",
                f"`{c['import_path']}`",
                c['export_type'],
                wraps_str if c['wraps'] else "—",
                props_summary[:60] if props_summary else "—",
            ])
        out += table(["Component", "Import Path", "Export", "Wraps", "Props"], rows)

    out += "---\n\n"
    out += "> **Usage**: Prefer these custom components over raw UI library components. "
    out += "They enforce project conventions (styling, behavior, layout).\n"
    return out


def generate_06_conventions(conv: dict) -> str:
    out = heading("Code Conventions")

    rows = [
        ["TypeScript", str(conv["typescript"])],
        ["File Extension (primary)", conv["file_extension"]],
        ["Quotes", conv["quotes"]],
        ["Semicolons", conv["semicolons"]],
        ["Indentation", conv["indent"]],
        ["Export Style (preferred)", conv["export_style"]],
        ["CSS Approach", conv["css_approach"]],
        ["Line Width (max)", conv["line_width"]],
        ["Naming Convention", conv["naming"]],
    ]
    out += table(["Convention", "Value"], rows)

    out += heading("Guidelines for New Code", 2)
    out += "When creating new pages or components, follow these rules:\n\n"

    if conv["typescript"]:
        out += "1. **TypeScript** — all new files must be `.ts`/`.tsx`, not `.js`/`.jsx`\n"
    else:
        out += "1. **JavaScript** — all new files in existing `.js`/`.jsx` style\n"

    if conv["export_style"] == "default":
        out += f"2. **Exports** — use `export default function ComponentName` (default exports preferred)\n"
    elif conv["export_style"] == "named":
        out += f"2. **Exports** — use `export const ComponentName` (named exports preferred)\n"
    else:
        out += f"2. **Exports** — both default and named exports are used; follow the pattern of the closest sibling file\n"

    out += f"3. **Quotes** — use {'single' if conv['quotes'] == 'single' else 'double'} quotes for strings\n"
    out += f"4. **Semicolons** — {'always use' if conv['semicolons'] == 'yes' else 'omit'} semicolons\n"
    out += f"5. **CSS** — use {conv['css_approach'].lower()}\n"
    out += f"6. **Naming** — PascalCase for components, camelCase for variables/functions\n"

    out += "\n---\n\n"
    out += "> **Note**: These conventions are inferred from code analysis. When in doubt, "
    out += "match the style of the closest existing file.\n"
    return out


def generate_readme(root_name: str) -> str:
    out = heading(f"Design System: {root_name}")
    out += f"Auto-generated by `design-sense` on {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    out += "## Files\n\n"
    out += table(["File", "Description"],
                 [["01-component-libraries.md", "UI framework + component library analysis"],
                  ["02-css-strategy.md", "CSS approach + preprocessor + utilities"],
                  ["03-design-tokens.md", "Design tokens (colors, typography, spacing, shadows, radii)"],
                  ["04-page-patterns.md", "Page routes + layout skeletons + pattern classification"],
                  ["05-component-inventory.md", "Reusable component catalog (import paths, props, categories)"],
                  ["06-code-conventions.md", "Code style guide (quotes, semicolons, exports, CSS approach)"]])
    out += "\n## Usage\n\n"
    out += "Load the `design-sense` skill when creating new pages or modifying layouts.\n"
    out += "The agent will reference these files to maintain design consistency.\n"
    return out


# ──────────────────────────── Incremental Update ────────────────────────────

SCAN_STATE_FILE = ".scan-state.json"

def get_git_head(root: Path) -> Optional[str]:
    """Get current git HEAD hash, or None if not a git repo."""
    out = quiet_run(["git", "log", "-1", "--format=%H"], root)
    return out.strip() if out.strip() else None


def get_git_changed_files(root: Path) -> List[str]:
    """Get list of changed files (committed since HEAD~1 + uncommitted)."""
    # Committed changes since last scan
    committed = quiet_run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], root).strip()
    # Uncommitted changes (working tree + staged)
    uncommitted = quiet_run(["git", "status", "--porcelain"], root).strip()
    changed = set()
    if committed:
        for line in committed.split("\n"):
            if line.strip():
                changed.add(line.strip())
    if uncommitted:
        for line in uncommitted.split("\n"):
            parts = line.strip().split(None, 1)
            if len(parts) >= 2:
                changed.add(parts[1])
    return sorted(changed)


def check_update_needed(root: Path, out_root: Path, verbose: bool) -> Optional[str]:
    """
    Check if a re-scan is needed. Returns:
    - None if no update needed (up to date)
    - str with reason if update needed
    """
    state_file = out_root / SCAN_STATE_FILE

    current_head = get_git_head(root)

    if not out_root.is_dir() or not list(out_root.glob("*.md")):
        return "no existing scan data"

    if current_head:
        if state_file.is_file():
            try:
                state = json.loads(state_file.read_text(encoding='utf-8'))
                last_head = state.get("git_head")
                if last_head == current_head:
                    # Same HEAD — check for uncommitted changes
                    changed = get_git_changed_files(root)
                    if not changed:
                        return None  # up to date
                    return f"uncommitted changes in {len(changed)} file(s)"
                else:
                    return f"git HEAD changed: {last_head[:8] or 'none'} → {current_head[:8]}"
            except (json.JSONDecodeError, KeyError):
                return "scan state file corrupted"
        else:
            return "no previous scan state"
    else:
        # Not a git repo — check by timestamp on key files
        key_files = ["package.json"]
        for kf in key_files:
            src = root / kf
            if src.is_file() and state_file.is_file():
                src_mtime = src.stat().st_mtime
                try:
                    state = json.loads(state_file.read_text(encoding='utf-8'))
                    last_scan = state.get("last_scan_time", 0)
                    if src_mtime > last_scan:
                        return f"{kf} modified since last scan"
                except (json.JSONDecodeError, KeyError):
                    return "scan state file corrupted"
        return None  # Nothing detected as changed


def save_scan_state(root: Path, out_root: Path):
    """Save scan state for future --update checks."""
    current_head = get_git_head(root)
    state = {
        "git_head": current_head or "",
        "last_scan_time": datetime.now().timestamp(),
        "scanned_at": datetime.now().isoformat(),
    }
    state_file = out_root / SCAN_STATE_FILE
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')


def get_scan_time(out_root: Path) -> str:
    """Get human-readable last scan time from state file."""
    state_file = out_root / SCAN_STATE_FILE
    if state_file.is_file():
        try:
            state = json.loads(state_file.read_text(encoding='utf-8'))
            return state.get("scanned_at", "unknown")
        except (json.JSONDecodeError, KeyError):
            return "unknown"
    return "never"


# ──────────────────────────── Main ────────────────────────────

def scan_project(project_path: str, output_dir: str = ".design/sense", update: bool = False, verbose: bool = False):
    root = Path(project_path).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory.", file=sys.stderr)
        sys.exit(1)

    out_root = root / output_dir

    # ── Incremental update check ──
    if update:
        reason = check_update_needed(root, out_root, verbose)
        if reason is None:
            print(f"✓ Design system is up to date (last scan: {get_scan_time(out_root)}).")
            print(f"  Run without --update for a full re-scan.")
            return
        print(f"⟳ Update needed: {reason}")
        print(f"  Re-scanning {root}...\n")
    else:
        print(f"🔍 Scanning project: {root}")

    # Verify it's a frontend project
    pkg_file = root / "package.json"
    if not pkg_file.is_file():
        print(f"Warning: No package.json found at {root}. Some scans will be limited.", file=sys.stderr)

    out_root.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output: {out_root}/\n")

    # Step 1: package.json
    if verbose: print("  [1/6] Scanning package.json...")
    pkg_info = scan_package_json(root)
    framework = detect_framework(pkg_info)
    if verbose: print(f"    → Framework: {framework}, UI libs: {len(pkg_info['ui_libs'])}")

    # Step 2: Config files
    if verbose: print("  [2/6] Scanning config files...")
    tailwind_tokens = scan_tailwind_config(root)
    postcss_plugins = scan_postcss_config(root)
    if verbose: print(f"    → Tailwind tokens: {len(tailwind_tokens['colors']) + len(tailwind_tokens['fontFamily'])}")

    # Step 3: Design tokens
    if verbose: print("  [3/6] Extracting design tokens...")
    css_tokens = scan_css_tokens(root)
    if verbose: print(f"    → CSS vars: {len(css_tokens['css_vars'])}, SCSS vars: {len(css_tokens['scss_vars'])}")

    # Step 4: Conventions
    if verbose: print("  [4/6] Analyzing code conventions...")
    conv = scan_conventions(root)
    if verbose: print(f"    → Quotes: {conv['quotes']}, Semi: {conv['semicolons']}, CSS: {conv['css_approach']}")

    # Step 5: Routes/pages
    if verbose: print("  [5/6] Scanning routes and pages...")
    pages = scan_routes(root, framework)
    if verbose: print(f"    → Pages found: {len(pages)}")

    # Step 6: Components
    if verbose: print("  [6/6] Building component inventory...")
    components = scan_components(root)
    if verbose: print(f"    → Components found: {len(components)}")

    # Generate markdown files
    print("\n📝 Generating reports...")
    write_md(out_root / "README.md", generate_readme(root.name))
    write_md(out_root / "01-component-libraries.md", generate_01_libraries(root, pkg_info, framework))
    write_md(out_root / "02-css-strategy.md", generate_02_css_strategy(root, pkg_info, conv, postcss_plugins))
    write_md(out_root / "03-design-tokens.md", generate_03_tokens(root, css_tokens, tailwind_tokens))
    write_md(out_root / "04-page-patterns.md", generate_04_pages(root, pages, framework))
    write_md(out_root / "05-component-inventory.md", generate_05_components(root, components))
    write_md(out_root / "06-code-conventions.md", generate_06_conventions(conv))

    # Save scan state for future --update checks
    save_scan_state(root, out_root)

    # Summary
    print(f"\n{'='*50}")
    print(f"✅ Scan complete!")
    print(f"{'='*50}")
    print(f"  Project:  {pkg_info['project_name'] or root.name}")
    print(f"  Framework: {framework.capitalize() if framework != 'unknown' else 'Unknown'}")
    print(f"  UI Libs:  {', '.join(l for l, _ in pkg_info['ui_libs']) or 'None detected'}")
    print(f"  CSS:      {conv['css_approach']}")
    print(f"  Pages:    {len(pages)}")
    print(f"  Components: {len(components)}")
    print(f"  Output:   {out_root}/")
    print(f"{'='*50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan a project's design system")
    parser.add_argument("project", help="Path to the frontend project")
    parser.add_argument("--output-dir", default=".design/sense", help="Output directory name (default: .design/sense)")
    parser.add_argument("--update", "-u", action="store_true", help="Incremental update: only re-scan if git HEAD changed or files modified")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print progress details")
    args = parser.parse_args()
    scan_project(args.project, args.output_dir, args.update, args.verbose)
