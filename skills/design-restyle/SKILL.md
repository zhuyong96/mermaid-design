---
name: design-restyle
description: "Systematic UI restyling — read a deep design audit, synthesize target design tokens, inject token infrastructure, apply value mapping layer by layer, and verify consistency. Requires .design/audit/ output from design-audit skill. No dependency changes, no framework changes, no interaction changes."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [design-system, refactoring, css, restyling, frontend]
    related_skills: [design-audit, design-sense]
---

# Design Restyle

## Overview

`design-restyle` takes the output of `design-audit` and systematically applies
a unified style to an existing project — **without changing any dependency,
framework, interaction, or data logic**.

```
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│ design-audit │ ──> │ design-restyle│ ──> │  Unified UI  │
│ (what we     │     │ (how we fix   │     │  (consistent │
│  have)       │     │  it)          │     │   result)    │
└──────────────┘     └───────────────┘     └──────────────┘
```

## When to Use

- An existing project has inconsistent colors, spacing, or fonts
- You want to migrate hardcoded values to a token system
- You need a "style refresh" without rewriting the whole app
- You want to bring a project to a consistent design system standard

**Do NOT use for:**
- New greenfield projects (use `design-sense` instead)
- Projects where you can change dependencies (use a proper design system library)
- Small 1-file fixes (just patch manually)

---

## The 5-Phase Workflow

```
Phase 1: Load Audit Data     ← read .design/audit/ + .design/sense/
Phase 2: Synthesize Tokens   ← AI infers intended design + creates mapping
Phase 3: Inject Token Layer  ← add CSS vars / Tailwind config / SCSS vars
Phase 4: Apply Layer by Layer ← mechanical replacement + agent-assisted
Phase 5: Verify              ← scan, build, compare, report
```

---

## Phase 1: Load Audit Data

### Prerequisites

The project must have:
- `.design/audit/` directory (from `design-audit` scan)
- `.design/sense/` directory (from `design-sense` scan) — for framework context

### Load Order

```bash
# Ensure data is fresh
python3 skills/design-audit/scripts/audit-hardcoded-values.py <project-path> --update
python3 skills/design-sense/scripts/scan-design-sense.py <project-path> --update
```

Then read these files in order:

| # | File | What to Get |
|---|------|-------------|
| 1 | `.design/sense/02-css-strategy.md` | CSS approach (Tailwind/CSS Modules/CSS-in-JS) |
| 2 | `.design/sense/01-component-libraries.md` | UI library used (Ant Design, Element, etc.) |
| 3 | `.design/audit/05-inconsistencies.md` | Known issues |
| 4 | `.design/audit/01-all-colors.md` | Color palette (sorted by frequency) |
| 5 | `.design/audit/03-all-spacing.md` | Spacing values and grid |
| 6 | `.design/audit/02-all-typography.md` | Font usage |
| 7 | `.design/audit/04-all-borders-shadows.md` | Radii and shadows |

### Key Questions to Answer

After reading, answer these:

| Question | Where to Look |
|----------|---------------|
| What framework? (React/Vue/Next/Nuxt) | `.design/sense/01-*.md` |
| What CSS approach? | `.design/sense/02-*.md` |
| What UI lib? | `.design/sense/01-*.md` |
| What's the dominant color palette? | `.design/audit/01-all-colors.md` (top 20) |
| What spacing grid (4px/8px)? | `.design/audit/03-all-spacing.md` "Grid Compliance" |

---

## Phase 2: Reference → Semantic Mapping

This is the core innovation. Instead of mapping old values to the **most frequent
old value** (which only guarantees consistency, not beauty), we:

1. **Choose an external reference design system** — a curated, professionally
   designed token set that looks good
2. **Classify old values by semantic role** — using CSS property + value
   heuristics to understand what each value *means* (is `#f5f5f5` a page bg
   or a card bg?)
3. **Map each semantic role to the reference token** — old color → role →
   new beautiful value

```
旧: #1890ff (47x, used in background)         旧: #f5f5f5 (32x, used in background)
  → CSS property: background-color               → CSS property: background-color
  → Semantic role: bg-card                        → Semantic role: bg-page
  → Reference token: tailwind/primary             → Reference token: tailwind/bg-page
  → New value: #3b82f6                            → New value: #f9fafb
```

### Step 2a: Choose a Reference Design System

```bash
python3 skills/design-restyle/scripts/semantic-mapper.py <project-path> --list
```

Output:
```
Available reference presets:
  tailwind     Tailwind CSS Default — Universal, reliable, widely adopted
  radix        Radix Colors — Perceptually uniform color scales
  shadcn       shadcn/ui — Minimal, component-style tokens
  antd         Ant Design 5 — Enterprise-grade, Chinese-friendly
  catppuccin   Catppuccin Mocha — Modern warm pastel palette
```

| Preset | When to Use |
|--------|-------------|
| **tailwind** | Generic web apps, need a safe/professional look |
| **radix** | Accessibility-focused, need perceptually uniform colors |
| **shadcn** | Modern minimal aesthetic, CSS-variable-native |
| **antd** | 中文企业级应用，后台/中台系统 |
| **catppuccin** | Creative/niche projects, want a distinctive look |

The preset is just the starting point — you can override individual tokens
after generation.

### Step 2b: Run Semantic Mapper

```bash
python3 skills/design-restyle/scripts/semantic-mapper.py <project-path> --reference tailwind
```

This does all the work automatically:

| What the script does | How |
|----------------------|-----|
| Reads `.design/audit/06-value-map.json` | Gets every hardcoded value + file + property context |
| Classifies each value by CSS property | `color:` → text role, `background:` → bg role, etc. |
| Refines by brightness heuristics | Dark text → `text-primary`, mid gray → `text-secondary` |
| Groups values by semantic role | All page bg colors together, all borders together, etc. |
| Maps each role to the reference token | `bg-page` → `var(--color-bg-page)` from Tailwind preset |
| Snaps spacing to reference grid | `13px` → nearest token on 4px/8px grid |

Output:
```
.design/audit/
├── semantic-mapping.json         # Flat old→new mapping for apply-value-mapping.py
├── semantic-mapping-report.md    # Human-readable: role assignments, decisions
└── synthesis-recommendations.yaml（可选，AI review后的最终版）
```

### Step 2c: Agent Review + Adjustments

The `semantic-mapper.py` does **~90% correctly** by algorithm. The agent
reviews `semantic-mapping-report.md` and makes adjustments:

| Issue | How to Fix |
|-------|------------|
| `#fff` used as both page bg and card bg | Split mapping by property: `background: #fff` → `--bg-card`, `border: #fff` → `--border-light` |
| `border-radius: 50%` classified as spacing | Override: keep as `50%`, don't map to px token |
| Shadow values misdetected | Check `box-shadow` classification manually |
| Spacing `1px` mapped to `--spacing-xs` (4px) | Keep `1px` border widths, map spacing values only |

When adjustments are needed, edit the `synthesis-recommendations.yaml` manually
and regenerate the flat mapping, or apply per-context replacements directly
in Phase 4.

### Semantic Role Taxonomy

The mapper uses this role system:

| Category | Roles | Example Properties |
|----------|-------|-------------------|
| **color/text** | `text-primary`, `text-secondary`, `text-tertiary`, `text-inverse`, `text-disabled`, `text-link` | `color`, `fill`, `stroke` |
| **color/background** | `bg-page`, `bg-card`, `bg-surface`, `bg-hover`, `bg-active`, `bg-elevated`, `bg-modal-overlay` | `background`, `background-color` |
| **color/border** | `border-default`, `border-hover`, `border-focus`, `border-light` | `border-color`, `outline-color` |
| **color/semantic** | `primary`, `success`, `warning`, `danger`, `info` | Button bg, badge bg, tag bg |
| **color/** | `primary-bg`, `success-bg`, `danger-bg`, `warning-bg`, `info-bg` | Semantic background tints |
| **spacing** | Snapped to reference grid | `margin`, `padding`, `gap` |
| **typography/font-size** | Snapped to reference scale | `font-size` |
| **radius** | Snapped to reference scale | `border-radius` |
| **shadow** | Mapped by similarity | `box-shadow` |

### Value Mapping Output

The final `semantic-mapping.json` is a flat JSON suitable for `apply-value-mapping.py`:

```json
{
  "#1890ff": "#3b82f6",
  "#1a90ff": "#3b82f6",
  "#40a9ff": "#2563eb",
  "#333": "#111827",
  "#999": "#6b7280",
  "#f5f5f5": "#f9fafb",
  "#ffffff": "#ffffff",
  "#e8e8e8": "#e5e7eb",
  "14px": "16px",
  "8px": "8px",
  "6px": "6px",
  "24px": "24px"
}
```

The mapping target format depends on the project's CSS strategy
(determined in Phase 3):

---

## Phase 3: Inject Token Infrastructure

### Strategy-Specific Instructions

#### A) Tailwind CSS

```js
// tailwind.config.js — extend only, no dependency changes
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: '#1890ff',
        'primary-hover': '#40a9ff',
        'text-primary': '#1a1a1a',
        'text-secondary': '#8c8c8c',
        'bg-page': '#f5f5f5',
        // ... add all from synthesis-recommendations.yaml
      },
      spacing: {
        xs: '4px',
        sm: '8px',
        md: '16px',
        lg: '24px',
      },
      fontSize: {
        xs: '12px',
        sm: '13px',
        base: '14px',
        lg: '16px',
        xl: '20px',
      },
      borderRadius: {
        sm: '4px',
        md: '6px',
        lg: '8px',
      },
    },
  },
};
```

#### B) CSS Custom Properties

```css
/* tokens.css — imported first in the app, or append to existing global CSS */
:root {
  /* Colors */
  --color-primary: #1890ff;
  --color-primary-hover: #40a9ff;
  --color-primary-active: #096dd9;
  --color-success: #52c41a;
  --color-warning: #faad14;
  --color-danger: #ff4d4f;
  --color-text-primary: #1a1a1a;
  --color-text-secondary: #8c8c8c;
  --color-text-disabled: #d9d9d9;
  --color-bg-page: #f5f5f5;
  --color-bg-card: #ffffff;
  --color-border-default: #e8e8e8;

  /* Typography */
  --font-family-base: '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', sans-serif;
  --font-size-xs: 12px;
  --font-size-sm: 13px;
  --font-size-base: 14px;
  --font-size-lg: 16px;
  --font-size-xl: 20px;
  --font-size-xxl: 24px;
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;

  /* Spacing */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;

  /* Border */
  --border-radius-sm: 4px;
  --border-radius-md: 6px;
  --border-radius-lg: 8px;
  --border-radius-full: 9999px;

  /* Shadows */
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
}
```

#### C) SCSS Variables

```scss
// _tokens.scss
$color-primary: #1890ff;
$color-text-primary: #1a1a1a;
$font-size-base: 14px;
// ... etc
```

#### D) Styled Components / CSS-in-JS

```typescript
// tokens.ts — export a theme object
export const tokens = {
  colorPrimary: '#1890ff',
  colorTextPrimary: '#1a1a1a',
  fontSizeBase: '14px',
  // ...
};
```

### Injection Rules

| Rule | Why |
|------|-----|
| Add new file, never edit existing token files | Safety — if something breaks, the new tokens are easy to remove |
| Use the framework's native config extension (e.g., `theme.extend`) | No dependency changes needed |
| Don't delete old values yet | They'll be replaced in Phase 4, not removed now |
| The token file itself should be the only file with raw values | All other files will reference tokens |

---

## Phase 4: Apply Layer by Layer

### Execution Order

```
Layer 1: Token files only             (the new tokens themselves)
Layer 2: Global CSS / App.css         (replace common styles)
Layer 3: Component CSS files          (module-level CSS)
Layer 4: JSX/TSX inline styles        (style={{...}} objects)
Layer 5: Styled-components / CSS-in-JS (template literals)
Layer 6: Tailwind className strings   (utility class replacements)
Layer 7: SVG colors                   (fill, stroke attributes)
Layer 8: Third-party theme overrides  (Ant Design, Element Plus config)
```

### Layer Execution Pattern

For each layer, use this pattern:

```bash
1. list files in this layer
2. for each file:
   a. read the file
   b. apply value mappings (old_value → token reference)
   c. write the file
3. verify no old values remain in this layer
4. git commit with message "restyle: <layer name>"
5. move to next layer
```

### How the Agent Applies Each Layer

#### For CSS files (Layer 2-3):

Use the `patch` tool — targeted find-and-replace with fuzzy matching:

```
Input:  .my-class { background: #1890ff; color: #333; }
Output: .my-class { background: var(--color-primary); color: var(--color-text-primary); }
```

Strategy:
1. For each file, group replacements by target token
2. Apply using `patch` with `replace_all=true` when the old value is unique enough
3. If the old value appears in many contexts (e.g., `#fff` as both background and border),
   apply per-context replacement (background: #fff → var(--color-bg-card);
   border: 1px solid #fff → var(--color-border-default))

#### For JSX/TSX inline styles (Layer 4):

Strategy per pattern:

| Inline Style Pattern | Replacement |
|----------------------|-------------|
| `color: '#1890ff'` | `color: 'var(--color-primary)'` or CSS variable reference |
| `backgroundColor: '#f5f5f5'` | `backgroundColor: 'var(--color-bg-page)'` |
| `fontSize: '14px'` | `fontSize: 'var(--font-size-base)'` |
| `borderRadius: '8px'` | `borderRadius: 'var(--border-radius-lg)'` |

**CRITICAL**: Do NOT replace values in non-style contexts. When patching inline
styles, ensure the replacement only happens inside `style={{...}}` blocks.
Use the `style=` context in the `old_string` to anchor the match.

#### For Tailwind classNames (Layer 6):

```
Input:  className="text-sm text-gray-600"
Output: className="text-sm text-text-secondary"

Input:  className="bg-blue-500"
Output: className="bg-primary"
```

**CRITICAL**: Tailwind utility names depend on the project's Tailwind config.
If the project extended `colors: { primary: '...' }`, then use `bg-primary`,
not `bg-[#1890ff]`. If no Tailwind config extension exists, use arbitrary
values: `bg-[color:var(--color-primary)]` or `text-[color:var(--color-text-primary)]`.

### Per-Layer Safety Checks

| Check | How |
|-------|-----|
| No build errors | Run `npm run build` or equivalent |
| No old value leaks | Run `verify-restyle.py --check-remaining` |
| No interaction changes | git diff — only style values should differ |
| No new magic values | All new values come from the token set |
| No accidental non-style replacements | Verify with git diff, review changes |

### Commit Strategy

```
restyle/phase1: inject token infrastructure
restyle/phase2: migrate global CSS
restyle/phase3: migrate component CSS
restyle/phase4: migrate inline styles (JSX/TSX)
restyle/phase5: migrate Tailwind classes
restyle/phase6: migrate SVG/icon colors
restyle/phase7: final verification
```

---

## Phase 5: Verify

### Automated Verification

```bash
python3 skills/design-restyle/scripts/verify-restyle.py <project-path> --tokens .design/audit/semantic-mapping.json
```

The script checks:

| Check | What It Tests |
|-------|---------------|
| ✅ Still compiles | Project builds without errors |
| ✅ Zero old colors | No colors from the "replaces" list exist outside token files |
| ✅ On-grid spacing | All px values are multiples of the target grid |
| ✅ Font scale compliance | Font sizes come from the target scale |
| ✅ Consistent radius | Border-radius uses at most 3 unique values |
| ✅ No magic values | Every visual value is a token reference (var(), config key, or variable) |

### Manual Verification

1. **Visual diff** — Navigate key pages (home, list, detail, form) and compare to screenshots
2. **Component check** — Verify buttons, inputs, cards, tables look right
3. **Dark mode** (if applicable) — Verify it still works
4. **Responsive** — Verify no layout shifts from spacing changes

### Report

Write to `.design/audit/restyle-report.md`:

```markdown
# Restyle Report

| Metric | Before | After |
|--------|--------|-------|
| Unique colors | 47 | 12 |
| Unique spacing values | 23 | 7 |
| Unique border-radius | 6 | 3 |
| Font families | 3 | 1 |
| Font sizes | 8 | 5 |

## Files Modified
- tokens.css (new)
- 14 CSS files
- 22 component files

## Remaining Issues
- 3 files still use `#e8e8e8` — needs manual review
```

---

## Safety Net: Rollback

If anything goes wrong at any layer:

```bash
# If you committed per layer:
git reset --hard HEAD~1

# If you haven't committed:
git checkout -- <affected-files>
```

**Golden rule**: Commit after each verified layer. Never apply two layers
without a checkpoint commit.

---

## Multi-Style Switching

Once the project uses CSS variables for all visual values (Phase 3 enforces this),
**switching styles becomes trivial** — just swap the token definitions.

### How It Works

After restyling, all hardcoded values have been replaced with `var(--xxx)` references.
The only place with raw values is the token file:

```css
/* tokens.css — the ONLY file with raw values */
:root {
  --color-primary: #3b82f6;
  --color-bg-page: #f9fafb;
  --color-text-primary: #111827;
  /* ... 50+ tokens ... */
}
```

### Style Variants

Create alternate token files for different styles:

```css
/* Dark mode */
[data-theme="dark"] {
  --color-primary: #60a5fa;
  --color-bg-page: #0f172a;
  --color-text-primary: #f1f5f9;
  --shadow-sm: 0 1px 3px 0 rgba(0, 0, 0, 0.3);
}
```

```css
/* Brand B (e.g., after company rebrand) */
[data-brand="acme"] {
  --color-primary: #7c3aed;
  --color-primary-hover: #6d28d9;
}
```

### Generating Alternate Styles

```bash
# Generate style variants from different reference presets
python3 semantic-mapper.py <path> --reference catppuccin  --output .design/audit/catppuccin-mapping.json
python3 semantic-mapper.py <path> --reference radix       --output .design/audit/radix-mapping.json

# Then generate token files from each
python3 apply-value-mapping.py <path> .design/audit/catppuccin-mapping.json --include "tokens.css" --dry-run
```

### Use Cases

| Scenario | Strategy |
|----------|----------|
| Dark mode | A second `:root` set under `[data-theme="dark"]` selector — swap with JS toggle |
| Multi-brand | Different CSS files for each brand, loaded at build time |
| User customization | Expose token values in a settings panel, update CSS variables in JS |
| Seasonal/event | Replace tokens.css for holidays, promotions |

**Key insight**: Because `var()` resolves at runtime, none of these require
rebuilding the app. The same compiled JS serves different themes.

---

## Complete Skill Pipeline

```
User: "美化这个项目 → 换风格到 Tailwind 色系"

1. Load `design-sense` skill
   → Run scan: python3 scan-design-sense.py <path> [--update]

2. Load `design-audit` skill
   → Run audit: python3 audit-hardcoded-values.py <path>

3. Load `design-restyle` skill
   → Phase 1: Read audit output (agent reads files)
   → Phase 2a: Choose reference — ask user or run --list
   → Phase 2b: Run semantic-mapper.py --reference tailwind
   → Phase 2c: Review semantic-mapping-report.md, adjust if needed
   → Phase 3: Inject token infrastructure (CSS variables preferred)
   → Phase 4: Apply layer by layer (apply-value-mapping.py + agent patches)
   → Phase 5: Run verification (verify-restyle.py + build test)
   → Optional: Generate alternate styles (catppuccin/radix dark mode)
   → Report results
```

## Common Pitfalls

1. **Skipping audit.** Don't go straight to restyling — without audit data, you can't know what to change or verify completeness.
2. **Over-aggressive replacement.** `#333` in a `style={{}}` is a color; `#333` in a string like `url(#333)` is an SVG ID. Always check context.
3. **Incomplete token mapping.** If you map `#1890ff → var(--color-primary)` but miss a file, that file will have a broken-looking color. Use `--check-remaining` after each layer.
4. **Forgetting the UI library theme.** Ant Design, Element Plus, etc. have their own theme config. They use their own variable names — replace the theme config keys, not just the rendered values.
5. **Design token scope creep.** Start with colors only. Add spacing and typography in a second pass. Doing everything at once makes debugging impossible.
6. **Not committing between layers.** If Layer 4 breaks and you can't distinguish it from Layer 3 changes, you lose time reverting.

## Related Skills

- `design-audit` — Run first to get the data needed for restyling
- `design-sense` — Provides framework/component context for token injection decisions
- `requesting-code-review` — Use before merging the restyle PR
