# Red Ocean Scanner · 避红海扫描器

**An agent skill that tells you whether a product idea is worth building — before you spend a month on it.**

Most "find your niche" advice is vibes. This is a scanner: it measures real supply
and demand signals, then returns a **red / yellow / green verdict** with the evidence
and the disqualifying signals.

**Works for both global and Chinese markets** — with separate engines, because the
reliable signals are completely different in each.

[中文说明 ↓](#中文说明)

---

## The problem it solves

"Low competition is not an opportunity — **it might just mean nobody cares.**"
Every rule here came from a real counter-example, not theory.

The scanner exists to prevent one specific mistake: **judging a market by supply alone.**

### The counter-example that started this

`录音转文字` (audio transcription) looked perfect on supply metrics:

- Only **1,000** WeChat articles — thin competition
- **4** titles advertising paid/downloadable tools — demand already monetized

Any supply-only analysis says "build this." The demand side says the opposite:

```
录音转文字永久免费版            ("permanent free version")
豆包录音转文字在线免费使用       ("free use of Doubao's transcriber")
录音转文字在线免费网页版         ("free online web version")
```

Users aren't looking for a tool. **They're looking for a free replacement.** It's a
price war that already hit zero, with a big free incumbent in it. Score: 10 → 3.

## Two engines, because one doesn't fit both markets

| Engine | Market | Reliable signals | Viewpoint |
|---|---|---|---|
| `global` | Global / English | App Store ratings (consumer) + GitHub repo density (developer) + Google/Bing autocomplete (demand) | All three market types |
| `cn` | Chinese | WeChat article density + 360 related searches | Search intent |

The global engine auto-detects whether a direction is **consumer** or **B2B**,
because the criteria differ — App Store ratings are meaningless for B2B. Override
with `--market consumer|business`.

Merging them into one parameter would produce a tool that's wrong for both.

## Install

Pure Python 3.8+ standard library. **No dependencies, no API keys.**

```bash
git clone https://github.com/xxdeye/red-ocean-scanner.git

# Option A — run directly
python3 red-ocean-scanner/skills/red-ocean-scanner/scan.py -e global "your keyword"

# Option B — install as an agent skill
cp -r red-ocean-scanner/skills/red-ocean-scanner ~/.claude/skills/   # Claude Code
cp -r red-ocean-scanner/skills/red-ocean-scanner ~/.dsh/skills/      # DeepSeek Harness
```

## Usage

```bash
cd skills/red-ocean-scanner

# Global market
python3 scan.py --engine global "veterinary clinic software"

# Chinese market
python3 scan.py --engine cn "代账公司对账单"

# Same keywords, both markets
python3 scan.py --engine both "invoice excel"

# JSON output
python3 scan.py --engine global --json "habit tracker"
```

The unified entry point routes to the right engine — **always prefer `scan.py`** over
calling the engine scripts directly.

### Speed it up with a GitHub token (optional)

The global engine hits GitHub's search API, which allows **10 requests/min
unauthenticated but 30/min with a token**. The scanner detects a token
automatically and cuts the cooldown from 22s to 7s per keyword — no config needed:

```bash
export GITHUB_TOKEN=ghp_your_token_here   # or GH_TOKEN
python3 scan.py -e global "keyword1" "keyword2" "keyword3"
```

Without a token it still works, just slower. The Chinese engine is unaffected.

## Example output

**Global engine** — consumer red ocean with an unbeatable incumbent:

```
🔴 receipt scanner    红    5/10   [global · 消费级市场]
消费  App Store 22 款，头部 7,642,608 条评价，均分 4.72
        7,642,608 评 ★4.9  Fetch: Receipts for Gift Cards
        1,360,696 评 ★4.9  Scanner App: Genius Scan
开发  GitHub 1,400 仓库 [低]，头部 312★
否决项
      − App Store 头部 7,642,608 条评价 → 已有不可撼动的既得利益者，且是免费产品
```

Note the score is 5/10 but the verdict is **red**. That is deliberate: a blocker
overrides the score, because a 7.6M-review free incumbent cannot be offset by good
numbers elsewhere. Verdict precedence is `incomplete data > blocker > score`.

**Global engine** — a genuine gap:

```
🟢 veterinary clinic scheduling    绿    9/10   [global]
供给  GitHub 117 仓库 [极低]，头部 13★
            10★ Rubel011/Vetspot_veterinary-clinic_website — The Veterinary System…
            13★ blingyplus/Vet-Management-System — A comprehensive veterinary hosp…
依据
      + GitHub 仅 117 个仓库 → 开发者生态几乎没有覆盖
      + 头部仅 13★ → 没有赢家。需求存在但没人做好，缺口的典型形态
下一步  GitHub 供给稀薄只证明没人做，不证明有人买。去该行业的垂直社区读真实抱怨。
```

**Global engine** — saturated:

```
🔴 todo list app    红    2/10   [global]
供给  GitHub 90582 仓库 [红海]，头部 2121★
否决项
      − 头部仓库 2121★ → 已有成熟开源替代品
      − 仓库数达五位数 → 红海，不要靠加功能挽救
```

**Chinese engine** — free-tier race:

```
🔴 录音转文字    红    3/10
需求  高购买意图长尾 1 条: ★ 录音转文字软件
      免费白嫖词 4 条: 录音转文字在线免费 / 豆包录音转文字在线免费使用
否决项
      − 4 条免费白嫖词 → 用户要找免费替代品，不会付钱
      − 相关搜索出现垄断品牌《豆包录音转文字在线免费使用》→ 该词已被占位
```

## A correction worth documenting

An earlier version of this tool claimed Google, Wikipedia, and DuckDuckGo were
unreachable, and deliberately excluded them. **That was wrong.**

The cause: connectivity was tested with Node's `fetch`, and Node on that machine
resolves DNS abnormally — every request returned `CONNECT_TIMEOUT`. Re-tested with
Python `urllib` (the runtime these scripts actually use):

| Source | curl | Python urllib | Node fetch |
|---|---|---|---|
| google.com | ✅ 200 | ✅ 200 | ❌ timeout |
| en.wikipedia.org | ✅ 200 | ✅ 200 | ❌ timeout |
| html.duckduckgo.com | ✅ 200 | ✅ 200 | ❌ timeout |
| www.reddit.com | — | ⚠️ 403 | ❌ timeout |

Google autocomplete, the App Store API, and DuckDuckGo search are now wired in —
which is what made consumer-market assessment possible at all.

**The lesson: verify reachability with the runtime you actually ship, not with a
different HTTP client.**

## How scoring works

Score = supply scarcity + incumbent strength + distribution channel.

**Only reliable signals are scored.** Measured signal quality:

| Signal | Engine | Measured discrimination |
|---|---|---|
| GitHub repo count | global | **4000x range**: todo app 90,582 → vet scheduling 117 |
| Top repo stars | global | 14,139★ (habit tracker, red ocean) → 2★ (funeral homes, gap) |
| WeChat article count | cn | 8,580 (red ocean) → 511 (gap) |
| 360 related searches | cn | Real query behavior; high-intent terms are countable |

### Signals we deliberately stopped using

| Signal | Why it's unusable |
|---|---|
| **StackOverflow search** | Fuzzy matching, heavy noise. `invoice excel` matched an Automapper question; `funeral home management` matched a UIPickerView question |
| **npm / PyPI search** | Also fuzzy. `sports team scheduling` returns 52,825 packages |
| GitHub issues | Mixed bug reports and feature requests — needs human reading |

**Design principle: better to miss a signal than to be wrong about one.**
A tool that gives a false green light is worse than no tool. So noisy signals are
demoted to "reference only" and never scored.

### Calibration anchors

**Global** (measured):

| Direction | Repos | Top ★ | Score | Verdict |
|---|---|---|---|---|
| funeral home management | 23 | 2 | 9 | 🟢 |
| veterinary clinic scheduling | 117 | 13 | 9 | 🟢 |
| invoice excel | 2,262 | 411 | 5 | 🟡 |
| habit tracker | 60,479 | 14,139 | 2 | 🔴 |
| todo list app | 90,582 | 2,121 | 2 | 🔴 |

**Chinese** (measured): see [`docs/实测数据-中文.md`](docs/实测数据-中文.md).

## Limits — read this

- **B2B markets are only weakly assessed.** App Store rating counts are
  meaningless for B2B (business buyers rarely review: a B2B vet app tops out at
  40k ratings vs 7.6M for a consumer receipt app), and G2/Capterra are
  Cloudflare-blocked. The scanner labels this limitation rather than inventing a
  score.
- **Reddit, Product Hunt, G2, Capterra, AlternativeTo return HTTP 403** — platform
  blocks, not network issues. They need official API keys or paid data.
- **Intent data, not sales data.** The scan proves supply is thin. It does **not**
  prove anyone has ever paid. That last step is manual and mandatory: Chinese market
  → search Xianyu (闲鱼) for real completed sales; global market → check pricing
  pages and review sites.
- **Rate limited.** GitHub search ≈10 req/min unauthenticated, 30/min with a
  token (set `GITHUB_TOKEN` to speed up ~3x); Sogou WeChat ≈45s recovery.
  Run few keywords at a time.
- **Fuzzy search is fuzzy.** Ambiguous keywords produce garbage in any search API.
  Use specific multi-word phrases (`veterinary clinic scheduling`, not `scheduling`).
- Not financial or legal advice.

## Repo layout

```
skills/red-ocean-scanner/
  SKILL.md              # agent skill: verdict rubric, signal taxonomy, workflows
  scan.py               # unified entry point (routes by market)
  global_scan.py        # global/English engine
  red_ocean_scan.py     # Chinese market engine
docs/
  实测数据-中文.md        # measured scores across 18 real Chinese keywords
```

## License

MIT

---

# 中文说明

**一个 agent skill：在你花一个月做产品之前，先告诉你这个方向该不该做。**

市面上"找蓝海"的建议大多是感觉。这个是扫描：实测真实供给与需求信号，
输出**红/黄/绿裁决**，附证据和否决项。

**同时支持全球市场与中文市场**，用两个独立引擎——因为两个市场的可靠信号
完全不同，合并会得到一个两边都不准的工具。

## 为什么需要它

**存量少不等于机会，可能只是没人关心。** 这个仓库里的每条规则都来自真实反例。

典型反例 `录音转文字`：供给侧完美（微信仅 1000 篇、4 条付费工具信号），
但相关搜索全是《永久免费版》《豆包在线免费》——**用户不是要找工具，是要找免费替代品。**
评分从 10 掉到 3。

## 快速开始

```bash
cd skills/red-ocean-scanner

export GITHUB_TOKEN=ghp_xxx                                   # 可选，提速 3 倍
python3 scan.py --engine global "veterinary clinic software"   # 全球市场
python3 scan.py --engine cn     "代账公司对账单"                  # 中文市场
python3 scan.py --engine both   "invoice excel"                 # 双市场对比
```

纯标准库，无需 `pip install`，不需要 API key。

## 两个引擎

| 引擎 | 市场 | 可靠信号 | 视角 |
|---|---|---|---|
| `global` | 全球/英文 | GitHub 仓库密度 + star 分布 | 开发者生态 |
| `cn` | 中文 | 微信内容存量 + 360 相关搜索 | 搜索意图 |

## 核心方法论：信号可靠性分级

**只有可靠信号计入评分**，噪声信号降级为参考：

| 信号 | 区分度（实测） |
|---|---|
| ✅ GitHub 仓库数 | **4000 倍量级**：todo app 90,582 vs 兽医排班 117 |
| ✅ 头部仓库 star | 14,139★（红海）vs 2★（缺口） |
| ✅ 微信内容存量 | 8,580（红海）vs 511（缺口） |
| ✅ 360 相关搜索词 | 真实搜索行为，可数 |
| ❌ StackOverflow | 模糊匹配噪声极大：`invoice excel` 匹配到 Automapper 问题 |
| ❌ npm / PyPI 搜索 | 同样模糊：`sports team scheduling` 返回 52,825 个包 |

**设计原则：宁可漏判，不可误判。** 一个会给出错误绿灯的工具，比没有工具更糟。

## 校准锚点（实测）

**全球**：殡葬管理 23 仓库/2★ → 🟢9；兽医排班 117/13★ → 🟢9；
发票 Excel 2,262/411★ → 🟡5；习惯打卡 60,479/14,139★ → 🔴2；
待办清单 90,582/2,121★ → 🔴2。

**中文**：见 `docs/实测数据-中文.md`。

## 边界（重要）

- **看不到消费级市场。** Google、Reddit、Product Hunt、G2 在本环境全部不可达。
  两个引擎都是开发者/搜索生态视角。遇到消费类方向，工具会**主动说明局限**，
  而不是硬给一个绿灯。
- **这是意图数据，不是成交数据。** 扫描证明"供给稀薄"，
  **不证明有人掏过钱**。最后一步必须人工：中文看闲鱼真实成交，全球看定价页与评测站。
- 有频率限制，一次别跑太多词。

## 详细文档

- `skills/red-ocean-scanner/SKILL.md` — 完整判读规则、信号分级、双引擎工作流、盲点清单
- `docs/实测数据-中文.md` — 18 个中文关键词的实测评分与反例分析
