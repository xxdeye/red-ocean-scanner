# Red Ocean Scanner · 避红海扫描器

**An agent skill that tells you whether a product idea is worth building — before you spend a month on it.**

Most "find your niche" advice is vibes. This is a scanner: it measures real search
demand and real content supply, then returns a **red / yellow / green verdict** with
the evidence and the disqualifying signals.

Built for the **Chinese market**, where the highest-value demand data sits behind
login walls that no tool can crawl (Xiaohongshu, Douyin, WeChat Moments). It works
around that with two sources that *are* reachable — and that turn out to be enough.

[中文说明 ↓](#中文说明)

---

## The problem it solves

"When choosing what to build, **low competition is not an opportunity — it might just
mean nobody cares.**" Every rule in this repo came from a real counter-example, not theory.

The scanner exists to prevent one specific mistake: **judging a market by supply alone.**

### The counter-example that started this

`录音转文字` (audio transcription) looked like a perfect market on supply metrics:

- Only **1,000** WeChat articles — low competition
- **4** titles advertising paid/downloadable tools — demand already monetized

Any supply-only analysis says "build this." The demand side says the opposite:

```
录音转文字永久免费版            ("permanent free version")
豆包录音转文字在线免费使用       ("free use of Doubao's transcriber")
录音转文字在线免费网页版         ("free online web version")
```

Users aren't looking for a tool. **They're looking for a free replacement.** It's a
price war that already hit zero, with a big free incumbent in it. Score: 10 → 3.

---

## Install

The script is pure Python 3.8+ standard library. **No dependencies, no API keys.**

```bash
git clone https://github.com/xxdeye/red-ocean-scanner.git

# Option A — run it directly
python3 red-ocean-scanner/skills/red-ocean-scanner/red_ocean_scan.py "关键词"

# Option B — install as an agent skill
cp -r red-ocean-scanner/skills/red-ocean-scanner ~/.dsh/skills/     # DeepSeek Harness
cp -r red-ocean-scanner/skills/red-ocean-scanner ~/.claude/skills/  # Claude Code
```

## Usage

```bash
python3 red_ocean_scan.py "关键词1" "关键词2"
python3 red_ocean_scan.py --report report.md "关键词"
python3 red_ocean_scan.py --json "关键词"
```

Max ~6 keywords per run. Each keyword hits two sources; the script enforces a 6s
cooldown between them.

## Example output

```
==================================================================
🔴 录音转文字    红    3/10
==================================================================
供给  微信 1000 篇 [低]
      标题信号: 已有付费工具×4 | 教程/怎么用×2
需求  高购买意图长尾 1 条:
        ★ 录音转文字软件
      免费白嫖词 4 条: 录音转文字在线免费 / 豆包录音转文字在线免费使用
      垄断品牌: 豆包录音转文字在线免费使用
依据
      + 标题出现在售/可下载的工具 → 需求已被验证能收钱
      + 1 条高购买意图长尾，例：《录音转文字软件》
否决项
      − 4 条免费白嫖词（《录音转文字在线免费》）→ 用户要找免费替代品，不会付钱
      − 相关搜索出现垄断品牌《豆包录音转文字在线免费使用》→ 该词已被占位
下一步  放弃。不要试图靠加功能挽救一个红海方向。
```

Compare with a green light:

```
🟢 代账公司对账单    绿    8/10
供给  微信 511 篇 [低]
需求  高购买意图长尾 2 条:
        ★ 代账公司内账报价明细表
        ★ 代账公司收费价目表
依据
      + 标题以教程为主 → 需求真实但没人做出好工具，是缺口
下一步  去闲鱼搜该词，看有没有人在卖同类服务、价格、成交数。
```

## How it works

| Source | Measures | Why it's trustworthy |
|---|---|---|
| **360 Search** (`so.com`) "related searches" | **Demand** | Algorithmically generated from real query volume — a free keyword tool |
| **Sogou WeChat** (`weixin.sogou.com`) | **Supply** | Article count + title signals from the WeChat ecosystem |

Score = supply (3) + nature of supply (3) + demand (4).

### Three disqualifiers

These override the score. Each has a real case behind it.

| Disqualifier | Trigger | Real case |
|---|---|---|
| **Free-tier race** | Related searches contain 免费/破解/永久免费 | `录音转文字` — users price-shopping against free alternatives |
| **Incumbent lock-in** | A specific product name dominates (Doubao, iFlytek, Jianying…) | `试卷排版` — 3 of 9 high-intent queries were for one incumbent tool |
| **Zero moat** | Titles contain `vibecoding` / "I built this in a day" | `房贷提前还款计算器` — strong demand, but someone built it in one day |

The third is the most dangerous: **every demand signal is green, only this one is red.**

### Rate-limit safety

Sogou WeChat returns **empty pages instead of errors** when rate-limited. Naively
parsed, that reads as "0 articles" — the exact opposite of the truth. The script
retries with backoff and, if it still can't get data, returns `🟡 incomplete` and
**never a green light.**

## Limits — read this

- **Chinese market only.** The data sources are Chinese search engines. For Western
  markets, use Google Keyword Planner / Ahrefs / Reddit instead; the reasoning
  framework transfers, the script doesn't.
- **Intent data, not sales data.** The scan proves demand exists and supply is thin.
  It does **not** prove anyone has ever paid. That last step is manual: search Xianyu
  (闲鱼) for the keyword and look at actual completed sales.
- **Rate limited.** ~45s cooldown after bursts. Run few keywords at a time.
- **Not financial or legal advice.** Verify platform rules and compliance yourself.

## Repo layout

```
skills/red-ocean-scanner/
  SKILL.md              # agent skill definition (verdict rubric, workflow, blind-spot scan)
  red_ocean_scan.py     # the scanner
docs/
  实测数据-中文.md        # measured scores across 18 real keywords, with analysis
```

## License

MIT

---

# 中文说明

**一个 agent skill：在你花一个月做产品之前，先告诉你这个方向该不该做。**

市面上"找蓝海"的建议大多是感觉。这个是扫描：实测真实搜索需求和内容供给，
输出**红/黄/绿裁决**，附证据和否决项。

### 为什么需要它

**存量少不等于机会，可能只是没人关心。** 这个仓库里的每条规则都来自真实反例，
不是理论。它存在的目的是防止一个具体错误：**只看供给就下结论。**

典型反例 `录音转文字`：供给侧完美（微信仅 1000 篇、4 条付费工具信号），
但相关搜索全是《永久免费版》《豆包在线免费》——**用户不是要找工具，是要找免费替代品。**
评分从 10 掉到 3。

### 快速开始

```bash
git clone https://github.com/xxdeye/red-ocean-scanner.git
python3 red-ocean-scanner/skills/red-ocean-scanner/red_ocean_scan.py "你的关键词"
```

纯标准库，无需 `pip install`，不需要 API key。

### 三类一票否决

| 否决项 | 触发 | 真实案例 |
|---|---|---|
| **免费白嫖** | 相关搜索出现《永久免费版》《破解》 | `录音转文字` — 用户在跟免费产品比价 |
| **垄断占位** | 出现具体产品名（豆包/讯飞/鲁青…） | `试卷排版` — 9 条高意图词里 3 条指向同一产品 |
| **壁垒归零** | 标题出现 `vibecoding` /「我自己做了」 | `房贷提前还款计算器` — 需求旺，但有人一天就做出来了 |

第三条最危险：**所有需求指标都亮绿灯，只有这一个信号在报警。**

### 关键设计

**限流不会变成假结论。** 搜狗微信被限流时返回空页面而不是报错。如果直接解析，
会读成"0 篇"——**得出完全相反的结论**。脚本会退避重试，取不到就输出
`🟡 数据不完整`，**绝不给绿灯**。

### 边界（重要）

- **只适用于中文市场。** 数据源是中文搜索引擎。框架可迁移，脚本不可。
- **这是意图数据，不是成交数据。** 扫描证明"需求旺 + 供给少"，
  **不证明有人掏过钱**。最后一步必须人工：去闲鱼搜该词，看真实成交。
- 频率限制约 45 秒冷却，一次别跑太多词。

### 详细文档

- `skills/red-ocean-scanner/SKILL.md` — 完整判读规则、评分表、标准工作流、盲点清单
- `docs/实测数据-中文.md` — 18 个真实关键词的实测评分与反例分析
