# 小鲸排 Skill · 公众号排版发布流水线 · 完整说明

把 **排版（skill）** 和 **推送（官方 API）** 串成一条链路。全程不需要浏览器登录。

```
文章（Markdown / 腾讯文档）
      │
      ▼
① 排版             ← 必须 Agent 介入（组件库是提示词文档，脚本替代不了）
      │              xiaojingpai-render（字节绿 / AGI绿 / 杂志绿 / 鲸选Pro蓝）
      ▼
   已排版.html（只含行内样式 + <span leaf=""> 包裹）
      │
      ▼
② 推送（一条命令走完 4 步）
      ├─ 1/4  合规校验   xiaojingpai/scripts/validate_html.py
      ├─ 2/4  预览页     排版产物自带的 preview.html（带「复制到公众号」按钮）
      ├─ 3/4  主题色封面 make_cover.py（Pillow，900×383）
      └─ 4/4  写草稿箱   push_to_wechat_draft.py --html（cgi-bin/draft/add）
      │
      ▼
   浏览器核对预览页 → 公众号后台微调 → 群发
```

## 为什么排版不能全自动

`references/theme-*.md` 是给 Agent 读的**组件库提示词**（设计变量、组件 HTML、配方表、映射规则），不是可执行模板。所以"读组件库 → 判文章类型 → 按配方装配 HTML"必须由 Agent 完成；脚本负责它之后的全部机械环节。

## 脚本清单

| 文件 | 职责 |
|---|---|
| `scripts/publish_pipeline.py` | 编排：校验 → 预览页 → 封面 → 推送 |
| `scripts/make_cover.py` | 900×383 封面，`--theme`（小鲸排 4 套 + 上游 6 套）或 `--color`（任意 hex，优先级更高） |
| `scripts/push_to_wechat_draft.py` | 推送主脚本。`--html` 模式吃排版产物；不加则走 Markdown 简易转换 |
| `~/.workbuddy/wechat/.env` | 凭据 `WECHAT_APPID` / `WECHAT_APPSECRET`（Windows 原写作 `C:\Users\xhshow\...`，macOS 换 `~`） |

## make_cover.py 主题色对照（小鲸排）

| 主题 ID | 主色 | 适用 |
|---|---|---|
| `agi-green` AGI绿 | `#2ea250` | **默认**。新闻解读、行业观察、叙事长文 |
| `byte-green` 字节绿 | `#2ea250` | 工具实测、教程、功能清单 |
| `magazine-green` 杂志绿 | `#2ea250` | 测评、快讯、工具盘点 |
| `pro-blue` 鲸选Pro蓝 | `#0057ff` | 商业观察、专业长文 |

绿主题统一色带 `#2ea250 → #09fc3c`，封面色取 `#2ea250`。`--color` 优先级高于 `--theme`，传了 `--color` 就按传的走。

上游遗留主题仍兼容（一般不用）：

| 主题 ID | 主色 |
|---|---|
| `moyu-green` | `#059669` |
| `red-white` | `#DC2626` |
| `graphite` | `#52525B` |
| `zen` | `#4A5D52` |
| `moyu-ticket` | `#059669`+`#FCD34D` |
| `olive` | `#1e1f23`+`#ed7b2f` |

## 环境依赖

| 组件 | 解释器 | 依赖 |
|---|---|---|
| 推送 / 编排脚本 | `C:/Users/xhshow/.workbuddy/binaries/python/versions/3.13.12/python.exe` | 纯标准库 |
| 封面生成 | `C:/Users/xhshow/.workbuddy/binaries/python/envs/default/Scripts/python.exe` | Pillow（装在隔离 venv） |

## 踩过的坑

1. **草稿接口强制要封面**：`thumb_media_id` 传空 → `40007 invalid media_id`。pipeline 默认自动生成封面，除非显式 `--no-cover`。
2. **校验会拦 ERROR**：pipeline 第 1 步就卡住，必须先把 HTML 修干净（目标：`✅ 完全合规`，`span leaf` 全覆盖）。
3. **IP 白名单**：`40164` = 本机公网 IP 不在公众号后台白名单；去「设置与开发 → 基本配置 → IP 白名单」添加。
4. **Git Bash 路径转换**：用 `C:/...`、`D:/...`；写 `/c/Users/...` 会被拼成 `d:\c\Users\...` 而找不到文件。
5. **PowerShell 调用 Python 输出常被吞**：用 bash 跑、重定向到文件再读，或直接 bash 管道。
6. **中文乱码**：先 `export PYTHONIOENCODING=utf-8`。
7. **图片不自动上传**：排版产物里的 `<img>` 只是标签，需手动上传微信素材库后替换——这是排版 skill 本身的限制。
8. **access_token 有缓存**：存在 `scripts/.wechat_token_cache.json`，有效期内（7200s，留 300s 余量）不重复请求；`--check` 会强制刷新。
9. **`40001 invalid credential`**（2026-09-20 实际踩到）：缓存里的 token 尚未过期，服务端却已作废——原因是同一公众号的 token 被别处刷新顶掉了。经典 `cgi-bin/token` 接口每取一次就让上一个失效，多设备/多会话并存时必踩。已改为：
   - 优先用 `cgi-bin/stable_token`（POST，`{"grant_type":"client_credential","appid","secret","force_refresh":false}`），并发安全；
   - `post_with_token()` 在命中 `40001/40014/41001/42001` 时强制换新 token 重试一次；
   - `stable_token` 不可用才回退经典接口。
   都不行再查 AppSecret / IP 白名单。
10. **`draft/update` 整篇覆盖，冲掉后台手工编辑**（2026-09-20 实际踩到）：用户在公众号后台编辑器里加过内容，我为了「避免重复草稿」一直用 `--media-id` 原地更新，等于用本地 HTML 整篇替换掉后台那篇，他的改动就没了（反过来也一样 —— 本地 JSON 从不读后台，两边分叉时必有一边丢）。
    - 修法：新增 `guard_overwrite()` —— 更新前 `draft/get`（只读）拉回后台内容，与 `.wechat_push_state.json` 里记录的「上次推送内容指纹」比对；不一致或本地无记录就**拒绝更新并退出**，提示 `--force` 或改用 `draft/add` 新建。
    - 指纹记的是**后台归一化后**的内容（推送成功后回读一次再算哈希），否则拿「发出的 HTML」和「存回来的 HTML」比会永远不等。
    - 离线用例：`test_guard.py`（5 种情形，全通过）。
    - **行为准则**：用户只要在后台动过这篇，就别带 `--media-id` 推；拿不准就先 `draft/get` 读回来看，或直接问他。
11. **微信把带引号字体的 `style` 整条丢掉**（2026-10-08 实际踩到，最隐蔽的一个）：只要 `font-family` 里出现带引号的字体名（`'Segoe UI'` / `'Helvetica Neue'` / `'SFMono-Regular'`），微信编辑器保存后会把**整个 `style` 属性清空成 `style=""`** —— 不是只丢 font-family，是整条。
    - 症状：本地预览一切正常，推进草稿箱后 AGI绿 H2 的斜体绿编号 `01.`–`06.` 变成无样式纯文本，三张提示词卡的等宽字体/字号/行高全没了，卡片垮成普通段落。
    - 定位方法（可复用）：`draft/get` 回读，逐个 `<span style="…">` 和本地比对，看哪些 style 变成 `style=""`；再用「属性逐项累加」法二分——把 style 按 `;` 拆开，前 N 项拼一起发一个测试草稿，看第几项开始被清空。
    - 修法：带空格的字体名不加引号在 CSS 里同样合法。渲染器已在 `tag()` 里统一过 `wechatSafeStyle()` 去掉引号（`xiaojingpai-render` commit 229d649）。
    - **所以第⑧ 步回读校验不能只看 `<img>` 数**：一定要逐个关键版式（编号 badge、提示词卡、等宽正文、wrapper）比对 style 是否原样保留。计数类指标（`<img>`、`span leaf`）全对上也可能整块版式已经没了。
12. **`draft/add` 的 `articles` 必须是数组**（2026-10-08踩到）：传对象报 `errcode 44003 empty news data`。另外内容太纯简时也会被判 empty news data，包几段普通文字垫一下即可。
13. **IP 白名单可能延迟生效**（2026-10-08 实测）：用户截图确认 IP 已加，但接口连续 10 分钟仍报 `40164`。IP 未变、AppID 正确、强制 IPv4 都无效时就是微信侧生效慢。
    - **对策**：别原地反复重试，直接后台跑轮询脚本（`auto_push.sh` 模式：每 30s 试一次`--check`，一通过就自动串起上传配图 → 注入 → 重渲染 → 校验 → 推送），最长跑 20 分钟。

14. **40164 到底是「IP 变了」还是「代理」**（2026-10-10 实测，别每次重头猜）：先跑这三行，一次定性。

    ```bash
    # a) 微信实际看到的 IP（唯一权威值，直接从报错里抓）
    "$PY" "$PUSH/push_to_wechat_draft.py" --check 2>&1 | grep -o "invalid ip [0-9a-f.:]*"
    # b) 同一次分别走代理 / 禁代理，看是否同一个 IP
    curl -s -x http://127.0.0.1:7897 https://api.ipify.org; echo# 代理出口
    curl -s --noproxy '*' https://api.ipify.org; echo                   # 直连出口
    # c) 归属地（判断是否运营商动态段）
    curl -s --noproxy '*' "http://ip-api.com/json/<IP>?lang=zh-CN"
    ```

    - **报错里的 `ipv6 ::ffff:x.x.x.x` 是 IPv4-mapped 地址**，说明脚本拿到的是本机 IPv4，和 `curl` 直连结果一致 → **代理不是原因**，不用去折腾代理开关。
    - 2026-10-10 实例：白名单里 `114.244.124.109`（北京联通）、`116.115.231.234`（内蒙 CNC）、`103.240.39.52`（兰州联通）**分属三家不同运营商**，而当时出口是 `223.104.40.39`（中国移动北京）。说明是**换了网络**（住处/宽带商/热点），不是同一条宽带轻微漂移。
    - **只有两条路，没有第三条**（2026-10-10 用户截图核实）：后台「IP白名单设置」弹窗**只有输入框，没有任何关闭/跳过开关**。别再跟用户提"关闭 IP 白名单校验"——那个选项不存在，会误导人白找一趟。
        1. **加 IP**（推荐）：把当前出口 IP 追加进输入框保存即可，见上方三步定性法。
        2. **微信云托管**（一般不值得）：官方文档 `developers.weixin.qq.com/doc/subscription/guide/dev/api/` 原话——"(如你使用云托管的云调用，则不需要后续生成 Access Token 过程，也无需配置 IP 白名单)"。代价是要开云托管环境、关联公众号、部署带依赖的 Node 服务（封面要 html2image 转图）、容器内改用 `http://api.weixin.qq.com` 调用、云环境有固定出口 IP。**为偶尔推一篇稿子搭一套云服务不划算**，除非用户本来就在用云托管。
    - **加白之后仍可能延迟生效**：用户加完立刻测往往还是 40164，属微信侧生效慢。此时才启动轮询脚本（`auto_push.sh` 模式：每 30s 试一次 `--check`，一通过就自动串起上传配图 → 注入 → 重渲染 → 校验 → 推送）。2026-10-10 实测加白后等数分钟才通，故脚本设 40 分钟 / 80 次上限。
    - **轮询要放长**：白名单未加时轮询必然白跑。2026-10-10 实测跑满 60 次 / 31 分钟仍 40164。**加白之前不要启动轮询**——先让用户去后台加，确认加完再起轮询，否则只是空转。

## 完整实跑示例（2026-09-20）

```bash
# 文章：苹果OV等抢点发布，"AI OS元周"，到底谁更能打？
# 排版：xiaojingpai-render 的 agi-green，48px 栈式大编号，66 处 span leaf

"$VP" "$SK/make_cover.py" "苹果OV等抢点发布，“AI OS元周”，到底谁更能打？" "鲸选AI · AGI绿" \
    "D:/.../cover_agi-green.png" --color "#2ea250"

"$PY" "$SK/push_to_wechat_draft.py" "D:/.../article.html" --html \
    --title "苹果OV等抢点发布，“AI OS元周”，到底谁更能打？" \
    --author "鲸选AI" --cover "D:/.../cover_agi-green.png"

# → 封面上传成功 Yayqz_O4mX...
# → 已写入草稿箱，media_id Yayqz_O4mXnO6_8w-Uu5jQw4WA-...
# → batchget 验证：total_count 55，该草稿位于列表首位，author=鲸选AI，cover=True
```

## 反面教材（不要重犯）

2026-09-12 / 09-20 两次尝试用 `agent-browser` 驱动浏览器登录公众号推送草稿，结果：扫码登录被打断、会话不跨调用保留、`--profile` 被已运行的 daemon 忽略、无头模式下用户看不到窗口……白白消耗了大量轮次。

**结论：推送环节永远优先走 API。** 只有「后台批量改设置」「抓取后台数据」这类 API 覆盖不到的操作，才考虑浏览器自动化。
