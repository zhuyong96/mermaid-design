# Source vs Runtime: The Audit Gap

The `audit-hardcoded-values.py` script scans **source files** — what's written
in `.tsx`, `.css`, `.vue` files before any build step runs. It does **not** see
values that only appear after building the project.

## What Gets Missed

### 1. Tailwind CSS Utility Classes (Biggest Gap)

```tsx
// Source — no color value visible to the scanner
<div className="text-blue-500 bg-gray-100 p-4 rounded-lg" />
```

Tailwind's `text-blue-500` resolves to `#3b82f6` at build time. The scanner
sees the string `"text-blue-500"` — not a hex color, not a size, so it passes
unnoticed. For a heavy Tailwind project, **most actual visual values are invisible**
to the source audit.

**Workaround**: Before running the audit, extract Tailwind utility classes
from className strings and resolve them using a known mapping.

### 2. SCSS/Less Computed Values

```scss
$base: #1890ff;
.button { background: darken($base, 8%); }
```

The source contains `darken(#1890ff, 8%)` — not a final hex value.

**Workaround**: Build the project first, then scan the output CSS files.

### 3. CSS Variable Runtime Resolution

```css
.button { background: var(--color-primary); }
```

The scanner sees `var(--color-primary)` — correctly skips it because there's
nothing to replace. This is fine — `var()` references are already tokenized.

### 4. PostCSS Plugin Transforms

Plugins like `postcss-preset-env`, `postcss-color-function` transform source CSS
at build time. Their output values are invisible to source scanning.

## The Cross-Reference Approach

Most complete audit = source scan + build output analysis:

```
Phase A: Source Scan (current script)
  → Knows "what I wrote" and "where to edit it"

Phase B: Build Output Scan
  → npm run build → scan dist/output.css
  → Knows "what actually ends up in the browser"

Phase C: Cross-Reference
  ┌──────────────────┬──────────────────────┐
  │ In both source   │ Normal: replaceable   │
  │ and build        │                       │
  ├──────────────────┼──────────────────────┤
  │ In build only    │ Tailwind/PostCSS/SCSS │
  │                  │ generated             │
  ├──────────────────┼──────────────────────┤
  │ In source only   │ Dead code or unused   │
  └──────────────────┴──────────────────────┘
```

### Quick Build Scan

```bash
npm run build
BUILD_CSS=$(find dist .next build -name "*.css" 2>/dev/null | head -1)
grep -ohP '#[0-9a-fA-F]{6}\b' "$BUILD_CSS" | sort | uniq -c | sort -rn | head -30
grep -ohP '\d+px' "$BUILD_CSS" | sort | uniq -c | sort -rn | head -20
```

Compare these against the source audit values to find the gaps.

## When Source-Only Is Good Enough

| Project Type | Source Only? |
|-------------|-------------|
| Pure CSS / CSS Modules + hand-written CSS | ✅ Sufficient |
| SCSS with few color functions | ✅ Sufficient |
| Heavy Tailwind (80%+ classes) | ❌ Major gap — need build output |
| Heavy CSS-in-JS with runtime themes | ⚠️ Partial — var() refs are fine |
| PostCSS-heavy setups | ⚠️ Depends on plugin specifics |

## Summary

- Source audit tells you **what to edit and where**
- Build output tells you **what you missed**
- For most projects, source audit + reference presets is sufficient
- Tailwind-heavy projects need build output too
