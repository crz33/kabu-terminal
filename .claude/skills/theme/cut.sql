-- テーマの地図の足切り。候補のコードを渡すと、時価総額・高値比・直近 2 期の利益と、落ちる理由を返す
--   psql ... -v codes='6526,6834' -f cut.sql
WITH c AS (SELECT unnest(string_to_array(:'codes', ',')) AS code),
px AS (
  SELECT t.code,
         (array_agg(coalesce(t.adjusted_close, t.close) ORDER BY t.date DESC))[1] AS adj_now,
         (array_agg(t.close ORDER BY t.date DESC))[1] AS close_now,
         max(coalesce(t.adjusted_close, t.close)) AS hi
  FROM ticks t JOIN c USING (code)
  WHERE t.date >= (SELECT min(date) FROM (SELECT DISTINCT date FROM ticks ORDER BY date DESC LIMIT 250) w)
  GROUP BY t.code),
sh AS (
  SELECT DISTINCT ON (d.code) d.code,
         max(f.value) FILTER (WHERE f.concept LIKE '%NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock')
       - coalesce(max(f.value) FILTER (WHERE f.concept LIKE '%NumberOfTreasuryStockAtTheEndOfFiscalYear'), 0) AS shares
  FROM tdnet_disclosures d JOIN c USING (code) JOIN tdnet_summary_facts f ON f.doc_id = d.doc_id AND f.scope = 'Current'
  GROUP BY d.code, d.doc_id, d.disclosed_date
  HAVING max(f.value) FILTER (WHERE f.concept LIKE '%NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock') IS NOT NULL
  ORDER BY d.code, d.disclosed_date DESC),
pl AS (
  SELECT code,
         array_agg(round(value/1e8, 1) ORDER BY period_end) FILTER (WHERE item = 'operating_income') AS op,
         array_agg(round(value/1e8, 1) ORDER BY period_end) FILTER (WHERE item = 'net_income') AS ni
  FROM (SELECT l.*, row_number() OVER (PARTITION BY l.code, l.item ORDER BY l.period_end DESC) AS rn
        FROM latest_financials l JOIN c USING (code)
        WHERE l.period_kind = 'year' AND l.item IN ('operating_income', 'net_income')) x
  WHERE rn <= 2 GROUP BY code)
SELECT s.code, s.name,
       round(px.close_now * sh.shares / 1e8) AS 時価総額億円,
       round(100 * px.adj_now / px.hi) AS 高値比pct,
       pl.op AS 営業利益_前期_当期, pl.ni AS 純利益_前期_当期,
       CASE WHEN px.adj_now / px.hi < 0.6 THEN '高値比'
            WHEN pl.op[array_length(pl.op, 1)] < 0 THEN '営業赤字'
            WHEN pl.ni[1] < 0 AND pl.ni[2] < 0 THEN '2期最終赤字' END AS 足切り
FROM c JOIN stocks s USING (code) LEFT JOIN px USING (code) LEFT JOIN sh USING (code) LEFT JOIN pl USING (code)
ORDER BY 3 DESC NULLS LAST;
