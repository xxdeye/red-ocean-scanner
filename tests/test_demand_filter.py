#!/usr/bin/env python3
"""需求侧过滤规则的离线回归测试（不打网络）。

锁住的是一个**过杀 bug**：`_is_generic_strip` 只比较主干前缀，于是
`vet clinic software` 的 12 条 Bing 建议（…demo / …pricing / …reviews）
全部被当成「Bing 剥掉了 software」丢掉——两次请求都成功，却记为
`google:5 bing:0 ddg:0`。三源交叉验证静默退化成一源，需求强度被低估。

规则本身的边界：必须同时满足
  ① query 以通用产品词结尾
  ② 建议以剥掉通用词后的主干开头
  ③ 建议里**不再出现**被剥掉的那个产品词
③ 是这次修的：`…pricing` 含 software → 真实细化；`…design` 不含 → 替换匹配。
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "red-ocean-scanner"))
import global_scan as G  # noqa: E402

# (query, suggestion, 期望丢弃?, 说明)   — 全部来自实测响应
CASES = [
    ("vet clinic software", "vet clinic software pricing", False, "Bing 真实细化（曾误杀）"),
    ("vet clinic software", "vet clinic software demo", False, "Bing 真实细化（曾误杀）"),
    ("vet clinic software", "vet clinic software reviews", False, "Bing 真实细化（曾误杀）"),
    ("vet clinic software", "vet clinic software", False, "回显由调用方过滤"),
    ("banana peeling machine software", "banana peeling machine design", True,
     "Bing 忽略 software 换成 design"),
    ("banana peeling machine software", "banana peeling machine reviews", True,
     "Bing 忽略 software 换成 reviews"),
    ("banana peeling machine software", "banana peeling machine video", True,
     "Bing 忽略 software 换成 video"),
    ("habit tracker", "habit tracker app", False, "query 不以通用词结尾 → 向下细化"),
    ("invoice software", "invoice software free", False, "保留含 software 的细化"),
    ("invoice software", "invoice excel", True, "含 software 的替换匹配 → 丢弃"),
    ("software", "accounting software", False, "主干为空 → 规则不适用"),
]

# 三源返回体（与实盘一致）：过滤后每个源各自应该留下多少条
SOURCE_BODIES = {
    "google": ('["vet clinic software", ["vet clinic software", "vet clinic software programs",'
               ' "vet practice software", "pet clinic software"]]', 3),
    "bing": ('["vet clinic software", ["vet clinic software", "vet clinic software demo",'
             ' "vet clinic software pricing"]]', 2),
    # DDG 实测只回显查询本身（本机实测 ddg:0 是数据源特性，不是过滤器过杀）
    "ddg": ('["vet clinic software", ["vet clinic software"]]', 0),
}


def main():
    bad = 0
    print("  通用词剥离判定：")
    for q, sg, want, why in CASES:
        got = G._is_generic_strip(q, sg)
        ok = got == want
        bad += not ok
        print(f"    {'✓' if ok else '✗'} {'丢弃' if got else '保留'}  {why}")

    print("  三源合并（回显不计入）：")
    for name, (body, want_kept) in SOURCE_BODIES.items():
        got = [w for w in _parse(name, body)
               if w.lower() != "vet clinic software" and not G._is_generic_strip("vet clinic software", w)]
        ok = len(got) == want_kept
        bad += not ok
        print(f"    {'✓' if ok else '✗'} {name:6} 保留 {len(got)} 条（期望 {want_kept}）")

    # 回归的核心断言：Bing 不再被清空。曾实测 google:5 bing:0 ddg:0。
    print("  回归断言：")
    per_src = {n: [w for w in _parse(n, b)
                   if w.lower() != "vet clinic software"
                   and not G._is_generic_strip("vet clinic software", w)]
               for n, (b, _) in SOURCE_BODIES.items()}
    ok = len(per_src["bing"]) >= 2
    bad += not ok
    print(f"    {'✓' if ok else '✗'} Bing 保留 {len(per_src['bing'])} 条"
          f"（过杀 bug 时恒为 0，两次请求都成功却记为 bing:0）")
    ok = sum(len(v) for v in per_src.values()) >= 5
    bad += not ok
    print(f"    {'✓' if ok else '✗'} 三源合计保留 {sum(len(v) for v in per_src.values())} 条"
          f"（修复前只有 google 一源在工作）")

    print(f"\n  {'全部通过' if bad == 0 else f'{bad} 项失败'}")
    return 0 if bad == 0 else 1


def _parse(name, body):
    import json
    d = json.loads(body)
    if name == "ddg":
        return [x.get("phrase", "") for x in d if isinstance(x, dict)]
    return d[1]


if __name__ == "__main__":
    sys.exit(main())
