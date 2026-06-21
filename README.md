# Mermaid Design — 前端设计治理三件套

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Hermes Agent](https://img.shields.io/badge/Hermes%20Agent-Skills-8A2BE2)](https://github.com/zhuyong96/mermaid-design)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue)](#)

一套面向 **Hermes Agent** 的可组合前端设计治理管线 — 从代码扫描 → 深度审计 → 系统性重构，覆盖项目生命周期中与 UI 一致性相关的全部场景。

> **适用对象：** 前端架构师、中后台开发者、维护老旧项目的工程师、引入 Design Token 体系的团队。

---

## 管线一览

| # | Skill | 做什么 | 依赖 | 产出 |
|---|-------|--------|------|------|
| 1 | **design-sense** | 扫描前端项目，提取设计系统参考手册，并基于参考构建新页面 | 无（独立可用） | `.design-system/`（7 份参考文档） |
| 2 | **design-audit** | 找出项目中**所有**硬编码视觉值及不一致，构建机器可读的映射 JSON | 建议先跑 design-sense | `.design-audit/`（6 份报告 + value-map） |
| 3 | **design-restyle** | 基于审计结果注入 Token 体系，逐层替换硬编码值，输出统一后的代码 | **依赖** design-audit 结果 | 统一后的项目代码 |

```
               ┌─────────────────────────────┐
               │     用户需求 / 问题输入        │
               └──────────┬──────────────────┘
                          │
          ┌───────────────┼───────────────────┐
          ▼               ▼                    ▼
   需要新页面       项目风格不一致         项目要换主题
  ─────────        ────────────────       ─────────────
  design-sense     design-audit           design-restyle
  (扫描+构建)       (深度审计)              (5 阶段流水线)
      │                │                      │
      ▼                ▼                      ▼
  .design-system/  .design-audit/        统一后的代码
  (设计系统参考)    (所有硬编码值)          (全部使用 token)
```

---

## 为什么需要这个？

前端项目在迭代中几乎必然发生 **风格漂移**：

- 同一个蓝色，有的地方用 `#1890ff`，有的用 `#1a90ff`、`#188fff`
- 间距随意写，没有网格约束（`10px`、`13px`、`17px` 共存）
- 字体、圆角、阴影没有统一尺度
- 新来的人不知道现有组件怎么用，凭感觉写新的

**Mermaid Design 解决的就是这个问题** — 通过自动化扫描 + AI 推理 + 逐层替换，让老旧项目在不改框架、不改依赖、不改交互的前提下，恢复设计一致性。

---

## 快速开始

### 克隆

```bash
git clone git@github.com:zhuyong96/mermaid-design.git
cd mermaid-design
```

### 安装至 Hermes Agent

```bash
# 方式一：直接安装（推荐）
hermes skills install ./skills/design-sense/SKILL.md
hermes skills install ./skills/design-audit/SKILL.md
hermes skills install ./skills/design-restyle/SKILL.md

# 方式二：复制到 skills 目录
cp -r skills/* ~/.hermes/skills/
```

### 在对话中使用

```
> 扫描这个项目，提取设计系统信息          → 自动加载 design-sense
> 检查这个项目的风格一致性问题             → design-sense → design-audit
> 把这个项目的配色换成 Tailwind 风格       → 全管线自动执行
> 在项目里新增一个文章列表页               → design-sense 扫描 + 构建
```

### 先决条件

- **Hermes Agent** 环境（CLI 或 TUI）
- **Python 3.8+**（全部脚本使用 stdlib，零外部依赖）
- 目标前端项目（React / Vue / Svelte / Next.js / Nuxt 均可）

---

## 三个 Skill 详解

### ① design-sense — 设计感知扫描

**能力：扫描 → 构建**

扫描阶段自动提取项目的**7 份设计参考文档**到 `.design-system/` 目录：

```
.design-system/
├── README.md                     # 概览
├── 01-component-libraries.md     # UI 框架 + 组件库清单
├── 02-css-strategy.md            # CSS 方案（Tailwind / CSS Modules / styled）
├── 03-design-tokens.md           # 颜色、字体、间距、阴影、圆角
├── 04-page-patterns.md           # 路由 → 组件树 + 布局骨架
├── 05-component-inventory.md     # 自定义组件 + 导入路径 + props
├── 06-code-conventions.md        # 代码规范
└── .scan-state.json              # Git HEAD 缓存（增量更新用）
```

构建阶段利用这些参考，在已有项目中生成**风格一致的新页面** — 自动匹配路由模式、组件库、Token、代码规范，零魔数。

### ② design-audit — 设计深度审计

**能力：扫描** `*.jsx`、`*.tsx`、`*.css`、`*.scss`、`*.vue`、`*.svelte` 等文件，提取**所有硬编码的视觉值**：

| 报告 | 内容 |
|------|------|
| `01-all-colors.md` | 所有颜色值 + 出现频率 + 上下文 |
| `02-all-typography.md` | 字体大小、字重、行高 |
| `03-all-spacing.md` | 外边距、内边距、间距 |
| `04-all-borders-shadows.md` | 边框宽度、圆角、阴影 |
| `05-inconsistencies.md` | 语义相同但值不同的问题（AI 分析） |
| `06-value-map.json` | 机器可读：值 → [{文件, 行号, 类型}] |

AI 代理阅读报告后，自动推断出**真正的设计系统**，输出 `synthesis-recommendations.yaml`，作为下一阶段的输入契约。

### ③ design-restyle — 系统化 UI 重构

**5 阶段流水线：**

```
Phase 1: 加载审计数据     ← 读 .design-audit/ + .design-system/
Phase 2: 语义映射         ← 选择参考设计系统（Tailwind / Radix / Ant Design 等）
Phase 3: 注入 Token 层    ← 创建 CSS 变量 / Tailwind extend / SCSS 变量
Phase 4: 逐层替换         ← CSS 文件 → 内联样式 → Tailwind 类 → SVG → 第三方主题
Phase 5: 验证             ← 构建 + 扫描 + 比对 + 报告
```

**核心设计原则：**

- **一层一 commit** — 每层验证通过才继续，出问题回滚一层
- **只改样式值** — 不改数据逻辑、依赖、框架
- **零魔法值** — 替换后所有视觉值都来自 Token 引用
- **90% 自动 + 10% 人工审查** — Semantic Mapper 做 ~90%，AI 审查剩余

---

## 使用场景

### 场景 A：新页面开发

```
用户需求 → design-sense (扫描) → design-sense (构建) → 零魔数新页面
```

### 场景 B：项目风格统一

```
design-sense (扫描) → design-audit (审计) → design-restyle (替换) → 统一后的代码
```

### 场景 C：换肤 / 品牌升级

```
Token 注入完成后，只需替换 tokens.css 中的值，无需重新构建。
还支持 [data-theme="dark"] 暗色模式、多品牌色系同时管理。
```

### 场景 D：持续治理

```
Cron 定时扫描 + Git hook 后自动增量扫描 + 按需审计 = 常看常新的设计系统
```

---

## 项目结构

```
mermaid-design/
├── ARCHITECTURE.md                       # 完整架构文档（深）
├── README.md                             # 本文件（上手指南）
├── LICENSE                               # MIT
├── .gitignore
│
└── skills/
    ├── design-sense/
    │   ├── SKILL.md                      # Skill 定义 + 完整流程
    │   └── scripts/
    │       └── scan-design-system.py      # 扫描脚本（stdlib only）
    │
    ├── design-audit/
    │   ├── SKILL.md                      # Skill 定义 + 完整流程
    │   ├── scripts/
    │   │   └── audit-hardcoded-values.py  # 深度审计脚本
    │   └── references/
    │       └── source-vs-build-gap.md     # 扫描盲区说明（Tailwind 等）
    │
    └── design-restyle/
        ├── SKILL.md                      # Skill 定义 + 完整 5 阶段流程
        ├── scripts/
        │   ├── semantic-mapper.py         # 语义映射（旧值 → 语义角色 → 新值）
        │   ├── apply-value-mapping.py     # 批量替换执行
        │   ├── verify-restyle.py          # 验证脚本
        │   └── references/
        │       └── default.json           # 参考设计系统预设（5 套）
        └── templates/                     # （预留）CSS 变量模板
```

---

## 路线图

- [x] 核心三件套发布（v1.0.0）
- [ ] Tailwind utility class 反编译支持（build 输出交叉分析）
- [ ] 暗色模式自动生成（从 tokens.css 推导 dark 变体）
- [ ] 多项目统管（Monorepo 下跨子项目扫描与对齐）
- [ ] 设计变更 PR 自动生成（GitHub Actions 集成）
- [ ] Figma Token 导入兼容（W3C DTCG 格式）

---

## 许可

MIT © 2026 AlpineCurator

---

## 相关文档

- [ARCHITECTURE.md](./ARCHITECTURE.md) — 完整架构说明、每个 Skill 的详细工作机制、FAQ
- 每个 Skill 的 `SKILL.md` 文件包含完整的触发条件、参数、安全措施和回滚策略
- `design-audit/references/source-vs-build-gap.md` — 解析 Tailwind 等构建工具的盲区与解决方案
