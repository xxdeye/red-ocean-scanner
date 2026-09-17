#!/usr/bin/env python3
"""收窄阶梯 / Narrowing ladder

把一个大词（通常红海）自动拆成更窄的变体，并按饱和度排序，
找到「同一个需求、更小的战场」。

为什么需要它：**红海是针对词而言的，不是针对需求而言的。**
`invoice app` 有 17,249 个 GitHub 仓库（红海），
`invoice export` 只有 1,826 个（窄口）。需求是同一个，战场小十倍。

这是本工具最反直觉的一条规则：
**不要问「这个方向是不是红海」，要问「这个词是不是红海」。**
换一个更窄的词，同一个需求可能完全不同。

阶梯怎么生成（两级）：
  1. 修饰词模板：把原词与行业通用修饰语组合
  2. 自动补全发现：用 Google/Bing 补全词作为真实存在的窄口
两个来源都会逐个测量供给，避免凭空猜测。

用法:
  python3 ladder_scan.py "invoice"
  python3 ladder_scan.py --top 12 "scheduling"
  python3 ladder_scan.py --json "habit"
"""

import argparse
import json
import os
import sys
import time
import urllib.parse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# HTTP 层统一交给 _http：磁盘缓存 + GitHub 配额门 + 跨进程配额持久化。
#
# 这里原来是裸 urllib：不打缓存、不读 X-RateLimit-Remaining、也不落盘配额。
# 后果是阶梯扫描（一次 12+ 个请求，最费配额的路径）**最容易撞 10 次/分钟**，
# 撞了就中断，而它的固定 sleep 只是猜间隔、不是读配额——相邻两个词若命中
# 缓存，那 12 秒也是白等。改用 _http 后与其他引擎同一套节流与缓存。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _http  # noqa: E402

# 收窄修饰语：把宽词切到具体人群/场景/动作。这些是通用维度，不猜具体行业。
MODIFIERS = [
    # 具体人群/场景：收窄的主力，越具体越可能找到没被做烂的战场
    "for small business", "for freelancers", "for teachers", "for contractors",
    "for restaurants", "for clinics", "for landlords", "for nonprofits",
    "for photographers", "for consultants", "for salons",
    # 动作/形态
    "template", "generator", "export", "automation", "tracker", "ocr",
]

# 供给分档（GitHub 仓库数），与 global_scan 保持一致
GH_TIERS = [
    (20000, "红海"), (5000, "高"), (1500, "中"), (300, "低"), (0, "极低"),
]


def gh_count(kw):
    u = ("https://api.github.com/search/repositories?q="
         + urllib.parse.quote(kw) + "&per_page=1")
    return json.loads(_http.fetch(u, timeout=20)).get("total_count", 0)


def autocomplete(kw):
    q = urllib.parse.quote(kw)
    out = []
    for url, pick in [
        (f"https://suggestqueries.google.com/complete/search?client=firefox&q={q}",
         lambda d: d[1]),
        (f"https://api.bing.com/osjson.aspx?query={q}", lambda d: d[1]),
    ]:
        try:
            d = json.loads(_http.fetch(url, timeout=12, tries=1))
            out.extend(pick(d) or [])
        except Exception:                                    # noqa: BLE001
            pass
    seen, uniq = set(), []
    for w in out:
        w = (w or "").strip()
        if w and w.lower() != kw.lower() and w.lower() not in seen:
            seen.add(w.lower())
            uniq.append(w)
    return uniq


def tier(n):
    for t, label in GH_TIERS:
        if n >= t:
            return label
    return "未知"


def build_candidates(kw):
    """两级候选：模板 + 补全发现。补全词优先（它们真实存在）。

    品牌噪声过滤：补全列表里的**单词**条目几乎总是品牌名
    （invoicenow、receiptify）。这些品牌的衍生词（invoicenow iras）也要一起
    排除，否则会霸占"最窄"位置——品牌词对应的不是市场，是某家公司的产品线。
    """
    ac = autocomplete(kw)
    brands = {w.lower() for w in ac
              if len(w.split()) == 1 and w.lower() != kw.lower()}

    cands = [f"{kw} {m}" for m in MODIFIERS]
    for w in ac[:12]:
        low = w.lower()
        if len(w.split()) < 2:
            continue
        if any(low.startswith(b) for b in brands):   # 品牌的衍生词
            continue
        if any(b in low for b in ("meaning", "pronunciation", "in chinese",
                                  " vs ", "definition")):
            continue
        cands.append(w)

    seen, uniq = set(), []
    for c in cands:
        lc = c.lower()
        if lc not in seen and lc != kw.lower():
            seen.add(lc)
            uniq.append(c)
    return uniq


def scan(kw, top=8, gap=None, limit=12):
    if gap is None:
        import os
        has_tok = bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
        # GitHub 未授权搜索限流约 10 次/分钟，必须留足间隔，否则会被限流并拖慢
        gap = 7.0 if has_tok else 12.0
    base = gh_count(kw)
    time.sleep(gap)
    cands = build_candidates(kw)[:limit]
    print(f"[ladder] {kw}: 测 {len(cands)} 个候选，每个间隔 {gap:.0f}s，"
          f"预计 {len(cands)*gap/60:.1f} 分钟", file=sys.stderr, flush=True)
    rows = []
    aborted = None
    for i, c in enumerate(cands):
        try:
            n = gh_count(c)
            rows.append({"term": c, "repos": n, "tier": tier(n),
                         "vs_base": (base / n) if n else float("inf")})
        except Exception as e:                               # noqa: BLE001
            # 被限流就停止，不要对剩余每个候选再各试一遍——那会把耗时放大数倍
            aborted = f"测到第 {i+1}/{len(cands)} 个时被限流（{type(e).__name__}）"
            break
        time.sleep(gap)
    # 关键过滤：0 仓库不代表「处女地」，代表「这个词没人用」。
    # 真正的窄口是有一定供给（说明需求被承认）但显著少于原词。
    rows = [r for r in rows if r.get("repos") is not None and r["repos"] >= 3]
    rows.sort(key=lambda r: r["repos"])
    return {"seed": kw, "seed_repos": base, "seed_tier": tier(base),
            "rows": rows[:top], "tested": len(rows),
            "candidates": len(cands), "aborted": aborted}


def render(r):
    L = [f"\n{'='*72}",
         f"🪜 {r['seed']}    收窄阶梯",
         f"{'='*72}",
         f"原词：{r['seed_repos']:,} 个 GitHub 仓库 [{r['seed_tier']}]"
         f"（测了 {r['tested']}/{r.get('candidates','?')} 个变体）",
         ""]
    if r.get("aborted"):
        L.append(f"  ⚠️ {r['aborted']}，结果不完整。")
        L.append("     冷却约 1 分钟后重跑，或设置 GITHUB_TOKEN 提速 3 倍。")
        L.append("")
    if not r["rows"]:
        L.append("  没有测到可用变体（可能被限流）")
        return "\n".join(L)
    L.append(f"{'变体':<38}{'仓库数':>9}  {'档位':<5}{'比原词窄':>9}")
    L.append("-" * 72)
    for x in r["rows"]:
        v = x["vs_base"]
        vs = "—" if v == float("inf") else (f"{v:.1f}x" if v >= 1 else f"{1/v:.1f}x 更宽")
        L.append(f"{x['term'][:37]:<38}{x['repos']:>9,}  {x['tier']:<5}{vs:>9}")
    best = r["rows"][0]
    L.append("")
    L.append(f"最窄变体  「{best['term']}」 {best['repos']:,} 仓库 [{best['tier']}]")
    if best["repos"] and r["seed_repos"]:
        L.append(f"         比原词窄 {r['seed_repos']/best['repos']:.1f} 倍")
    L.append("")
    L.append("怎么用这个结果：")
    L.append("  · 不要问「这个方向是不是红海」，要问「这个词是不是红海」")
    L.append("  · 同一个需求换一个更窄的词，战场可能小十倍")
    L.append("  · 挑最上面的 2-3 个，用 global_scan.py 跑完整裁决（含 App Store）")
    L.append("  · 窄 ≠ 好：还要确认那个窄口真的有人付钱，见 SKILL.md 付费验证")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="收窄阶梯")
    ap.add_argument("keywords", nargs="+")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--limit", type=int, default=12,
                    help="最多测多少个候选变体（每个约 12s，默认 12 个≈2.5 分钟）")
    ap.add_argument("--gap", type=float, default=None,
                    help="请求间隔秒数，默认自适应（无 token 12s / 有 token 7s）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    out = []
    for i, kw in enumerate(a.keywords):
        if i:
            time.sleep(2)
        out.append(scan(kw, a.top, a.gap, a.limit))

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    for r in out:
        print(render(r))


if __name__ == "__main__":
    main()
