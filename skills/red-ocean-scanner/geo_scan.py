#!/usr/bin/env python3
"""地理套利扫描 / Geographic arbitrage scan

找一个方向在哪个国家/地区还没被做烂。

原理：同一个需求在不同 App Store 地区的饱和度可以差几百倍。实测
  invoice        美国头部 265,331 评 → 中国头部 193 评（差 1,374 倍）
  receipt scanner 美国 7,642,608 → 中国 18,311（差 417 倍）
这不是"中国市场落后"，而是**同一个产品概念在不同市场的竞争结构完全不同**——
往往因为本地化、支付、税务、语言形成了天然壁垒。

输出：成熟市场（验证需求真实存在）+ 空白市场（竞争真空）。
两者结合才是机会：**需求已被别处证明，本地还没人做。**

重要警告：低评价数有两种完全相反的原因
  ① 竞争真空（好机会）
  ② 没人有智能手机/不用这类工具（伪机会）
本工具用「同地区全品类基准」区分二者，见 --benchmark。

用法:
  python3 geo_scan.py "invoice"
  python3 geo_scan.py --regions us,cn,jp "habit tracker"
  python3 geo_scan.py --json "receipt scanner"
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# 生态基准 App：用它们在各地的评价量级，代表该地区 App 生态的整体规模。
# 归一化 = 目标品类头部评价数 / 该地区生态基准。
# 这样比较的是「相对本地生态的饱和度」，而不是绝对数字——绝对数字会骗人：
# 中国 receipt scanner 头部 18,311 评，看着比巴西 todo app 的 34,919 小，
# 但巴西 todo 相对本地生态是 0.0031、中国 receipt 是 0.0009，结论相反。
BASE_APPS = ["whatsapp", "facebook", "instagram"]

REGIONS = [
    ("us", "美国"), ("gb", "英国"), ("de", "德国"), ("fr", "法国"),
    ("jp", "日本"), ("kr", "韩国"), ("cn", "中国"), ("in", "印度"),
    ("br", "巴西"), ("ru", "俄罗斯"), ("id", "印尼"), ("mx", "墨西哥"),
    ("au", "澳洲"), ("ca", "加拿大"), ("es", "西班牙"), ("it", "意大利"),
]


def ecosystem_base(country):
    """该地区 App 生态基准 = 头部热门 App 的最高评价数。"""
    best = 0
    for a in BASE_APPS:
        try:
            best = max(best, app_stats(a, country)["top"])
        except Exception:                                    # noqa: BLE001
            pass
        time.sleep(0.3)
    return best or 1


def app_stats(kw, country):
    u = ("https://itunes.apple.com/search?term=" + urllib.parse.quote(kw)
         + f"&entity=software&limit=25&country={country}")
    req = urllib.request.Request(u, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode("utf-8", "ignore"))
    apps = d.get("results", [])
    ratings = [(a.get("userRatingCount", 0) or 0) for a in apps]
    return {
        "apps": len(apps),
        "top": max(ratings) if ratings else 0,
        "sum": sum(ratings),
        "avg_rating": (sum(a.get("averageUserRating", 0) or 0 for a in apps)
                       / len(apps)) if apps else 0,
        "paid": sum(1 for a in apps
                    if (a.get("formattedPrice") or "Free") != "Free"),
    }


def scan(kw, regions=None, min_size=1000):
    codes = [c for c, _ in REGIONS if not regions or c in regions]
    names = dict(REGIONS)
    res = {}
    for c in codes:
        try:
            res[c] = app_stats(kw, c)
        except Exception as e:                              # noqa: BLE001
            res[c] = {"error": type(e).__name__}
        time.sleep(0.45)

    ok = {c: v for c, v in res.items() if "top" in v}
    if not ok:
        return {"keyword": kw, "regions": res, "error": "所有地区均取数失败"}

    # 归一化：相对本地生态的饱和度
    for c in ok:
        base = ecosystem_base(c)
        ok[c]["base"] = base
        ok[c]["norm"] = ok[c]["top"] / base if base else 0

    # 成熟市场 = 归一化饱和度最高的地区（需求在该生态里被充分验证）
    mature = max(ok, key=lambda c: ok[c]["norm"])
    mt, mn = ok[mature]["top"], ok[mature]["norm"]

    # 空白市场 = 归一化饱和度最低，且绝对量不至于小到「市场不存在」。
    # 用归一化而非绝对量：绝对量会同时误判两个方向——
    #   · 把「小市场里的正常品类」当成机会（巴西 todo app 34,919 评）
    #   · 把「大市场里的真空白」当成没市场（中国 receipt 18,311 评）
    viable = [(c, v) for c, v in ok.items()
              if c != mature and v["top"] >= min_size]
    if viable:
        blank, bv = min(viable, key=lambda kv: kv[1]["norm"])
        bt, bn = bv["top"], bv["norm"]
        ratio = (mn / bn) if bn else float("inf")
        if ratio >= 20:
            verdict = "✅ 强套利信号：需求在成熟市场被验证，该市场相对本地生态几乎无竞争"
        elif ratio >= 8:
            verdict = "🔸 中等套利信号：差距明显，但仍需核实本地化成本"
        elif ratio >= 3:
            verdict = "🔸 弱套利信号：有差距但不悬殊"
        else:
            verdict = "❌ 无套利：各地区相对竞争程度接近"
    else:
        under = [(c, v) for c, v in ok.items()
                 if c != mature and v["top"] < min_size]
        blank, bv = (min(under, key=lambda kv: kv[1]["norm"]) if under
                     else (mature, ok[mature]))
        bt, bn = bv["top"], bv["norm"]
        ratio = (mn / bn) if bn else float("inf")
        verdict = (f"⚠️ 其他市场头部评价数均低于 {min_size:,}。"
                   f"差距可能存在，但绝对规模太小，很可能是市场不存在而非竞争真空")

    return {
        "keyword": kw, "regions": res, "mature": mature, "blank": blank,
        "mature_name": names.get(mature, mature), "blank_name": names.get(blank, blank),
        "mature_top": mt, "blank_top": bt, "ratio": ratio,
        "mature_norm": mn, "blank_norm": bn,
        "min_size": min_size,
        "arbitrage_verdict": verdict,
    }


def render(r):
    L = [f"\n{'='*70}",
         f"🌍 {r['keyword']}    地理套利扫描", f"{'='*70}"]
    if "error" in r and r.get("error"):
        L.append(f"  {r['error']}")
        return "\n".join(L)
    ok = {c: v for c, v in r["regions"].items() if "top" in v}
    mx = max(v["norm"] for v in ok.values()) or 1
    L.append("地区饱和度（头部 App 评价数 / 本地生态基准，越低越不饱和）")
    name_of = {c: n for c, n in REGIONS}
    for c, _ in REGIONS:
        v = r["regions"].get(c)
        if not v or "top" not in v:
            continue
        bar = "█" * max(1, int(26 * v["norm"] / mx))
        star = ""
        if c == r["mature"]:
            star = "  ← 成熟市场"
        elif c == r["blank"]:
            star = "  ← 空白市场"
        L.append(f"  {name_of.get(c,c):4}({c}) {v['top']:>10,} 评 "
                 f"归一 {v['norm']:.4f} {bar}{star}")
    L.append("")
    L.append(f"成熟市场  {r['mature_name']}  {r['mature_top']:,} 条评价"
             f"（归一 {r.get('mature_norm',0):.4f}，需求已被验证）")
    L.append(f"空白市场  {r['blank_name']}  {r['blank_top']:,} 条评价"
             f"（归一 {r.get('blank_norm',0):.4f}，相对本地生态竞争稀薄）")
    L.append(f"差距倍数  {r['ratio']:,.0f}x（按归一化饱和度，非绝对评价数）")
    L.append(f"裁决      {r['arbitrage_verdict']}")
    L.append("")
    L.append("为什么用归一化：绝对值会同时误判两个方向——把小市场里的正常品类")
    L.append("当成机会，也把大市场里的真空白当成没市场。比值必须相对本地生态。")
    L.append("")
    L.append("下一步  这不是「抄一个 App 搬到小市场」那么简单——")
    L.append("        先确认空白市场的壁垒是什么（语言/支付/税务/渠道），")
    L.append("        壁垒既是它没被做烂的原因，也是你要跨过的成本。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="地理套利扫描")
    ap.add_argument("keywords", nargs="+")
    ap.add_argument("--regions", help="逗号分隔的地区代码，默认全部")
    ap.add_argument("--min-size", type=int, default=1000,
                    help="空白市场的头部评价数下限，低于此视为市场不存在")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    regs = a.regions.split(",") if a.regions else None
    out = []
    for i, kw in enumerate(a.keywords):
        if i:
            time.sleep(2)
        out.append(scan(kw, regs, a.min_size))

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    for r in out:
        print(render(r))
    ranked = [r for r in out if r.get("ratio")]
    if len(ranked) > 1:
        print(f"\n{'='*70}\n按套利差距排名")
        for i, r in enumerate(sorted(ranked, key=lambda x: -x["ratio"]), 1):
            print(f"  {i}. {r['ratio']:>8,.0f}x  {r['keyword']}"
                  f"  ({r['mature_name']} → {r['blank_name']})")


if __name__ == "__main__":
    main()
