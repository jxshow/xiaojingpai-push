# 公众号排版发布流水线 · 完整说明

把 **排版（skill）** 和 **推送（官方 API）** 串成一条链路。全程不需要浏览器登录。

```
文章（Markdown / 腾讯文档）
      │
      ▼
① 排版             ← 必须 Agent 介入（组件库是提示词文档，脚本替代不了）
      │              gzh-design-skill（摸鱼绿/红白/石墨/禅意/票据/橄榄）
      │              或 jingxuan-ai-gzh（字节绿/AGI绿/杂志绿/鲸选Pro蓝）
      ▼
   已排版.html（只含行内样式 + <span leaf=""> 包裹）
      │
      ▼
② 推送（一条命令走完 4 步）
      ├─ 1/4  合规校验   gzh-design-skill/scripts/validate_gzh_html.py
      ├─ 2/4  预览页     gzh-design-skill/scripts/wrap_preview.py（带「复制到公众号」按钮）
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
| `scripts/make_cover.py` | 900×383 封面，`--theme`（6 套主题）或 `--color`（任意 hex，优先级更高） |
| `scripts/push_to_wechat_draft.py` | 推送主脚本。`--html` 模式吃排版产物；不加则走 Markdown 简易转换 |
| `C:\Users\xhshow\.workbuddy\wechat\.env` | 凭据 `WECHAT_APPID` / `WECHAT_APPSECRET` |

## make_cover.py 主题色对照（gzh-design-skill）

| 主题 ID | 主色 | 适用 |
|---|---|---|
| `moyu-green` | `#059669` | 教程、测评、清单、工具盘点（默认） |
| `red-white` | `#DC2626` | 深度分析、观点、力量感话题 |
| `graphite` | `#52525B` | 设计、科技评论、专业观点 |
| `zen` | `#4A5D52` | 禅意、极简生活、深度随笔 |
| `moyu-ticket` | `#059669`+`#FCD34D` | 工具对比、创意评测 |
| `olive` | `#1e1f23`+`#ed7b2f` | 内刊手记、深度评测、案例复盘 |

jingxuan-ai-gzh 的主题不在上表内，直接用 `--color`：

| 主题 | 主色 |
|---|---|
| `byte-green` 字节渐变绿 | `#07C160` |
| `agi-green` AGI绿 | `#2ea250` |
| `magazine-green` 杂志绿 | 见 `jingxuan-ai-gzh/references/` |
| `pro-blue` 鲸选Pro蓝 | 见 `jingxuan-ai-gzh/references/` |

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

## 完整实跑示例（2026-09-20）

```bash
# 文章：苹果OV等抢点发布，"AI OS元周"，到底谁更能打？
# 排版：jingxuan-ai-gzh 的 agi-green，48px 栈式大编号，66 处 span leaf

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
