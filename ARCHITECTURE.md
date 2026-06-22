# Hermes 前端设计三件套：Skill 说明文档

## 概述

三个 skill 构成一套完整的**前端项目设计治理管线**，从代码扫描 → 深度审计 → 系统性改造，覆盖项目生命周期中与 UI 一致性相关的全部场景。

```
                           ┌─────────────────────────────┐
                           │     用户需求 / 问题输入        │
                           └──────────┬──────────────────┘
                                      │
                    ┌─────────────────┼────────────────────┐
                    ▼                 ▼                     ▼
           需要新页面          项目风格不一致          项目要换主题
         ───────────        ────────────────        ─────────────
          design-sense      design-audit            design-restyle
            (扫描+构建)        (深度审计)              (系统改造)
                │                 │                      │
                ▼                 ▼                      ▼
        .design/sense/    .design/audit/         统一后的代码
        (设计系统参考)       (所有硬编码值)          (全部使用 token)
```

---

## Skill 1: design-sense — 设计感知扫描

### 解决什么问题

- **新接手一个前端项目**，需要快速理解它的组件库、CSS 策略、设计 token、页面模式
- **要在已有项目里新增页面**，但不知道现有组件怎么用、token 是什么、风格怎么保持
- **团队协作中风格漂移**，需要一份自动生成的"设计系统参考手册"

### 工作机制

**两步走：Scan → Build**

#### Step 1: Scan 扫描

```
用户说"扫描项目"
  → 自动加载 skill
  → 运行 scan-design-sense.py <project-path>
  → 生成 .design/sense/ 目录 (7 个参考文件)
```

输出目录结构：

```
.design/sense/
├── README.md                     # 概览
├── 01-component-libraries.md     # UI 框架 + 组件库
├── 02-css-strategy.md            # CSS 方案 (Tailwind / CSS Modules / styled)
├── 03-design-tokens.md           # 颜色、字体、间距、阴影、圆角
├── 04-page-patterns.md           # 路由 → 组件树 + 布局骨架
├── 05-component-inventory.md     # 自定义组件列表 + 导入路径 + props
├── 06-code-conventions.md        # 代码规范
└── .scan-state.json              # Git HEAD 缓存 (用于增量更新)
```

#### Step 2: Build 构建

```
用户说"在项目里新增一个文章列表页"
  → 自动检查 .design/sense/ 是否最新 (--update)
  → 读取 7 个参考文件
  → 分类页面类型 (列表/详情/表单/看板/标签页)
  → 寻找最相似的已有页面作为模板
  → 按组件库、设计 token、代码规范生成新页面代码
  → 验证：零魔数颜色、间距符合网格、导入路径正确
```

### 触发机制

| 触发方式 | 说明 |
|----------|------|
| **手动命令** | 用户说"扫描项目"、"分析这个项目"、"看看项目用了什么" |
| **构建前自动** | Build 前自动执行 `--update` 检查，有变更则重新扫描 |
| **Cron 定时** | 可配置每周扫描，自动检测设计系统变更 |
| **Git hook** | 团队场景下 `post-merge` 钩子自动增量扫描 |

### 与其他 skill 的关系

**管线中的角色：第一环。** 提供框架/组件/Token 上下文，供 design-audit 和 design-restyle 使用。

---

## Skill 2: design-audit — 设计深度审计

### 解决什么问题

- **项目看起来颜色不一致**，有的按钮用 #1890ff，有的用 #1a90ff
- **即将进行视觉改造**，需要知道"到底有多少个位置用了这些颜色/间距/字体"
- **想迁移到设计 token 体系**，但不知道哪些值是硬编码的、在哪里
- **设计师说"这个蓝色不对"**，你不知道它出现了多少次、影响多大

### 工作机制

```
用户说"审计这个项目"
  → 确保 design-sense scan 已完成 (获取框架上下文)
  → 运行 audit-hardcoded-values.py <project-path>
  → 生成 .design/audit/ 目录 (6 个报告 + value-map.json)
  → 代理分析报告 → 推断"真正的设计系统" → 输出改造建议
```

输出目录结构：

```
.design/audit/
├── README.md                       # 概览：文件数、值数、问题汇总
├── 01-all-colors.md                # 所有颜色值 + 出现频率 + 上下文
├── 02-all-typography.md            # 字体大小、字重、行高
├── 03-all-spacing.md               # 外边距、内边距、间距 (px/rem)
├── 04-all-borders-shadows.md       # 边框宽度、圆角、阴影
├── 05-inconsistencies.md           # 语义相同但值不同的问题 (AI 分析)
├── 06-value-map.json               # 机器可读：值 → [{文件, 行号, 上下文}]
└── .audit-state.json               # Git HEAD 缓存 (用于增量更新)
```

### 扫描能力

| 文件类型 | 能提取什么 |
|----------|-----------|
| `*.css/.scss/.less` | 硬编码颜色、尺寸、圆角、阴影、字体 |
| `*.jsx/.tsx` | `style={{...}}` 内联样式、styled-components |
| `*.vue` | `<style>` 块、`:style` 绑定 |
| `*.svelte/.html` | 内联样式、style 标签 |
| `tailwind.config.*` | 已注册的主题 token (用于交叉引用) |

**注意**：Tailwind utility class（如 `text-blue-500`）对扫描器不可见，需要配合 build 输出分析。

### 触发机制

| 触发方式 | 说明 |
|----------|------|
| **手动命令** | 用户说"审计这个项目"、"检查代码风格一致性问题" |
| **restyle 前置** | design-restyle 自动触发 audit 的 `--update` |
| **定时巡检** | 配置 Cron 定期审计，跟踪一致性趋势 |

### 关键输出：AI 推理

代理读完审计报告后，会自动生成 `synthesis-recommendations.yaml`，包含：

```yaml
target_tokens:
  colors:
    primary: { value: "#1890ff", replaces: ["#1890ff", "#1a90ff", "#188fff"] }
    text-primary: { value: "#1a1a1a", replaces: ["#1a1a1a", "#333"] }
    bg-page: { value: "#f5f5f5" }
  spacing:
    grid: 4
  typography:
    font-family: "-apple-system, BlinkMacSystemFont, ..."
```

这个 YAML 文件就是 **design-restyle 的输入契约**。

### 与其他 skill 的关系

**管线中的角色：中间环节。** 上游依赖 design-sense（框架上下文），输出供 design-restyle 消费。

---

## Skill 3: design-restyle — 系统化 UI 重构

### 解决什么问题

- **项目颜色不统一**，要把所有 #1890ff 统一到一个 token
- **要把整个项目的配色方案换掉**，比如从自定色系换成 Tailwind/Tailwind
- **现有代码有几百个硬编码视觉值**，不可能手动改
- **想建立设计 token 体系**，为以后换主题、暗色模式铺路

### 工作机制：5 阶段流水线

```
Phase 1: 加载审计数据    ← 读 .design/audit/ + .design/sense/
Phase 2: 语义映射        ← AI 推断语义角色 → 映射到参考设计系统
Phase 3: 注入 Token 层   ← 创建 CSS 变量 / Tailwind 扩展 / SCSS 变量
Phase 4: 逐层应用        ← 从 CSS 到内联样式到 SVG，逐层替换
Phase 5: 验证            ← 扫描、构建、对比、报告
```

#### Phase 1: 加载审计数据

自动读取 `.design/audit/` 和 `.design/sense/`，明确：

- 项目框架和 CSS 策略
- 颜色调色板（按频率排序）
- 间距网格
- 字体使用情况
- 已知不一致

#### Phase 2: 参考 → 语义映射（核心创新）

**核心思想**：不是把旧值映射到出现最多的旧值（只会让丑陋一致化），而是：

```
旧: #1890ff (47x, background)   旧: #f5f5f5 (32x, background)
  → 角色: bg-card                  → 角色: bg-page
  → 映射到 tailwind/primary        → 映射到 tailwind/bg-page
  → 新值: #3b82f6                  → 新值: #f9fafb
```

参考预设：

| 预设 | 适用场景 |
|------|----------|
| **tailwind** | 通用 Web 应用，安全专业 |
| **radix** | 无障碍优先，感知均匀色阶 |
| **shadcn** | 现代极简，CSS 变量原生 |
| **antd** | 中文企业级，后台/中台 |
| **catppuccin** | 创意/个性化，温暖潮流 |

运行脚本自动生成 `semantic-mapping.json`，AI 审查调整后进入下一步。

#### Phase 3: 注入 Token 层

根据项目的 CSS 策略，选择注入方式：

| 策略 | 做法 |
|------|------|
| Tailwind | `theme.extend`，添加自定义色/字号/间距/圆角 |
| CSS 变量 | 创建 `tokens.css`，`:root { --color-primary: ... }` |
| SCSS | 创建 `_tokens.scss` |
| CSS-in-JS | 创建 `tokens.ts` 主题对象 |

**关键规则**：新建文件不修改已有 token 文件，方便回滚。

#### Phase 4: 逐层应用

```
Layer 1: Token 文件本身
Layer 2: 全局 CSS / App.css
Layer 3: 组件 CSS 文件
Layer 4: JSX/TSX 内联样式
Layer 5: styled-components / CSS-in-JS
Layer 6: Tailwind className 字符串
Layer 7: SVG 颜色 (fill/stroke)
Layer 8: 第三方 UI 库主题覆盖
```

每条规则：**一层一 commit，确保可回滚**。

#### Phase 5: 验证

- ✅ 项目仍然能构建
- ✅ 零旧颜色残留（扫描检查）
- ✅ 间距符合目标网格
- ✅ 字体来自目标量表
- ✅ 圆角最多 3 个值
- ✅ 所有视觉值都是 token 引用（没有魔数）

### 触发机制

| 触发方式 | 说明 |
|----------|------|
| **手动命令** | 用户说"美化这个项目"、"换风格"、"统一配色" |
| **管线自动** | 自动触发 design-sense scan --update + design-audit --update |
| **多风格切换** | CSS 变量注入后，切换主题只需替换 tokens.css |

### 安全措施

- **逐层 commit**：每层验证通过后提交，出问题回滚一层
- **预处理读**：Semantic Mapper 做 ~90% 正确，AI 审查调整剩余 10%
- **零交互改动**：只改样式值，不改数据逻辑、依赖、框架

### 与其他 skill 的关系

**管线中的角色：最终执行者。** 上游依赖 design-audit（数据输入）和 design-sense（框架上下文）。

---

## 完整管线流程

### 场景 A：新页面开发

```
用户需求 → design-sense (扫描) → design-sense (构建) → 新页面代码
```

### 场景 B：项目风格统一 / 配色美化

```
用户需求
  → design-sense (扫描)                   获取框架/组件/token上下文
  → design-audit (审计)                   找出所有硬编码值 + 不一致
  → design-restyle Phase 1 (加载)         读取审计结果
  → design-restyle Phase 2 (语义映射)      选择参考风格 → 生成映射
  → design-restyle Phase 3 (注入 Token)   创建 tokens.css
  → design-restyle Phase 4 (逐层应用)     替换数百个硬编码值
  → design-restyle Phase 5 (验证)         构建 + 扫描 + 报告
```

### 场景 C：项目换主题

```
CSS 变量注入完成后
  → 只需替换 tokens.css 中的值
  → 或添加 [data-theme="dark"] 选择器
  → 或加载不同的 tokens.css 实现换肤
  → 无需重新构建
```

---

## Skill 目录结构

```
~/.hermes/skills/software-development/
├── design-sense/
│   ├── SKILL.md                          # Skill 定义 + 完整流程
│   └── scripts/
│       └── scan-design-sense.py          # 扫描脚本
│
├── design-audit/
│   ├── SKILL.md                          # Skill 定义 + 完整流程
│   ├── scripts/
│   │   ├── audit-hardcoded-values.py      # 深度审计脚本
│   │   └── __pycache__/                   # Python 缓存
│   └── references/
│       └── source-vs-build-gap.md         # 扫描盲区说明文档
│
└── design-restyle/
    ├── SKILL.md                          # Skill 定义 + 完整流程
    └── scripts/
        ├── semantic-mapper.py             # 语义映射脚本
        ├── apply-value-mapping.py         # 应用值映射脚本
        ├── verify-restyle.py              # 验证脚本
        └── references/
            └── default.json               # 参考设计系统预设
```

---

## 常见问题

### Q1: 三个 skill 必须一起用吗？

**不需要。** 它们是*可组合的管线*，不是耦合的。

- **只需要扫描？** 只用 `design-sense scan`
- **只需要审计？** `design-sense scan` → `design-audit`
- **只需要改风格？** 三个全走

### Q2: 支持哪些框架？

React / Vue / Next.js / Nuxt / Svelte 都支持。扫描器按文件类型工作，不依赖特定框架。

### Q3: 每次改颜色都要跑全流程吗？

前两次需要全跑，之后用 `--update` 只检变更部分。如果没有变更，2ms 就退出。

### Q4: 会改坏代码吗？

- 一层一 commit，每层验证通过才继续
- 只改样式值，不改逻辑/交互/依赖
- 第三方 UI 库有独立覆盖机制
- Semantic Mapper 输出可 AI 审查，确认后再执行替换

### Q5: Tailwind 项目适配吗？

适配，但有盲区：`text-blue-500` 在源代码中没有 hex 值，扫描器不解析 Tailwind utility classes。建议结合 build 输出交叉检查，详见 design-audit 的 `references/source-vs-build-gap.md`。
