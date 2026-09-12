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

# 每个引擎词间冷却不同，因为限流规则不同：
#   全球版每次打 2 个 GitHub 端点，未授权限流约 10 次/分钟 → 22s
#   中文版每次打 2 个源（360 + 搜狗微信），搜狗风控严格 → 6s 起步但易触发
ENGINES = {
    "global": {
        "script": "global_scan.py",
        "gap": "22",
        "desc": "全球/英文市场 — GitHub 仓库密度 + star 分布",
        "market": "global",
    },
    "cn": {
        "script": "red_ocean_scan.py",
        "gap": "6",
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
    cmd = [sys.executable, path, "--gap", cfg["gap"]] + extra + list(keywords)
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
