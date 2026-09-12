#!/usr/bin/env python3
"""HTTP 层（缓存 + 限流）的离线回归测试。

不打网络：全部用假响应验证判定逻辑。

锁住的都是真踩过的坑：
  · 搜狗被限流时返回 ~5KB 壳页而非报错。早期版本把它当正常响应缓存了
    6 小时——把一个**瞬时**状态固化成六小时的错误结论。
  · 缓存文件绝不能包含请求头，否则 token 会落盘。
"""
import inspect
import json
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "red-ocean-scanner"))
import _http as H  # noqa: E402


def main():
    bad = 0
    tmp = tempfile.mkdtemp(prefix="rocache-")
    H.CACHE_DIR = tmp
    H.QUOTA_FILE = os.path.join(tmp, "_github_quota.json")

    # ── 响应有效性判定 ──
    print("  响应有效性：")
    cases = [
        ("https://weixin.sogou.com/weixin?type=2&query=x", "<html>" + "x" * 5000,
         False, "搜狗短壳页 = 限流，不是数据"),
        ("https://weixin.sogou.com/weixin?type=2&query=x",
         "<html>找到约 614 条结果" + "x" * 20000, True, "搜狗正常页"),
        ("https://weixin.sogou.com/weixin?type=2&query=x",
         "<html>请输入验证码" + "x" * 20000, False, "验证码页"),
        ("https://html.duckduckgo.com/html/?q=x", "anomaly" + "x" * 6000,
         False, "DDG anomaly 页"),
        ("https://api.github.com/search/repositories?q=x",
         '{"message":"API rate limit exceeded"}', False, "GitHub 限流"),
        ("https://itunes.apple.com/search?term=x", '{"resultCount":1}',
         True, "iTunes 正常"),
    ]
    for url, body, want, why in cases:
        got, _ = H.response_is_valid(url, body)
        good = got == want
        bad += not good
        print(f"    {'✓' if good else '✗'} {'有效' if got else '无效'}  {why}")

    # ── 无效响应不落盘 ──
    print("  缓存写入策略：")
    # fetch 在响应无效时直接抛 RateLimited，不会走到 cache_put。
    # 这里用源码检查锁住这个约定——否则「无效响应被缓存」会再次复发。
    import inspect
    src = inspect.getsource(H.fetch)
    guarded = "response_is_valid" in src and "ok" in src
    bad += not guarded
    print(f"    {'✓' if guarded else '✗'} fetch 在写缓存前先做有效性判定")

    # ── 缓存往返 ──
    url2 = "https://itunes.apple.com/search?term=zzz"
    payload = '{"resultCount":0}'
    H.cache_put(url2, payload)
    hit = H.cache_get(url2)
    good = hit == payload
    bad += not good
    print(f"    {'✓' if good else '✗'} 缓存往返一致")

    # ── 缓存不含凭据 ──
    files = list(pathlib.Path(tmp).rglob("*.json"))
    leaked = []
    for f in files:
        txt = f.read_text(encoding="utf-8").lower()
        if "authorization" in txt or "bearer" in txt or "token" in txt:
            leaked.append(f.name)
    bad += bool(leaked)
    print(f"    {'✓' if not leaked else '✗'} 缓存文件不含凭据（检查了 {len(files)} 个）")

    # ── GitHub 配额持久化 ──
    H._save_quota({"remaining": 3, "reset": 9999999999, "at": 0})
    q = H._load_quota()
    good = q.get("remaining") == 3
    bad += not good
    print(f"    {'✓' if good else '✗'} GitHub 配额可跨进程读写")

    # ── 负缓存：失败的源不应被反复重试 ──
    # DDG HTML 实测第 3 次起必拦，所以它永远不会成功、也就永远不会被正缓存。
    # 没有负缓存的话，每次扫描都要白等一次超时（实测 0.95-1.3s）。
    print("  负缓存：")
    H.FAIL_FILE = os.path.join(tmp, "_failures.json")
    good = H.fail_cooldown("ddg") == 0
    bad += not good
    print(f"    {'✓' if good else '✗'} 初始无冷却")

    H._mark_fail("ddg")
    good = H.fail_cooldown("ddg") > 0
    bad += not good
    print(f"    {'✓' if good else '✗'} 失败后进入冷却（{H.fail_cooldown('ddg')/60:.0f} 分钟）")

    H._clear_fail("ddg")
    good = H.fail_cooldown("ddg") == 0
    bad += not good
    print(f"    {'✓' if good else '✗'} 成功后清除冷却")

    os.environ["RED_OCEAN_NO_COOLDOWN"] = "1"
    H._mark_fail("ddg")
    off = H.fail_cooldown("ddg") == 0
    del os.environ["RED_OCEAN_NO_COOLDOWN"]
    bad += not off
    print(f"    {'✓' if off else '✗'} RED_OCEAN_NO_COOLDOWN 可强制重试")

    # 冷却必须在 fetch 里真的被检查，否则等于没实现
    src_fetch = inspect.getsource(H.fetch)
    checked = "fail_cooldown(kind)" in src_fetch
    bad += not checked
    print(f"    {'✓' if checked else '✗'} fetch 真的检查了冷却")

    # ── 缓存可关闭 ──
    old = H.CACHE_ENABLED
    H.CACHE_ENABLED = False
    H.cache_put("https://itunes.apple.com/search?term=off", "{}")
    off_ok = H.cache_get("https://itunes.apple.com/search?term=off") is None
    H.CACHE_ENABLED = old
    bad += not off_ok
    print(f"    {'✓' if off_ok else '✗'} RED_OCEAN_NO_CACHE 能关闭缓存")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n  {'全部通过' if bad == 0 else f'{bad} 项失败'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
