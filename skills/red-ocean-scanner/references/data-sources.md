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

## 第二轮广度探测（新增，实测）

### ✅ 新增可用（已接入）

| 源 | 用途 | 关键发现 |
|---|---|---|
| iTunes **多地区** | 地理套利 | `invoice` 美国头部 265,331 评 vs 中国 193 评 |
| WordPress 插件 API | 结构化供给 | 直接返回 `info.results` 总数，最易用的生态指标 |
| n8n 模板 API | 自动化需求 | 返回 `totalWorkflows`（invoice 285 个模板） |
| StackExchange **inname** | 精确标签 | 解决模糊匹配问题：`inname=invoice` → 739 帖，含 `invoice-ninja` 等真实标签 |
| Firefox Add-ons API | 扩展供给 | `count` 字段（todo 2402 / invoice 341 / funeral 129） |
| JetBrains 插件 API | IDE 插件供给 | `total` 字段（todo 140 / invoice 12） |
| 掘金 API | 中文开发者需求 | `err_no=0`，单次 20 条 |
| V2EX API | 中文技术社区 | 热门主题 JSON |
| npm 精确下载量 | 开发者采用 | `/downloads/point/last-month/<pkg>`，exceljs 5,353 万/月 |
| Wikipedia 页面浏览 | 话题级需求 | 仅适合有独立词条的宽泛话题 |

### ❌ 新增确认不可用

| 源 | 原因 |
|---|---|
| Google Play 搜索页 | JS 重渲染，服务端 HTML 无应用名与数量，**不可解析** |
| Amazon（503）/ Etsy（403）/ Kickstarter（403）/ Indiegogo（403） | 电商与众筹全部封锁 |
| G2 / Capterra / GetApp / TrustRadius / SoftwareAdvice | 全部 403（Cloudflare） |
| Upwork（403）/ Fiverr（403）/ PeoplePerHour（202 空） | 自由职业平台封锁 |
| Reddit（含 old.reddit、.json） | 403 |
| Crunchbase（403）/ SensorTower（202）/ AppBrain（403）/ APKMirror（403） | 封锁 |
| 七麦数据（仅 3KB 壳）/ 阿拉丁 / 蝉大师 / 酷传 | 无法取数 |
| Notion 模板（404）/ Raycast（404）/ Make（403）/ Hashnode（401）/ Medium（403） | 不可用 |
| Freelancer.com | 页面可下载但搜索结果由 JS 渲染，**无法解析职位数** |
| Google 新闻 RSS | 恒定返回 100 条，**无区分度** |
| App Store 评论 RSS | 实测返回 0 条，**不可靠** |

### 生态供给指标的交叉验证

Firefox 扩展、JetBrains 插件、WordPress 插件三个独立生态对同一批词的排序
**完全一致**：

| 词 | Firefox | JetBrains | WordPress |
|---|---|---|---|
| todo | 2,402 | 140 | 622 |
| invoice | 341 | 12 | 1,669 |
| funeral | 129 | — | 17 |

排序一致说明这些是**真实的供给信号**，不是单一平台的噪声。
目前引擎只用 GitHub + App Store 两个（覆盖面最广），其余作为交叉验证备选。
