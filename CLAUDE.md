# kabu-terminal

株式投資判断システム kabu の作業ルート。Claude Code はここで起動する。

## 構成

4 つのリポジトリを `.gitignore` で入れ子にしている。git としては 4 つとも独立で、それぞれが自分の `.git`・リモート・履歴を持つ。物理配置の入れ子と git の独立性は別の話である。

```text
kabu-terminal/              # public。スキルと CLAUDE.md
├── .claude/skills/
├── kabu-vault/             # private。知識層。LLM Wiki パターン
├── kabu-app/               # public。取得バッチ、DB スキーマ、XBRL パーサ。ラズパイが pull
├── kabu-lab/               # public。解析・バックテスト。Mac のみ。書き捨て歓迎
└── data -> /Volumes/data   # symlink。ラズパイの SSD (SMB, 読み取り専用)
```

- コミットは各リポジトリで別々に行う。`kabu-terminal` で `git status` を叩いても中の変更は出ない
- `.ignore` が無いと ripgrep が `.gitignore` を尊重して中身を素通りする。横断検索を維持するために消さないこと

## 知識とコードの境界

ある記述をどこに置くかは、次の 1 本で判断する。

> そのアプリを捨てて別のアプリを作り直したとき、その記述は生き残るか。

生き残るなら `kabu-vault`、一緒に無価値になるならコード側のリポジトリに置く。粒度や分量では判断しない。

- ノウハウ (「EDINET API は直近 5 年分しか遡れない」など) は時間が経っても価値が残るので vault の `concepts/`
- 構成情報 (テーブルの主キー、動いている systemd timer の設定) は必ず腐るのでコード側

リンクは**コード → wiki の一方向**に限る。wiki からアプリの実装ファイルを指すとリファクタで嘘になる。バックテスト結果を `concepts/` に書くときもコードへのリンクは張らず、使った期間・銘柄の母集団・判定条件を文章で残す。

## 個人 vault との使い分け

LLM Wiki パターンそのものの知見は個人 vault (`~/workspace/llm-wiki/vault/`) にある。

- ドメイン知識 (株式・会計・銘柄) は `kabu-vault`
- LLM Wiki パターンの運用・改善で分かったことは個人 vault に戻す
- 引くときは `/query`、書き戻すときは `/session`

## データとインフラ

- 生データはラズパイの SSD にあり、Mac からは SMB (NetFS) で `/Volumes/data` にマウントする。`data` はそこへの symlink
- マウントポイントを実ディレクトリにしない。SMB が外れたとき空ディレクトリとして残り、バッチが「未マウント」ではなく「0 件」を見てしまう。symlink なら壊れたリンクで即エラーになる
- PostgreSQL はラズパイのローカル (SSD 直) で動く。SMB 公開しない。Mac からは TCP で接続する
- ロールは 3 つ。`kabu_dev` (Mac からの開発、フル)、`kabu_app` (ラズパイのバッチ、localhost のみ、フル)、`kabu_ro` (分析・参照、SELECT のみ)
- データのパスをコードに埋めない。Mac は `kabu-terminal/data`、ラズパイは `/mnt/usb/data` になるため `KABU_DATA_DIR` で受ける
