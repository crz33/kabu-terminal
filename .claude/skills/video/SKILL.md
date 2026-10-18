---
name: video
description: 週次市況のレポートを、スライドと読み上げと字幕の動画 (1920x1080、4 分前後) にして、claude.ai の非公開ページに載せる。kessannote の reports/*_weekly-market.md から台本を書き、pillow と Google Cloud Text-to-Speech と ffmpeg で mp4 を作る。「週次の動画を作って」「レポートを動画にして」と言われたときに使う。
---

# 週次市況の動画

週次レポートを書いたあとに作る。数字はレポートから写す。DB は引き直さない。動画とレポートの数字が
ずれるのが一番まずい。

## 前提

| 対象 | 値 |
| --- | --- |
| 台本 | `kessannote/videos/<レポートと同じ名前>.py` |
| 描画 | `.claude/skills/video/render.py` (venv `~/.venvs/video` の python で動く) |
| 声 | Google Cloud Text-to-Speech の `ja-JP-Chirp3-HD-Sulafat`。プロジェクトは `kabu-video` |
| API キー | `~/.config/kabu/video.env` の `GOOGLE_TTS_API_KEY` (権限 600。表示しない) |
| 出力 | `data/video/<レポートと同じ名前>/video.mp4`。途中のファイルは同じ場所の `work/` |
| 見せる場所 | https://claude.ai/artifact/LF5znpF9SVkqTvs5XtS1b5 (非公開。元のページは `page.html`) |

venv が無ければ作る。この python には pip も ensurepip も無い。

```bash
python3 -m venv --without-pip ~/.venvs/video
curl -fsSL https://bootstrap.pypa.io/get-pip.py -o <scratchpad>/get-pip.py
~/.venvs/video/bin/python <scratchpad>/get-pip.py -q
~/.venvs/video/bin/pip install -q pillow
```

## 手順

### 1. 台本を書く

前の週の `kessannote/videos/*.py` を型にする。`TITLE` と `SLIDES` を定義し、スライドの `kind` は
title / bignums / bars / hbars / bullets の 5 つ。`say` は文のリストで、1 文が読み上げ 1 回と字幕
1 枚になる。

構成は、タイトル → 週の騰落 (日経平均・中央値・時価総額加重) → ポイント 3 つ → そのほか → まとめと
免責。7〜8 枚、30 文前後で 4 分になる。

- 数字はレポートの本文と表から写す。レポートに無い数字を足さない
- 読み上げの文では符号を「プラス」「マイナス」と書く。`-5.37%` は「マイナス5.37%」
- 理由はレポートで出典の付いたものだけ言う。レポートの未確定は動画で言わない。「まだ確かめて
  いません」は視聴者に要らない。気になる動きなら、まとめで「来週は〜に注目します」と言う
- 台本を書く前に、レポートの未確定のうち動画で触れたいものを weekly スキルの手順 8 で調べて
  おく。解ければ理由を言えるし、レポートも進む
- 冒頭は「日本株の週次市況です。」で始める。「kabu」は視聴者に通じないので言わない
- 最後の文は必ず免責にする。言い方は「この動画は、個人が公開されているデータをもとに調査した
  内容です。特定の銘柄の売買を勧めるものではありません。投資判断はご自身でお願いします。」
- 何が動いたかを毎回言う。「2倍を超えました」ではなく「株価は1週間で2倍を超えました」、
  「反発し」ではなく「日経平均が反発し」。耳で聞くと前の文の主語は残らない
- 「軒並み」のように範囲のぼやける言葉は避ける。全体の話か、一部の業種の話かを言い分ける

### 2. 作る

```bash
cd ~/kabu-terminal
.claude/skills/video/render.py kessannote/videos/<名前>.py data/video/<名前>
```

読み上げは文ごとにキャッシュする (`work/s###.txt` に声の名前と文、mp3)。初回は 30 文で約 2 分半、
文か声を直した 2 回目以降は、変わった文だけ作り直す。最後に `video.mp4 <秒数>s ...` と出れば終わり。

### 3. 見た目を確かめる

`work/f###.png` (字幕付きの各フレーム) を何枚か Read で見る。字幕が 2 行の文を選ぶこと。
見るのは、字幕がグラフやラベルを隠していないか、横棒のラベルがはみ出していないか。

### 4. ページに載せる

ページは 1 枚で、週ごとに動画が上から並ぶ。別の会話から更新するので、毎回 `url` を渡す。

1. `Artifact` の `action: "read"` でページを読む。いまの版を手元に保存する
2. `Artifact` の publish に `url`、`asset: true`、`file_path` に mp4 を渡してアップロードする。
   返ってきた `/_blob/<id>` を控える
3. 読んだページの `EPISODES` の先頭に 1 行足す (`week`、`title`、`length`、`src`)
4. `url` を付けて publish する。`capabilities` は渡さない (前の版の `assets` が引き継がれる)
5. `page.html` も同じ中身に書き換えておく

会話にファイルとして送る (SendUserFile) 道は、このセッションの形では使えない。

### 5. YouTube のタイトルと概要欄を書く

`kessannote/videos/<名前>.youtube.md` に置く。前の週のものを型にする。チャプターの時刻は
`work/frames.txt` の文ごとの長さをスライドごとに足して出す。概要欄には、レポートへのリンク、
対象の銘柄数と期間、免責、合成音声であることを必ず入れる。上げるのはユーザがスマホから行う。

### 6. commit する

台本は `kessannote` に commit して push する。`render.py` や `page.html` を直したら
`kabu-terminal` に別に commit する (push はユーザの指示を待つ)。

## つまずきどころ

**読み上げは Google Cloud の Text-to-Speech で、文字数で課金される。** Chirp 3: HD は毎月 100 万文字
まで無料で、1 本は 1,200〜1,500 文字。キーは Text-to-Speech API だけに制限してあり、予算アラートは
月 1 ドル。日本語の Chirp 3: HD の声は 30 種あり、2026-10-18 に女性の声を全部聴き比べて Sulafat に
決めた。IRIS から引き継いだ時点の edge-tts (Microsoft Edge の読み上げの非公式利用) は、規約が
はっきりしないので替えた。

**ffmpeg の concat のリストは、リストのある場所からの相対パスで読まれる。** render.py は出力先を
絶対パスに直してから使う。

**字幕が 2 行になると下の 220px ほどを覆う。** スライドの注記や軸のラベルは y 800 より上に置く。
縦棒の日付のラベルが隠れたので、グラフの下端を 780 に上げた。

**読み違える語は `READING` で読みだけ言い換える。** 値がさ→ねがさ、kessannote→けっさんノート。
字幕には元の表記が出る。

**上げは赤、下げは青。** 日本の相場表示に合わせている。

**Google Drive に上げるなら、自分の OAuth クライアントが要る。** rclone の共用の client_id は
2026 年中に止まる。rclone は `~/.local/bin/rclone` に入れてある。
