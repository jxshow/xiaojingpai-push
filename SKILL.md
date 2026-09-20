---
name: jingxuan-draft-push
description: 用微信公众平台 AppID/AppSecret 走官方 API，把已排版的公众号 HTML 推送进草稿箱（自动合规校验 + 生成主题色封面 + 写入草稿）。当用户说"推送到公众号后台""推到草稿箱""排版后一键推送""发布到公众号"时使用。禁止为此使用浏览器扫码登录——凭据已在本机 .env，直接调 API。
agent_created: true
---

# jingxuan-draft-push · 公众号 API 推送

## 最重要的一条：不要开浏览器

公众号草稿是**可以用官方 API 写的**，凭据已存在本机：

```
C:\Users\xhshow\.workbuddy\wechat\.env        # WECHAT_APPID / WECHAT_APPSECRET
```

**绝对不要**为了推送去驱动浏览器登录 `mp.weixin.qq.com`：那会遇到扫码、验证码、会话不跨调用保留等一堆问题，而且完全没有必要。先 `--check` 确认凭据可用，再直接推送。

## 三步流程

```bash
# 环境准备（Git Bash 必做，否则 dirname/cd 报错）
export PATH="/usr/bin:/bin:/c/Windows/System32:$PATH"
export PYTHONIOENCODING=utf-8          # 中文不乱码
PY="C:/Users/xhshow/.workbuddy/binaries/python/versions/3.13.12/python.exe"
VP="C:/Users/xhshow/.workbuddy/binaries/python/envs/default/Scripts/python.exe"   # 带 Pillow，只给封面用
SK="C:/Users/xhshow/.workbuddy/skills/jingxuan-draft-push/scripts"

# ① 连通性自检（不写草稿）
"$PY" "$SK/push_to_wechat_draft.py" --check

# ② 生成封面（草稿接口强制要封面，缺了报 40007）
"$VP" "$SK/make_cover.py" "文章标题" "副标题" "输出路径/cover.png" --color "#2ea250"

# ③ 推送
"$PY" "$SK/push_to_wechat_draft.py" "已排版.html" --html \
    --title "文章标题" --author "鲸选AI" --cover "输出路径/cover.png"
```

成功会打印 `草稿 media_id: ...`。

一键版（校验 + 预览页 + 封面 + 推送）：

```bash
"$PY" "$SK/publish_pipeline.py" "已排版.html" --title "文章标题" --author "鲸选AI"
# 加 --local-only 则只出本地产物、不推送
```

## 更新已有草稿 / 复用封面

内容改了要重推时，用这两个参数原地更新，避免后台出现重复草稿、素材库重复封面：

```bash
"$PY" "$SK/push_to_wechat_draft.py" "已排版.html" --html \
    --title "标题" --author "鲸选AI" \
    --thumb-media-id "<已有封面 media_id>" \
    --media-id "<已有草稿 media_id>"
```

⚠️ `draft/update` 的 `articles` 是**单个对象**，而 `draft/add` 是**数组** —— 传错报 `47001 data format error`。

### ⚠️ 更新 = 整篇覆盖，会冲掉后台的手工编辑

`draft/update` **不是增量合并**，而是用你传的 `content` 整篇替换掉后台那篇。用户在公众号后台编辑器里加的图、删的字、调的顺序，只要推一次就全没了。

脚本已内置覆盖保护：更新前先用 `draft/get`（只读）拉回后台内容，和本地记录的「上次推送内容指纹」（`scripts/.wechat_push_state.json`）比对：

- 一致 → 正常更新
- 不一致（后台被改过）或本地无记录 → **拒绝更新并退出**，提示两个选项：加 `--force` 强制覆盖，或去掉 `--media-id` 新建一条草稿保留后台那份
- 读不到后台（网络/权限问题）→ 打印提示后继续

所以：**只要用户在后台动过这篇，就不要带 `--media-id` 推**，除非他明确说「覆盖掉」。不确定时先 `draft/get` 读回来看看。

## 正文配图（必须走 uploadimg）

正文里的图片不能直接写外链，必须先用 `cgi-bin/media/uploadimg` 换成 `mmbiz.qpic.cn` 地址再写进 `content`，否则不显示。

```
POST https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token=TOKEN
multipart 字段名 media；仅 JPG/PNG，且 < 1MB
返回 {"url": "http://mmbiz.qpic.cn/..."}
```

要点：

- 返回的是 `http://`，但入库时用 `https://` 更稳（同域名 https 可正常访问）。
- 超 1MB 先降质缩放（Pillow：质量 90/84/78/72 × 宽度 1600/1400/1200/1000 逐档试）。
- 图注写明图源（如「图源：Apple 官方新闻稿」），比裸图稳妥。
- 取图优先**官方新闻稿**（Apple Newsroom 的 `apple.com/newsroom/images/...` 可直接抓）；JS 渲染的页面（腾讯新闻、OPPO 官网）抓不到正文图。
- 入库后用 `draft/get` 复核：`<img>` 数、`border-bottom` 数、`font-weight:700` 数是否与本地一致，确认微信没吞样式。

## 默认参数

| 项 | 值 |
|---|---|
| 作者 | `鲸选AI`（接口上限 8 字；标题上限 64 字） |
| 封面尺寸 | 900×383，`make_cover.py` 生成 |
| AGI绿 主色 | `#2ea250`（jingxuan-ai-gzh 的 agi-green，用 `--color` 传） |
| 校验脚本 | `C:\Users\xhshow\.workbuddy\skills\gzh-design-skill\scripts\validate_gzh_html.py` |

## 已知坑

1. **草稿接口强制要封面**：`thumb_media_id` 为空 → `40007 invalid media_id`。
2. **IP 白名单**：`--check` 报 `40164` 说明本机公网 IP 不在公众号后台白名单，需先去后台加 IP。
3. **Git Bash 路径**：一律用 `C:/...`、`D:/...`，**不要用 `/c/...`**（会被错误拼成 `d:\c\...`）。
4. **封面必须用 venv 解释器**（Pillow 装在 `envs/default`），其余脚本用 managed Python。
5. **推送前必过校验**：`validate_gzh_html.py` 有 ERROR 就先修 HTML。
6. **图片不会自动上传**：排版产物里的 `<img>` 只是标签，需先传微信素材库再替换。
7. **凭据优先级**：环境变量 `WECHAT_APPID`/`WECHAT_APPSECRET` > `WECHAT_ENV_FILE` 指定的文件 > 脚本同目录 `.env` > 用户级凭据目录。
8. `.env` 含明文密钥，别截图、别提交仓库；怀疑泄露就去后台重置 AppSecret。
9. **`40001 invalid credential`**：缓存里的 token 看着没过期，但已被别处刷新顶掉（多设备 / 多会话同时用同一公众号时常见）。脚本已改用 `stable_token`（并发安全、不会被顶掉），并在命中 `40001/40014/42001` 时自动强制换新 token 重试一次；仍失败才是 AppSecret 或 IP 白名单问题。
10. **`draft/update` 会整篇覆盖，冲掉后台手工编辑**（2026-09-20 实际踩到：用户已在后台加过内容，一次更新全丢）。脚本已加覆盖保护，详见上文「更新 = 整篇覆盖」。**本地 JSON 是唯一事实源，后台的改动永远不会被拉回本地** —— 两边分叉时必有一边丢，所以推之前要问清楚。

## 推送后验证

```bash
"$PY" - <<'EOF'
import json,urllib.request
t=json.load(open(r'C:\Users\xhshow\.workbuddy\skills\jingxuan-draft-push\scripts\.wechat_token_cache.json',encoding='utf-8'))['access_token']
b=json.dumps({'offset':0,'count':5,'no_content':1}).encode()
r=urllib.request.Request('https://api.weixin.qq.com/cgi-bin/draft/batchget?access_token='+t,data=b,headers={'Content-Type':'application/json'},method='POST')
d=json.loads(urllib.request.urlopen(r,timeout=20).read().decode())
print('total:',d.get('total_count'))
for i in d.get('item',[]):
    for a in i['content']['news_item']: print(' -',a['title'],'| author=',a['author'],'| cover=',bool(a.get('thumb_media_id')))
EOF
```

详见 `references/pipeline-notes.md`。
