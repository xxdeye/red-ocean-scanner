#!/usr/bin/env python3
"""Red Ocean Scanner / 避红海扫描器

一条命令判断一个方向该不该做。

双源交叉验证：
  需求 = 360搜索(so.com) 的「相关搜索」词，真实搜索行为
  供给 = 搜狗微信(weixin.sogou.com) 的文章存量 + 标题信号

输出：红黄绿裁决 + 证据 + 决策依据。

用法:
  python3 red_ocean_scan.py "关键词1" "关键词2" ...
  python3 red_ocean_scan.py --report report.md "关键词"
  python3 red_ocean_scan.py --json "关键词"

限流：搜狗微信连续请求会静默返回空。本脚本会检测并退避重试，
绝不把「被限流」当成「无人竞争」——那是会得出相反结论的错误。

依赖：仅 Python 3.8+ 标准库，无需 pip install。
"""
import argparse
import html
import json
import os
import re
import sys
import time
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

# ── 信号词典 ────────────────────────────────────────────────
# 高购买意图：想找工具 / 在算预算，而不是想学知识
INTENT = (r"工具|软件|推荐|哪个好|批量|一键|自动|插件|小程序|专业版|企业版"
          r"|多少钱|价格|收费|报价|费用|成本|价目|明细表|对比|排行|十大")
# 白嫖意图：在找免费替代品的人不会付钱
FREEBIE = r"免费|破解|永久免费|白嫖|不用钱|绿色版|不要钱"
# 纯知识问法：在问「怎么做/在哪/什么意思」，不是在找工具。
# 补全词里这类占比很高（实测「发票批量导出」10 条高意图里 4 条是纯问法），
# 不排除的话高意图计数会被问句灌水、把需求档位抬高一档。
#
# **「多少」不在这里**：《多少钱》《报价多少》是 B2B 的强购买意图
# （用户在算预算），engine-cn.md 把它列为正信号。若按通用问法一并剔除，
# 会把 B2B 方向的价格信号全部误杀——那正好是最值钱的那类词。
KNOWLEDGE = (r"怎么|如何|是什么|什么是|为什么|哪里|在哪|哪些|多久"
             r"|能不能|可以吗|教程|入门|区别|含义|意思|步骤|流程|方法")
# 垄断品牌：该搜索词已被强势产品占死
BRAND = r"豆包|讯飞|剪映|通义|文心|鲁青|金蝶|用友|钉钉|飞书|腾讯文档|金山"

TITLE_SIGNALS = [
    ("已有付费工具", r"神器|助手|软件|一键|工具推荐|下载|破解|绿色版|安装包|会员|发布|内测"),
    ("已有人自己做出来", r"我(用|写|做|开发)了|自己(做|写|开发)|vibecod|cursor|claude|一行代码|源码|手把手教你做"),
    ("教程/怎么用", r"怎么|如何|教程|方法|步骤|指引|攻略|入门|教学|操作|技巧"),
    ("官方/机构发文", r"税务|社保局|公积金|官方|政策|通知|公告|人社|医保局"),
    ("纯内容/观点", r"为什么|揭秘|真相|思考|趋势|盘点|误区|指南"),
]


# HTTP 层统一交给 _http：磁盘缓存 + 主动限流。
# 中文源实测边界：360 与搜狗都不给 Retry-After，但搜狗在 2s 间隔下
# 连打 6+ 次无碍；搜狗被限流时返回**空页面而非报错**，所以必须把
# 「空响应」当限流处理，绝不能读成「存量 0 篇」。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _http  # noqa: E402

RateLimited = _http.RateLimited


def fetch(url, tries=3, backoff=25):
    """取数据。有效性判定（壳页/验证码/长度门槛）统一在 _http 里按源做。

    这里**不再**做统一的长度检查：早期用 `len(body) <= 500`
    一刀切，会把 360 补全接口的完整响应（约 460B）判成风控而丢弃。
    长度下限必须按源给——搜狗 8000B、360 SERP 2000B、360 补全 100B。
    """
    return _http.fetch(url, timeout=20, tries=tries, backoff=backoff)


def tier(n):
    if n is None:
        return "未知"
    if n < 500:
        return "极低"
    if n < 1500:
        return "低"
    if n < 3500:
        return "中"
    if n < 6000:
        return "高"
    return "红海"


def so_related(kw):
    """360 的相关搜索 = 真实需求长尾"""
    s = fetch("https://www.so.com/s?q=" + urllib.parse.quote(kw))
    m = re.search(r'<table class="rs-table">(.*?)</table>', s, re.S)
    words = []
    if m:
        for a in re.findall(r"<a[^>]*>(.*?)</a>", m.group(1), re.S):
            t = html.unescape(re.sub(r"<[^>]+>", "", a)).strip()
            if t and len(t) > 1:
                words.append(t)
    return list(dict.fromkeys(words))


def so_suggest(kw):
    """360 补全接口 = 用户正在输入的查询（需求长尾的第二来源）。

    为什么要加它：相关搜索表是「实体词」（怎么写、模板），补全词是
    「查询原句」（软件哪个好用、工具在哪）。实测两者的高意图覆盖不同：
      录音转文字    相关搜索 1 条 vs 补全 5 条
      公众号排版    相关搜索 1 条 vs 补全 2 条（且这 2 条是相关搜索没有的）
    更关键的是：相关搜索偶发取不到时，旧实现会直接判「没有相关搜索词
    → 基本没人在搜，这是最危险的信号」——一个**假警报**。补全源可用时
    就不该报这个。
    """
    s = fetch("https://sug.so.360.cn/suggest?word=" + urllib.parse.quote(kw))
    try:
        d = json.loads(s)
    except ValueError:
        raise RateLimited("补全响应不是 JSON，疑似风控")
    if d.get("errorcode") not in (0, "0", None):
        raise RateLimited(f"补全接口返回 errorcode={d.get('errorcode')}")
    return [x.get("word", "").strip() for x in d.get("result", [])
            if x.get("word", "").strip()]


def wechat(kw):
    """搜狗微信 = 供给存量 + 标题信号"""
    s = fetch("https://weixin.sogou.com/weixin?type=2&query=" + urllib.parse.quote(kw))
    m = re.search(r"找到约\s*([\d,]+)\s*条结果", s)
    if not m and "找到约" not in s and "结果" not in s:
        raise RateLimited("页面无结果标记，疑似风控")
    cnt = int(m.group(1).replace(",", "")) if m else 0
    titles = [
        html.unescape(re.sub(r"<[^>]+>", "", t)).strip().replace("_", "")
        for t in re.findall(r"<h3>\s*<a[^>]*>(.*?)</a>", s, re.S)
    ]
    titles = [t for t in titles if t]
    sig = {}
    for name, pat in TITLE_SIGNALS:
        n = sum(1 for t in titles if re.search(pat, t, re.I))
        if n:
            sig[name] = n
    return cnt, titles, sig


def scan(kw):
    """返回一条完整裁决"""
    r = {"keyword": kw, "blockers": [], "evidence": [],
         # 先置空再按需覆盖：否则 JSON 输出的字段随成败变化，
         # 下游按固定字段解析就会在有/无错误两种情况下拿到不同结构。
         "error_demand": None, "error_suggest": None}
    rel = related = []
    try:
        related = so_related(kw)
    except Exception as e:                          # noqa: BLE001
        r["error_demand"] = f"需求源失败: {e}"
    r["related_searches"] = related

    # 第二需求源：360 补全。**只在相关搜索为空时并入**——
    # 评分阈值（高意图 ≥4 满分 / ≥2 得 3 分）是按相关搜索的词数校准的，
    # 两个源直接合并会把计数灌大（实测「发票批量导出」8 → 18 条，
    # 虚增一档）。所以它的职责是**补盲**，不是加码。
    time.sleep(2)
    suggests = []
    try:
        suggests = so_suggest(kw)
    except Exception as e:                          # noqa: BLE001
        r["error_suggest"] = f"补全源失败: {e}"
    r["suggestions"] = suggests
    r["demand_source"] = "相关搜索+补全" if suggests else "相关搜索"

    time.sleep(3)
    try:
        cnt, titles, sig = wechat(kw)
        r.update(wechat_articles=cnt, supply_tier=tier(cnt),
                 top_titles=titles[:6], signals=sig)
    except RateLimited as e:
        r["error_supply"] = f"供给源被限流: {e}"
        r["wechat_articles"] = None
        r["supply_tier"] = "未测到"
        r["signals"] = {}
        r["blockers"].append("供给侧未取到数据（限流），本结论不完整")
    except Exception as e:                          # noqa: BLE001
        r["error_supply"] = str(e)
        r["wechat_articles"] = None
        r["supply_tier"] = "未测到"
        r["signals"] = {}
        r["blockers"].append("供给侧未取到数据，本结论不完整")

    # ── 打分 ────────────────────────────────────────────
    cnt = r.get("wechat_articles")
    sig = r.get("signals", {})
    # 需求词的取用顺序：相关搜索优先；为空才退回补全。
    # 补全里纯问法（怎么写/在哪/什么意思）占比高，先剔除再数高意图。
    pool = related or suggests
    r["demand_used"] = ("相关搜索" if related else
                        ("补全（相关搜索为空，已降级）" if suggests else "无"))
    hi = [w for w in pool if re.search(INTENT, w) and not re.search(KNOWLEDGE, w)]
    fb = [w for w in pool if re.search(FREEBIE, w)]
    br = [w for w in pool if re.search(BRAND, w)]
    r["high_intent"] = hi
    r["freebie"] = fb
    r["brand"] = br
    if not related and suggests:
        r["evidence"].append(
            f"相关搜索为空，需求改用 360 补全词（{len(suggests)} 条，"
            f"{len(hi)} 条高意图）——不是「没人搜」，是相关搜索表没出词")

    s = 0
    # 供给 (3)
    if cnt is not None:
        s += 3 if cnt < 1500 else (1 if cnt < 3500 else 0)
    # 供给性质 (3)
    if "已有付费工具" in sig:
        s += 3
        r["evidence"].append("标题出现在售/可下载的工具 → 需求已被验证能收钱")
    elif "教程/怎么用" in sig:
        s += 2
        r["evidence"].append("标题以教程为主 → 需求真实但没人做出好工具，是缺口")
    elif sig:
        s += 1
    # 需求 (4)
    if pool:
        s += 4 if len(hi) >= 4 else (3 if len(hi) >= 2 else (2 if hi else 0))
        if hi:
            r["evidence"].append(f"{len(hi)} 条高购买意图长尾，例：《{hi[0]}》")
        else:
            know = [w for w in pool if re.search(KNOWLEDGE, w)]
            if know:
                r["evidence"].append(
                    f"需求词全是问法（例：《{know[0]}》）→ 在找知识不在找工具，"
                    f"付费意愿存疑")
    else:
        s -= 2
        r["blockers"].append(
            "相关搜索与 360 补全都为空 → 基本没人在搜，这是最危险的信号")

    # ── 一票否决 ────────────────────────────────────────
    if len(fb) >= 4:
        s = min(s, 3)
        r["blockers"].append(
            f"{len(fb)} 条免费白嫖词（《{fb[0]}》）→ 用户要找免费替代品，不会付钱")
    elif len(fb) >= 2:
        s = min(s, 6)
        r["blockers"].append(f"{len(fb)} 条免费词，付费意愿被压制")
    if br:
        s = min(s, 4)
        r["blockers"].append(f"相关搜索出现垄断品牌《{br[0]}》→ 该词已被占位")
    if "已有人自己做出来" in sig:
        s = min(s, 3)
        r["blockers"].append(
            "标题出现「我自己做了/vibecoding」→ 开发壁垒已归零，你做完守不住")

    r["score"] = max(0, min(10, s))
    # 与全球引擎共用同一套裁决词表，避免两个引擎输出不同的符号
    # （全球引擎用 绿/红/🟠 + verdict_kind；这里保持一致）。
    # 中文引擎目前只有单一综合分，没有矩阵，所以 kind 按分数粗分。
    if r["score"] >= 8:
        r["verdict"], r["verdict_kind"] = "绿", "机会"
    elif r["score"] >= 5:
        r["verdict"], r["verdict_kind"] = "黄", "有硬伤"
    else:
        r["verdict"], r["verdict_kind"] = "红", "红海"
    if cnt is None:
        r["verdict"], r["verdict_kind"] = "黄(不完整)", "数据缺失"
    return r


def render(r):

    L = [f"\n{'='*66}",
         f"{r['verdict']}  {r['keyword']}    {r['score']}/10",
         f"{'='*66}"]
    if r.get("wechat_articles") is not None:
        L.append(f"供给  微信 {r['wechat_articles']} 篇 [{r['supply_tier']}]")
    else:
        L.append(f"供给  未测到（{r.get('error_supply','')}）")
    if r.get("signals"):
        L.append("      标题信号: " + " | ".join(f"{k}×{v}" for k, v in r["signals"].items()))
    if r.get("high_intent"):
        L.append(f"需求  高购买意图长尾 {len(r['high_intent'])} 条"
                 f"（来源：{r.get('demand_used','相关搜索')}）:")
        for w in r["high_intent"][:5]:
            L.append(f"        ★ {w[:54]}")
    else:
        L.append(f"需求  无高购买意图长尾（来源：{r.get('demand_used','相关搜索')}）")
    # 相关搜索为空、改用补全时，把补全原文列出来——它是这条裁决的唯一需求证据，
    # 不展示的话用户无法核对。
    if not r.get("related_searches") and r.get("suggestions"):
        L.append("      补全词样本: " +
                 " / ".join(w[:20] for w in r["suggestions"][:4]))
    if r.get("error_suggest"):
        L.append(f"      补全源不可用: {r['error_suggest'][:40]}")
    if r.get("freebie"):
        L.append(f"      免费白嫖词 {len(r['freebie'])} 条: " +
                 " / ".join(w[:22] for w in r["freebie"][:3]))
    if r.get("brand"):
        L.append(f"      垄断品牌: {' / '.join(w[:22] for w in r['brand'][:3])}")
    if r.get("top_titles"):
        L.append("      样本标题: " + r["top_titles"][0][:50])
    if r["evidence"]:
        L.append("依据")
        for e in r["evidence"]:
            L.append(f"      + {e}")
    if r["blockers"]:
        L.append("否决项")
        for b in r["blockers"]:
            L.append(f"      − {b}")
    L.append("下一步  " + next_step(r))
    return "\n".join(L)


def next_step(r):
    """按 verdict_kind 判断，不要用 verdict 字符串比较——
    它可能带「(不完整)」后缀，用 == 会把绿灯错判成红灯。"""
    kind = r.get("verdict_kind", "")
    if kind == "机会":
        return "去闲鱼搜该词，看有没有人在卖同类服务、价格、成交数。有人卖就开做。"
    if kind == "有硬伤":
        return "先别做。去闲鱼验证付费，或回到需求侧换更窄的关键词再扫一次。"
    if kind == "数据缺失":
        return "数据不完整，隔几分钟重跑一次，别在此结论上做决定。"
    return "放弃。不要试图靠加功能挽救一个红海方向。"


def main():
    ap = argparse.ArgumentParser(description="避红海扫描器")
    ap.add_argument("keywords", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--report", metavar="FILE")
    ap.add_argument("--gap", type=float, default=6.0,
                    help="词间冷却秒数（被统一入口调用时由调度器覆盖）")
    a = ap.parse_args()

    results = []
    for i, kw in enumerate(a.keywords):
        if i:
            time.sleep(a.gap)      # 词间冷却，降低触发风控概率
        results.append(scan(kw))

    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(render(r))
        ranked = sorted(results, key=lambda x: -x["score"])
        print(f"\n{'='*66}\n排名（分高者优先）")
        for i, r in enumerate(ranked, 1):
            print(f"  {i}. {r['score']:>2}/10  {r['verdict']:<16}"
                  f"{r.get('verdict_kind',''):<8} {r['keyword']}")

    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            f.write("# 避红海扫描报告\n\n")
            f.write("| 关键词 | 评分 | 裁决 | 微信存量 | 高意图长尾 | 否决项 |\n")
            f.write("|---|---|---|---|---|---|\n")
            for r in sorted(results, key=lambda x: -x["score"]):
                f.write(f"| {r['keyword']} | {r['score']}/10 | {r['verdict']} | "
                        f"{r.get('wechat_articles') or '-'} | {len(r.get('high_intent', []))} | "
                        f"{'；'.join(r['blockers'])[:80] or '-'} |\n")
            f.write("\n## 明细\n")
            for r in results:
                f.write(f"\n### {r['keyword']}\n\n")
                f.write(f"- 评分：{r['score']}/10（{r['verdict']}）\n")
                f.write(f"- 供给：{r.get('wechat_articles')} 篇 [{r.get('supply_tier')}]\n")
                if r.get("signals"):
                    f.write(f"- 标题信号：{r['signals']}\n")
                if r.get("high_intent"):
                    f.write("- 高购买意图长尾：" + "；".join(r["high_intent"][:8]) + "\n")
                if r.get("freebie"):
                    f.write("- 免费白嫖词：" + "；".join(r["freebie"]) + "\n")
                if r.get("brand"):
                    f.write("- 垄断品牌：" + "；".join(r["brand"]) + "\n")
                if r.get("blockers"):
                    f.write("- **否决项**：" + "；".join(r["blockers"]) + "\n")
                f.write(f"- 下一步：{next_step(r)}\n")
        print(f"\n报告已写入 {a.report}")


if __name__ == "__main__":
    main()
