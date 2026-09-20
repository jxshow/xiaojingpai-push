# -*- coding: utf-8 -*-
"""
publish_pipeline.py —— 公众号排版发布流水线（把 gzh-design-skill 和推送链路串起来）

一条命令走完：已排版 HTML → 合规校验 → 预览页 → 主题色封面 → 推送草稿箱

用法:
    # 1) 全流程：校验 + 预览页 + 封面 + 推送草稿箱
    python publish_pipeline.py "文章_排版_摸鱼绿(moyu-green).html"

    # 2) 只做本地准备(校验+预览页+封面)，不推送(推荐先跑一次看效果)
    python publish_pipeline.py "文章_排版_摸鱼绿(moyu-green).html" --local-only

    # 3) 手动指定主题/标题/封面
    python publish_pipeline.py "已排版.html" --theme red-white --title "我的标题"
    python publish_pipeline.py "已排版.html" --cover "我的封面.png"

设计说明:
    - 「排版」这步必须由 Agent 用 gzh-design-skill 完成(组件库是提示词文档，
      不是代码)，本脚本负责排版之后的全部机械流程。
    - 主题可从文件名 `_排版_{中文名}({英文标识}).html` 自动推断，无需手填。
"""

import argparse
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # 用当前解释器,保证 venv/依赖一致

GZH_SKILL_DIR = os.environ.get(
    "GZH_SKILL_DIR",
    r"C:\Users\xhshow\.workbuddy\skills\gzh-design-skill",
)
GZH_VALIDATOR = os.path.join(GZH_SKILL_DIR, "scripts", "validate_gzh_html.py")
GZH_PREVIEW = os.path.join(GZH_SKILL_DIR, "scripts", "wrap_preview.py")
PUSH_SCRIPT = os.path.join(BASE_DIR, "push_to_wechat_draft.py")
COVER_SCRIPT = os.path.join(BASE_DIR, "make_cover.py")
COVER_PY = os.environ.get(
    "COVER_PY",  # make_cover.py 依赖 Pillow,可能装在 venv 里
    r"C:\Users\xhshow\.workbuddy\binaries\python\envs\default\Scripts\python.exe",
)

# 文件名里的主题中文名 → 主题 ID
THEME_NAME_MAP = {
    "摸鱼绿": "moyu-green",
    "红白色系": "red-white",
    "红白": "red-white",
    "石墨极简": "graphite",
    "石墨极简风": "graphite",
    "留白禅意": "zen",
    "留白禅意风": "zen",
    "摸鱼票据": "moyu-ticket",
    "摸鱼票据风": "moyu-ticket",
    "橄榄手记": "olive",
}
# 主题 ID → 中文名（封面副标题用）
THEME_CN = {v: k for k, v in THEME_NAME_MAP.items()}
THEME_CN.update({
    "moyu-green": "摸鱼绿", "red-white": "红白色系", "graphite": "石墨极简",
    "zen": "留白禅意", "moyu-ticket": "摸鱼票据", "olive": "橄榄手记",
})

STEP = "[%d/%d]"


def infer_theme(path):
    """从文件名推断主题 ID: 支持 (_moyu-green) 或 _排版_摸鱼绿 两种写法。"""
    name = os.path.basename(path)
    m = re.search(r"\(([a-z\-]+)\)", name)
    if m and m.group(1) in set(THEME_NAME_MAP.values()):
        return m.group(1)
    for cn, tid in THEME_NAME_MAP.items():
        if cn in name:
            return tid
    return None


def infer_title(path):
    """从文件名推断标题:去掉 _排版_主题 后缀。"""
    name = os.path.splitext(os.path.basename(path))[0]
    name = re.sub(r"_排版_[^_]*$", "", name)
    name = re.sub(r"_预览$", "", name)
    return name.strip()


def run(cmd, desc):
    print("     $ %s" % " ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    out = (proc.stdout or "").rstrip()
    if out:
        for line in out.splitlines():
            print("       " + line)
    err = (proc.stderr or "").rstrip()
    if err:
        for line in err.splitlines():
            print("       ! " + line)
    return proc.returncode


def main():
    ap = argparse.ArgumentParser(
        description="公众号排版发布流水线: 校验 → 预览页 → 封面 → 推送草稿箱")
    ap.add_argument("html", help="gzh-design-skill 排版产物 HTML 路径")
    ap.add_argument("--theme", help="主题 ID(留空则从文件名推断)")
    ap.add_argument("--title", help="文章标题(留空则从文件名推断)")
    ap.add_argument("--author", default="", help="作者名")
    ap.add_argument("--digest", default="", help="摘要(留空由微信自动截取)")
    ap.add_argument("--cover", help="封面图路径(留空则按主题色自动生成)")
    ap.add_argument("--local-only", action="store_true",
                    help="只做校验+预览页+封面, 不推送草稿箱")
    ap.add_argument("--no-cover", action="store_true", help="跳过封面生成")
    args = ap.parse_args()

    if not os.path.isfile(args.html):
        sys.exit("x 找不到 HTML 文件: %s" % args.html)

    theme = args.theme or infer_theme(args.html)
    title = args.title or infer_title(args.html)
    total = 4
    idx = 0

    print("=" * 58)
    print("公众号排版发布流水线")
    print("  输入: %s" % args.html)
    print("  主题: %s" % (theme or "(未识别,用默认色)"))
    print("  标题: %s" % title)
    print("=" * 58)

    # ---- 1/4 合规校验 ----
    idx += 1
    print("\n%s 合规校验 (gzh-design-skill/validate_gzh_html.py)" % (STEP % (idx, total)))
    if os.path.exists(GZH_VALIDATOR):
        rc = run([PY, GZH_VALIDATOR, args.html], "validate")
        if rc != 0:
            sys.exit("\nx 校验未通过(ERROR 必须清零), 修正 HTML 后重跑。")
    else:
        print("     ! 未找到校验脚本, 跳过: %s" % GZH_VALIDATOR)

    # ---- 2/4 预览页 ----
    idx += 1
    print("\n%s 生成预览页 (右上角有「复制到公众号」按钮)" % (STEP % (idx, total)))
    if os.path.exists(GZH_PREVIEW):
        rc = run([PY, GZH_PREVIEW, args.html], "wrap_preview")
        preview_path = os.path.splitext(args.html)[0] + "_预览.html"
    else:
        print("     ! 未找到预览脚本, 跳过: %s" % GZH_PREVIEW)
        preview_path = None

    # ---- 3/4 封面 ----
    idx += 1
    cover_path = args.cover
    print("\n%s 封面图" % (STEP % (idx, total)))
    if args.no_cover:
        print("     (已跳过)")
    elif cover_path:
        print("     使用指定封面: %s" % cover_path)
    else:
        # 文件名用主题短名,避免超长路径
        cover_path = os.path.join(BASE_DIR, "cover_%s.png" % (theme or "auto"))
        subtitle = THEME_CN.get(theme, "") + " · 公众号排版" if theme else "公众号排版"
        cmd = [COVER_PY, COVER_SCRIPT, title, subtitle, cover_path]
        if theme:
            cmd += ["--theme", theme]
        rc = run(cmd, "make_cover")
        if rc != 0:
            print("     ! 封面生成失败(检查 Pillow 是否装在 %s)" % COVER_PY)
            cover_path = None

    # ---- 4/4 推送 ----
    idx += 1
    print("\n%s 写入公众号草稿箱" % (STEP % (idx, total)))
    if args.local_only:
        print("     (--local-only, 已跳过推送)")
    else:
        cmd = [PY, PUSH_SCRIPT, args.html, "--html", "--title", title]
        if args.author:
            cmd += ["--author", args.author]
        if args.digest:
            cmd += ["--digest", args.digest]
        if cover_path and os.path.exists(cover_path):
            cmd += ["--cover", cover_path]
        else:
            print("     ! 无可用封面, 微信接口会拒绝建草稿(40007)。")
            print("       请用 --cover 指定封面, 或去掉 --no-cover 自动生成。")
            sys.exit(1)
        rc = run(cmd, "push")
        if rc != 0:
            sys.exit("\nx 推送失败。")

    # ---- 汇总 ----
    print("\n" + "=" * 58)
    print("完成。产物:")
    print("  干净正文 HTML : %s" % args.html)
    if preview_path:
        print("  预览页(推荐) : %s" % preview_path)
    if cover_path and os.path.exists(cover_path):
        print("  封面图        : %s" % cover_path)
    if args.local_only:
        print("\n下一步: 浏览器打开预览页确认效果 → 去掉 --local-only 重跑即可推送。")
    else:
        print("\n草稿箱: https://mp.weixin.qq.com/")


if __name__ == "__main__":
    main()