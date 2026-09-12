#!/usr/bin/env python3
"""Red Ocean Scanner — 统一入口 / Unified entry point

一个命令跑所有市场。按引擎分派到两个独立实现：

  global  → 全球（英文）市场   GitHub 仓库密度 + star 分布
  cn      → 中文市场           微信内容存量 + 360 相关搜索

用法:
  python3 scan.py --engine global "veterinary clinic software"
  python3 scan.py --engine cn "代账公司对账单"
  python3 scan.py --engine both "invoice excel"        # 同词双市场对比
  python3 scan.py --list-engines

为什么分成两个引擎而不是一个：两个市场的**可靠信号完全不同**。
中文版靠「相关搜索词」判断付费意愿；全球版靠 GitHub 供给密度。
强行合并会得到一个两个市场都不准的工具。
"""

import argparse
import os
import subprocess
import sys


# ── 跨平台 UTF-8 ────────────────────────────────────────────
# 脚本输出含中文与 emoji，Windows 默认 cp1252 控制台会直接抛
# UnicodeEncodeError。在任何输出发生前把流切到 UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):   # 非 TTY 或被重定向的旧环境
    pass


HERE = os.path.dirname(os.path.abspath(__file__))

# 词间冷却由各引擎自己决定，调度器不覆盖——否则会压掉引擎内部的自适应逻辑
# （例如检测到 GITHUB_TOKEN 就把冷却从 22s 降到 7s）。
# 设 RED_OCEAN_GAP 可强制覆盖，仅用于调试。
GAP_OVERRIDE = os.environ.get("RED_OCEAN_GAP", "")

ENGINES = {
    "global": {
        "script": "global_scan.py",
        "desc": "全球/英文市场 — App Store + GitHub + Google/Bing 自动补全",
        "market": "global",
    },
    "cn": {
        "script": "red_ocean_scan.py",
        "desc": "中文市场 — 微信内容存量 + 360 相关搜索",
        "market": "cn",
    },
}


def run(engine, keywords, extra):
    cfg = ENGINES[engine]
    path = os.path.join(HERE, cfg["script"])
    if not os.path.exists(path):
        print(f"引擎脚本缺失: {path}", file=sys.stderr)
        return 1
    cmd = [sys.executable, path]
    if GAP_OVERRIDE:
        cmd += ["--gap", GAP_OVERRIDE]
    cmd += extra + list(keywords)
    return subprocess.call(cmd)


def main():
    ap = argparse.ArgumentParser(
        description="Red Ocean Scanner — 统一入口（支持全球与中文市场）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--engine", "-e", choices=list(ENGINES) + ["both"],
                    default="global")
    ap.add_argument("--list-engines", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("keywords", nargs="*")
    a = ap.parse_args()

    if a.list_engines:
        print("可用引擎：\n")
        for name, cfg in ENGINES.items():
            print(f"  {name:<8} {cfg['desc']}")
        print("\n  both     同一组关键词在两个市场各跑一遍")
        return 0

    if not a.keywords:
        ap.print_help()
        return 1

    extra = ["--json"] if a.json else []

    if a.engine == "both":
        rc = 0
        for name in ("cn", "global"):
            print(f"\n{'#'*70}\n#  市场：{ENGINES[name]['desc']}\n{'#'*70}",
                  flush=True)
            rc |= run(name, a.keywords, extra)
        return rc
    return run(a.engine, a.keywords, extra)


if __name__ == "__main__":
    sys.exit(main())
