---
name: status
description: ラズパイで動いているバッチの直近の実行結果をレポートする。cron のログ (journalctl) と DB の最新データを突き合わせ、成功したか・何件入ったか・詰まっていないかを報告する。「昨晩の実行結果」「バッチ動いてる?」「データ最新?」と聞かれたときに使う。
---

# Status

ラズパイ (`raspi`) の夜間バッチと週次バッチについて、直近の実行結果を調べて報告する。

このスキルは **読み取り専用** である。ログ・DB・ファイルのいずれにも書き込まない。バッチの再実行もしない。詰まりを見つけても、対処はユーザに提案するだけにとどめる。

引数があれば調査範囲の指定として扱う (「EDINET だけ」「今週ぶん」など)。無ければ直近 1 回の実行を対象にする。

## 前提

| 対象 | 値 |
| --- | --- |
| ssh 先 | `raspi` (`~/.ssh/config` に定義済み) |
| nightly のログタグ | `kabu` |
| weekly のログタグ | `kabu-ticks` |
| DB 接続 | Mac の `kabu-app/.env` にある `DATABASE_URL` (`kabu_dev`) |

スケジュールは `crontab -l` で読む。この文書に書き写さない。cron を直せば嘘になるため。

## 手順

### 1. cron の定義を取る

```bash
ssh raspi 'crontab -l; date'
```

ラズパイの現在時刻も一緒に見る。実行予定の直前・直後や、実行中かどうかの判断に要る。

### 2. ログを読む

```bash
ssh raspi 'journalctl -t kabu       --since "3 days ago" --no-pager -o short-iso' | tail -60
ssh raspi 'journalctl -t kabu-ticks --since "8 days ago" --no-pager -o short-iso' | tail -20
```

`nightly.sh` は `=== <名前> 開始 / 完了 / 失敗 ===` を出し、最後に `すべて完了 (N 秒)` か `失敗した処理: ...` で締める。締めの行が無ければ、まだ動いているか途中で死んでいる。

週次の株価取得は 2 時間以上かかる。土曜の朝に叩くと進行中のことがある。その場合は「N / 3713 銘柄」の進捗行から残り時間を見積もって伝える。

### 3. DB で裏を取る

ログの件数だけで判断しない。DB の実データと突き合わせる。

```bash
cd kabu-app
set -a && . ./.env && set +a
export PGURL="${DATABASE_URL#postgresql+psycopg://}"
psql "postgresql://$PGURL" -A -F' | ' -c "<SQL>"
```

`DATABASE_URL` にはパスワードが入っている。`echo` しない。`psql` に渡す 1 か所だけで使う。

見るのはこの 3 つ。

```sql
-- EDINET: 提出日ごとのメタデータ件数と ZIP 取得済み件数
SELECT submit_date, count(*) AS meta, count(downloaded_at) AS dl
FROM edinet_documents WHERE submit_date >= current_date - 7 GROUP BY 1 ORDER BY 1;

-- TDnet: 開示日ごとの同上。取り逃しは 31 日で永久に取れなくなる
SELECT disclosed_date, count(*) AS meta, count(downloaded_at) AS dl
FROM tdnet_disclosures WHERE disclosed_date >= current_date - 7 GROUP BY 1 ORDER BY 1;

-- ticks: 最新日と、その日に値が入っている銘柄数
SELECT max(date) AS latest,
       count(*) FILTER (WHERE date = (SELECT max(date) FROM ticks)) AS codes_on_latest
FROM ticks;
```

`meta` と `dl` が食い違う日は、取得に失敗した書類が残っている。EDINET は次回が拾い直すので放っておいてよい。TDnet で 31 日を過ぎたものは二度と取れない。

### 4. レポートする

結論を 1 行目に置く。「全ジョブ成功」か「N 件失敗」か「実行された形跡なし」。そのあとに開始・終了時刻と所要時間を書く。

続けてジョブごとの内訳を箇条書きにする。件数はログの数字をそのまま引く。丸めない。

最後に、判断を変える異常だけを書く。無ければ書かない。以下は毎回確認する。

- **`ticks` の最新日が直近の営業日より古い** — 週次が飛んでいる。土日祝を挟むので営業日で数える
- **TDnet の未取得が積み上がっている** — 31 日を過ぎると永久欠損になる。最優先で報告する
- **`調整後終値が飛んでいる銘柄が N 件`** — 遡りの残数。1 晩 50 銘柄で消化するので、N / 50 日かかる。前回の実行時より増えていれば伝える
- **所要時間が普段の倍以上** — 決算期の TDnet は重い。それ以外なら回線か Yahoo 側を疑う

## つまずきどころ

**ログに「取得 0 件」が出ていても異常とは限らない。** 手動で流した直後に cron が走ると、取り込み済みの日を冪等に抜ける。DB の `downloaded_at` のタイムスタンプを見れば、いつ入ったか分かる。バッチの時刻と違えば手動実行のぶんである。

**ラズパイ上で `sudo -u postgres psql` は通らない。** パスワードを求められて止まる。DB は必ず Mac から `kabu_dev` で見る。

**`journalctl` にログが無い期間は、バッチが止まっていたとは限らない。** cron を仕掛けた日より前は当然何も無い。`journalctl -t kabu --no-pager | head -1` で最古の行を見て、いつから記録があるか確かめてから「止まっている」と言う。

**`data/` の更新時刻は判断材料にならない。** SMB マウント越しなので、見えている時刻が実際の書き込みとずれる。ファイルの有無の確認までにとどめ、件数は DB で数える。
