# kabu-terminal

株式投資判断システム kabu の作業ルート。Claude Code はここで起動する。

## 構成

3 つのリポジトリを `.gitignore` で入れ子にしている。git としては 3 つとも独立で、それぞれが自分の `.git`・リモート・履歴を持つ。物理配置の入れ子と git の独立性は別の話である。

```text
kabu-terminal/              # public。スキルと CLAUDE.md
├── .claude/skills/
├── kabu-app/               # public。取得バッチ、DB スキーマ、XBRL パーサ。ラズパイが pull
├── kessannote/             # private。調べたことのレポート
└── data -> /Volumes/data   # symlink。ラズパイの SSD (SMB, 読み取り専用)
```

- コミットは各リポジトリで別々に行う。`kabu-terminal` で `git status` を叩いても中の変更は出ない
- `.ignore` が無いと ripgrep が `.gitignore` を尊重して中身を素通りする。横断検索を維持するために消さないこと

## 何をどこに書くか

判断は 1 本。**読むのはいつか。**

- コードを直すときに読むなら、そのコードの docstring かリポジトリの README
- 銘柄や市況を判断するときに読むなら `kessannote/reports/`

EDINET API の仕様はバッチを直すときにしか読まないので `kabu-app`。企業の実態やバックテストの結果は判断するときに読むので `kessannote`。

投資のアイデアを試す手順は `idea` スキルにある。アイデアごとの定義は `kessannote/methods/`、SQL は `kessannote/analysis/`、結果は `kessannote/reports/` に、同じ名前と版で置く。DB や表紙の癖のように次のアイデアでも踏むものはスキルの「つまずきどころ」に足す。

レポートからコードの実装ファイルへリンクを張らない。リファクタで嘘になる。テーブル名とビュー名までにとどめる。

## データとインフラ

- DB のデータを引く前に `kabu-app/README.md` の「どれを引くか」を読む。テーブルとビューの選び方が書いてある。列の意味は DB の `COMMENT` にあるので `psql` の `\d+` で読む
- 生データはラズパイの SSD にあり、Mac からは SMB (NetFS) で `/Volumes/data` にマウントする。`data` はそこへの symlink
- マウントポイントを実ディレクトリにしない。SMB が外れたとき空ディレクトリとして残り、バッチが「未マウント」ではなく「0 件」を見てしまう。symlink なら壊れたリンクで即エラーになる
- PostgreSQL はラズパイのローカル (SSD 直) で動く。SMB 公開しない。Mac からは TCP で接続する
- ロールは 3 つ。`kabu_dev` (Mac からの開発、フル)、`kabu_app` (ラズパイのバッチ、localhost のみ、フル)、`kabu_ro` (分析・参照、SELECT のみ)
- データのパスをコードに埋めない。Mac は `kabu-terminal/data`、ラズパイは `/mnt/usb/data` になるため `KABU_DATA_DIR` で受ける
