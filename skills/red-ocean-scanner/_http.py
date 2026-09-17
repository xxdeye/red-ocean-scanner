#!/usr/bin/env python3
"""统一 HTTP 层：磁盘缓存 + 主动限流 + 跨进程配额持久化。

为什么需要这一层
────────────────
实测各数据源的限流边界（本机 2026 实测）：

  源                边界                     是否有 Retry-After
  GitHub search     硬性 10 次/分钟           无 ← 必须自己读 header
  DDG HTML          第 3 次起必拦（anomaly）   无
  360 搜索          宽松                      无
  搜狗微信          2s 间隔下 6+ 次无碍        无
  iTunes            30 次连打 0 失败          无
  Google/Bing 补全  12 次连打 0 失败          无

三条设计结论：

1. **没有任何源给 Retry-After。** 所以"等 403 再退避"是纯浪费——
   GitHub 要等到整分钟窗口重置，而退避 25s/50s 各一次可能正好错过窗口。
   必须主动读 `X-RateLimit-Remaining` 并在耗尽前等待。

2. **GitHub 配额是跨进程的。** 它是按 IP 限，不是按进程限。
   在内存里记计数毫无意义——换个进程照样撞墙。
   所以配额状态要落盘。

3. **市场数据变化很慢，缓存命中率极高。**
   "invoice 的仓库数"一小时甚至一周内几乎不变。
   缓存既是提速手段，也是最有效的限流手段：不打请求就不会被限。

安全：缓存只存响应体，**不存任何请求头**，token 不会落盘。
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# 缓存目录：跟随 skill 目录，便于清理；也可用 RED_OCEAN_CACHE 覆盖
_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.environ.get("RED_OCEAN_CACHE") or os.path.join(_HERE, ".cache")
CACHE_ENABLED = os.environ.get("RED_OCEAN_NO_CACHE", "") == ""

# 各源缓存时长（秒）。依据"数据变化速度"，不是拍脑袋：
#   GitHub 仓库数 / App Store 评价数 —— 一周内几乎不变
#   搜索补全词 —— 会随热点变，但一天内足够稳
#   搜狗文章存量 —— 每天在动
TTL = {
    "github": 7 * 24 * 3600,
    "itunes": 7 * 24 * 3600,
    "autocomplete": 24 * 3600,
    "so360": 12 * 3600,
    "so360sug": 12 * 3600,
    "sogou": 6 * 3600,
    "ddg": 24 * 3600,
    "default": 3600,
}


# 各源的「这不是有效响应」特征。命中则不缓存，并按限流处理。
#
# 为什么必须这么做：搜狗被限流时返回一个约 5KB 的壳页而不是报错。
# 早期版本把它当正常响应当缓存了 6 小时——等于把一个**瞬时**状态
# 固化成六小时的错误结论，之后每次命中缓存都继续误判。
# 缓存只能缓存「确定有效」的响应。
#
# 长度下限必须**按源**给，不能用统一的 500B 门槛：
# 360 补全接口的完整响应只有约 460B（10 条词条），统一门槛会把它
# 判成「疑似风控」而丢弃——实测中文引擎取 360 数据时正是这样失败的。
BAD_RESPONSE = {
    "sogou": (r"验证码|antispider|访问过于频繁|请输入验证码|安全验证", 8000),
    "ddg": (r"anomaly|unusual traffic|blocked", 5000),
    "github": (r"API rate limit exceeded", 0),
    "so360": (r"^\s*$", 2000),          # SERP 页正常约 540KB
    "so360sug": (r"^\s*$", 100),        # 补全 JSON 正常约 460B
    "itunes": (r"^\s*$", 0),
    "default": (r"^\s*$", 0),
}


def response_is_valid(url, body):
    """(是否有效, 原因)。无效的响应绝不写缓存。"""
    kind = classify(url)
    # JSON 接口收到 HTML 一定是门户/风控/错误页，不是数据。
    # 这类响应长度可以很大，纯靠长度门槛拦不住——实测用假服务器把 360 的
    # HTML 错误页喂进解析路径时，两份 HTML 都被当成有效响应缓存了。
    # 门禁类响应一旦进缓存，TTL 内每次命中都继续误判。
    if kind in JSON_SOURCES and body.lstrip()[:1] not in ("{", "["):
        return False, "期望 JSON，收到非 JSON 响应（疑似门户/风控页）"
    pat, min_len = BAD_RESPONSE.get(kind, BAD_RESPONSE["default"])
    if min_len and len(body) < min_len:
        return False, f"响应过短（{len(body)}B < {min_len}B）"
    if pat and re.search(pat, body, re.I):
        return False, "命中风控/限流特征"
    return True, ""


# 返回体必须是 JSON 的源。SERP / DDG HTML 这类当然是 HTML，不在其中。
JSON_SOURCES = {"github", "itunes", "autocomplete", "so360sug"}


def classify(url):
    if "api.github.com" in url:
        return "github"
    if "itunes.apple.com" in url:
        return "itunes"
    if "suggestqueries.google" in url or "osjson.aspx" in url or "/ac/?" in url:
        return "autocomplete"
    # 360 补全接口（sug.so.360.cn）与 SERP（www.so.com）长度差三个数量级，
    # 必须是两个源、两套长度门槛——早期只认 so.com，补全响应落进 default。
    if "sug.so.360.cn" in url:
        return "so360sug"
    if "so.com" in url:
        return "so360"
    if "weixin.sogou.com" in url:
        return "sogou"
    if "duckduckgo" in url:
        return "ddg"
    return "default"


# ── 磁盘缓存 ────────────────────────────────────────────
def _key(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _path(url):
    return os.path.join(CACHE_DIR, classify(url), _key(url) + ".json")


def cache_get(url):
    if not CACHE_ENABLED:
        return None
    p = _path(url)
    try:
        with open(p, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    if time.time() - rec.get("t", 0) > rec.get("ttl", 0):
        return None
    return rec.get("body")


def cache_put(url, body):
    if not CACHE_ENABLED:
        return
    p = _path(url)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"t": time.time(), "ttl": TTL.get(classify(url),
                                                        TTL["default"]),
                       "url": url, "body": body}, f)
        os.replace(tmp, p)          # 原子写，避免并发读到半个文件
    except OSError:
        pass                        # 缓存失败不该影响主流程


def cache_stats():
    """返回 (条目数, 总字节)。"""
    n = sz = 0
    for root, _, files in os.walk(CACHE_DIR):
        for fn in files:
            if fn.endswith(".json"):
                n += 1
                try:
                    sz += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
    return n, sz


def cache_clear():
    import shutil
    shutil.rmtree(CACHE_DIR, ignore_errors=True)


# ── GitHub 配额：跨进程持久化 ──────────────────────────
# GitHub 按 IP 限流，所以状态必须落盘，否则每个新进程都以为配额是满的。
QUOTA_FILE = os.path.join(CACHE_DIR, "_github_quota.json")
_last_gh_call = [0.0]
GA_MIN_GAP = 6.5      # 10 次/分钟 → 理论 6.0s，留 0.5s 余量


def _load_quota():
    try:
        with open(QUOTA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_quota(d):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(QUOTA_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


def github_gate(verbose=True):
    """必要时阻塞，保证不撞 GitHub 搜索限流。

    先看剩余配额与重置时间：若配额已耗尽且重置还没到，就睡到重置。
    否则按最小间隔节流。

    「上一次调用时刻」与配额一起落盘：限流按 IP 算、不按进程算，
    只记内存的话每个新进程都以为自己刚起步——连续跑几条命令就会
    各来一串 10 连发，一发不剩地撞满再等整分钟。
    """
    q = _load_quota()
    now = time.time()
    remaining = q.get("remaining")
    reset = q.get("reset", 0)

    if remaining is not None and remaining <= 0 and reset > now:
        wait = reset - now + 1.0
        if verbose:
            print(f"  [限流] GitHub 配额已耗尽，等待 {wait:.0f}s 至窗口重置…",
                  file=sys.stderr, flush=True)
        time.sleep(wait)
        now = time.time()

    last = max(_last_gh_call[0], q.get("last_call", 0))
    gap = GA_MIN_GAP - (now - last)
    if gap > 0:
        time.sleep(gap)
    _last_gh_call[0] = time.time()

    # 只更新 last_call，保留 _record_quota 写的 remaining/reset
    q = _load_quota()
    q["last_call"] = _last_gh_call[0]
    _save_quota(q)


def _record_quota(headers):
    try:
        rem = headers.get("X-RateLimit-Remaining")
        rst = headers.get("X-RateLimit-Reset")
        if rem is not None:
            _save_quota({"remaining": int(rem),
                         "reset": int(rst) if rst else 0,
                         "at": time.time()})
    except (TypeError, ValueError):
        pass


# ── 请求 ────────────────────────────────────────────────
class FetchError(Exception):
    pass


class RateLimited(FetchError):
    pass


# 上一次 fetch 是否真的走了网络。调用方可据此跳过不必要的节流等待。
last_was_network = False

# 负缓存：记住某类源刚刚失败过，在冷却期内直接跳过。
#
# 为什么需要：DDG HTML 实测第 3 次起必拦，所以它**永远不会成功、
# 也就永远不会被正缓存**——每次扫描都要白等一次超时（实测 0.95s）。
# 失败的源应该被记住，而不是反复重试。
FAIL_FILE = os.path.join(CACHE_DIR, "_failures.json")
FAIL_COOLDOWN = {
    "ddg": 1800,        # DDG 拦得最狠，冷却 30 分钟
    "sogou": 300,       # 搜狗风控约几分钟
    "default": 0,       # 其他源不记负缓存，避免掩盖真实故障
}


def _load_fails():
    try:
        with open(FAIL_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_fails(d):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(FAIL_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


def fail_cooldown(kind):
    """返回剩余冷却秒数；0 表示可以重试。设 RED_OCEAN_NO_COOLDOWN=1 可禁用。"""
    if os.environ.get("RED_OCEAN_NO_COOLDOWN"):
        return 0
    cd = FAIL_COOLDOWN.get(kind, 0)
    if not cd:
        return 0
    at = _load_fails().get(kind, 0)
    left = cd - (time.time() - at)
    return max(0, left)


def _mark_fail(kind):
    if FAIL_COOLDOWN.get(kind, 0):
        d = _load_fails()
        d[kind] = time.time()
        _save_fails(d)


def _clear_fail(kind):
    d = _load_fails()
    if kind in d:
        d.pop(kind)
        _save_fails(d)


# 单次 fetch 的总重试时间预算（秒）。超过就放弃，交给负缓存。
#
# 为什么需要：搜狗被限流时风控持续数分钟，重试两次（25s + 50s）基本是
# 白等——实测中文引擎冷启动因此要 78.8 秒。而重试成功的前提是"限流是瞬时的"，
# 对搜狗并不成立。宁可快速失败并交给负缓存，也不要让用户干等一分多钟。
RETRY_BUDGET = 20.0


def fetch(url, timeout=20, tries=2, backoff=10, use_cache=True,
          headers=None, verbose=True):
    """带缓存与主动限流的 GET。

    返回响应体字符串。限流时抛 RateLimited——**绝不返回空串伪装成
    「没有数据」**，那会让上层把限流误读成「无竞争」。
    """
    global last_was_network
    if use_cache:
        hit = cache_get(url)
        if hit is not None:
            last_was_network = False
            return hit
    last_was_network = True

    kind = classify(url)

    # 负缓存：该源刚失败过就在冷却期内直接跳过，不要反复重试。
    # 否则一个永远失败的源（如 DDG HTML）每次扫描都要白等一次超时。
    left = fail_cooldown(kind)
    if left > 0:
        raise RateLimited(f"{kind} 处于失败冷却中，还需 {left/60:.0f} 分钟"
                          f"（RED_OCEAN_NO_COOLDOWN=1 可强制重试）")

    last = None
    deadline = time.time() + RETRY_BUDGET
    for i in range(tries):
        if kind == "github":
            github_gate(verbose)
        h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
             "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}
        if headers:
            h.update(headers)
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token and kind == "github":
            h["Authorization"] = f"Bearer {token}"
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "ignore")
                if kind == "github":
                    _record_quota(r.headers)
            ok, why = response_is_valid(url, body)
            if ok:
                if use_cache:
                    cache_put(url, body)
                _clear_fail(kind)
                return body
            # 无效响应：不缓存，按限流抛出，让上层区分「没数据」和「被打回」
            last = RateLimited(why)
        except urllib.error.HTTPError as e:
            if kind == "github":
                _record_quota(e.headers)
            if e.code in (403, 429):
                last = RateLimited(f"HTTP {e.code} 限流")
            else:
                last = FetchError(f"HTTP {e.code}")
        except Exception as e:                               # noqa: BLE001
            last = FetchError(str(e)[:70])
        if i < tries - 1:
            wait = backoff * (i + 1)
            if time.time() + wait > deadline:
                break            # 超预算，不再等——交给负缓存
            time.sleep(wait)
    if isinstance(last, RateLimited):
        _mark_fail(kind)
    raise last
