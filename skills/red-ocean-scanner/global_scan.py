#!/usr/bin/env python3
"""Red Ocean Scanner — Global engine / 全球市场引擎

判断一个方向在英文（全球）市场该不该做。中文市场请用 red_ocean_scan.py。

═══════════════════════════════════════════════════════════════════
重要修正（实测）
  早期版本声称 Google / Wikipedia / DuckDuckGo 不可达，那是**错误的**。
  错误来源：用 Node 的 fetch 做连通性测试，而 Node 在本机 DNS 解析异常，
  所有请求 CONNECT_TIMEOUT。改用 Python urllib（本 skill 的实际运行时）
  重测后，绝大多数源可用：
      ✅ Google 搜索 / Google 自动补全 / Bing / DuckDuckGo
      ✅ Wikipedia / Wikidata / iTunes(App Store) / Chrome 商店
      ✅ GitHub / HackerNews / StackExchange / npm / PyPI
      ⚠️ 真 403（对方主动封锁，非网络问题）：
         Reddit / Product Hunt / G2 / Capterra / AlternativeTo
  教训值得记：**测试工具本身也会错，连通性结论必须用目标运行时复验。**
═══════════════════════════════════════════════════════════════════

三类市场，三套供给信号：
  consumer  → App Store 评价数（消费级饱和的唯一可见证据）
  developer → GitHub 仓库密度 + star 分布
  web/SaaS  → 搜索结果的商业意图密度

用法:
  python3 global_scan.py "keyword1" "keyword2"
  python3 global_scan.py --json "keyword"
  python3 global_scan.py --market business "keyword"
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# GitHub 搜索限流：未授权 10 次/分钟，带 token 30 次/分钟。
GH_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""

COMMERCIAL = (r"software|app|tool|best|review|pricing|price|cost|buy|"
              r"for small business|alternative|vs\b|comparison|free|"
              r"download|template|online|system|platform|service")
INFORMATIONAL = r"what is|meaning|definition|how to|why|example|format|difference"

# App Store 评价数分档（真实采样校准）
#   receipt scanner 7,642,608 / todo list 1,002,579 / shift scheduling 149,956
#   veterinary clinic 33,992（B2B）/ funeral home 3,520（B2B）
APP_TIERS = [
    (300000, "红海", 0),
    (50000, "高", 0),
    (10000, "中", 1),
    (2000, "低", 2),
    (0, "极低", 3),
]

# GitHub 仓库数分档
#   todo 90,582 / habit 60,479 / shift scheduling 2,896 / invoice excel 2,262
#   receipt scanner 1,400 / veterinary clinic 42 / funeral home 23
GH_TIERS = [
    (20000, "红海", 0),
    (5000, "高", 0),
    (1500, "中", 1),
    (300, "低", 2),
    (0, "极低", 3),
]

MONOPOLY_STARS = 2000
# App Store 头部评价数超过此值 = 不可撼动的既得利益者
APP_MONOPOLY = 100000

# B2B 词汇：命中则 App Store 评价数不可用作消费级判据
B2B_HINT = (r"clinic|practice|patient|invoice|invoicing|payroll|compliance|"
            r"inventory|dental|salon|restaurant|logistics|fleet|property|"
            r"legal|funeral|veterinary|medical|ehr|emr|crm|erp|wholesale")

# 软件/工具形态的标志词。与 PHYSICAL_HINT 同时命中时，以「这是软件」为准——
# 例如 "restaurant scheduling software" 里的 restaurant 只是行业限定词，
# 用户要做的显然是软件，不是开餐厅。
SOFTWARE_HINT = (
    r"software|app|apps|application|system|systems|platform|tool|tools|saas|"
    r"api|sdk|plugin|extension|dashboard|automation|crm|erp|pos|"
    r"management system|booking system|scheduling|analytics|tracker|"
    r"generator|calculator|converter|scanner|ocr|excel|spreadsheet|"
    r"template|widget|bot|integration|database|website|web app|mobile app")

# 实体产品 / 线下服务的标志词。
# 这些品类的竞争格局不在 GitHub 也不在 App Store 上——工具的两个数据源
# 都不代表它们。实测 "handmade soap business" 被判成「无人区」，
# 还因为模糊匹配到 Etsy 而误报「已有 727 万条评价的既得利益者」。
# 那是**自信的错误结论**，比"无法判断"危险得多，所以这里主动拒绝作答。
PHYSICAL_HINT = (
    r"handmade|hand-made|etsy|craft fair|soap|candle|jewel(?:lery|ry)|pottery|"
    r"ceramic|knit|sewing|embroidery|leather|woodwork|furniture|clothing|"
    r"apparel|t-shirt|merch|print on demand|dropship|wholesale|"
    r"food truck|catering|bakery|coffee shop|restaurant|cleaning service|"
    r"landscap|plumbing|hvac|roofing|moving company|photography studio|"
    r"tutoring|childcare|daycare|pet grooming|hair salon|barber|massage|"
    r"fitness studio|yoga studio|real estate agent|insurance agent")


# HTTP 层统一交给 _http：磁盘缓存 + 主动限流 + 跨进程配额持久化。
# 见 _http.py 顶部注释——实测 GitHub search 是硬性 10 次/分钟且不给
# Retry-After，DDG HTML 第 3 次起必拦，所以必须主动读 header 等待，
# 而不是撞了 403 再退避。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _http  # noqa: E402

FetchError = _http.FetchError
RateLimited = _http.RateLimited


def get(url, timeout=20):
    return _http.fetch(url, timeout=timeout)


def get_json(url, tries=2):
    return json.loads(_http.fetch(url, tries=tries))


def decide(supply_thin, demand_str, deadly, supply_dims, n_dims):
    """裁决核心：纯函数，不依赖网络，便于回归测试。

    返回 (verdict, kind, reason)。

    顺序很重要：先算矩阵，再让否决项生效。矩阵能区分「无人区」（没人要）
    和「红海」（打不过），如果在矩阵之前就因否决项返回「红」，会把无人区
    误报成红海——两者的应对完全不同。
    """
    thin_ok = supply_thin is not None and supply_thin >= 0.5
    demand_ok = demand_str is not None and demand_str >= 0.5

    if thin_ok and demand_ok:
        verdict, kind = "绿", "机会"
        reason = "供给稀薄 + 需求存在（**但这不等于蓝海**，见下方护城河追问）"
    elif thin_ok and not demand_ok:
        verdict, kind = "🟠", "无人区"
        reason = ("供给稀薄但需求信号弱 → 大概率是没人关心的领域。"
                  "**低竞争在这里等于没市场**")
    else:
        verdict, kind = "红", "红海"
        reason = ("需求旺但供给厚 → 已被认领" if demand_ok
                  else "供给厚且需求弱 → 没有进入理由")
        if supply_thin is not None and supply_thin < 1.0 and supply_dims:
            worst = min(supply_dims, key=lambda x: x[1] / x[2])
            reason += f"（主因：{worst[0]}）"

    # 否决项只在矩阵给出「机会」时一票否决。矩阵说红海时它是冗余信息；
    # 矩阵说无人区时，「没有市场」比「有既得利益者」更准确地描述问题。
    if deadly and verdict == "绿":
        verdict, kind = "红", "红海"
        reason = "矩阵指向机会，但有硬性否决项 → " + deadly[0]
    elif deadly and verdict == "🟠":
        reason += "（另有否决项：" + deadly[0] + "）"

    if n_dims < 3:
        verdict += "(覆盖度低)"
        reason += f"；仅测到 {n_dims} 个维度，把握有限"
    return verdict, kind, reason


MOAT_PROMPT = (
    "绿灯只说明「供给薄 + 有需求」，不说明你守得住。"
    "追问一句：10 个人下周抄我，我靠什么还活着？"
    "答不出 → 这是短期现金流，不是事业。见 references/blue-ocean-methods.md"
)


def is_out_of_scope(kw):
    """这个方向是否超出本工具的判断范围（实体产品 / 线下服务）。

    抽成独立函数是为了让测试能调用**同一份**逻辑。曾经把判定抄进测试里，
    结果 scan() 内遗留了一个无条件判断、把软件查询也拦掉时，测试依然全绿——
    复制逻辑的测试会连 bug 的盲区一起复制。

    规则：实体词命中 **且** 没有软件信号才算超范围。
    实测教训："restaurant scheduling software" / "coffee shop pos system"
    里的实体词只是行业限定语，用户要做的显然是软件。
    """
    physical = bool(re.search(PHYSICAL_HINT, kw, re.I))
    software = bool(re.search(SOFTWARE_HINT, kw, re.I))
    return physical and not software


def tier_of(n, tiers):
    for thresh, label, pts in tiers:
        if n >= thresh:
            return label, pts
    return "未知", 0


# ── 需求：三源自动补全 ────────────────────────────────
# 通用产品词：补全引擎会把它们从查询里剥掉再匹配，制造虚假需求。
# 实测：查询 "banana peeling machine software"（不存在的组合）
#   Google 返回 0 条 ✅
#   Bing  返回 12 条 ❌ 全是 "banana peeling machine design/reviews/video..."
# 即 Bing 忽略了 "software"。若不识别，会把完全不存在的需求判成「需求旺」。
GENERIC_TAIL = {
    "software", "app", "apps", "tool", "tools", "system", "systems",
    "platform", "service", "services", "solution", "solutions", "online",
}


def _is_generic_strip(query, suggestion):
    """suggestion 是否只是 query 剥掉尾部通用产品词后的产物？

    只在 query **以通用产品词结尾**时才可能发生。
    实测：query="banana peeling machine software" 时 Bing 忽略 "software"，
    返回 "banana peeling machine design/reviews/video"，与词尾剥离一致 → 丢弃。

    反例（必须保留）：query="habit tracker" 时 "habit tracker app" 是
    合法的向下细化，不是剥离产物——query 本身不以通用词结尾。
    """
    q = re.findall(r"\w+", query.lower())
    sg = re.findall(r"\w+", suggestion.lower())
    if not q or not sg:
        return False
    if q[-1] not in GENERIC_TAIL:      # query 不以通用产品词结尾 → 不可能是剥离
        return False
    stem = q[:]
    while stem and stem[-1] in GENERIC_TAIL:
        stem.pop()
    if not stem:
        return False
    # 建议词以去掉通用词后的主干开头，就是在匹配被剥掉的那个词
    return sg[:len(stem)] == stem


def autocomplete(kw):
    q = urllib.parse.quote(kw)
    merged, src, dropped = [], {}, 0
    for name, url, pick in [
        ("google", f"https://suggestqueries.google.com/complete/search"
                   f"?client=firefox&q={q}", lambda d: d[1]),
        ("bing", f"https://api.bing.com/osjson.aspx?query={q}", lambda d: d[1]),
        ("ddg", f"https://duckduckgo.com/ac/?q={q}&type=list",
         lambda d: [x.get("phrase", "") for x in d if isinstance(x, dict)]),
    ]:
        try:
            words = pick(json.loads(get(url)))
            kept = 0
            for w in words or []:
                if not w:
                    continue
                if _is_generic_strip(kw, w):
                    dropped += 1
                    continue
                if w.lower() not in [m.lower() for m in merged]:
                    merged.append(w)
                    kept += 1
            src[name] = kept
        except Exception:                                    # noqa: BLE001
            src[name] = 0
    return {
        "merged": merged,
        "sources": src,
        "dropped_generic": dropped,
        "commercial": [w for w in merged if re.search(COMMERCIAL, w, re.I)],
        "informational": [w for w in merged if re.search(INFORMATIONAL, w, re.I)],
    }


# ── 消费市场：App Store ────────────────────────────────
# iTunes 的 entity=software **不排除游戏**，实测搜 "banana peeling machine
# software" 会返回 Fruit Ninja（373,282 评）并触发「不可撼动的既得利益者」
# 否决项——一个完全不存在的需求被判成红海。必须按 genre 过滤。
EXCLUDED_GENRES = {"games"}


# iTunes 的搜索是**模糊匹配**，会返回大量与查询无关的 App。
# 实测：搜 "handmade soap business" 会返回 Etsy（7,275,714 条评价），
# 因为苹果用 "handmade" 做了替换匹配。Etsy 与「手工皂生意」毫无关系，
# 却会触发「不可撼动的既得利益者」否决项，把一个真实市场判成红海。
#
# 所以必须做相关性过滤：App 名称里至少要命中一个查询实词。
def _relevant(app_name, kw):
    toks = [t for t in re.findall(r"[a-z0-9]{4,}", kw.lower())
            if t not in GENERIC_TAIL]
    if not toks:                       # 查询全是通用词，无法判断，全部保留
        return True
    name = (app_name or "").lower()
    return any(t in name for t in toks)


def appstore(kw, country="us"):
    d = get_json("https://itunes.apple.com/search?term="
                 + urllib.parse.quote(kw)
                 + f"&entity=software&limit=25&country={country}")
    raw = d.get("results", [])
    kept = [a for a in raw
            if (a.get("primaryGenreName", "") or "").lower() not in EXCLUDED_GENRES]
    apps = [a for a in kept if _relevant(a.get("trackName", ""), kw)]
    ratings = sorted(((a.get("userRatingCount", 0) or 0) for a in apps),
                     reverse=True)
    # 用 P75 而不是 max：一个离群 App（或一次模糊匹配的残留）不该单独决定裁决。
    # 实测 "funeral home management" 的搜索顺序里混着 Find a Grave 等无关项，
    # 单看 max 会把噪声当成市场头部。
    def pct(vals, q):
        if not vals:
            return 0
        return vals[min(len(vals) - 1, int(len(vals) * q))]
    return {
        "total": len(apps),
        "excluded_games": len(raw) - len(kept),
        "excluded_irrelevant": len(kept) - len(apps),
        "max_ratings": ratings[0] if ratings else 0,
        "p75_ratings": pct(ratings, 0.25),   # 降序，前 25% 分位
        "sum_ratings": sum(ratings),
        "avg_rating": (sum(a.get("averageUserRating", 0) or 0 for a in apps)
                       / len(apps)) if apps else 0,
        # 展示按评价数排序的前几名，而不是搜索顺序——后者常含无关项，
        # 会让用户以为它们是头部
        "top": [(a.get("trackName", "")[:42],
                 round(a.get("averageUserRating", 0) or 0, 1),
                 a.get("userRatingCount", 0) or 0)
                for a in sorted(apps, key=lambda x: -(x.get("userRatingCount", 0) or 0))[:5]],
    }


# ── 开发者市场：GitHub ─────────────────────────────────
def github(kw):
    d = get_json("https://api.github.com/search/repositories?q="
                 + urllib.parse.quote(kw) + "&per_page=10")
    items = d.get("items", [])
    stars = [i.get("stargazers_count", 0) for i in items]
    return {
        "total": d.get("total_count", 0),
        "max_stars": max(stars) if stars else 0,
        "top": [(i.get("full_name", ""), i.get("stargazers_count", 0))
                for i in items[:4]],
    }


# ── Web/SaaS：搜索结果 ─────────────────────────────────
# DDG 限流时会返回一个含 anomaly 标记的页面，且 **0 条结果**。
# 如果不识别，就会把「被限流」读成「没有评测站」——一个静默的错误结论。
# 实测：连续请求 5 次后必然触发。
DDG_BLOCK = re.compile(r"anomaly|unusual traffic|blocked", re.I)
REVIEW_SITES = (r"g2\.com|capterra|getapp|softwareadvice|trustradius|"
                r"softwaresuggest|slashdot|producthunt")
# B2B 定价信号：标题里出现这些词说明市场已有商业化产品
PRICE_WORDS = r"pricing|price|plans|free trial|demo|buy|cost|quote"


def web_serp(kw):
    """搜索结果信号，**仅作参考、不参与评分**。

    实测 DDG HTML 在第 3 次请求起必然返回 anomaly 页，且不给 Retry-After。
    既然这个维度不计分，就**不做退避重试**——原来固定重试 3 次、每次退避
    8-12s，等于为一个不参与判定的维度白等 36 秒。
    改为单次尝试 + 24 小时缓存，失败就明确标记为不可用。
    """
    try:
        h = _http.fetch("https://html.duckduckgo.com/html/?q="
                        + urllib.parse.quote(kw), timeout=12, tries=1)
    except Exception as e:                                   # noqa: BLE001
        return {"error": f"{str(e)[:40]}（该维度不计分，忽略即可）"}
    if DDG_BLOCK.search(h) or len(h) < 5000:
        return {"error": "DDG 限流（该维度不计分，忽略即可）"}
    titles = [re.sub(r"<[^>]+>", "", t).strip()
              for t in re.findall(r'class="result__a"[^>]*>(.*?)</a>', h, re.S)]
    titles = [t for t in titles if t]
    if not titles:
        return {"error": "页面无结果条目（结构可能变了，该维度不计分）"}
    domains = [d.strip() for d in
               re.findall(r'class="result__url"[^>]*>\s*(.*?)\s*<', h, re.S)]
    return {
        "results": len(titles),
        "review_sites": sum(1 for d in domains
                            if re.search(REVIEW_SITES, d, re.I)),
        "pricing_signals": sum(1 for t in titles
                               if re.search(PRICE_WORDS, t, re.I)),
        "top": titles[:5],
    }


def scan(kw, market="auto"):
    r = {"keyword": kw, "engine": "global", "deadly": [], "evidence": [],
         "limits": []}

    try:
        r["demand"] = autocomplete(kw)
    except Exception as e:                                   # noqa: BLE001
        r["demand"] = None
        r["deadly"].append(f"需求数据未取到（{str(e)[:40]}）")

    for key, fn in [("appstore", appstore), ("github", github)]:
        try:
            r[key] = fn(kw)
        except Exception as e:                               # noqa: BLE001
            r[key] = {"error": str(e)[:50]}
        # 间隔只在未命中缓存、真的打了网络请求时才需要——命中缓存时纯属白等。
        # GitHub 的主动限流由 _http.github_gate() 负责，这里不重复实现。
        if _http.last_was_network:
            time.sleep(1.0)
    # 搜索结果只作参考展示，不参与评分：DDG/Startpage/Mojeek/searx 实测都会
    # 限流，把它计入评分会让分数随搜索引擎的心情波动。
    # 另外：既然实体产品/线下服务方向最终会拒绝作答，就不必为它打这个
    # 会退避重试（每次 8-12s）的源——那是纯粹的等待。
    # 只有当查询「指向实体生意」而不是「指向软件」时才拒绝作答。
    # 实测教训：起初只用 PHYSICAL_HINT 判断，结果把
    # "restaurant scheduling software" / "coffee shop pos system" /
    # "bakery inventory software" 这类明显的软件查询也拦掉了——
    # 实体词只是行业限定语。所以必须有软件信号时优先按软件处理。
    _out_of_scope = is_out_of_scope(kw)
    if _out_of_scope:
        r["web"] = {"skipped": "超出适用范围，跳过搜索结果采集"}
    else:
        try:
            r["web"] = web_serp(kw)
        except Exception as e:                               # noqa: BLE001
            r["web"] = {"error": str(e)[:50]}

    # 供给档位在数据收集阶段就算出来，供展示与提前返回的路径共用
    _gh = r.get("github") or {}
    if "total" in _gh:
        r["gh_tier"] = tier_of(_gh["total"], GH_TIERS)[0]

    # ── 市场类型判定 ────────────────────────────────────
    is_b2b = bool(re.search(B2B_HINT, kw, re.I))
    if market == "auto":
        market = "business" if is_b2b else "consumer"
    r["market"] = market
    r["is_b2b_guess"] = is_b2b

    # 数据源适用性检查：实体产品与线下服务的竞争格局不在本工具的数据源里。
    # 宁可拒绝作答，也不要给一个自信的错误裁决。
    # 必须复用上面算好的 _is_physical/_is_software——这里曾遗留一个无条件
    # 的 PHYSICAL_HINT 判断，把 "restaurant scheduling software" 这类
    # 明显是软件的查询也拦掉了。
    if _out_of_scope:
        r["dimensions"] = []
        r["supply_thin"] = r["demand_str"] = None
        r["score"] = 0
        r["verdict"], r["verdict_kind"] = "⚪ 不适用", "超出适用范围"
        r["verdict_reason"] = (
            "这个方向看起来是实体产品或线下服务，它的竞争格局既不在 GitHub "
            "也不在 App Store 上——本工具的两个数据源都不代表它。"
            "给结论会是自信的错误，所以不判。")
        r["deadly"] = []
        r["evidence"] = []
        r["limits"].append(
            "若你想做的其实是「给这个行业做软件」（例如婚礼摄影工作室用的排期工具），"
            "请把查询改成工具本身，例如 'wedding photography scheduling software'。")
        r["limits"].append(
            "若你想评估的是实体生意本身，本工具帮不上。可用的人工路径："
            "在 Etsy/亚马逊搜同类卖家数量与销量、看批发平台同类供应量、"
            "或在本地实地数竞争对手。")
        return r

    # ── 评分：按维度分别打薄分，最后取平均 ──────────────
    #
    # 为什么取平均而不是相加：不同市场能测到的维度数不同
    # （消费级有 App Store，B2B 没有）。相加会导致 B2B 满分只有 8，
    # 恰好卡在绿线上——任何一项掉档就永远够不着绿灯。维度数不可比，
    # 就不该直接比分数。
    #
    # 每个维度的分都是 0-3 的「薄分」（3 = 供给稀薄，0 = 饱和）。
    dims = []          # [(维度名, 薄分, 满分)]

    # ① 开发者供给
    gh = r.get("github") or {}
    if "total" in gh:
        label, pts = tier_of(gh["total"], GH_TIERS)
        dims.append(("开发者供给", pts, 3))
        if gh["total"] < 300:
            r["evidence"].append(f"GitHub 仅 {gh['total']} 仓库 → 开发者侧几乎无人做")
        elif gh["total"] < 1500:
            r["evidence"].append(f"GitHub {gh['total']} 仓库 → 开发者侧供给稀薄")
        elif gh["total"] >= 20000:
            r["deadly"].append(f"GitHub {gh['total']:,} 仓库 → 开发者侧已饱和")
        if gh.get("max_stars", 0) >= MONOPOLY_STARS:
            r["deadly"].append(
                f"头部仓库 {gh['max_stars']}★ → 成熟开源替代品，会压制付费意愿")

    # ② 消费供给（仅消费级市场）
    ap = r.get("appstore") or {}
    if "max_ratings" in ap:
        if market == "consumer" and ap["total"] < 3:
            # 样本太少时这个维度不可信：相关 App 不足 3 个，P75 就等于某一个
            # App 的评价数（实测 "vet clinic software" 只留下 1 款，
            # 那 33,992 条评价会独自决定整个消费供给维度）。
            # 宁可标为「不可用」，也不要让单个样本冒充市场信号。
            r["limits"].append(
                f"App Store 相关结果仅 {ap['total']} 款，样本不足 → "
                f"消费供给维度未计入评分")
        elif market == "consumer":
            # 用 P75 判垄断：单个离群 App 不足以构成「既得利益者」
            metric = ap.get("p75_ratings", ap["max_ratings"])
            label, pts = tier_of(metric, APP_TIERS)
            r["app_tier"] = label
            dims.append(("消费供给", pts, 3))
            if metric >= APP_MONOPOLY:
                r["deadly"].append(
                    f"App Store 同类头部（P75）{metric:,} 条评价 → "
                    f"已有不可撼动的既得利益者，且是免费产品")
            elif metric < 2000:
                r["evidence"].append(
                    f"App Store 头部（P75）仅 {metric:,} 条评价 → "
                    f"没有强势消费级产品")
            if ap["avg_rating"] and ap["avg_rating"] < 3.6 and ap["total"] >= 8:
                r["evidence"].append(
                    f"同类 App 均分仅 {ap['avg_rating']:.2f} → 现有产品口碑差，缺口信号")
        else:
            r["limits"].append(
                "B2B 方向，App Store 评价数不作判据（企业买家很少写评价："
                "兽医类最高 3.4 万 vs 消费类 760 万）")

    # 已删除的实验维度：App Store 「在售产品数」。
    # 实测无区分度——所有品类都返回 22-25 款
    # （funeral home management 25 / todo list app 23 / receipt scanner 22），
    # 这是 iTunes 模糊匹配的产物，不是市场信号，而且会错误惩罚 B2B
    # （B2B 软件本来就不在 App Store 卖）。宁可用 2 个真维度，
    # 也不要 3 个里面掺一个假的。

    # 消费供给已在 ② 计入（仅消费级市场）。B2B 因此只有 2 个维度，
    # 这是真实的信息缺口，不是评分缺陷——所以分数按**已测维度**取比例，
    # 并在输出里标注覆盖度。

    # ④ 需求
    d = r.get("demand")
    if d and d["merged"]:
        n, c = len(d["merged"]), len(d["commercial"])
        if c >= 5:
            dims.append(("需求强度", 3, 3))
            r["evidence"].append(f"{c} 条商业意图补全词，例《{d['commercial'][0]}》")
        elif c >= 2:
            dims.append(("需求强度", 2, 3))
            r["evidence"].append(f"{c} 条商业意图补全词")
        elif n >= 8:
            dims.append(("需求强度", 1, 3))
        else:
            dims.append(("需求强度", 0, 3))
        if d["informational"] and len(d["informational"]) > c:
            r["evidence"].append(
                f"信息型词({len(d['informational'])})多于商业型({c}) → "
                f"用户在找知识而非产品，付费意愿存疑")
    elif d is not None:
        dims.append(("需求强度", 0, 3))
        r["deadly"].append("三个自动补全源均无结果 → 可能没人在搜")

    r["dimensions"] = [{"name": nm, "thin": sc, "of": of} for nm, sc, of in dims]
    got, tot = sum(x[1] for x in dims), sum(x[2] for x in dims)

    # 把维度分成「供给」与「需求」两类，分别汇总。
    # 为什么不在一个分数里平均：供给和需求回答的是两个不同问题——
    #   供给薄 + 没需求 = 无人区（别做）
    #   供给厚 + 有需求 = 红海（别做）
    #   供给薄 + 有需求 = 机会
    # 平均会把「无人区」和「红海」都算成中间分，两者却被混为一谈。
    SUPPLY_DIMS = ("开发者供给", "消费供给")
    sup = [x for x in dims if x[0] in SUPPLY_DIMS]
    dem = [x for x in dims if x[0] not in SUPPLY_DIMS]
    r["supply_thin"] = (sum(x[1] for x in sup) / sum(x[2] for x in sup)) if sup else None
    r["demand_str"] = (sum(x[1] for x in dem) / sum(x[2] for x in dem)) if dem else None
    r["score"] = round(10 * got / tot) if tot else 0
    r["coverage"] = len(dims)
    # 裁决优先级：否决项 > 覆盖度不足 > 分数。
    # 否决项一律判红不看分数：一个"已有 760 万评价的既得利益者"的方向，
    # 绝不能因为别处得分高就降级成黄灯。
    # 覆盖度不足时降级为「不完整」：维度少意味着不确定性大，
    # 这时给绿灯是在假装有把握。
    r["verdict"], r["verdict_kind"], r["verdict_reason"] = decide(
        r["supply_thin"], r["demand_str"], r["deadly"], sup, len(dims))
    return r


def render(r):
    mk = {"consumer": "消费级", "business": "B2B"}.get(r["market"], r["market"])
    L = [f"\n{'='*70}",
         f"{r['verdict']}  {r['keyword']}    {r['score']}/10"
         f"   [global · {mk}市场]",
         f"{'='*70}",
         f"裁决  {r.get('verdict_reason','')}"]
    st, ds = r.get("supply_thin"), r.get("demand_str")
    if st is not None and ds is not None:
        L.append(f"      供给薄度 {st:.0%}（越高越没人做）   "
                 f"需求强度 {ds:.0%}（越高越有人要）")
    d = r.get("demand")
    if d:
        src = " ".join(f"{k}:{v}" for k, v in (d.get("sources") or {}).items())
        L.append(f"需求  自动补全 {len(d['merged'])} 条（{src}）"
                 f"，商业意图 {len(d['commercial'])} 条")
        for w in d["commercial"][:3]:
            L.append(f"        ★ {w[:56]}")
    ap = r.get("appstore") or {}
    if "max_ratings" in ap:
        L.append(f"消费  App Store {ap['total']} 款，头部 {ap['max_ratings']:,} 条评价，"
                 f"均分 {ap['avg_rating']:.2f}")
        for n_, rt, rc in ap["top"][:3]:
            L.append(f"        {rc:>9,} 评 ★{rt}  {n_}")
    gh = r.get("github") or {}
    if "total" in gh:
        L.append(f"开发  GitHub {gh['total']:,} 仓库 [{r.get('gh_tier')}]，"
                 f"头部 {gh['max_stars']}★")
    w = r.get("web") or {}
    if "results" in w:
        L.append(f"Web   搜索结果 {w['results']} 条，评测站 {w['review_sites']} 个，"
                 f"定价信号 {w.get('pricing_signals',0)} 条")
    if r.get("dimensions"):
        L.append(f"评分  基于 {r.get('coverage',0)} 个维度"
                 f"（每个 0-3 薄分，取比例，维度数无关）")
        for x in r["dimensions"]:
            bar = "▓" * x["thin"] + "░" * (x["of"] - x["thin"])
            L.append(f"        {x['name']:10} {bar} {x['thin']}/{x['of']}")
    if r["evidence"]:
        L.append("依据")
        for x in r["evidence"]:
            L.append(f"      + {x}")
    if r["deadly"]:
        L.append("否决项")
        for x in r["deadly"]:
            L.append(f"      − {x}")
    if r["limits"]:
        L.append("口径限制")
        for x in r["limits"]:
            L.append(f"      ! {x}")
    L.append("下一步  " + next_step(r))
    if r.get("verdict_kind") == "机会":
        L.append("")
        L.append("护城河追问（工具测不到，必须你自己答）")
        L.append("      " + MOAT_PROMPT)
    return "\n".join(L)


def next_step(r):
    """按裁决种类给下一步。

    必须用 verdict_kind 而不是 verdict 字符串来判断——verdict 可能带
    「(覆盖度低)」后缀，用 == 比较会把绿灯错判成红灯，给出完全相反的建议。
    """
    kind = r.get("verdict_kind", "")
    if kind == "超出适用范围":
        return ("本工具判不了这个方向——数据源不对口。"
                "要么把查询改成这个行业用的**软件**，要么改用人工方式评估实体生意。")
    if kind == "机会":
        return ("多源都指向供给稀薄，但这是意图数据不是成交数据。"
                "去目标用户聚集地读真实抱怨，挂落地页收邮箱。")
    if kind == "无人区":
        return ("这是无人区不是机会：先证明有人要（找 5 个真实的人问），"
                "再谈做产品。没有需求证据就不要投入。")
    if kind == "红海":
        return "放弃。多个独立数据源都指向饱和，不要靠加功能挽救。"
    return "数据不完整，稍后重跑，不要在此结论上做决定。"


def main():
    ap = argparse.ArgumentParser(description="Red Ocean Scanner — Global engine")
    ap.add_argument("keywords", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--market", choices=["auto", "consumer", "business"],
                    default="auto")
    ap.add_argument("--gap", type=float, default=4.0)
    a = ap.parse_args()

    res = []
    for i, kw in enumerate(a.keywords):
        if i:
            time.sleep(a.gap)
        res.append(scan(kw, a.market))

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    for r in res:
        print(render(r))
    if len(res) > 1:
        print(f"\n{'='*70}\n排名（分高者优先）")
        for i, r in enumerate(sorted(res, key=lambda x: -x["score"]), 1):
            print(f"  {i}. {r['score']:>2}/10  {r['verdict']:<16}"
                  f"{r.get('verdict_kind',''):<6} {r['keyword']}")


if __name__ == "__main__":
    main()
