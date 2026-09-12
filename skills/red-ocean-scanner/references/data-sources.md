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

## 数据质量陷阱（第三轮审计发现，已修）

这一节记录的是**静默错误**——不会报错、但会得出相反结论的问题。
它们比「取不到数据」危险得多。

### ① iTunes `entity=software` 不排除游戏

实测搜 `banana peeling machine software`（不存在的需求）会返回
**Fruit Ninja®（373,282 条评价）**，触发「不可撼动的既得利益者」否决项，
把一个空需求判成红海。

修法：按 `primaryGenreName` 过滤掉 Games。实测该字段可靠，
且游戏会稳定出现在 `entity=software` 的结果里。

### ② Bing 自动补全会剥掉尾部通用产品词

同一个不存在的查询，两个源的返回完全不同：

| 源 | `banana peeling machine software` |
|---|---|
| Google | **0 条** ✅ |
| Bing | **12 条** ❌ 全是 `banana peeling machine design / reviews / video` |

Bing 忽略了 `software`，改为匹配剩余部分。不识别就会把空需求判成「需求旺」。

修法：只在**查询本身以通用产品词结尾**时，丢弃「等于查询减掉该词」的建议。
必须限定这个条件——否则会误杀合法细化：
`habit tracker` → `habit tracker app` 是正常的向下细化，不是剥离产物。

### ③ DuckDuckGo 限流返回 0 结果而非报错

连续请求 5 次后必然触发。页面含 `anomaly` 标记且**结果数为 0**。
原实现会把它读成「0 个评测站」，即「没有竞争」。

修法：检测 anomaly 标记，退避重试，失败就明确报「维度缺失」并提示
**不要**读成没有竞争。同时把 SERP 从评分中移除——它太不稳定，
会让分数随搜索引擎的心情波动。

### ④ 被证伪并删除的信号

| 信号 | 为什么删 |
|---|---|
| App Store「在售产品数」 | 无区分度：所有品类都返回 22-25 款（模糊匹配产物），且错误惩罚 B2B |
| StackOverflow 模糊搜索 | 噪声极大（`invoice excel` 匹配到 Automapper 问题）。改用 `inname` 精确标签 |
| npm / PyPI 搜索 | 同样模糊（`sports team scheduling` 返回 52,825 个包）。只用精确下载量端点 |
| App Store 评论 RSS | 实测返回 0 条 |
| Google 新闻 RSS | 恒定 100 条，无区分度 |
| SERP 评测站密度 | DDG/Startpage/Mojeek/searx 全部限流，不稳定 |

**原则：宁可少一个维度，也不要一个有噪声的维度。** 噪声维度会让分数看起来
更精确，实际更错。

## 仍然存在的局限（判断力边界）

**B2B 市场只能弱判。** App Store 评价数对 B2B 无效——企业买家很少写评价
（实测：B2B 兽医软件头部 4 万条 vs 消费级 764 万条），而 G2 / Capterra
这一层专业评测站全部 403。引擎检测到 B2B 会主动标注「口径限制」，
不硬给分数。**看到「口径限制」请当作真实的信息缺口，不是噪音。**

**消费级市场之外看不到。** 两个引擎都是开发者/搜索生态视角，
对纯线下生意、非软件品类判断力弱。

**非英文/中文市场不可见。** 其他语言市场（德语、日语、葡语、阿拉伯语）
对本工具几乎不存在。这既是局限，也是提示：未被覆盖的语言市场本身就是方向。

### ⑤ iTunes 模糊匹配会把无关 App 当成市场头部

搜索是**词级模糊匹配**，不是短语匹配。实测搜 `handmade soap business`
返回了 **Etsy（7,275,714 条评价）**——苹果用 "handmade" 做了替换匹配。
Etsy 与「手工皂生意」毫无关系，却触发了「不可撼动的既得利益者」否决项，
把一个真实市场判成红海。

**两个修法叠加**：

1. **相关性过滤**：App 名称至少要命中一个查询实词。Etsy 被剔除后，
   该查询的头部从 7,275,714 降到 10,517。
2. **改用 P75 而不是 max**：P75（降序前 25% 分位）比 max 稳健得多。
   实测对比：

   | 查询 | max | P75 |
   |---|---|---|
   | receipt scanner | 7,642,608 | 268,104 |
   | todo list app | 1,002,579 | 47,272 |
   | funeral home management | 1,748 | 67 |

   注意 todo list app 的 max 是百万级离群值，P75 才反映真实的市场头部。

3. **最小样本量**：相关 App 少于 3 款时该维度不计分。
   实测 `vet clinic software` 过滤后只剩 1 款，那 33,992 条评价会独自
   决定整个消费供给维度——单个样本不能冒充市场信号。

### ⑥ 数据源不适用时必须拒绝作答

最危险的不是「取不到数据」，是**用不对口的数据给出自信的结论**。

实测 `handmade soap business` 被判成「无人区：没人关心」，
还因上面的 Etsy 问题误报「已有 727 万条评价的既得利益者」。
但手工皂是**实体产品**，它的竞争格局既不在 GitHub 也不在 App Store 上。

**修法**：命中实体产品/线下服务标志词时输出 `⚪ 不适用`，并给出替代路径，
而不是硬给红黄绿。

**踩过的坑**：第一版只用实体词判断，把
`restaurant scheduling software` / `coffee shop pos system` /
`bakery inventory software` 这类明显的软件查询也拦掉了——实体词只是行业
限定语。正确规则是 **实体词命中 且 无软件信号** 才算超范围。

**测试教训**：这个 bug 最初没被测试抓到，因为测试**复制**了判定逻辑而不是
调用真代码——复制逻辑的测试会连 bug 的盲区一起复制。现在判定抽成
`is_out_of_scope()`，测试调用它，并且额外检查 `scan()` 确实复用了它。

## 各源限流边界（实测，选择缓存策略的依据）

用连续请求逐个探边界，不是猜的：

| 源 | 实测边界 | 是否给 `Retry-After` | 应对方式 |
|---|---|---|---|
| **GitHub search** | **第 10 次必 403**（硬性 10 次/分钟） | ❌ 不给 | 读 `X-RateLimit-Remaining` **主动等**，窗口重置再打 |
| **DDG HTML** | **第 3 次起返回 anomaly 页** | ❌ 不给 | 单次尝试、不重试、24h 缓存 |
| 搜狗微信 | 2s 间隔下 6+ 次无碍，但会**静默返回 ~5KB 壳页** | ❌ 不给 | 缓存 + 壳页识别 |
| 360 搜索 | 宽松，连打无碍 | ❌ 不给 | 12h 缓存 |
| iTunes | **30 次连打 0 失败** | — | 7d 缓存（不是瓶颈） |
| Google/Bing/DDG 补全 | 12 次连打 0 失败 | — | 24h 缓存 |

### 关键结论：没有任何源给 Retry-After

所以「撞了 403 再退避」是纯浪费——GitHub 要等整分钟窗口重置，
而退避 25s/50s 各一次可能正好错过窗口。必须**主动读 header 并提前等待**。

### GitHub 配额是跨进程的

它按 IP 限，不是按进程限。在内存里记计数毫无意义——换个进程照样撞墙。
所以配额状态落盘到 `.cache/_github_quota.json`。

## 缓存策略

`_http.py` 统一处理，缓存时长按「数据变化速度」定，不是拍脑袋：

| 源 | TTL | 理由 |
|---|---|---|
| github / itunes | 7 天 | 仓库数、评价数一周内几乎不变 |
| autocomplete / ddg | 24 小时 | 会随热点变，一天内足够稳 |
| 360 | 12 小时 | 相关搜索词随话题波动 |
| sogou | 6 小时 | 文章存量每天在动 |

**缓存同时也是最有效的限流手段**：不打请求就不会被限。

实测收益（同一查询）：

```
冷缓存  12.3s
热缓存   0.08s   ← 150x
```

### 只缓存「确定有效」的响应

这是踩过的坑：搜狗被限流时返回约 **5KB 的壳页**而不是报错。
早期版本把它当正常响应当缓存了 6 小时——**把一个瞬时状态固化成
六小时的错误结论**，之后每次命中缓存都继续误判。

现在 `response_is_valid()` 会检查响应长度与风控特征，
无效响应**一律不写缓存**，并按限流抛出，让上层区分「没数据」和「被打回」。

缓存只存响应体，**不存任何请求头**——token 不会落盘（有测试守着）。

### 运维命令

```bash
python3 scan.py --cache-stats     # 看占用与各源分布
python3 scan.py --clear-cache     # 清空
export RED_OCEAN_NO_CACHE=1       # 本次运行禁用缓存
export RED_OCEAN_CACHE=/path      # 换缓存目录
```

### 负缓存：失败的源不该反复重试

DDG HTML 第 3 次起必拦，所以它**永远不会成功、也就永远不会被正缓存**——
没有负缓存的话每次扫描都要白等一次超时（实测 0.95–1.3s）。

`_http.py` 会记住某类源刚失败过，冷却期内直接跳过：

| 源 | 冷却 | 理由 |
|---|---|---|
| ddg | 30 分钟 | 拦得最狠 |
| sogou | 5 分钟 | 风控持续数分钟 |
| 其他 | 不记 | 避免掩盖真实故障 |

`RED_OCEAN_NO_COOLDOWN=1` 可强制重试。

### 重试预算：限流持续数分钟时，重试是白等

搜狗被限流时风控持续**数分钟**，而原实现重试 3 次、退避 25s + 50s——
实测中文引擎冷启动因此要 **78.8 秒**。

关键在于「重试能成功」的前提是**限流是瞬时的**，对搜狗并不成立。
所以加了单次 fetch 的总重试预算 `RETRY_BUDGET = 20s`：超过就快速失败，
交给负缓存。效果：中文引擎冷启动 78.8s → **3.6s**。

### 汇总：实测提速

| 场景 | 改前 | 改后 |
|---|---|---|
| 全局引擎冷缓存 | 13.4s | 11–17s（含限流等待） |
| 全局引擎热缓存 | 13.4s | **0.06s** |
| 中文引擎冷启动 | 78.8s | **3.6s** |
| 中文引擎热缓存 | — | **3.1s** |
| 被限流时的行为 | 静默误判 / 干等 75s | 明确标记 + 5 分钟冷却 |
