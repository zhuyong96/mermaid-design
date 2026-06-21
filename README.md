# Mermaid Design Skills — 前端设计治理三件套

一套可组合的**前端项目设计治理管线**，从代码扫描 → 深度审计 → 系统性重构，覆盖项目生命周期中与 UI 一致性相关的全部场景。

| 技能 | 依赖 | 说明 |
|------|------|------|
| **design-sense** | 无（独立可用） | 扫描前端项目，提取设计系统参考手册 |
| **design-audit** | 无（独立可用，建议配合 design-sense）| 深度审计，找出所有硬编码视觉值及不一致 |
| **design-restyle** | **依赖 design-audit 审计结果** (`.design-audit/`) | 基于审计结果注入 Token 体系，逐层替换 |

## 快速开始

```bash
git clone https://github.com/<YOU>/mermaid-design-skills.git
```

### 在 Hermes Agent 中使用

```bash
hermes skills install ./skills/design-sense/SKILL.md
hermes skills install ./skills/design-audit/SKILL.md
hermes skills install ./skills/design-restyle/SKILL.md
```

或直接复制到 `~/.hermes/skills/`：

```bash
# Hermes Agent (local repo clone)
cp -r skills/* ~/.hermes/skills/

# Claude Code
cp -r skills/design-sense /path/to/your/project/.claude/instructions/

# Cursor
cp -r skills/design-sense /path/to/your/project/.cursor/rules/
```

或直接在对话中引用：

> "请加载 design-sense 技能，然后扫描这个前端项目"

### 前置依赖

- Python 3.8+（全部脚本使用 stdlib，零外部依赖）
- 目标前端项目（React / Vue / Svelte / Next.js / Nuxt 均可）

## 管线流程

```
新项目页面开发:        design-sense (扫描) → design-sense (构建) → 新页面代码
现有项目风格统一:      design-sense → design-audit → design-restyle → 统一后的代码
项目换主题:            design-restyle (替换 tokens.css 即可)
```

详见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

## 许可

MIT
