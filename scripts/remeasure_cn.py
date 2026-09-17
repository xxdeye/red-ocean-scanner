#!/usr/bin/env python3
"""重测中文关键词，重新生成 docs/实测数据-中文.md。

为什么需要它：那份文档里的存量数字和评分是**某一时点的快照**，而微信存量、
相关搜索词、标题信号都在动——实测半年内 `摸鱼` 从 8,580 涨到 8,675，
`代账对账单` 从 511 涨到 558，个别关键词的评分已经对不上正文的结论。
文档里那句「用同一个脚本可以重跑验证」原本是空头支票，这个脚本把它兑现。

用法:
  python3 scripts/remeasure_cn.py                 # 全部关键词，写入 docs/
  python3 scripts/remeasure_cn.py --limit 3       # 只测前 3 个（快速抽查）
  python3 scripts/remeasure_cn.py --dry-run       # 只打印，不写文件

不打网络的测试不受影响；这个脚本必须联网。
"""
import argparse
import datetime
import pathlib
import re
import sys
import time
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "red-ocean-scanner"
sys.path.insert(0, str(SKILL))
import _http            # noqa: E402
import red_ocean_scan as R  # noqa: E402

# 与 docs/实测数据-中文.md 同一批关键词，便于逐行对照
KEYWORDS = [
    "代账公司对账单", "淘宝标题优化", "发票批量导出excel", "试卷排版工具",
    "公众号排版", "录音转文字", "图片批量加水印", "房贷提前还款计算器",
    "PDF批量提取", "进销存表格", "合同管理", "员工排班",
    "客户跟进记录", "库存预警", "报销单填写", "工资条生成",
    "网店对账", "投标文件检查",
]


def verdict_rank(r):
    """按裁决排序：机会 > 有硬伤 > 数据缺失 > 红海。"""
    order = {"机会": 0, "有硬伤": 1, "数据缺失": 2, "红海": 3}
    return (order.get(r.get("verdict_kind", ""), 9), -r.get("score", 0))


def measure(kw):
    t = time.time()
    r = R.scan(kw)
    r["_secs"] = time.time() - t
    return r


def table(rows):
    L = ["| 关键词 | 评分 | 裁决 | 微信存量 | 标题信号 | 高意图词 | 需求来源 |",
         "|---|---|---|---|---|---|---|"]
    for r in rows:
        sig = " ".join(f"{k}×{v}" for k, v in (r.get("signals") or {}).items()) or "—"
        hi = len(r.get("high_intent") or [])
        L.append(f"| {r['keyword']} | {r['score']} | {r.get('verdict','?')}"
                 f" | {r.get('wechat_articles') if r.get('wechat_articles') is not None else '未测到'}"
                 f" | {sig} | {hi} | {r.get('demand_used','?')} |")
    return L


def render(rows, started, secs):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [f"# 中文关键词实测数据（重测于 {now}）",
         "",
         "由 `scripts/remeasure_cn.py` 用**当前版本**的引擎实测生成，可一键复跑：",
         "",
         "```bash",
         "python3 scripts/remeasure_cn.py",
         "```",
         "",
         "**需求** = 360 相关搜索词（主）+ 360 补全词（仅在相关搜索为空时补位）",
         "**供给** = 搜狗微信文章存量 + 标题信号",
         "**评分** = 供给 3 分 + 供给性质 3 分 + 需求 4 分；裁决 = 供给×需求矩阵 + 一票否决",
         "",
         "> 存量数字随时间变化，评分也会小幅波动；**判读结论（红/黄/绿）比数字稳定**，",
         "> 因为它由市场结构决定。要看趋势请对比不同日期的本文件（都在 git 历史里）。",
         "",
         f"本次耗时 {secs/60:.1f} 分钟（{len(rows)} 个关键词，含限流冷却）。",
         "",
         "## 一、实测排名（按裁决优先，同裁决按分）",
         "",
         ]
    L += table(sorted(rows, key=verdict_rank))
    L += ["", "## 二、逐条明细", ""]
    for r in sorted(rows, key=verdict_rank):
        L.append(f"### {r['keyword']} — {r['score']}/10 {r.get('verdict','')}")
        L.append("")
        L.append(f"- 微信存量：{r.get('wechat_articles')} 篇 [{r.get('supply_tier')}]")
        if r.get("signals"):
            L.append(f"- 标题信号：{r['signals']}")
        if r.get("high_intent"):
            L.append("- 高购买意图词：" + "；".join(r["high_intent"][:6]))
        if r.get("freebie"):
            L.append("- 免费白嫖词：" + "；".join(r["freebie"][:6]))
        if r.get("brand"):
            L.append("- 垄断品牌：" + "；".join(r["brand"][:4]))
        if r.get("blockers"):
            L.append("- **否决项**：" + "；".join(r["blockers"]))
        if r.get("evidence"):
            for e in r["evidence"]:
                L.append(f"- 依据：{e}")
        L.append(f"- 下一步：{R.next_step(r)}")
        L.append("")
    L += ["---", "",
          "## 三、这份数据在说什么（读法）", "",
          "1. **存量少 ≠ 机会。** 存量少可能只是没人关心；必须同时看需求侧。",
          "2. **需求侧只算「找工具」的词。**《怎么写/在哪里》这类纯问法被剔除，",
          "   而《多少钱/报价》保留——后者是 B2B 的强购买意图。",
          "3. **否决项一律判红**，不看分数：免费白嫖词、垄断品牌、壁垒归零（vibecoding）。",
          "4. **绿灯也只是意图数据，不是成交数据。** 最后一步永远是去闲鱼看真实成交。",
          ""]
    return "\n".join(L)


def preflight():
    """先花一个请求确认供给侧活着，再决定要不要跑整批。

    为什么必须先探：搜狗微信会做**IP 级封锁**，封锁期间每个请求都返回
    约 5.3KB 的壳页（实测连续 18 分钟不解除，换 UA/Referer/Accept 都无效）。
    不预检就开跑，结果是 18 个关键词里 14 个标成「黄(不完整)」、
    写出一份没有价值的文档，还白等十几分钟。

    返回 (可用?, 说明)。
    """
    # 单次尝试 + 不走负缓存：预检失败不该给整批留下 5 分钟冷却，
    # 也不该因为一次抖动就判定「封锁中」。
    try:
        u = ("https://weixin.sogou.com/weixin?type=2&query="
             + urllib.parse.quote("对账单"))
        body = _http.fetch(u, timeout=20, tries=1, use_cache=False)
        m = re.search(r"找到约\s*([\d,]+)\s*条结果", body)
        return True, f"供给侧可用（探针词存量 {m.group(1) if m else '?'} 篇）"
    except Exception as e:                                       # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:70]}"


def main():
    ap = argparse.ArgumentParser(description="重测中文关键词并生成实测数据文档")
    ap.add_argument("--limit", type=int, help="只测前 N 个关键词")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    ap.add_argument("--force", action="store_true", help="跳过供给侧预检，照跑不误")
    ap.add_argument("--out", default=str(ROOT / "docs" / "实测数据-中文.md"))
    a = ap.parse_args()

    if not a.force:
        ok, why = preflight()
        print(f"预检：{why}", file=sys.stderr, flush=True)
        if not ok:
            print("\n供给侧取不到数据，**不生成文档**——写出来会是一份"
                  "没有供给侧的半成品。\n"
                  "搜狗微信是 IP 级封锁，通常要等较久（实测 18 分钟仍未解除）。\n"
                  "选择：① 过一段时间重跑；② 换网络出口；"
                  "③ 确实要半成品就加 --force。", file=sys.stderr)
            return 2

    kws = KEYWORDS[:a.limit] if a.limit else KEYWORDS
    started, t0 = datetime.datetime.now(), time.time()
    rows = []
    for i, kw in enumerate(kws, 1):
        if i > 1:
            time.sleep(6)          # 词间冷却，别把搜狗打出风控
        print(f"[{i}/{len(kws)}] {kw} …", file=sys.stderr, flush=True)
        try:
            r = measure(kw)
            rows.append(r)
            print(f"    {r['score']}/10 {r.get('verdict')} "
                  f"微信{r.get('wechat_articles')} 高意图{len(r.get('high_intent') or [])}"
                  f" ({r['_secs']:.1f}s)", file=sys.stderr, flush=True)
        except Exception as e:                                   # noqa: BLE001
            print(f"    失败：{type(e).__name__}: {str(e)[:60]}", file=sys.stderr)
    if not rows:
        print("一个都没测到（网络或限流），什么都没写。", file=sys.stderr)
        return 1

    # 供给侧缺失的行不能悄悄混进文档：它们的「存量/供给性质」是空的，
    # 分数只反映需求侧，读起来却像完整结论（实测一次批量跑出现过 14/18）。
    missing = [r["keyword"] for r in rows if r.get("wechat_articles") is None]
    if missing:
        print(f"\n⚠️ {len(missing)}/{len(rows)} 个关键词**没取到供给侧**："
              f"{'、'.join(missing[:6])}{'…' if len(missing) > 6 else ''}\n"
              f"   这些行的分数只反映需求侧，别当完整结论读。",
              file=sys.stderr)

    text = render(rows, started, time.time() - t0)
    if a.dry_run:
        print(text)
        return 0
    pathlib.Path(a.out).write_text(text, encoding="utf-8")
    print(f"\n已写入 {a.out}（{len(rows)} 个关键词）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
