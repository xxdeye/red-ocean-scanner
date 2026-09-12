#!/usr/bin/env python3
"""Red Ocean Scanner — Global engine / 全球市场引擎

判断一个产品方向在英文（全球）市场该不该做。中文市场请用 red_ocean_scan.py。

═══════════════════════════════════════════════════════════════════
设计原则：宁可漏判，不可误判。
一个会给出错误绿灯的工具，比没有工具更糟。因此本引擎只把**可验证**的
信号计入评分，噪声信号一律降级为「参考」并明确标注。
═══════════════════════════════════════════════════════════════════

信号分级（实测得出，不是猜的）：

  可靠信号 ── 计入评分
    · GitHub 仓库数        供给密度，4000 倍量级区分度（todo 90k vs 兽医 117）
    · 头部仓库 star 分布    是否已有强势玩家/免费替代品

  噪声信号 ── 仅作参考，不计分
    · StackOverflow 搜索    模糊匹配，噪声极大。实测 "invoice excel" 会匹配到
                           Automapper 问题，"funeral home management" 匹配到
                           UIPickerView 问题。不可用作需求代理。
    · GitHub issues         混合了 bug 报告与功能请求，需人工读标题判断。

不可访问（本环境实测）：
  Google / Reddit / DuckDuckGo / Wikipedia / Product Hunt / G2 / Capterra
  全部网络不可达或被 Cloudflare 拦截。因此本引擎**看不到消费级市场**，
  这是明确的局限，不是可以绕过的实现细节。

用法:
  python3 global_scan.py "keyword1" "keyword2"
  python3 global_scan.py --json "keyword"
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


# ── 跨平台 UTF-8 ────────────────────────────────────────────
# 脚本输出含中文与 emoji，Windows 默认 cp1252 控制台会直接抛
# UnicodeEncodeError。在任何输出发生前把流切到 UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):   # 非 TTY 或被重定向的旧环境
    pass


UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# GitHub 搜索限流：未授权 10 次/分钟，带 token 30 次/分钟。
# 每次扫描打 2 个端点，所以两者词间冷却差 3 倍。
# 设置 GITHUB_TOKEN 或 GH_TOKEN 环境变量即可自动提速，不需要改代码。
GH_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
GH_GAP = 2.5
KW_GAP = 7.0 if GH_TOKEN else 22.0

# 供给分档：用真实采样校准
#   todo list app 90582 / habit tracker 60478 / invoice excel 2262
#   sports team scheduling 331 / veterinary clinic 117 / funeral home 23
SUPPLY_TIERS = [
    (20000, "红海", 0),
    (5000, "高", 0),
    (1500, "中", 1),
    (300, "低", 3),
    (0, "极低", 3),
]

MONOPOLY_STARS = 2000      # 超过此 star 说明已有强势开源替代品
WEAK_LEADER_STARS = 50     # 头部低于此 star 说明没有真正的赢家


class FetchError(Exception):
    pass


class RateLimited(FetchError):
    pass


def get_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            hdrs = {"User-Agent": UA, "Accept": "application/json"}
            if GH_TOKEN:
                hdrs["Authorization"] = f"Bearer {GH_TOKEN}"
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                last = RateLimited(f"HTTP {e.code} 限流")
                time.sleep(25 * (i + 1))
                continue
            last = FetchError(f"HTTP {e.code}")
            break
        except Exception as e:                          # noqa: BLE001
            last = FetchError(str(e))
            time.sleep(3)
    raise last


def gh_repos(kw):
    d = get_json("https://api.github.com/search/repositories?q="
                 + urllib.parse.quote(kw) + "&per_page=10")
    items = d.get("items", [])
    stars = [i.get("stargazers_count", 0) for i in items]
    return {
        "total": d.get("total_count", 0),
        "max_stars": max(stars) if stars else 0,
        "top": [(i.get("full_name", ""), i.get("stargazers_count", 0),
                 (i.get("description") or "")[:58]) for i in items[:4]],
    }


def gh_issues(kw):
    """仅作参考。标题含关键词才算，避免完全跑题的匹配。"""
    d = get_json("https://api.github.com/search/issues?q="
                 + urllib.parse.quote(kw) + "+in:title&per_page=10")
    items = d.get("items", [])
    toks = [t for t in re.split(r"\W+", kw.lower()) if len(t) > 3]
    rel = [i for i in items
           if not toks or any(t in (i.get("title") or "").lower() for t in toks)]
    return {
        "total": d.get("total_count", 0),
        "open": sum(1 for i in items if i.get("state") == "open"),
        "relevant": len(rel),
        "top": [(i.get("title") or "")[:66] for i in rel[:3]],
    }


def tier_of(n):
    for thresh, label, pts in SUPPLY_TIERS:
        if n >= thresh:
            return label, pts
    return "未知", 0


def scan(kw):
    r = {"keyword": kw, "engine": "global", "deadly": [], "signals": [], "notes": []}

    try:
        repos = gh_repos(kw)
        r["repos"] = repos
        r["supply_tier"] = tier_of(repos["total"])[0]
    except FetchError as e:
        r.update(repos=None, supply_tier="未测到", score=None, verdict="黄(不完整)")
        r["deadly"].append(f"供给数据未取到（{e}）——本结论不完整，不要据此决定")
        return r
    time.sleep(GH_GAP)

    try:
        r["issues"] = gh_issues(kw)
    except FetchError as e:
        r["issues"] = None
        r["notes"].append(f"issue 数据未取到（{e}），仅供参考的该项缺失")

    # ── 打分 ────────────────────────────────────────────
    # 三个独立维度相加，不互相抢分：
    #   供给稀缺 0-4 + 无强势玩家 0-3 + 发布通路 0-3
    # 前两项来自可靠信号；第三项是结构性事实（有没有可用的分发渠道），
    # 不是从噪声数据猜出来的。
    s = 0
    n, mx = repos["total"], repos["max_stars"]

    # 供给稀缺（0-4）
    if n < 300:
        s += 4
        r["signals"].append(f"GitHub 仅 {n} 个仓库 → 开发者生态几乎没有覆盖")
    elif n < 1500:
        s += 3
        r["signals"].append(f"GitHub {n} 个仓库 → 供给稀薄")
    elif n < 5000:
        s += 2
        r["signals"].append(f"GitHub {n} 个仓库 → 中等竞争，需要明确差异化")
    elif n < 20000:
        s += 1
        r["signals"].append(f"GitHub {n} 个仓库 → 竞争密集")
    else:
        r["signals"].append(f"GitHub {n} 个仓库 → 严重饱和")

    # 无强势玩家（0-3）
    if mx >= MONOPOLY_STARS:
        r["deadly"].append(
            f"头部仓库 {mx}★ → 已有成熟开源替代品。开源会压制付费意愿，"
            f"除非你的买家是企业而不是开发者")
    elif mx < WEAK_LEADER_STARS and n < 3000:
        s += 3
        r["signals"].append(
            f"头部仅 {mx}★ → 没有赢家。需求存在但没人做好，缺口的典型形态")
    elif mx < 300:
        s += 2
        r["signals"].append(f"头部仅 {mx}★ → 没有强势玩家")
    elif mx < MONOPOLY_STARS:
        s += 1
        r["signals"].append(f"头部 {mx}★ → 有玩家但未形成垄断")

    # 发布通路（0-3）：结构性判断，与数据噪声无关
    r["channels"] = {
        "developer": "GitHub / npm / PyPI / VS Code 市场 —— 零成本、可搜索",
        "business": "行业垂直社区 / LinkedIn / 冷邮件 —— 需人工触达",
        "consumer": "应用商店 / 社交平台 —— 获客成本高，本引擎无法评估",
    }
    r["scoring_note"] = ("本分数只反映**供给健康度**（有没有人做、有没有人守），"
                         "不反映需求大小。需求必须人工验证。")
    s += 2   # 中性基准：任何方向都有某种通路，差异留给人工判断

    if n >= 20000:
        r["deadly"].append("仓库数达五位数 → 红海，不要靠加功能挽救")

    r["score"] = max(0, min(10, s))

    # 需求侧全部降级为参考
    if r.get("issues") and r["issues"]["relevant"]:
        r["notes"].append(
            f"参考（不计分）：{r['issues']['relevant']}/{r['issues']['total']} 条 "
            f"issue 标题含关键词，需人工读判断是 bug 还是功能请求")
    r["notes"].append(
        "参考（不计分）：StackOverflow 匹配噪声过大，本引擎已停用该信号")
    r["notes"].append(
        "参考（不计分）：消费级需求无法从本引擎获得——Google/Reddit 在本环境不可达")

    if r["score"] >= 8:
        r["verdict"] = "绿"
    elif r["score"] >= 5:
        r["verdict"] = "黄"
    else:
        r["verdict"] = "红"
    return r


def render(r):
    icon = {"绿": "🟢", "黄": "🟡", "红": "🔴"}.get(r["verdict"], "🟡")
    sc = "—" if r.get("score") is None else r["score"]
    L = [f"\n{'='*68}",
         f"{icon} {r['keyword']}    {r['verdict']}    {sc}/10   [global]",
         f"{'='*68}"]
    if r.get("repos"):
        L.append(f"供给  GitHub {r['repos']['total']} 仓库 [{r['supply_tier']}]"
                 f"，头部 {r['repos']['max_stars']}★")
        for name, st, desc in r["repos"]["top"]:
            L.append(f"        {st:>6}★ {name} — {desc}")
    else:
        L.append("供给  未测到")
    if r.get("issues"):
        L.append(f"参考  GitHub issues {r['issues']['total']} 条"
                 f"（{r['issues']['open']} 未关闭，{r['issues']['relevant']} 条疑似相关）")
        for t in r["issues"]["top"][:2]:
            L.append(f"        · {t}")
    if r["signals"]:
        L.append("依据")
        for x in r["signals"]:
            L.append(f"      + {x}")
    if r["deadly"]:
        L.append("否决项")
        for x in r["deadly"]:
            L.append(f"      − {x}")
    if r["notes"]:
        L.append("局限")
        for x in r["notes"]:
            L.append(f"      ! {x}")
    L.append("下一步  " + next_step(r))
    return "\n".join(L)


def next_step(r):
    v = r["verdict"]
    if v == "绿":
        return ("GitHub 供给稀薄只证明没人做，不证明有人买。去该行业的垂直社区"
                "（如兽医用 Facebook 群 / 行业论坛）读真实抱怨，再挂落地页收邮箱。")
    if v == "黄":
        return "换更窄的场景词重扫（例：'veterinary clinic scheduling' 而非 'scheduling'）。"
    if v.startswith("黄"):
        return "数据不完整，稍后重跑，不要在此结论上做决定。"
    return "放弃。不要试图靠加功能挽救一个饱和方向。"


def main():
    ap = argparse.ArgumentParser(description="Red Ocean Scanner — Global engine")
    ap.add_argument("keywords", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gap", type=float, default=KW_GAP,
                    help="词间冷却秒数（被统一入口调用时由调度器覆盖）")
    a = ap.parse_args()

    res = []
    for i, kw in enumerate(a.keywords):
        if i:
            time.sleep(a.gap)
        res.append(scan(kw))

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    for r in res:
        print(render(r))
    if len(res) > 1:
        print(f"\n{'='*68}\n排名（分高者优先）")
        for i, r in enumerate(sorted(res, key=lambda x: -(x.get("score") or 0)), 1):
            print(f"  {i}. {str(r.get('score')):>2}/10  {r['verdict']:<9} {r['keyword']}")


if __name__ == "__main__":
    main()
