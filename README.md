# Red Ocean Scanner

**English** · [中文](README.zh.md)

**An agent skill that tells you whether a product idea is worth building — before you spend a month on it.**

Most "find your niche" advice is vibes. This is a scanner: it measures real supply
and demand signals, then returns a **red / yellow / green verdict** with the evidence
and the disqualifying signals.

**Works for both global and Chinese markets** — with separate engines, because the
reliable signals are completely different in each.


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

---

## How to actually use this to avoid red oceans

This is the part that matters. Three tools, used in order.

### The one rule that changes everything

**A red ocean is a property of a *word*, not of a *need*.**

`invoice app` → 17,249 GitHub repos (bloodbath).
`invoice export` → 1,826 repos. Same need. One-tenth the battlefield.

So don't ask *"is this market saturated?"* Ask *"is this keyword saturated?"*
Then change the keyword.

### Step 1 — Find the narrow gate (`--mode ladder`)

Feed it your broad idea. It generates narrower variants two ways: modifier
templates (`for teachers`, `template`, `export`) and — more valuable — **real
autocomplete queries**, which are narrow gates that provably exist.

```bash
cd skills/red-ocean-scanner
python3 scan.py --mode ladder "invoice" --limit 8
```

Real output:

```
原词：145,975 个 GitHub 仓库 [红海]（测了 8/8 个变体）

变体                                          仓库数  档位    比原词窄
invoice for nonprofits                            3  极低  48658.3x
invoice for teachers                             22  极低   6635.2x
invoice for landlords                            24  极低   6082.3x
invoice for clinics                              92  极低   1586.7x
invoice for contractors                         172  极低    848.7x
```

**Read it like this:** the broad word is a red ocean; the narrow gates are not.
That 48,658x is not a typo — it's the difference between "an invoicing app" and
"invoicing for nonprofits."

Cost: ~12s per variant (GitHub rate limit). Cap it with `--limit`.

### Step 2 — Get a verdict on your top 2–3 gates (`scan.py`)

```bash
python3 scan.py -e global "invoice for nonprofits"
```

The global engine measures three independent things:

| Signal | Source | What it catches |
|---|---|---|
| Consumer supply | App Store rating counts | A free incumbent with 7.6M reviews |
| Developer supply | GitHub repo count + stars | 90,000 repos and a 14k-star leader |
| Demand | Google + Bing + DDG autocomplete | Whether anyone is searching at all |

**Blockers override the score.** A direction with a 7.6M-review free competitor
is red even if everything else looks good — verdict precedence is
`incomplete data > blocker > score`.

### Step 3 — Check geographic arbitrage (`--mode geo`)

Same need, different country, completely different competition. Measured:

| Region | `invoice` top app | `receipt scanner` top app |
|---|---|---|
| US | 265,331 ratings | 7,642,608 |
| China | **193** | 18,311 |
| Brazil | 3,458 | 47,821 |

```bash
python3 scan.py --mode geo "receipt scanner" --regions us,gb,de,jp,cn,br
```

**Critical detail: it normalizes against each region's own app ecosystem.**
Absolute numbers lie in both directions — they make a normal category in a small
market look like an opportunity, and a genuine gap in a big market look like no
market at all. The tool divides by a local baseline (top apps in that region).

This caught a real false positive during development: `todo list app` in Brazil
looked like a 29x arbitrage on raw numbers, but Brazil's top todo app has 34,919
ratings — a served market. Normalized, the gap is 14x, not 29x.

**Then ask why the gap exists.** The barrier *is* the reason it's unclaimed, and
it's also your cost of entry: language, payments, tax rules, local channels.

### Step 4 — Verify someone actually pays (manual, non-negotiable)

Every step above measures **intent**, not **money**. Do not skip this:

- **Chinese market** → search Xianyu (闲鱼) for the keyword. Real completed sales.
- **Global market** → check pricing pages and review sites. A paid tier with
  customers is the proof.

Someone selling with real sales → build. Nobody selling → suspicion, not
opportunity.

### Worked example

Starting from a deliberately terrible idea: *"I'll build an invoicing app."*

```
1. scan.py --mode ladder "invoice"
   → 145,975 repos. Red ocean. But "invoice for nonprofits" = 3 repos.

2. scan.py --engine global "invoice for nonprofits"
   → check App Store + GitHub + demand. (Do not skip — 3 repos
     could mean "untapped" or "nobody wants this.")

3. scan.py --mode geo "invoice"
   → US saturated (265k), China 193. If you can serve China, the
     barrier is localization — know what it costs before you commit.

4. Xianyu / pricing pages
   → is anyone paying for nonprofit invoicing? This is the only step
     that proves money changes hands.
```

### What each tool answers

| Question | Command |
|---|---|
| Is this word a red ocean? | `scan.py` (default mode) |
| What's a narrower word that isn't? | `scan.py --mode ladder` |
| Where in the world is it not saturated? | `scan.py --mode geo` |
| Will anyone pay? | You. Manually. |

All three run through one entry point:

```bash
python3 scan.py --mode scan   --engine global "invoice for nonprofits"
python3 scan.py --mode ladder "invoice" --limit 8
python3 scan.py --mode geo    "receipt scanner" --regions us,cn,br
```

Argument convention: dispatcher options go **before** the keyword, target-script
options go **after** it.

### The traps this will not save you from

- **"Nobody's doing it" usually means nobody wants it.** Low supply is not
  evidence of demand. That's why demand is measured separately.
- **Zero results is not a gap.** A keyword with 0 repos is a term nobody uses.
  The ladder filters these out for that reason.
- **Narrow ≠ viable.** A gate with 3 repos might be 3 repos because the market is
  3 people. Always run step 2 and step 4.
- **A gap can be a moat you can't cross.** If the US is saturated and China isn't,
  the reason might be regulation you can't satisfy.
- **This tool sees English and Chinese only.** Other language markets are invisible
  to it, and that is itself an unexplored direction.

---

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

Sample runs below. Counts drift with the data; the *verdicts* are stable because
they follow structure. Exact anchors are in
[`references/calibration.md`](skills/red-ocean-scanner/references/calibration.md).

**Consumer red ocean with an unbeatable incumbent:**

```
红  receipt scanner    6/10   [global · 消费级市场]
裁决  需求旺但供给厚 → 已被认领（主因：消费供给）
      供给薄度 33%（越高越没人做）   需求强度 100%（越高越有人要）
需求  自动补全 17 条（google:10 bing:7 ddg:0），商业意图 6 条
消费  App Store 22 款，头部 7,642,608 条评价，均分 4.72
        7,642,608 评 ★4.9  Fetch: Receipts for Gift Cards
        1,360,696 评 ★4.9  Scanner App: Genius Scan
开发  GitHub 1,399 仓库 [低]，头部 312★
```

Note the score is 6/10 yet the verdict is **red**. That is deliberate: the matrix
plus the blocker decide, not the number. A free incumbent with 7.6M ratings
cannot be offset by decent numbers elsewhere.

**A genuine gap:**

```
绿(覆盖度低)  vet clinic software    10/10   [global · B2B市场]
裁决  供给稀薄 + 需求存在（**但这不等于蓝海**，见下方护城河追问）；仅测到 2 个维度
需求  自动补全 11 条（google:0 bing:11 ddg:0），商业意图 11 条
消费  App Store 23 款，头部 40,320 条评价，均分 4.45
开发  GitHub 70 仓库 [极低]，头部 13★
依据
      + GitHub 仅 70 仓库 → 开发者侧几乎无人做
      + 11 条商业意图补全词，例《vet clinic software pricing》
护城河追问（工具测不到，必须你自己答）
      绿灯只说明「供给薄 + 有需求」，不说明你守得住。
      追问一句：10 个人下周抄我，我靠什么还活着？
```

The bracketed numbers are **per-source contribution counts** — read them before the
verdict. A source showing 0 is more often a fetch failure than an absence of
suggestions, and the query echo itself is not counted as commercial intent.

`(覆盖度低)` is honest labelling, not a defect: B2B directions have no App Store
criterion, so only 2 dimensions are measurable.

**Chinese engine — a free-tier race:**

```
红  录音转文字    3/10
供给  微信 1000 篇 [低]
      标题信号: 已有付费工具×5 | 教程/怎么用×2
需求  高购买意图长尾 1 条: ★ 录音转文字软件
      免费白嫖词 5 条: 录音转文字在线免费 / 豆包录音转文字在线免费使用
      垄断品牌: 豆包录音转文字在线免费使用
否决项
      − 5 条免费白嫖词 → 用户要找免费替代品，不会付钱
      − 相关搜索出现垄断品牌 → 该词已被占位
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

The verdict comes from a **supply × demand matrix**, not a single blended score.
Supply and demand answer different questions, and averaging them merges two
opposite dead ends into one middle number:

|  | Strong demand | Weak demand |
|---|---|---|
| **Thin supply** | 🟢 **Opportunity** | 🟠 **Dead zone** — don't |
| **Thick supply** | 🔴 **Red ocean** — don't | 🔴 **Red ocean** — don't |

**The orange cell is the one that catches people out.** Most niche advice says
"find where competition is low." But thin supply has two opposite causes:
*nobody's doing it* and *nobody wants it*. Only measuring supply conflates them.

Verdict precedence: `blocker > low coverage > matrix`. Any blocker forces red
regardless of everything else. This came from a real failure — `receipt scanner`
had thin GitHub supply (1,400 repos) and strong demand, but its App Store leader
is **free with 7,642,608 ratings**. Any blended score lets that fact be averaged
away, so blockers override.

`(coverage low)` means only 2 dimensions were measurable (B2B directions have no
App Store criterion). That's a real information gap, so it's labelled rather than
hidden.

The numeric score is **for ranking only** — it measures supply thinness, not
demand, and never replaces the paid-validation step.

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

## Beyond avoiding red oceans: how to actually find a blue one

The scanner can only **rule out** — it measures supply and search intent, both of
which exist only for needs that have already been named. A genuine blue ocean is
usually created, not found, so it will never appear in this data.

`references/blue-ocean-methods.md` covers the part the tool can't do:

- **Moats (7 Powers).** A green light proves supply is thin; it says nothing about
  whether you can hold the position. The book's test is *Benefit + Barrier* — a
  cost or quality advantage **plus** something rivals can't copy without hurting
  themselves. Most apparently-good businesses have zero Powers. For a solo
  developer only two are realistically available: **counter-positioning** (a model
  incumbents can't adopt without cannibalising themselves) and **switching costs**.
- **The ERRC grid.** The ladder only narrows along one axis. ERRC moves four at
  once — Eliminate, Reduce, Raise, Create — to redraw the value curve so
  competition becomes irrelevant. The *Create* row is where blue oceans come from.
- **Six paths.** A systematic way to look past industry boundaries: substitute
  industries, strategic groups, buyer groups, complements, functional vs emotional
  appeal, and time.

That file also states plainly what the scanner **cannot** see: unnamed needs,
non-English/Chinese markets, your own cost of entry, timing, and regulatory
resets. **The tool excludes; you create.** Treating the scanner as an idea
generator yields a pile of narrow gates nobody wants.

## Limits — read this

- **B2B markets are only weakly assessed.** App Store rating counts are
  meaningless for B2B (business buyers rarely review: a B2B vet app tops out at
  40k ratings vs 7.6M for a consumer receipt app), and G2/Capterra are
  Cloudflare-blocked. The scanner labels this limitation rather than inventing a
  score. There is no cheap substitute: the plugin ecosystems (WordPress /
  Firefox / JetBrains) look like a fit but were measured and rejected — their
  counts come from fuzzy full-text search (the same word gives 1,691 vs 189
  depending on the endpoint), the hits are largely unrelated, and the top
  Firefox results are dead add-ons with zero daily users. GitHub remains the only
  real B2B supply signal.
- **Reddit, Product Hunt, G2, Capterra, AlternativeTo return HTTP 403** — platform
  blocks, not network issues. They need official API keys or paid data.
- **Search-engine sources are unreliable.** DuckDuckGo rate-limits from the 3rd
  request on and returns a page with *zero results* rather than an error — which
  reads as "no competition" if unhandled. The scanner detects the anomaly page
  and labels the dimension as missing, but deliberately makes **one attempt with
  no backoff retries** (waiting 36s for a dimension that does not score is pure
  waste), and SERP data is excluded from scoring so the verdict cannot drift with
  a search engine's mood.
- **Two data-quality traps are handled but worth knowing:** iTunes'
  `entity=software` does *not* exclude games (a nonsense query matched Fruit
  Ninja's 373k ratings), and Bing's autocomplete silently strips trailing
  generic words like "software", manufacturing demand that doesn't exist.
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
  SKILL.md                     # verdict rubric, signal taxonomy, workflow
  scan.py                      # unified entry point (mode × engine)
  _http.py                     # shared HTTP layer: disk cache, per-source
                               #   throttling, GitHub quota persisted to disk
  global_scan.py               # global/English engine
  red_ocean_scan.py            # Chinese market engine
  ladder_scan.py               # narrowing ladder: broad word → narrow gates
  geo_scan.py                  # geographic arbitrage across app-store regions
  references/
    blue-ocean-methods.md      # moats (7 Powers), ERRC grid, six paths — how to
                               #   go from "avoid red oceans" to "create a blue one"
    engine-global.md           # global engine detail
    engine-cn.md               # Chinese engine detail
    modes.md                   # ladder + geo detail
    calibration.md             # all measured calibration anchors
    data-sources.md            # source capability matrix + silent-failure traps
scripts/
  validate_skill.py            # spec rules + token budget + runs the tests
  remeasure_cn.py              # re-measure Chinese keywords / regenerate the
                               #   data doc (preflights supply, writes nothing
                               #   if the source is IP-blocked)
tests/
  test_decide.py               # offline regression on the global verdict matrix
  test_cn_engine.py            # offline regression on Chinese verdict dispatch
  test_demand_filter.py        # autocomplete filter (one source was silently emptied)
  test_http_cache.py           # cache / negative cache / quota / response validity
  test_http_shared.py          # ladder + geo really go through the shared layer
  test_scope_guard.py          # out-of-scope (physical goods) refusal
  test_supply_blocked.py       # a blocked supply source must not read as "0 articles"
  trigger_eval.json            # 20 trigger queries for description tuning
docs/
  实测数据-中文.md               # measured scores across 18 Chinese keywords
```

SKILL.md is kept to **232 lines / ~5,000 tokens** (the spec's progressive-disclosure
budget). Everything else loads on demand.

## License

MIT
