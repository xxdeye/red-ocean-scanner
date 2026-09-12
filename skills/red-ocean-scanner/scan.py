#!/usr/bin/env python3
"""Red Ocean Scanner — 统一入口 / Unified entry point

一个命令跑所有市场和所有分析模式。

三种分析模式:
  scan       判断一个词是不是红海，出红黄绿裁决（默认）
  ladder     把宽词收窄成多个窄口，按饱和度排序
  geo        地理套利：同一需求在哪个国家还没被做烂

市场引擎（scan 模式）:
  global     全球/英文 — App Store + GitHub + Google/Bing 自动补全
  cn         中文     — 微信内容存量 + 360 相关搜索
  both       同一组词在两个市场各跑一遍

参数约定（简单、无歧义）:
  调度器自己的选项写在**关键词前面**；要传给目标脚本的选项写在**关键词后面**。
  本调度器选项: --mode/-m  --engine/-e  --json  --list-modes  --list-engines
  其余一切原样透传给目标脚本。

用法:
  python3 scan.py --engine cn "代账公司对账单"
  python3 scan.py --engine global "vet clinic software"
  python3 scan.py --mode ladder "invoice" --limit 8
  python3 scan.py --mode geo "receipt scanner" --regions us,cn
  python3 scan.py --list-modes

为什么分成多个引擎：不同市场的**可靠信号完全不同**。
中文版靠相关搜索词判断付费意愿；全球版靠 App Store 评价数与 GitHub 供给密度。
强行合并会得到一个两边都不准的工具。
"""

import argparse
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))

# 词间冷却由各引擎自己决定，调度器不覆盖——否则会压掉引擎内部的自适应逻辑
# （例如检测到 GITHUB_TOKEN 就自动降低冷却）。设 RED_OCEAN_GAP 可强制覆盖。
GAP_OVERRIDE = os.environ.get("RED_OCEAN_GAP", "")

ENGINES = {
    "global": {
        "script": "global_scan.py",
        "desc": "全球/英文市场 — App Store + GitHub + Google/Bing 自动补全",
    },
    "cn": {
        "script": "red_ocean_scan.py",
        "desc": "中文市场 — 微信内容存量 + 360 相关搜索",
    },
}

MODES = {
    "scan": {"script": None, "desc": "判断一个词是不是红海，出红黄绿裁决"},
    "ladder": {"script": "ladder_scan.py",
               "desc": "收窄阶梯：把宽词拆成更窄的战场，按饱和度排序"},
    "geo": {"script": "geo_scan.py",
            "desc": "地理套利：同一需求在哪个国家还没被做烂"},
}


def run_script(script, args):
    path = os.path.join(HERE, script)
    if not os.path.exists(path):
        print(f"脚本缺失: {path}", file=sys.stderr)
        return 1
    cmd = [sys.executable, path]
    if GAP_OVERRIDE:
        cmd += ["--gap", GAP_OVERRIDE]
    return subprocess.call(cmd + list(args))


def main():
    ap = argparse.ArgumentParser(
        description="Red Ocean Scanner — 统一入口（多市场 · 多模式）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--mode", "-m", choices=list(MODES), default="scan",
                    help="分析模式（默认 scan）")
    ap.add_argument("--engine", "-e", choices=list(ENGINES) + ["both"],
                    default="global", help="市场引擎（仅 scan 模式用）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list-engines", action="store_true")
    ap.add_argument("--list-modes", action="store_true")
    # REMAINDER：关键词与其后的目标脚本专属选项原样接收，不猜测切分
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    if a.list_engines:
        print("可用市场引擎（--engine）：\n")
        for name, cfg in ENGINES.items():
            print(f"  {name:<8} {cfg['desc']}")
        print("\n  both     同一组关键词在两个市场各跑一遍")
        return 0

    if a.list_modes:
        print("可用分析模式（--mode）：\n")
        for name, cfg in MODES.items():
            print(f"  {name:<8} {cfg['desc']}")
        return 0

    rest = [x for x in a.rest if x != "--"]
    if not rest:
        ap.print_help()
        return 1

    extra = (["--json"] if a.json else []) + rest

    if a.mode != "scan":
        return run_script(MODES[a.mode]["script"], extra)

    if a.engine == "both":
        rc = 0
        for name in ("cn", "global"):
            print(f"\n{'#'*70}\n#  市场：{ENGINES[name]['desc']}\n{'#'*70}",
                  flush=True)
            rc |= run_script(ENGINES[name]["script"], extra)
        return rc
    return run_script(ENGINES[a.engine]["script"], extra)


if __name__ == "__main__":
    sys.exit(main())
