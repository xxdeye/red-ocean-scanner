#!/usr/bin/env python3
"""中文引擎裁决逻辑的离线回归测试。

不打网络：只测 verdict_kind 分派与 next_step 的一致性。
运行: python3 tests/test_cn_engine.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "red-ocean-scanner"))
import red_ocean_scan as r  # noqa: E402

# next_step 必须按 verdict_kind 分派，不能按 verdict 字符串比较——
# verdict 可能带「(不完整)」后缀，用 == 会把绿灯判成红灯（全球引擎犯过这个错）。
NEXT_CASES = [
    ("机会", "闲鱼", "绿灯应引导去闲鱼验证付费"),
    ("有硬伤", "先别做", "黄灯应劝先别做"),
    ("数据缺失", "隔几分钟", "数据缺失应要求重跑，不应给结论"),
    ("红海", "放弃", "红灯应直接劝退"),
]

# verdict 带后缀时不能退化
SUFFIX_CASES = [
    ({"verdict": "黄(不完整)", "verdict_kind": "数据缺失"}, "放弃"),
    ({"verdict": "绿(覆盖度低)", "verdict_kind": "机会"}, "放弃"),
]


def main():
    bad = 0
    print("  next_step 分派：")
    for kind, must, why in NEXT_CASES:
        txt = r.next_step({"verdict": "绿", "verdict_kind": kind})
        good = must in txt
        bad += not good
        print(f"    {'✓' if good else '✗'} {kind:6} → {txt[:44]}  ({why})")

    print("  带后缀的裁决不退化：")
    for payload, forbidden in SUFFIX_CASES:
        txt = r.next_step(payload)
        good = forbidden not in txt
        bad += not good
        print(f"    {'✓' if good else '✗'} {payload['verdict']:14} 不含「{forbidden}」")

    print(f"\n  {'全部通过' if bad == 0 else f'{bad} 项失败'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
