#!/usr/bin/env python3
"""裁决矩阵的离线回归测试。

不打网络：只测 decide() 的纯逻辑。运行: python3 tests/test_decide.py
这些用例锁住的是本 skill 最核心的判断规则，改动评分逻辑时必须全绿。
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / "skills" / "red-ocean-scanner"))
import global_scan as g  # noqa: E402

DIMS3 = [("开发者供给", 0, 3), ("消费供给", 0, 3)]

CASES = [
    # (供给薄度, 需求强度, 否决项, 维度数, 期望 verdict 前缀, 期望 kind, 说明)
    (1.0, 1.0, [], 3, "绿", "机会", "薄供给+有需求 = 机会"),
    (1.0, 0.0, [], 3, "🟠", "无人区", "薄供给但没需求 = 无人区，不是机会"),
    (0.5, 0.5, [], 3, "绿", "机会", "刚好在阈值上算通过"),
    (0.49, 1.0, [], 3, "红", "红海", "供给略厚即判红海"),
    (1.0, 0.49, [], 3, "🟠", "无人区", "需求略弱即判无人区"),
    (0.0, 1.0, [], 3, "红", "红海", "供给饱和+需求旺 = 红海"),
    (0.0, 0.0, [], 3, "红", "红海", "两头都不行"),
    (1.0, 1.0, ["App Store 头部 7,642,608 条评价"], 3, "红", "红海",
     "否决项必须在机会上生效（receipt scanner 的教训）"),
    (1.0, 0.0, ["某个否决项"], 3, "🟠", "无人区",
     "无人区不被否决项改成红海——两者含义不同"),
    (1.0, 1.0, [], 2, "绿(覆盖度低)", "机会", "维度不足时标注覆盖度"),
]


def main():
    ok = 0
    for st, ds, deadly, nd, exp_v, exp_k, why in CASES:
        v, k, reason = g.decide(st, ds, deadly, DIMS3, nd)
        good = v.startswith(exp_v) and k == exp_k
        ok += good
        print(f"  {'✓' if good else '✗'} 供给{st:.0%} 需求{ds:.0%} "
              f"否决{len(deadly)} 维度{nd} → {v}/{k}  ({why})")
        if not good:
            print(f"      期望 {exp_v}/{exp_k}，实际 {v}/{k}；理由：{reason}")
    print(f"\n  {ok}/{len(CASES)} 通过")
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
