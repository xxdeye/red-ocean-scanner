# 数据源能力矩阵（实测）

**这份文档存在的原因**：早期版本声称 Google、Wikipedia、DuckDuckGo 不可达。
那是错的。错误的来源值得记录，因为它是一个方法论的教训。

## 教训：测试工具本身也会错

早期用 Node 的 `fetch` 做连通性测试，结论是这些站点全部 CONNECT_TIMEOUT。
但本 skill 的实际运行时是 Python 的 `urllib`，用 Python 重测后绝大多数源可用。

同一批 URL，三种客户端的结果完全不同：

| 源 | curl | Python urllib | Node fetch |
|---|---|---|---|
| google.com | ✅ 200 | ✅ 200 | ❌ CONNECT_TIMEOUT |
| en.wikipedia.org | ✅ 200 | ✅ 200 | ❌ CONNECT_TIMEOUT |
| html.duckduckgo.com | ✅ 200 | ✅ 200 | ❌ CONNECT_TIMEOUT |
| www.reddit.com | — | ⚠️ 403 Blocked | ❌ CONNECT_TIMEOUT |

**结论：连通性结论必须用目标运行时复验，不能用另一个 HTTP 客户端代测。**
Node 在本机的 DNS 解析走了异常路径（`www.google.com` 被解析到投毒 IP），
而 curl 和 Python 能正确回退，这不是网络封锁。

## 当前可用源（Python urllib 实测）

### ✅ 可用

| 源 | 用途 | 接入情况 |
|---|---|---|
| Google 自动补全 | 需求长尾 | 已接入 global 引擎 |
| Bing 自动补全 | 需求长尾（交叉验证） | 已接入 |
| DuckDuckGo 自动补全 | 需求长尾（交叉验证） | 已接入（本机常返回空） |
| iTunes Search API | **消费级市场**：评价数/评分/价格 | 已接入 |
| GitHub Search API | 开发者供给密度 + star | 已接入 |
| DuckDuckGo HTML | 搜索结果/评测站密度 | 已接入 |
| 360 搜索相关搜索 | 中文需求长尾 | 已接入 cn 引擎 |
| 搜狗微信 | 中文内容存量 | 已接入 cn 引擎 |

### ⚠️ 可用但未接入（有理由）

| 源 | 为什么没接 |
|---|---|
| Google 搜索页 | 现在是 JS 重渲染，服务端 HTML 里结果标题几乎为空，解析不可靠 |
| HackerNews Algolia | 评论搜索噪声大，需按发布时间/热度二次过滤才有意义 |
| StackExchange API | **模糊匹配，噪声极大**。`invoice excel` 匹配到 Automapper 问题；`funeral home management` 匹配到 UIPickerView 问题。已停用 |
| npm / PyPI 搜索 | 同样模糊。`sports team scheduling` 返回 52,825 个包。只用其精确下载量端点 |
| Chrome 商店 | 页面可抓但结构不稳定，未解析 |
| Wikipedia / Wikidata | 对"这个方向有没有人付费"无直接价值 |

### ❌ 真不可用（对方主动封锁）

| 源 | 状态 |
|---|---|
| Reddit（含 old.reddit、.json 端点） | HTTP 403 |
| Product Hunt | HTTP 403 |
| G2 / Capterra / AlternativeTo | HTTP 403（Cloudflare） |

这五个是**平台级封锁，不是网络问题**，需要官方 API key 或付费数据源。
不要浪费时间尝试绕过。

## 对判断力的影响

- **消费级市场**：可判。App Store 评价数是消费级饱和最直接的证据。
  实测区分度：receipt scanner 头部 764 万条评价 vs funeral home 3,520 条。
- **B2B 市场**：只能弱判。App Store 评价数对 B2B 无效（企业买家不写评价），
  G2/Capterra 又被封锁。**遇到 B2B 方向，工具会主动标注这一点。**
- **中文市场**：可判。360 相关搜索 + 搜狗微信存量，见 cn 引擎。

**遇到判断不了的市场类型，工具输出「口径限制」而不是硬给一个分数。**
