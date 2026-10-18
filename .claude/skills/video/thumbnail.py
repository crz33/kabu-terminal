#!/home/kabu/.venvs/video/bin/python
"""YouTube のサムネイル (1280x720) とチャンネルのアイコン (800x800) を作る。

使い方:
  thumbnail.py <spec.py> <出力ディレクトリ>   # spec の THUMB から thumb.png を作る
  thumbnail.py --icon <出力ファイル>           # チャンネルのアイコン。一度作れば足りる

THUMB は {"kicker": 上の小見出し, "nums": [(ラベル, 値), (ラベル, 値)], "line": 下の一言}。
色とフォントは render.py に揃える。
"""
import importlib.util
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/opentype/ipaexfont-gothic/ipaexg.ttf"
BG = (18, 24, 38)
FG = (236, 240, 245)
MUTED = (150, 160, 178)
ACCENT = (240, 180, 60)
UP = (232, 85, 75)
DOWN = (70, 140, 235)


def font(size):
    return ImageFont.truetype(FONT, size)


def fit(d, s, size, maxw):
    """maxw に収まるまで文字を小さくする。"""
    while d.textlength(s, font=font(size)) > maxw and size > 20:
        size -= 4
    return font(size)


def thumb(spec, out):
    t = spec.THUMB
    W, H = 1280, 720
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 14], fill=ACCENT)
    d.text((60, 52), t["kicker"], font=fit(d, t["kicker"], 46, W - 120), fill=ACCENT)
    colw = (W - 120) / len(t["nums"])
    for i, (label, v) in enumerate(t["nums"]):
        cx = 60 + colw * i + colw / 2
        f = font(44)
        d.text((cx - d.textlength(label, font=f) / 2, 170), label, font=f, fill=MUTED)
        s = f"{v:+.2f}%" if v else "0.00%"
        f = fit(d, s, 190, colw - 30)
        d.text((cx - d.textlength(s, font=f) / 2, 235), s, font=f, fill=UP if v > 0 else DOWN if v < 0 else MUTED)
    f = fit(d, t["line"], 96, W - 120)
    d.text(((W - d.textlength(t["line"], font=f)) / 2, 500), t["line"], font=f, fill=FG)
    f = font(34)
    d.text((W - 60 - d.textlength("けっさんノート", font=f), H - 70), "けっさんノート", font=f, fill=MUTED)
    out.mkdir(parents=True, exist_ok=True)
    im.save(out / "thumb.png")
    print(out / "thumb.png")


def icon(path):
    """紺地に「け」と、上げ下げの棒。YouTube は円く切り抜くので、絵は中央の円に収める。"""
    S = 800
    im = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(im)
    f = font(400)
    s = "け"
    d.text(((S - d.textlength(s, font=f)) / 2, 150), s, font=f, fill=ACCENT)
    # 下に小さな棒を 5 本 (上げは赤、下げは青)
    bars = [0.5, -0.3, 0.8, -0.6, 0.4]
    bw, gap, base = 44, 22, 640
    x0 = (S - (bw * len(bars) + gap * (len(bars) - 1))) / 2
    for i, v in enumerate(bars):
        x = x0 + i * (bw + gap)
        h = 70 * abs(v)
        d.rectangle([x, base - h if v > 0 else base, x + bw, base if v > 0 else base + h], fill=UP if v > 0 else DOWN)
    im.save(path)
    print(path)


def main():
    if sys.argv[1] == "--icon":
        icon(Path(sys.argv[2]))
        return
    spec_path, out = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
    s = importlib.util.spec_from_file_location("spec", spec_path)
    mod = importlib.util.module_from_spec(s)
    s.loader.exec_module(mod)
    thumb(mod, out)


if __name__ == "__main__":
    main()
