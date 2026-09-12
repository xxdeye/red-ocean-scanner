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


class FetchError(Exception):
    pass


class RateLimited(FetchError):
    pass


def get(url, timeout=15):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
         "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}
    if GH_TOKEN and "api.github.com" in url:
        h["Authorization"] = f"Bearer {GH_TOKEN}"
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def get_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            return json.loads(get(url))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and "api.github.com" in url:
                last = RateLimited(f"HTTP {e.code} 限流")
                time.sleep(20 * (i + 1))
                continue
            last = FetchError(f"HTTP {e.code}")
            break
        except Exception as e:                              # noqa: BLE001
            last = FetchError(str(e)[:60])
            time.sleep(2)
    raise last


def tier_of(n, tiers):
    for thresh, label, pts in tiers:
        if n >= thresh:
            return label, pts
    return "未知", 0


# ── 需求：三源自动补全 ────────────────────────────────
def autocomplete(kw):
    q = urllib.parse.quote(kw)
    merged, src = [], {}
    for name, url, pick in [
        ("google", f"https://suggestqueries.google.com/complete/search"
                   f"?client=firefox&q={q}", lambda d: d[1]),
        ("bing", f"https://api.bing.com/osjson.aspx?query={q}", lambda d: d[1]),
        ("ddg", f"https://duckduckgo.com/ac/?q={q}&type=list",
         lambda d: [x.get("phrase", "") for x in d if isinstance(x, dict)]),
    ]:
        try:
            words = pick(json.loads(get(url)))
            src[name] = len(words)
            for w in words:
                if w and w.lower() not in [m.lower() for m in merged]:
                    merged.append(w)
        except Exception:                                    # noqa: BLE001
            src[name] = 0
    return {
        "merged": merged,
        "sources": src,
        "commercial": [w for w in merged if re.search(COMMERCIAL, w, re.I)],
        "informational": [w for w in merged if re.search(INFORMATIONAL, w, re.I)],
    }


# ── 消费市场：App Store ────────────────────────────────
def appstore(kw, country="us"):
    d = get_json("https://itunes.apple.com/search?term="
                 + urllib.parse.quote(kw)
                 + f"&entity=software&limit=25&country={country}")
    apps = d.get("results", [])
    ratings = [(a.get("userRatingCount", 0) or 0) for a in apps]
    return {
        "total": len(apps),
        "max_ratings": max(ratings) if ratings else 0,
        "sum_ratings": sum(ratings),
        "avg_rating": (sum(a.get("averageUserRating", 0) or 0 for a in apps)
                       / len(apps)) if apps else 0,
        "top": [(a.get("trackName", "")[:42],
                 round(a.get("averageUserRating", 0) or 0, 1),
                 a.get("userRatingCount", 0) or 0) for a in apps[:5]],
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
def web_serp(kw):
    try:
        h = get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(kw))
    except Exception as e:                                   # noqa: BLE001
        return {"error": str(e)[:50]}
    titles = [re.sub(r"<[^>]+>", "", t).strip()
              for t in re.findall(r'class="result__a"[^>]*>(.*?)</a>', h, re.S)]
    domains = [d.strip() for d in
               re.findall(r'class="result__url"[^>]*>\s*(.*?)\s*<', h, re.S)]
    review = [d for d in domains
              if re.search(r"g2|capterra|getapp|softwareadvice|producthunt|"
                           r"trustradius|softwaresuggest", d, re.I)]
    return {"results": len([t for t in titles if t]), "review_sites": len(review),
            "top": [t for t in titles if t][:5]}


def scan(kw, market="auto"):
    r = {"keyword": kw, "engine": "global", "deadly": [], "evidence": [],
         "limits": []}

    try:
        r["demand"] = autocomplete(kw)
    except Exception as e:                                   # noqa: BLE001
        r["demand"] = None
        r["deadly"].append(f"需求数据未取到（{str(e)[:40]}）")

    for key, fn in [("appstore", appstore), ("github", github), ("web", web_serp)]:
        try:
            r[key] = fn(kw)
        except Exception as e:                               # noqa: BLE001
            r[key] = {"error": str(e)[:50]}
        time.sleep(1.5)

    # ── 市场类型判定 ────────────────────────────────────
    is_b2b = bool(re.search(B2B_HINT, kw, re.I))
    if market == "auto":
        market = "business" if is_b2b else "consumer"
    r["market"] = market
    r["is_b2b_guess"] = is_b2b

    s = 0

    # ① 开发者供给（0-3）
    gh = r.get("github") or {}
    if "total" in gh:
        label, pts = tier_of(gh["total"], GH_TIERS)
        r["gh_tier"] = label
        s += pts
        if gh["total"] < 300:
            r["evidence"].append(f"GitHub 仅 {gh['total']} 仓库 → 开发者侧几乎无人做")
        elif gh["total"] < 1500:
            r["evidence"].append(f"GitHub {gh['total']} 仓库 → 开发者侧供给稀薄")
        elif gh["total"] >= 20000:
            r["deadly"].append(f"GitHub {gh['total']:,} 仓库 → 开发者侧已饱和")
        if gh.get("max_stars", 0) >= MONOPOLY_STARS:
            r["deadly"].append(
                f"头部仓库 {gh['max_stars']}★ → 成熟开源替代品，会压制付费意愿")

    # ② 消费供给（0-3，仅消费市场）
    ap = r.get("appstore") or {}
    if "max_ratings" in ap:
        if market == "consumer":
            label, pts = tier_of(ap["max_ratings"], APP_TIERS)
            r["app_tier"] = label
            s += pts
            if ap["max_ratings"] >= APP_MONOPOLY:
                r["deadly"].append(
                    f"App Store 头部 {ap['max_ratings']:,} 条评价 → "
                    f"已有不可撼动的既得利益者，且是免费产品")
            elif ap["max_ratings"] < 2000:
                r["evidence"].append(
                    f"App Store 头部仅 {ap['max_ratings']:,} 条评价 → "
                    f"没有强势消费级产品")
            if ap["total"] < 5:
                r["deadly"].append(
                    f"App Store 仅 {ap['total']} 款同类 → 可能是伪需求或未被市场验证")
            if ap["avg_rating"] and ap["avg_rating"] < 3.6 and ap["total"] >= 8:
                r["evidence"].append(
                    f"同类 App 均分仅 {ap['avg_rating']:.2f} → 现有产品口碑差，缺口信号")
        else:
            r["limits"].append(
                "B2B 方向，App Store 评价数不作判据（企业买家很少写评价："
                "兽医类最高 3.4 万 vs 消费类 760 万）")

    # ③ 需求（0-3）
    d = r.get("demand")
    if d and d["merged"]:
        n, c = len(d["merged"]), len(d["commercial"])
        if c >= 5:
            s += 3
            r["evidence"].append(f"{c} 条商业意图补全词，例《{d['commercial'][0]}》")
        elif c >= 2:
            s += 2
            r["evidence"].append(f"{c} 条商业意图补全词")
        elif n >= 8:
            s += 1
        if d["informational"] and len(d["informational"]) > c:
            r["evidence"].append(
                f"信息型词({len(d['informational'])})多于商业型({c}) → "
                f"用户在找知识而非产品，付费意愿存疑")
    elif d is not None:
        r["deadly"].append("三个自动补全源均无结果 → 可能没人在搜")

    r["score"] = max(0, min(10, s))
    # 裁决优先级：数据不完整 > 否决项 > 分数。
    # 关键：**任何否决项一律判红，不看分数。** 一个"已有 760 万评价的
    # 既得利益者"的方向，绝不能因为别处得分高就降级成黄灯。
    if "total" not in (r.get("github") or {}):
        r["verdict"] = "黄(不完整)"
    elif r["deadly"]:
        r["verdict"] = "红"
    elif r["score"] >= 8:
        r["verdict"] = "绿"
    elif r["score"] >= 5:
        r["verdict"] = "黄"
    else:
        r["verdict"] = "红"
    return r


def render(r):
    icon = {"绿": "🟢", "黄": "🟡", "红": "🔴"}.get(r["verdict"], "🟡")
    mk = {"consumer": "消费级", "business": "B2B"}.get(r["market"], r["market"])
    L = [f"\n{'='*70}",
         f"{icon} {r['keyword']}    {r['verdict']}    {r['score']}/10"
         f"   [global · {mk}市场]",
         f"{'='*70}"]
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
        L.append(f"Web   搜索结果 {w['results']} 条，评测站 {w['review_sites']} 个")
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
    return "\n".join(L)


def next_step(r):
    v = r["verdict"]
    if v == "绿":
        return ("多源都指向供给稀薄，但这是意图数据不是成交数据。"
                "去目标用户聚集地读真实抱怨，挂落地页收邮箱。")
    if v == "黄":
        return "换更窄的场景词重扫（'veterinary clinic scheduling' 而非 'scheduling'）。"
    if v.startswith("黄"):
        return "数据不完整，稍后重跑，不要在此结论上做决定。"
    return "放弃。多个独立数据源都指向饱和，不要靠加功能挽救。"


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
            print(f"  {i}. {r['score']:>2}/10  {r['verdict']:<9} {r['keyword']}")


if __name__ == "__main__":
    main()
