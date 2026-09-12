#!/usr/bin/env python3
"""数据源适用范围守卫的离线回归测试。

不打网络：只测关键词分类。

这个守卫存在的理由：工具的两个数据源（GitHub / App Store）都**不代表**
实体产品与线下服务。实测 "handmade soap business" 被判成「无人区」，
还因模糊匹配到 Etsy 而误报「已有 727 万条评价的既得利益者」——
那是自信的错误结论，比「无法判断」危险得多。

运行: python3 tests/test_scope_guard.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "red-ocean-scanner"))
import global_scan as g  # noqa: E402


def blocked(kw):
    """判定「是否超出适用范围」。

    注意：这里**不再复制** scan() 里的正则逻辑，而是调用抽出来的
    is_out_of_scope()。早期版本把判定抄了一份，结果 scan() 里遗留了一个
    无条件判断把软件查询也拦掉时，测试依然是绿的——复制逻辑的测试会
    同时复制 bug 的盲区。
    """
    return g.is_out_of_scope(kw)


# (关键词, 期望被拦截?, 说明)
CASES = [
    # 应正常评估的软件方向
    ("invoice excel", False, "普通软件词"),
    ("vet clinic software", False, "行业词但不是实体词"),
    ("funeral home management", False, "B2B 软件"),
    ("habit tracker", False, "消费级 App"),
    # 这条是踩过的坑：实体词只是行业限定语，用户要做的显然是软件
    ("restaurant scheduling software", False, "实体词 + 软件词 → 按软件处理"),
    ("coffee shop pos system", False, "同上"),
    ("bakery inventory software", False, "同上"),
    ("fitness studio management software", False, "同上"),
    ("photography studio booking software", False, "同上"),
    ("salon booking app", False, "同上"),
    # 应被拒绝的实体生意
    ("handmade soap business", True, "实体产品，数据源不对口"),
    ("candle business", True, "实体产品"),
    ("tutoring service", True, "线下服务"),
    ("food truck", True, "线下餐饮"),
    ("pet grooming", True, "线下服务"),
    # 边界：不含任何软件信号，按实体处理（保守）
    ("handmade jewelry", True, "实体产品"),
]


def main():
    bad = 0
    print("  适用范围守卫（调用 is_out_of_scope）：")
    for kw, want_block, why in CASES:
        got = blocked(kw)
        good = got == want_block
        bad += not good
        tag = "拦截" if got else "评估"
        print(f"    {'✓' if good else '✗'} {tag}  {kw:36} ({why})")
    print(f"\n  {len(CASES)-bad}/{len(CASES)} 通过")

    # 关键补充：确认 scan() 真的用了这个判定。
    # 上面测的是函数本身，若 scan() 内部另有一套（或遗留一套）逻辑，
    # 上面的用例全绿也没意义。
    print("\n  scan() 是否复用同一判定：")
    import inspect
    src = inspect.getsource(g.scan)
    checks = [
        ("调用 is_out_of_scope", "is_out_of_scope(kw)" in src),
        ("无遗留的无条件 PHYSICAL_HINT 判断",
         "if re.search(PHYSICAL_HINT, kw, re.I):" not in src),
    ]
    for name, ok in checks:
        bad += not ok
        print(f"    {'✓' if ok else '✗'} {name}")

    print(f"\n  {'全部通过' if bad == 0 else f'{bad} 项失败'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
