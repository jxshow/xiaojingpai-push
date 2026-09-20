#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 Markdown 文章(或已排版 HTML)推送到微信公众号草稿箱。

用法:
    # 连通性自检(只取 access_token, 不写草稿)
    python push_to_wechat_draft.py --check

    # Markdown 模式:内置简易转换,只支持基础标题/段落/引用/列表/代码
    python push_to_wechat_draft.py "文章.md" --dry-run
    python push_to_wechat_draft.py "文章.md" --cover "封面.jpg"

    # HTML 模式(推荐):吃 小鲸排 排版好的 HTML
    python push_to_wechat_draft.py "已排版.html" --html --title "自定义标题"
    python push_to_wechat_draft.py "已排版.html" --html --cover "封面.jpg" --push

凭据读取顺序: 环境变量 > 脚本同目录的 .env 文件
    WECHAT_APPID=...
    WECHAT_APPSECRET=...
"""

import argparse
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

# 小鲸排 Skill 的安装位置(与 .env 同级目录),可用环境变量覆盖
SKILLS_DIR = os.path.join(os.path.expanduser("~"), ".workbuddy", "skills")
XJP_DIR = os.environ.get("XJP_DIR", os.path.join(SKILLS_DIR, "xiaojingpai"))
VALIDATOR = os.environ.get(
    "XJP_VALIDATOR",
    os.path.join(XJP_DIR, "scripts", "validate_html.py"),
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# .env 查找顺序: WECHAT_ENV_FILE 环境变量 > 脚本同目录 > 用户级凭据目录
ENV_CANDIDATES = [
    os.environ.get("WECHAT_ENV_FILE", ""),
    os.path.join(BASE_DIR, ".env"),
    r"C:\Users\xhshow\.workbuddy\wechat\.env",
]
ENV_PATH = next((p for p in ENV_CANDIDATES if p and os.path.exists(p)), ENV_CANDIDATES[1])
TOKEN_CACHE_PATH = os.path.join(BASE_DIR, ".wechat_token_cache.json")

API_TOKEN = "https://api.weixin.qq.com/cgi-bin/token"
API_STABLE_TOKEN = "https://api.weixin.qq.com/cgi-bin/stable_token"
API_DRAFT_ADD = "https://api.weixin.qq.com/cgi-bin/draft/add"
# 这些 errcode 都表示 access_token 失效, 需要用新 token 重试
TOKEN_ERRCODES = {40001, 40014, 41001, 42001}
API_DRAFT_UPDATE = "https://api.weixin.qq.com/cgi-bin/draft/update"
API_DRAFT_GET = "https://api.weixin.qq.com/cgi-bin/draft/get"
API_MATERIAL_ADD = "https://api.weixin.qq.com/cgi-bin/material/add_material"

# ---------------- 样式(公众号只认行内样式) ----------------
BODY_STYLE = (
    "font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',"
    "'Hiragino Sans GB','Microsoft YaHei',sans-serif;"
    "font-size:16px;line-height:1.8;color:#3f3f3f;letter-spacing:.4px;"
)
P_STYLE = "margin:0 0 1.05em;"
H2_STYLE = ("margin:1.7em 0 .8em;font-size:19px;font-weight:bold;"
            "color:#1a1a1a;line-height:1.45;")
H3_STYLE = ("margin:1.4em 0 .7em;font-size:17px;font-weight:bold;"
            "color:#1a1a1a;line-height:1.45;")
QUOTE_STYLE = ("margin:1.2em 0;padding:.85em 1em;border-left:3px solid #d0d0d0;"
               "background:#f7f7f7;color:#666;font-size:15px;")
LI_STYLE = "margin:.35em 0;"
HR_STYLE = "border:none;border-top:1px solid #e3e3e3;margin:1.8em 0;"
CODE_STYLE = "background:#f2f2f2;padding:1px 5px;border-radius:3px;font-size:14px;"


# ---------------- 基础 HTTP ----------------
def _read_json(resp):
    return json.loads(resp.read().decode("utf-8"))


def http_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "push-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _read_json(resp)


def http_post_json(url, payload, timeout=30):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "push-bot/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _read_json(resp)


# ---------------- 凭据 ----------------
def load_credentials():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                key, val = raw.split("=", 1)
                env[key.strip()] = val.strip().strip('"').strip("'")
    appid = os.environ.get("WECHAT_APPID") or env.get("WECHAT_APPID")
    secret = os.environ.get("WECHAT_APPSECRET") or env.get("WECHAT_APPSECRET")
    if not appid or not secret:
        sys.exit("x 缺少凭据: 请在 .env 里填 WECHAT_APPID / WECHAT_APPSECRET, "
                 "或设置同名环境变量。")
    return appid, secret


# ---------------- access_token(带本地缓存) ----------------
def get_access_token(appid, secret, force=False):
    """优先用 stable_token(并发安全, 不会被别处刷新顶掉); 拿不到再退回经典 token 接口。"""
    if not force and os.path.exists(TOKEN_CACHE_PATH):
        try:
            with open(TOKEN_CACHE_PATH, "r", encoding="utf-8") as fh:
                cache = json.load(fh)
            if cache.get("appid") == appid and cache.get("expires_at", 0) > time.time() + 300:
                return cache["access_token"]
        except Exception:
            pass

    data = {}
    # 1) stable_token: 并发调用不会互相作废, 是官方推荐方式
    try:
        data = http_post_json(
            API_STABLE_TOKEN,
            {"grant_type": "client_credential", "appid": appid,
             "secret": secret, "force_refresh": bool(force)},
        )
    except Exception as exc:
        data = {"errcode": "network", "errmsg": str(exc)}
    if "access_token" not in data:
        print("[!] stable_token 不可用(%s), 回退经典接口" % data.get("errmsg", data))
        qs = urllib.parse.urlencode(
            {"grant_type": "client_credential", "appid": appid, "secret": secret}
        )
        data = http_get_json(API_TOKEN + "?" + qs)

    if "access_token" not in data:
        sys.exit("x 获取 access_token 失败: %s\n"
                 "  常见原因: IP 不在白名单 / AppID 或 AppSecret 不对。" % data)

    with open(TOKEN_CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "appid": appid,
                "access_token": data["access_token"],
                "expires_at": time.time() + int(data.get("expires_in", 7200)),
            },
            fh,
        )
    return data["access_token"]


def post_with_token(url, body, appid, secret):
    """带 token 的 POST; 命中失效错误码就强制换新 token 重试一次。
       返回 (响应, 最终使用的 token) —— 拿最终 token 去做后续只读校验。"""
    tok = get_access_token(appid, secret)
    res = http_post_json(url + "?access_token=" + tok, body)
    if res.get("errcode") in TOKEN_ERRCODES:
        print("[!] access_token 已失效(%s), 重新获取后重试" % res.get("errcode"))
        tok = get_access_token(appid, secret, force=True)
        res = http_post_json(url + "?access_token=" + tok, body)
    return res, tok


# ---------------- 覆盖保护 ----------------
# draft/update 是「整篇替换」, 不是增量合并。如果后台草稿在人手编辑过,
# 直接更新会把改动整篇冲掉。所以推送前先比对后台内容指纹。
PUSH_STATE_PATH = os.path.join(BASE_DIR, ".wechat_push_state.json")


def _sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def load_push_state():
    try:
        with open(PUSH_STATE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_push_state(state):
    try:
        with open(PUSH_STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        print("[!] 推送记录写入失败(不影响推送结果): %s" % exc)


def fetch_draft(access_token, media_id):
    """只读拉取后台草稿; 失败返回 None。"""
    res = http_post_json(API_DRAFT_GET + "?access_token=" + access_token,
                         {"media_id": media_id})
    if res.get("errcode"):
        print("[!] 读取后台草稿失败: %s" % res)
        return None
    items = res.get("news_item") or []
    return items[0] if items else None


def record_push(access_token, media_id):
    """推送成功后记录「后台当前内容」的指纹(记录后台归一化后的内容, 便于下次比对)。"""
    remote = fetch_draft(access_token, media_id)
    if remote is None:
        return
    state = load_push_state()
    state[media_id] = {"hash": _sha(remote.get("content")), "at": time.time()}
    save_push_state(state)


def guard_overwrite(access_token, media_id, force):
    """更新前检查后台草稿是否被改过。返回 True 才允许继续。"""
    if force:
        print("[!] --force: 已跳过覆盖检查, 后台改动会被冲掉")
        return True
    remote = fetch_draft(access_token, media_id)
    if remote is None:
        print("[!] 读不到后台草稿, 无法判断是否被改过; 跳过检查继续(想严格把关请在网络正常时重试)")
        return True
    stored = load_push_state().get(media_id, {}).get("hash")
    remote_hash = _sha(remote.get("content"))
    if stored and remote_hash == stored:
        return True
    print("x 拒绝覆盖: 后台这篇草稿在最近一次推送之后被改过(或不是本机推的)。")
    print("   后台现状: 标题 %r / 正文 %d 字符"
          % (remote.get("title"), len(remote.get("content") or "")))
    print("   直接更新会整篇替换, 你在后台编辑器里的改动会全部丢失。")
    print("   选项一: 加 --force 强制覆盖(后台改动会丢)")
    print("   选项二: 去掉 --media-id 重新推送 —— 会在草稿箱新建一条, 后台那份保持不动")
    return False


# ---------------- Markdown -> 公众号 HTML ----------------
def _inline(text):
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+?)`",
                  r'<span style="%s">\1</span>' % CODE_STYLE, text)
    return text


def extract_title(md):
    m = re.search(r"^#\s+(.+)$", md, flags=re.MULTILINE)
    if m:
        return m.group(1).strip(), md.replace(m.group(0), "", 1)
    return None, md


def md_to_html(md):
    lines = md.split("\n")
    out = []
    i, n = 0, len(lines)
    para = []

    def flush_para():
        txt = " ".join(x.strip() for x in para).strip()
        if txt:
            out.append('<p style="%s%s">%s</p>' % (BODY_STYLE, P_STYLE, _inline(txt)))
        para.clear()

    while i < n:
        raw = lines[i]
        s = raw.strip()

        if not s:
            flush_para()
            i += 1
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            flush_para()
            out.append('<hr style="%s"/>' % HR_STYLE)
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush_para()
            level, txt = len(m.group(1)), m.group(2).strip()
            style = H2_STYLE if level <= 2 else H3_STYLE
            tag = "h2" if level <= 2 else "h3"
            out.append('<%s style="%s">%s</%s>' % (tag, style, _inline(txt), tag))
            i += 1
            continue

        if s.startswith(">"):
            flush_para()
            block = []
            while i < n and lines[i].strip().startswith(">"):
                block.append(lines[i].strip().lstrip(">").strip())
                i += 1
            inner = "<br/>".join(_inline(x) for x in block if x)
            out.append('<blockquote style="%s">%s</blockquote>' % (QUOTE_STYLE, inner))
            continue

        if re.match(r"^[-*+]\s+", s):
            flush_para()
            items = []
            while i < n and re.match(r"^[-*+]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*+]\s+", "", lines[i].strip()))
                i += 1
            lis = "".join('<li style="%s">%s</li>' % (LI_STYLE, _inline(x)) for x in items)
            out.append('<ul style="margin:1em 0;padding-left:1.4em;">%s</ul>' % lis)
            continue

        if re.match(r"^\d+\.\s+", s):
            flush_para()
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            lis = "".join('<li style="%s">%s</li>' % (LI_STYLE, _inline(x)) for x in items)
            out.append('<ol style="margin:1em 0;padding-left:1.4em;">%s</ol>' % lis)
            continue

        para.append(raw)
        i += 1

    flush_para()
    return "\n".join(out)


# ---------------- 读取 HTML 输入(供 小鲸排 排版产物) ----------------
def read_html_input(path):
    """读 HTML 文件并尝试提取标题(优先 H1,其次 <title>,再退化到文件名)。"""
    with open(path, "r", encoding="utf-8") as fh:
        html = fh.read()
    title = None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if m:
        raw = m.group(1)
        raw = re.sub(r"<[^>]+>", "", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        if raw:
            title = raw
    return html, title


def run_validator(html_path):
    """调小鲸排的 validate_html.py 跑合规校验,有 ERROR 就退出。"""
    if not os.path.exists(VALIDATOR):
        print("[warn] 未找到 小鲸排 校验脚本: %s" % VALIDATOR)
        print("       跳过校验。建议设置环境变量 VALIDATOR 指向实际路径。")
        return
    try:
        proc = subprocess.run(
            [sys.executable, VALIDATOR, html_path],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:
        print("[warn] 校验脚本执行失败: %s" % e)
        return
    print(proc.stdout.rstrip())
    if proc.returncode != 0:
        sys.exit("x 小鲸排 校验未通过,先修 HTML 再推送。")


# ---------------- 上传封面(可选) ----------------
def upload_cover(access_token, image_path):
    if not os.path.exists(image_path):
        sys.exit("x 找不到封面图: %s" % image_path)
    boundary = "----WXBoundary" + uuid.uuid4().hex
    ctype = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    with open(image_path, "rb") as fh:
        blob = fh.read()
    name = os.path.basename(image_path)

    body = b"".join([
        ("--%s\r\n" % boundary).encode(),
        ('Content-Disposition: form-data; name="media"; filename="%s"\r\n' % name).encode(),
        ("Content-Type: %s\r\n\r\n" % ctype).encode(),
        blob,
        b"\r\n",
        ("--%s--\r\n" % boundary).encode(),
    ])
    req = urllib.request.Request(
        API_MATERIAL_ADD + "?access_token=" + access_token + "&type=image",
        data=body,
        headers={
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "User-Agent": "push-bot/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = _read_json(resp)
    if "media_id" not in data:
        sys.exit("x 封面图上传失败: %s" % data)
    return data["media_id"]


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser(description="推送 Markdown / 已排版 HTML 到公众号草稿箱")
    ap.add_argument("article", nargs="?", help="Markdown 或 HTML 文件路径")
    ap.add_argument("--html", action="store_true",
                    help="把 --article 当作 HTML 输入(适用于 小鲸排 排版产物)")
    ap.add_argument("--title", help="覆盖文章标题")
    ap.add_argument("--author", default="", help="作者名")
    ap.add_argument("--digest", default="", help="摘要(留空由微信自动截取)")
    ap.add_argument("--cover", help="封面图路径(可选)")
    ap.add_argument("--thumb-media-id", help="复用已有封面 media_id，不重复上传")
    ap.add_argument("--media-id", help="更新已有草稿(不填则新建草稿)")
    ap.add_argument("--force", action="store_true",
                    help="更新草稿时跳过「后台是否被改过」的检查, 强制整篇覆盖")
    ap.add_argument("--check", action="store_true", help="只校验凭据与网络")
    ap.add_argument("--dry-run", action="store_true", help="只生成 HTML, 不推送")
    ap.add_argument("--no-validate", action="store_true",
                    help="跳过 小鲸排 的合规校验(默认会跑)")
    args = ap.parse_args()

    appid, secret = load_credentials()

    if args.check:
        tok = get_access_token(appid, secret, force=True)
        print("[OK] access_token 获取成功 (前 12 位): %s..." % tok[:12])
        print("[OK] 白名单与凭据均正常, 可以推送")
        return

    if not args.article:
        ap.error("需要提供 Markdown/HTML 文件路径, 或用 --check 自检")

    if args.html:
        html, html_title = read_html_input(args.article)
        title = args.title or html_title or os.path.splitext(os.path.basename(args.article))[0]
        content = html.strip()
        if not args.no_validate:
            run_validator(args.article)
    else:
        with open(args.article, "r", encoding="utf-8") as fh:
            md = fh.read()
        md_title, body_md = extract_title(md)
        title = args.title or md_title or os.path.splitext(os.path.basename(args.article))[0]
        body_html = md_to_html(body_md)
        content = '<section style="%s">%s</section>' % (BODY_STYLE, body_html)

    if args.dry_run:
        if args.html:
            print("[OK] HTML 输入已是最终产物(未再次转换): %s" % args.article)
        else:
            out_path = os.path.splitext(args.article)[0] + ".wechat.html"
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            print("[OK] 已生成 HTML(未推送): %s" % out_path)
        print("     标题: %s" % title)
        return

    tok = get_access_token(appid, secret)

    thumb = args.thumb_media_id or ""
    if thumb:
        print("[OK] 复用已有封面: %s" % thumb)
    elif args.cover:
        thumb = upload_cover(tok, args.cover)
        print("[OK] 封面上传成功: %s" % thumb)

    article = {
        "title": title[:64],
        "author": args.author[:8],
        "digest": args.digest[:120],
        "content": content,
        "content_source_url": "",
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    if thumb:
        article["thumb_media_id"] = thumb
    payload = {"articles": [article]}

    if args.media_id:
        if not guard_overwrite(tok, args.media_id, args.force):
            sys.exit(1)
        # 注意: draft/update 的 articles 是单个对象, 与 draft/add 的数组不同
        body = {"media_id": args.media_id, "index": 0, "articles": article}
        res, used = post_with_token(API_DRAFT_UPDATE, body, appid, secret)
        if res.get("errcode") == 0:
            record_push(used, args.media_id)
            print("[OK] 草稿已更新")
            print("     标题: %s" % title)
            print("     草稿 media_id: %s" % args.media_id)
            print("     去后台查看: https://mp.weixin.qq.com/")
        else:
            sys.exit("x 更新草稿失败: %s" % res)
        return

    res, used = post_with_token(API_DRAFT_ADD, payload, appid, secret)
    if "media_id" in res:
        record_push(used, res["media_id"])
        print("[OK] 已写入草稿箱")
        print("     标题: %s" % title)
        print("     草稿 media_id: %s" % res["media_id"])
        print("     去后台查看: https://mp.weixin.qq.com/")
    else:
        sys.exit("x 写入草稿失败: %s" % res)


if __name__ == "__main__":
    main()
