#!/usr/bin/env python3
"""供给侧被封锁时必须「说出来」，不能读成「存量 0 篇」（不打网络）。

锁住的坑：搜狗微信被 IP 级封锁时，每个请求都返回约 5.3KB 的壳页，
**而不是报错**。壳页里没有「找到约 N 条结果」，如果按常规解析会得到
「0 篇」——那是最危险的一类静默错误：把「被封锁」读成「没人写过」，
结论正好相反（供给薄 = 机会）。

同时锁住：壳页不得进正缓存。早期版本把壳页当正常响应缓存了 6 小时，
把一个瞬时状态固化成六小时的错误结论。

另外验证 `scripts/remeasure_cn.py` 的预检：封锁时**不生成文档**，
而不是写出一份没有供给侧的半成品（实测一次批量跑出现过 14/18 行缺供给）。
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "red-ocean-scanner"
sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(ROOT / "scripts"))
import _http as H           # noqa: E402
import red_ocean_scan as R  # noqa: E402

# 实测的壳页特征：长度恒定在 5.3KB 左右，既无「找到约」也无任何结果标题
SHELL = "<html><head><title>搜狗微信搜索</title></head><body>" + "x" * 5300 + "</body></html>"
REAL = ('<html><body><h3><a href="/x">发票批量导出工具推荐</a></h3>'
        '<p>找到约 614 条结果</p>' + "y" * 20000 + "</body></html>")


class FakeResp:
    headers = {}

    def __init__(self, body):
        self._b = body.encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def mk_opener(state):
    """按 URL 分派假响应：搜狗给壳页，JSON 接口给合法 JSON。

    不能对所有 URL 都回壳页——那会顺带污染 360 两个源的缓存，
    让「壳页没进缓存」的断言测出假失败。
    """
    def opener(req, timeout=None):
        url = getattr(req, "full_url", str(req))
        if "weixin.sogou.com" in url:
            return FakeResp(state["sogou"])
        if "sug.so.360.cn" in url:
            return FakeResp('{"errorcode":0,"result":[{"word":"发票工具"}]}')
        if "so.com" in url:
            return FakeResp('<html><table class="rs-table"><a href="/x">发票工具</a></table>'
                            + "z" * 3000 + "</html>")
        return FakeResp("{}")
    return opener


def main():
    bad = 0
    tmp = tempfile.mkdtemp(prefix="rosogou-")
    H.CACHE_DIR = tmp
    H.QUOTA_FILE = os.path.join(tmp, "_github_quota.json")
    H.FAIL_FILE = os.path.join(tmp, "_failures.json")
    real_opener = H.urllib.request.urlopen
    state = {"sogou": SHELL}

    H.urllib.request.urlopen = mk_opener(state)
    try:
        print("  壳页识别：")
        ok, why = H.response_is_valid("https://weixin.sogou.com/weixin?type=2&query=x", SHELL)
        bad += ok
        print(f"    {'✓' if not ok else '✗'} 壳页判为无效（{why}）")

        # 关键：解析层不得把它读成 0 篇
        try:
            R.wechat("发票")
            raised = False
        except R.RateLimited:
            raised = True
        bad += not raised
        print(f"    {'✓' if raised else '✗'} wechat() 抛 RateLimited，而不是返回「0 篇」")

        # scan() 必须标成不完整，且绝不给绿灯
        r = R.scan("发票")
        good = (r["wechat_articles"] is None
                and r["verdict_kind"] == "数据缺失"
                and not r["verdict"].startswith("绿")
                and any("未取到数据" in b for b in r["blockers"]))
        bad += not good
        print(f"    {'✓' if good else '✗'} scan() → {r['verdict']}/{r['verdict_kind']}"
              f"，存量={r['wechat_articles']}，带否决项")

        print("  壳页不进缓存：")
        # 只看 sogou 这一类源：其他源（360 SERP）在这次扫描里拿到的是**合法**
        # 响应，理应被缓存，把它们算进来是假失败。
        # 另注：`_failures.json` 是负缓存，记录「该源刚失败过」是它的职责。
        sogou_files = list((pathlib.Path(tmp) / "sogou").rglob("*.json"))
        bad += bool(sogou_files)
        print(f"    {'✓' if not sogou_files else '✗'} 壳页没有进正缓存"
              f"（sogou 缓存文件 {len(sogou_files)} 个）")
        marked = pathlib.Path(tmp) / "_failures.json"
        good = marked.exists() and "sogou" in json.loads(marked.read_text(encoding="utf-8"))
        bad += not good
        print(f"    {'✓' if good else '✗'} 记入负缓存，冷却期内不再反复重试")

        # 正常页仍然要能解析、能缓存（先解除负缓存，否则会被冷却挡住）
        os.environ["RED_OCEAN_NO_COOLDOWN"] = "1"
        state["sogou"] = REAL
        try:
            cnt, titles, sig = R.wechat("发票")
        finally:
            del os.environ["RED_OCEAN_NO_COOLDOWN"]
        cached2 = list((pathlib.Path(tmp) / "sogou").rglob("*.json"))
        good = cnt == 614 and titles and len(cached2) == 1
        bad += not good
        print(f"    {'✓' if good else '✗'} 正常页仍解析出 {cnt} 篇并缓存"
              f"（sogou 缓存文件 {len(cached2)} 个）")
    finally:
        H.urllib.request.urlopen = real_opener

    # 预检：封锁时不生成文档
    print("  remeasure 预检：")
    import remeasure_cn as M
    H.urllib.request.urlopen = mk_opener({"sogou": SHELL})
    out = pathlib.Path(tmp) / "should-not-exist.md"
    argv = sys.argv
    try:
        sys.argv = ["remeasure_cn.py", "--out", str(out)]
        rc = M.main()
    finally:
        sys.argv = argv
        H.urllib.request.urlopen = real_opener
    good = rc == 2 and not out.exists()
    bad += not good
    print(f"    {'✓' if good else '✗'} 封锁时退出码 {rc}、不写文档"
          f"（文档存在：{out.exists()}）")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n  {'全部通过' if bad == 0 else f'{bad} 项失败'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
