#!/usr/bin/env python3
"""阶梯 / 地理扫描必须走统一 HTTP 层的回归测试（不打网络）。

锁住的坑：`ladder_scan.py` 与 `geo_scan.py` 早期是裸 urllib——
不打磁盘缓存、不读 `X-RateLimit-Remaining`、配额也不落盘。
阶梯是**最费 GitHub 配额的路径**（一次 12+ 个请求），撞上 10 次/分钟
就直接中断；geo 一次 16 个地区 = 64 个请求，全量重来。

判定方式（离线、确定性）：把 GitHub 配额写成「已耗尽且重置在 10 分钟后」。
走统一层 → `github_gate()` 立刻抛错、绝不等到网络超时；
裸 urllib → 会真的去连网络然后超时。据此可区分两条路径。
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "red-ocean-scanner"))
import _http as H          # noqa: E402
import ladder_scan as L    # noqa: E402
import geo_scan as Geo     # noqa: E402

# 这三个模块必须共用同一份 _http（同一个 CACHE_DIR），否则缓存与配额不共享
SHARED = [("ladder_scan", L), ("geo_scan", Geo)]


def main():
    bad = 0
    tmp = tempfile.mkdtemp(prefix="roscan-")
    H.CACHE_DIR = tmp
    H.QUOTA_FILE = os.path.join(tmp, "_github_quota.json")

    print("  共用同一套 HTTP 层：")
    for name, mod in SHARED:
        same = mod._http is H
        bad += not same
        print(f"    {'✓' if same else '✗'} {name} 引用的是同一个 _http 模块")
        uses = "_http.fetch" in pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        bad += not uses
        print(f"    {'✓' if uses else '✗'} {name} 的请求都经 _http.fetch")
        bare = "urllib.request.urlopen" in pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        bad += bare
        print(f"    {'✓' if not bare else '✗'} {name} 里没有裸 urllib.request.urlopen")

    print("  配额门真的生效（离线判定）：")
    # 配额耗尽、重置在 1.5s 后 → 走统一层就会经 github_gate 睡到重置。
    # 用假 opener 替换 urllib 的网络层（不真发请求），同时记录 sleep。
    # 注意不能替换 _http.fetch 本身：那样会连 github_gate 一起短路，
    # 测的就不是同一件事了。
    H._save_quota({"remaining": 0, "reset": int(time.time()) + 1.5, "at": time.time()})
    slept, opened = [], []
    real_sleep, real_opener = H.time.sleep, H.urllib.request.urlopen

    class FakeResp:
        headers = {}

        def read(self):
            return b'{"total_count": 1234}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_opener(req, timeout=None):
        opened.append(getattr(req, "full_url", str(req)))
        return FakeResp()

    H.time.sleep = lambda s: slept.append(s)
    H.urllib.request.urlopen = fake_opener
    try:
        n = L.gh_count("invoice")
    finally:
        H.time.sleep, H.urllib.request.urlopen = real_sleep, real_opener
    gate_used = bool(slept) and any("api.github.com" in u for u in opened) and n == 1234
    bad += not gate_used
    print(f"    {'✓' if gate_used else '✗'} 配额耗尽时 gh_count 经 github_gate 等待重置"
          f"（睡 {slept and f'{slept[0]:.1f}s' or '没睡'}，返回 total_count={n}）")
    if not slept:
        print("         没睡 = 请求绕过了 github_gate，会直接撞 10 次/分钟限流")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n  {'全部通过' if bad == 0 else f'{bad} 项失败'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
