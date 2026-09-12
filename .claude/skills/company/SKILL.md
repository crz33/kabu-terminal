---
name: company
description: 特定の銘柄の企業レポートを作って kessannote に書く。業績の推移、直近四半期と会社予想の進捗、株主構成、株価を DB から出し、目立つ動きの原因を裏取りしてから markdown にする。「NGK のレポート作って」「7203 を調べて」のように銘柄を指定されたときに使う。
---

# 企業レポート

指定された銘柄を調べ、`kessannote/reports/` に置く。週次と違って定期ではない。見たいと
思ったときに書く。

**必要な数字はほとんど DB にある。** 業績も予想も株主も、損益計算書の内訳もセグメントも
入っている。Web を引くのは、値動きの理由と会社の発表を確かめるときだけになる。

## 前提

| 対象 | 値 |
| --- | --- |
| レポートの置き場 | `kessannote/reports/YYYYMMDD_<名前>-<コード>.md` |
| DB 接続 | `kabu-app/.env` の `DATABASE_URL` (`kabu_dev`) |

```bash
cd kabu-app
set -a && . ./.env && set +a
export PGURL="${DATABASE_URL#postgresql+psycopg://}"
psql "postgresql://$PGURL" -A -F' | ' -c "<SQL>"
```

`DATABASE_URL` にはパスワードが入っている。`echo` しない。

## 手順

### 1. 銘柄を確定する

名前で言われたら、まずコードを引く。**似た名前の別会社がある。**

```sql
SELECT code, name, market_segment, industry33_name, topix_scale_name
FROM stocks WHERE name LIKE '%<一部>%' ORDER BY code;
```

社名変更もある。NGK は旧・日本ガイシで、同じ業種に日本特殊陶業 (5334) が並ぶ。どちらの
ことか曖昧なら、両方を出してユーザに確かめる。

### 2. 業績の推移を出す

```sql
-- 通期。営業利益は当期と前期しか遡れない (有報の経営指標に載らないため)
SELECT period_end, item, round(value/1e8) AS 億円
FROM latest_financials WHERE code='<コード>' AND period_kind='year' ORDER BY period_end, item;
-- 期末の資産
SELECT period_end, item, round(value/1e8) AS 億円
FROM latest_financials WHERE code='<コード>' AND period_kind='year_end' ORDER BY period_end, item;
```

営業利益率を計算する。**規模より利幅の動きを見ること。** 売上が伸びていても利益率が
下がっていれば話が違う。

### 3. 直近四半期と会社予想の進捗を出す

```sql
-- 四半期累計
SELECT period_end, item, round(value/1e8) AS 億円, period_start
FROM latest_financials WHERE code='<コード>' AND period_kind='ytd' ORDER BY period_end DESC LIMIT 12;
-- 会社予想。最新の短信のもの
SELECT f.concept, f.period_end, round(f.value/1e8) AS 億円
FROM tdnet_summary_facts f JOIN tdnet_disclosures d ON d.doc_id=f.doc_id
WHERE d.code='<コード>' AND f.fact_type='Forecast' AND f.period_kind='Year'
  AND d.disclosed_date=(SELECT max(disclosed_date) FROM tdnet_disclosures WHERE code='<コード>')
ORDER BY f.concept;
```

通期予想に対する進捗率と、前年同期比を並べる。**利益の進捗が売上より速いかを見る。**
速ければ利幅が広がっている。

### 4. 株主を見る

```sql
SELECT rank, name, ratio, kind, is_owner FROM edinet_shareholders
WHERE doc_id = (SELECT doc_id FROM edinet_shareholders WHERE code='<コード>'
                ORDER BY period_end DESC NULLS LAST LIMIT 1) ORDER BY rank;
```

上位 10 名の合計、信託口の比率、オーナー系の有無を見る。全部が機関なら持ち合いの色が
残る会社、オーナーが上位にいれば別の読み方になる。

### 5. 株価を並べる

```sql
SELECT date, close, volume FROM ticks WHERE code='<コード>'
  AND date IN ((SELECT max(date) FROM ticks), '<節目の日>') ORDER BY date;
SELECT extract(year from date)::int AS 年, min(close), max(close) FROM ticks
WHERE code='<コード>' GROUP BY 1 ORDER BY 1;
```

大きく動いていたら、その理由は手順 8 で掘る。初回は事実だけ並べて「未確定」に落としてよい。

### 6. 書く

`kessannote/CLAUDE.md` の書き方に従う。frontmatter は `type: company`、`date` は作成日。
`summary` には**結論**を書く。会社の紹介ではなく、何が分かったかを書く。

数値の列は `|---:|` で右に寄せる。コードと日付と銘柄名は左のまま。

**出し方の節には、どのテーブルから引いたかを書く。** 手順は書き写さない。

### 7. 建てて commit する

```bash
cd kessannote && npx astro build && npx astro check
```

**push はしない。** ユーザが指示するまで待つ。ここから質問の往復が始まる。

## ここからが本番

レポートを出したら終わりではない。ユーザが読んで質問してくる。**調べた結果は会話で答えて
終わりにせず、必ずレポートに書き戻すこと。**

### 8. 値動きの理由を聞かれたら

**個別の材料を探す前に、まず固有かどうかを確かめる。** ここを飛ばすと、セクター全体の
動きに個別の理由を当ててしまう。

```sql
-- 同業と市場中央値を同じ期間で比べる
WITH px AS (SELECT code, date, coalesce(adjusted_close, close) AS p
            FROM ticks WHERE date IN ('<起点>','<終点>'))
SELECT s.code, s.name, round(100*(b1.p/b0.p-1),1) AS 騰落pct
FROM stocks s
JOIN px b0 ON b0.code=s.code AND b0.date='<起点>'
JOIN px b1 ON b1.code=s.code AND b1.date='<終点>'
WHERE s.code IN ('<対象>','<同業を数社>') ORDER BY 3;
```

全市場の中央値と業種の中央値も出す。**同業が揃って同じ幅で動いていれば、個別の材料では
ない。** 高値や安値を付けた日が同業で揃っているかも見る。数営業日に収まっていれば決まりになる。

株式分割の確認も忘れない。`adjusted_close` と `close` がずれている日を数えれば分かる。

固有でないと分かったら、セクターに何があったかを Web で引く。記事は開いて日付と中身を
確かめる。

### 9. 業績の中身を聞かれたら

Web を引く前に DB を見る。**四半期の短信に損益計算書の内訳とセグメント情報が入っている。**

```sql
-- 損益計算書の内訳。売上原価と販管費まで取れる
SELECT f.ordinal, f.concept, f.period_start, round(f.value/1e8,1) AS 億円
FROM tdnet_statement_facts f JOIN tdnet_disclosures d ON d.doc_id=f.doc_id
WHERE d.code='<コード>' AND d.disclosed_date='<開示日>' AND f.section='PL' AND f.member IS NULL
ORDER BY f.ordinal;
-- セグメント。member で事業を見分ける
SELECT f.concept, f.member, f.period_start, round(f.value/1e8,1) AS 億円
FROM tdnet_statement_facts f JOIN tdnet_disclosures d ON d.doc_id=f.doc_id
WHERE d.code='<コード>' AND d.disclosed_date='<開示日>' AND f.section='SG' ORDER BY f.ordinal;
```

**セグメント別の設備投資・減価償却費・資産は通期の短信にだけ入る。** 四半期には無い。
`jpcrp_cor_IncreaseInPropertyPlantAndEquipmentAndIntangibleAssets` と
`jpcrp_cor_DepreciationSegmentInformation`、`jppfs_cor_Assets` で引ける。

全社の減価償却費と設備投資は有報のキャッシュフロー計算書にある。

```sql
SELECT f.period_end, f.concept, round(f.value/1e8,1) AS 億円
FROM edinet_latest_facts f WHERE f.code='<コード>' AND f.section='CS' AND f.member IS NULL
  AND (f.concept LIKE '%DepreciationAndAmortizationOpeCF' OR f.concept LIKE '%PurchaseOfPropertyPlantAndEquipmentInvCF')
ORDER BY f.period_end;
```

### 10. 未確定を動かす

解けたものは外し、掘って出てきた問いを足す。未確定は減らすものではなく入れ替わるもの。

部分的にしか解けなければ、消さずに文を書き換える。何が分かって何が残っているかを書く。

`date` は同じ日の追記なら動かさない。`summary` は結論が変わったら直す。

### 11. 指示が出たら push する

```bash
cd kessannote && git push origin main
```

## つまずきどころ

**断面の評価は推移で見ると逆になる。** NGK のデジタルソサエティは「3 事業で最も利益率が
低い」ように見えた。通期で並べると 1.7% → 10.0% → 13.7% で、2 年で 12 ポイント上げた事業
だった。低いのではなく、上がったあと止まっている。**「最も低い」と書く前に推移を出すこと。**

**`edinet_latest_facts` は当期と前期の両方を持つ。** `fiscal_year_end` で集計すると同じ期に
2 つの値が並ぶ。`period_end` で分けること。

**全社の数字とセグメントの数字を混ぜない。** NGK は全社の償却が 3 期横ばいだった。そこから
「償却は重くない」と言えるのは全社の話で、セグメント別に確かめるまでは断定できない。通期
短信に入っているので確かめられる。

**発行済株式数は `tdnet_summary_facts` にある。** 上位株主の比率から逆算しないこと。
`concept = 'tse-ed-t_NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock'`
と `tse-ed-t_NumberOfTreasuryStockAtTheEndOfFiscalYear` を `scope = 'Current'` で引く。予想 EPS
(`NetIncomePerShare` か `BasicEarningsPerShareIFRS`) も同じ表にあり、予想 PER が出せる。

**営業利益は有報の経営指標に載らない。** 通期の推移を出すと、古い期が空く。欠損ではないので
そう書き添える。損益計算書から取るため当期と前期の 2 期しか遡れない。

**将来の試算は「試算」と明記する。** 耐用年数のように開示されていない前提を置いたときは、
仮定を書いて幅で出す。1 つの数字に見せない。
