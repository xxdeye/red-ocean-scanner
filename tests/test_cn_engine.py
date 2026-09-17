#!/usr/bin/env python3
"""中文引擎裁决逻辑的离线回归测试。

不打网络：只测 verdict_kind 分派与 next_step 的一致性。
运行: python3 tests/test_cn_engine.py
"""
import pathlib
import re
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

    # 360 补全源：实测完整响应只有约 460B，曾被统一 500B 门槛判成风控丢弃。
    print("  360 补全源：")
    real = ('{"errorcode":0,"query":"录音转文字","result":['
            '{"word":"录音转文字软件哪个好用"},{"word":"录音转文字在线免费"}],"sleep":21600}')
    old = r.fetch
    r.fetch = lambda *a, **k: real
    try:
        words = r.so_suggest("录音转文字")
    finally:
        r.fetch = old
    good = words == ["录音转文字软件哪个好用", "录音转文字在线免费"]
    bad += not good
    print(f"    {'✓' if good else '✗'} 解析补全 JSON（{len(words)} 条，460B 级响应不再被丢弃）")

    r.fetch = lambda *a, **k: '{"errorcode":10001,"result":[]}'
    try:
        r.so_suggest("x")
        good = False
    except r.RateLimited:
        good = True
    finally:
        r.fetch = old
    bad += not good
    print(f"    {'✓' if good else '✗'} errorcode 非 0 时按限流抛出，不读成「无需求」")

    # 纯问法不该计入高购买意图，否则需求档位会被问句灌水抬高一档。
    # 但**价格问法必须留下**：engine-cn.md 把《多少钱/报价》列为 B2B 强购买意图，
    # 按通用问法一并剔除会误杀最值钱的那类词。
    print("  需求词过滤：")
    pool = ["发票批量导出怎么操作", "发票批量导出在哪里", "电子发票批量导出工具",
            "代账软件多少钱", "开票工具报价多少"]
    hi = [w for w in pool if re.search(r.INTENT, w) and not re.search(r.KNOWLEDGE, w)]
    want = {"电子发票批量导出工具", "代账软件多少钱", "开票工具报价多少"}
    good = set(hi) == want
    bad += not good
    print(f"    {'✓' if good else '✗'} 5 条里留下 {len(hi)} 条：剔除「怎么/哪里」问法，"
          f"保留「多少钱/报价」价格意图")
    good = "多少钱" not in r.KNOWLEDGE
    bad += not good
    print(f"    {'✓' if good else '✗'} KNOWLEDGE 正则不含「多少」")

    print(f"\n  {'全部通过' if bad == 0 else f'{bad} 项失败'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
