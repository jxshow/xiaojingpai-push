# -*- coding: utf-8 -*-
"""
生成公众号封面图 (900x383, 2.35:1)

用法:
    # 普通模式:自己指定主色
    python make_cover.py "主标题" "副标题" [输出路径]
    python make_cover.py "主标题" "副标题" output.png --color "#059669"

    # 主题模式:从 gzh-design-skill 的 theme-index.md 自动取色
    python make_cover.py "主标题" "副标题" output.png --theme moyu-green
    python make_cover.py "主标题" "副标题" output.png --theme red-white

主题 ID 列表:
    moyu-green      摸鱼绿     #059669
    red-white       红白色系   #DC2626
    graphite        石墨极简   #52525B
    zen             留白禅意   #4A5D52
    moyu-ticket     摸鱼票据   #059669
    olive           橄榄手记   #1e1f23 (橙强调 #ed7b2f)

兜底颜色:深蓝渐变(8,14,28)→(24,46,90)
"""
import argparse
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 900, 383
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_REG = r"C:\Windows\Fonts\msyh.ttc"

THEME_INDEX = os.environ.get(
    "GZH_THEME_INDEX",
    r"C:\Users\xhshow\.workbuddy\skills\gzh-design-skill\references\theme-index.md",
)

# 主题 ID → 关键词,用来在 markdown 表格行里匹配
THEME_KEYWORDS = {
    "moyu-green": "摸鱼绿",
    "red-white": "红白色系",
    "graphite": "石墨极简风",
    "zen": "留白禅意风",
    "moyu-ticket": "摸鱼票据风",
    "olive": "橄榄手记",
}

# 主题默认配色(主色, 浅底, 强调),覆盖 gzh-design-skill 表格
THEME_DEFAULT_COLORS = {
    "moyu-green": ("#059669", "#A7F3D0", "#10B981"),
    "red-white": ("#DC2626", "#FECACA", "#EF4444"),
    "graphite": ("#52525B", "#A1A1AA", "#27272A"),
    "zen": ("#4A5D52", "#B5C8BC", "#2F3F37"),
    "moyu-ticket": ("#059669", "#FCD34D", "#10B981"),  # 票据感,辅以金色
    "olive": ("#1e1f23", "#3F3F46", "#ed7b2f"),       # 墨黑+橙强调
}


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def parse_theme_index(theme_id):
    """读 theme-index.md 的 markdown 表格,找这一行,提取主色 hex。"""
    if not os.path.exists(THEME_INDEX):
        return None
    kw = THEME_KEYWORDS.get(theme_id)
    if not kw:
        return None
    with open(THEME_INDEX, "r", encoding="utf-8") as fh:
        text = fh.read()
    # 表格行形如: | 摸鱼绿 | `#059669` emerald | 教程、... |
    for line in text.splitlines():
        if kw in line and line.lstrip().startswith("|"):
            m = re.search(r"`?#[0-9A-Fa-f]{6}`?", line)
            if m:
                return m.group(0).strip("`")
    return None


def resolve_color(theme_id, override):
    if override:
        return override.lstrip("#"), None, None
    if theme_id:
        # 优先从 theme-index.md 读,失败用默认表
        hex_main = parse_theme_index(theme_id) or THEME_DEFAULT_COLORS[theme_id][0]
        _, light, accent = THEME_DEFAULT_COLORS[theme_id]
        return hex_main, light, accent
    return "#172554", "#60A5FA", "#3B82F6"  # 兜底深蓝


def make_cover(title, subtitle, out_path, theme_id=None, override_color=None):
    main_hex, light_hex, accent_hex = resolve_color(theme_id, override_color)
    top_hex = "#0b1120"  # 顶部偏深,无论主题色都压得住

    top_rgb = hex_to_rgb(top_hex)
    main_rgb = hex_to_rgb(main_hex)
    light_rgb = hex_to_rgb(light_hex) if light_hex else None
    accent_rgb = hex_to_rgb(accent_hex) if accent_hex else main_rgb

    # 渐变:深→主色(只在底部混入主色,主体保持深色,文字才不糊)
    bottom_rgb = tuple(int(main_rgb[i] * 0.35 + top_rgb[i] * 0.65) for i in range(3))

    img = Image.new("RGB", (W, H), top_rgb)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        # 渐变靠底部 1/3 才混入主题色
        if t < 0.55:
            r, g, b = top_rgb
        else:
            mix = (t - 0.55) / 0.45
            r = int(top_rgb[0] + (bottom_rgb[0] - top_rgb[0]) * mix)
            g = int(top_rgb[1] + (bottom_rgb[1] - top_rgb[1]) * mix)
            b = int(top_rgb[2] + (bottom_rgb[2] - top_rgb[2]) * mix)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # 半透明光斑
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    if light_rgb:
        od.ellipse([620, -140, 1080, 320], fill=accent_rgb + (50,))
        od.ellipse([-140, 240, 240, 620], fill=light_rgb + (32,))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # 强调线(主题主色)
    draw.line([(60, 176), (196, 176)], fill=accent_rgb, width=3)

    # 文字
    size = 46
    f1 = ImageFont.truetype(FONT_BOLD, size)
    while draw.textlength(title, font=f1) > W - 120 and size > 24:
        size -= 2
        f1 = ImageFont.truetype(FONT_BOLD, size)
    f2 = ImageFont.truetype(FONT_REG, 20)

    draw.text((58, 98), title, font=f1, fill=(255, 255, 255))
    if subtitle:
        draw.text((62, 200), subtitle, font=f2, fill=(190, 200, 215))

    img.save(out_path, "PNG")
    print("saved: %s" % out_path)
    print("  color: %s (theme=%s)" % (main_hex, theme_id or "default"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="生成公众号封面图")
    ap.add_argument("title", nargs="?", default="验证码，被 AI 通关了")
    ap.add_argument("subtitle", nargs="?", default="GPT-6 Astra 通关 48 关全记录")
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--theme", choices=list(THEME_KEYWORDS.keys()),
                    help="主题 ID(从 gzh-design-skill theme-index 取色)")
    ap.add_argument("--color", help="自定义主色 hex,优先级高于 --theme")
    args = ap.parse_args()

    if not args.out:
        base = os.path.dirname(os.path.abspath(__file__))
        args.out = os.path.join(base, "cover_" + (args.theme or "default") + ".png")

    make_cover(args.title, args.subtitle, args.out, args.theme, args.color)