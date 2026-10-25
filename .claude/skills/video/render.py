#!/home/kabu/.venvs/video/bin/python
"""スライド + 読み上げ + 字幕の解説動画を作る。

使い方: render.py <spec.py> <出力ディレクトリ>
spec.py は SLIDES (スライドのリスト) と TITLE を定義する。各スライドは
{"kind": ..., ..., "say": [文, ...]} で、文ごとに読み上げと字幕を作る。
"""
import base64
import json
import os
import importlib.util
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FONT = "/usr/share/fonts/opentype/ipaexfont-gothic/ipaexg.ttf"
VOICE = "ja-JP-Chirp3-HD-Sulafat"  # Google Cloud Text-to-Speech。2026-10-18 に聴き比べて選んだ
KEY_FILE = Path.home() / ".config/kabu/video.env"  # GOOGLE_TTS_API_KEY=... (権限 600)
GAP = 0.35  # 文と文の間の無音 (秒)

BG = (18, 24, 38)
FG = (236, 240, 245)
MUTED = (150, 160, 178)
ACCENT = (240, 180, 60)
UP = (232, 85, 75)     # 上げ (日本の相場表示に合わせて赤)
DOWN = (70, 140, 235)  # 下げ (青)
GRID = (55, 65, 85)
SUB_BG = (0, 0, 0, 170)

# 読み上げ用の言い換え (字幕には元の表記を出す)
READING = {"値がさ": "ねがさ", "kessannote": "けっさんノート", "kabu": "カブ"}


def font(size):
    return ImageFont.truetype(FONT, size)


def text_w(d, s, f):
    return d.textlength(s, font=f)


def center(d, y, s, f, fill=FG):
    d.text(((W - text_w(d, s, f)) / 2, y), s, font=f, fill=fill)


def header(d, s, page=None):
    d.text((90, 60), s, font=font(64), fill=FG)
    d.rectangle([90, 150, 250, 156], fill=ACCENT)
    if page:
        f = font(30)
        d.text((W - 90 - text_w(d, page, f), 80), page, font=f, fill=MUTED)


def pct_color(v):
    return UP if v > 0 else DOWN if v < 0 else MUTED


def fmt_pct(v):
    return f"{v:+.2f}%" if v != 0 else "0.00%"


def draw_title(d, s):
    center(d, 300, s["kicker"], font(44), ACCENT)
    center(d, 390, s["title"], font(96))
    center(d, 540, s["sub"], font(52), MUTED)


def draw_bignums(d, s):
    header(d, s["head"], s.get("page"))
    n = len(s["nums"])
    colw = (W - 180) / n
    for i, (label, val, note) in enumerate(s["nums"]):
        cx = 90 + colw * i + colw / 2
        f = font(46)
        d.text((cx - text_w(d, label, f) / 2, 290), label, font=f, fill=MUTED)
        vs = fmt_pct(val) if isinstance(val, float) else val
        f = font(150)
        col = pct_color(val) if isinstance(val, float) else FG
        d.text((cx - text_w(d, vs, f) / 2, 370), vs, font=f, fill=col)
        f = font(38)
        d.text((cx - text_w(d, note, f) / 2, 570), note, font=f, fill=MUTED)
    if s.get("foot"):
        center(d, 760, s["foot"], font(44))


def fmt_val(v, s):
    """unit があれば金額などの量、無ければ騰落率として書く。"""
    if s.get("unit"):
        return f"{v:,.{s.get('digits', 0)}f}{s['unit']}"
    return fmt_pct(v)


def bar_color(v, s, dim=False):
    """騰落率は上げ赤・下げ青。量 (unit あり) は向きの意味が無いのでアクセント色。"""
    col = (ACCENT if v >= 0 else DOWN) if s.get("unit") else (pct_color(v) if v else MUTED)
    return tuple(int(ch * 0.55) for ch in col) if dim else col


def nice_step(x):
    """x 以上で一番小さい 1・2・5 × 10^n。"""
    e = 10 ** (len(str(int(x))) - 1)
    return next(m * e for m in (1, 2, 5, 10) if m * e >= x)


def draw_bars(d, s):
    """日ごとや期ごとなど、カテゴリ × 系列の縦棒。"""
    header(d, s["head"], s.get("page"))
    cats, series = s["cats"], s["series"]  # series: [(名前, [値...])]
    dims = set(s.get("dim", []))  # 予想など、薄く描くカテゴリの番号
    x0, x1, y0, y1 = 220, W - 120, 250, 780  # 日付のラベルを 2 行の字幕より上に置く
    vmax = max(abs(v) for _, vals in series for v in vals) * 1.25
    if min(v for _, vals in series for v in vals) >= 0:  # 全部プラスなら 0 を下端に置く
        zero, sc = y1, (y1 - y0) / vmax
        ticks = [0, vmax * 0.4, vmax * 0.8]
        if s.get("unit"):  # 金額は 1,000 や 2,000 のようなきりのいい目盛りにする
            step = nice_step(vmax / 4)
            ticks = [step * k for k in range(int(vmax / step) + 1)]
    else:
        zero, sc = (y0 + y1) / 2, (y1 - y0) / 2 / vmax
        ticks = [-vmax * 0.8, -vmax * 0.4, 0, vmax * 0.4, vmax * 0.8]
    for t in ticks:
        y = zero - t * sc
        d.line([x0, y, x1, y], fill=GRID if t else MUTED, width=2 if t else 3)
        if s.get("unit"):
            lab = f"{t:,.0f}" if t else "0"
        else:
            lab = f"{t:+.1f}%" if t else "0%"
        f = font(28)
        d.text((x0 - 20 - text_w(d, lab, f), y - 16), lab, font=f, fill=MUTED)
    groupw = (x1 - x0) / len(cats)
    barw = groupw * 0.7 / len(series)
    shades = [1.0, 0.55]
    for ci, c in enumerate(cats):
        gx = x0 + groupw * ci + groupw * 0.15
        for si, (_, vals) in enumerate(series):
            v = vals[ci]
            col = tuple(int(ch * shades[si]) for ch in bar_color(v, s, ci in dims))
            bx = gx + barw * si
            y = zero - v * sc
            d.rectangle([bx + 6, min(y, zero), bx + barw - 6, max(y, zero) + (2 if v == 0 else 0)], fill=col)
            lab = fmt_val(v, s)
            f = font(34 if s.get("unit") and len(series) == 1 else 28)
            ly = y - 44 if v >= 0 else y + 8
            d.text((bx + barw / 2 - text_w(d, lab, f) / 2, ly), lab, font=f, fill=FG)
        f = font(36)
        d.text((x0 + groupw * ci + groupw / 2 - text_w(d, c, f) / 2, y1 + 15), c, font=f, fill=FG)
    # 凡例
    lx = W - 120
    for si, (name, _) in reversed(list(enumerate(series))):
        f = font(32)
        lx -= text_w(d, name, f) + 70
        col = tuple(int(ch * shades[si]) for ch in (ACCENT if s.get("unit") else UP))
        d.rectangle([lx, 190, lx + 36, 222], fill=col)
        d.text((lx + 46, 188), name, font=f, fill=FG)
    if s.get("note"):
        d.text((x0, 200), s["note"], font=font(32), fill=ACCENT)


def draw_hbars(d, s):
    """銘柄・業種などの横棒。"""
    header(d, s["head"], s.get("page"))
    rows = s["rows"]  # [(名前, 値)]
    f = font(44)
    x0 = 90 + max(text_w(d, name, f) for name, _ in rows) + 30
    labs = [fmt_val(v, s) if s.get("unit") else f"{v:+.1f}%" for _, v in rows]
    x1, y0 = W - 110 - max(text_w(d, lab, f) for lab in labs), 230
    vmax = max(abs(v) for _, v in rows)
    rowh = min(110, (780 - y0) / len(rows))
    for i, (name, v) in enumerate(rows):
        y = y0 + i * rowh
        f = font(44)
        d.text((x0 - 30 - text_w(d, name, f), y + rowh / 2 - 26), name, font=f, fill=FG)
        w = (x1 - x0) * abs(v) / vmax
        d.rectangle([x0, y + rowh * 0.18, x0 + w, y + rowh * 0.82], fill=bar_color(v, s))
        lab = fmt_val(v, s) if s.get("unit") else f"{v:+.1f}%"
        d.text((x0 + w + 20, y + rowh / 2 - 26), lab, font=f, fill=FG)
    if s.get("foot"):
        d.text((90, 800), s["foot"], font=font(38), fill=MUTED)


def draw_bullets(d, s):
    header(d, s["head"], s.get("page"))
    y = 230
    for item in s["items"]:
        if isinstance(item, tuple):  # (ラベル, 本文)
            d.text((110, y), item[0], font=font(44), fill=ACCENT)
            d.text((560, y), item[1], font=font(44), fill=FG)
        else:
            d.ellipse([110, y + 16, 126, y + 32], fill=ACCENT)
            d.text((150, y), item, font=font(44), fill=FG)
        y += 90
    if s.get("foot"):
        d.text((110, 790), s["foot"], font=font(34), fill=MUTED)


def draw_line(d, s):
    """株価などの折れ線。marks で日付に印と注記を付ける。"""
    header(d, s["head"], s.get("page"))
    dates, vals = s["dates"], s["values"]
    x0, x1, y0, y1 = 220, W - 120, 260, 760
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.12
    lo, hi = max(0, lo - pad), hi + pad
    sx = (x1 - x0) / (len(vals) - 1)
    sy = (y1 - y0) / (hi - lo)
    px = lambda i: x0 + i * sx
    py = lambda v: y1 - (v - lo) * sy
    step = 10 ** (len(str(int(hi - lo))) - 1)
    t = (lo // step + 1) * step
    while t < hi:
        y = py(t)
        d.line([x0, y, x1, y], fill=GRID, width=2)
        lab = f"{t:,.0f}"
        f = font(28)
        d.text((x0 - 20 - text_w(d, lab, f), y - 16), lab, font=f, fill=MUTED)
        t += step
    # 月の目盛り。月が替わった最初の日に縦線
    f = font(30)
    for i in range(1, len(dates)):
        if dates[i][:7] != dates[i - 1][:7] and int(dates[i][5:7]) % s.get("month_step", 2) == 1:
            x = px(i)
            d.line([x, y1, x, y1 + 10], fill=MUTED, width=2)
            lab = f"{dates[i][2:4]}/{int(dates[i][5:7])}"
            d.text((x - text_w(d, lab, f) / 2, y1 + 16), lab, font=f, fill=MUTED)
    d.line([(px(i), py(v)) for i, v in enumerate(vals)], fill=ACCENT, width=5, joint="curve")
    for date, label, side in s.get("marks", []):
        i = dates.index(date)
        x, y = px(i), py(vals[i])
        d.ellipse([x - 11, y - 11, x + 11, y + 11], fill=FG)
        f = font(32)
        tw = text_w(d, label, f)
        tx = min(max(x - tw / 2, x0), x1 - tw)
        ty = y - 62 if side == "up" else y + 22
        d.rectangle([tx - 8, ty - 2, tx + tw + 8, ty + 42], fill=BG)  # 線と重ねない
        d.text((tx, ty), label, font=f, fill=FG)
    if s.get("note"):
        d.text((x0, 200), s["note"], font=font(32), fill=ACCENT)


DRAW = {"title": draw_title, "bignums": draw_bignums, "bars": draw_bars,
        "hbars": draw_hbars, "bullets": draw_bullets, "line": draw_line}


def wrap(d, s, f, maxw):
    lines, cur = [], ""
    for ch in s:
        if text_w(d, cur + ch, f) > maxw and ch not in "。、)」%":
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + [cur] if cur else lines


def with_subtitle(base, s):
    img = base.convert("RGBA")
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f = font(46)
    lines = wrap(d, s, f, W - 300)
    lh = 64
    top = H - 60 - lh * len(lines) - 30
    d.rectangle([0, top, W, H], fill=SUB_BG)
    for i, line in enumerate(lines):
        d.text(((W - text_w(d, line, f)) / 2, top + 22 + i * lh), line, font=f, fill=(255, 255, 255, 255))
    return Image.alpha_composite(img, ov).convert("RGB")


def reading(s):
    for k, v in READING.items():
        s = s.replace(k, v)
    return s


def api_key():
    if os.environ.get("GOOGLE_TTS_API_KEY"):
        return os.environ["GOOGLE_TTS_API_KEY"]
    for line in KEY_FILE.read_text().splitlines():
        if line.startswith("GOOGLE_TTS_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"GOOGLE_TTS_API_KEY が {KEY_FILE} にない")


def tts(text, path):
    body = {"input": {"text": reading(text)},
            "voice": {"languageCode": "ja-JP", "name": VOICE},
            "audioConfig": {"audioEncoding": "MP3"}}
    req = urllib.request.Request("https://texttospeech.googleapis.com/v1/text:synthesize",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-Goog-Api-Key": api_key()})
    with urllib.request.urlopen(req) as r:
        path.write_bytes(base64.b64decode(json.load(r)["audioContent"]))


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout)


def main():
    spec_path, out = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
    spec = importlib.util.spec_from_file_location("spec", spec_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)

    frames, wavs = [], []
    n = 0
    for si, s in enumerate(mod.SLIDES):
        base = Image.new("RGB", (W, H), BG)
        DRAW[s["kind"]](ImageDraw.Draw(base), s)
        base.save(work / f"slide{si:02d}.png")
        for sent in s["say"]:
            mp3, wav = work / f"s{n:03d}.mp3", work / f"s{n:03d}.wav"
            cache = work / f"s{n:03d}.txt"
            # 声を替えたときも作り直すよう、キャッシュの鍵に声の名前を含める
            key = f"{VOICE}\n{sent}"
            if not (mp3.exists() and cache.exists() and cache.read_text() == key):
                tts(sent, mp3)
                cache.write_text(key)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-af", f"apad=pad_dur={GAP}",
                            "-ar", "48000", "-ac", "1", str(wav)], check=True)
            png = work / f"f{n:03d}.png"
            with_subtitle(base, sent).save(png)
            frames.append((png, duration(wav)))
            wavs.append(wav)
            n += 1

    with open(work / "frames.txt", "w") as fp:
        for png, dur in frames:
            fp.write(f"file '{png}'\nduration {dur:.3f}\n")
        fp.write(f"file '{frames[-1][0]}'\n")
    with open(work / "audio.txt", "w") as fp:
        for wav in wavs:
            fp.write(f"file '{wav}'\n")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(work / "audio.txt"),
                    str(work / "audio.wav")], check=True)
    video = out / "video.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(work / "frames.txt"),
                    "-i", str(work / "audio.wav"), "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                    "-r", "30", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
                    str(video)], check=True)
    total = sum(dur for _, dur in frames)
    print(f"{video} {total:.1f}s {len(mod.SLIDES)} slides {n} sentences")


if __name__ == "__main__":
    main()
