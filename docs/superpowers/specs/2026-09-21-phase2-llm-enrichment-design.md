# Phase 2 サブプロジェクト1: LLM要約・注目度・おすすめ10選 設計スペック

## 背景・目的

Phase 1で「RSS取得・一覧化・自動公開・既読管理」までを実装済み。参考にしたYouTube動画では、取得した記事をLLM（動画内ではGoogle Gemini）に渡して要約・注目度評価・おすすめ記事の選定をさせていた。このサブプロジェクトはその部分を実装する。

対象はPhase 2の3つのサブプロジェクトのうち1つ目（LLM要約・注目度・おすすめ10選）。既読/未読タブ機能（サブプロジェクト2）は実装済み。パスコードロック（サブプロジェクト3）は対象外。

## 要件

- 取得した記事それぞれについて、LLMに以下を生成させる
  - `summary`: 1〜2文の日本語要約
  - `star`: 注目度を1〜5の整数で評価したもの
  - `recommended`: 全記事の中で特に重要な最大10件にtrueを付与するフラグ
- LLMは**完全無料で使えるAPI**を使う（Google Gemini API の無料枠）
- LLM呼び出しが失敗（APIキー未設定・ネットワークエラー・レート制限・レスポンス形式不正のいずれか）しても、サイト全体の更新は止めない。要約なしでPhase 1相当の表示にフォールバックする
- UIに「おすすめ」タブを追加する（既存の「未読」「既読」に加えて3タブ構成）。おすすめタブは`recommended=true`の記事のみを表示する
- 既存の既読/未読の判定ロジック（クライアント側localStorage、記事リンクをキーにする）とは独立して動作する（おすすめタブ内でも既読になった記事は通常通り既読/未読タブの分類に従う）

## 非対象（このサブプロジェクトでは扱わない）

- パスコードロック・非公開化（サブプロジェクト3）
- 英語ソースの追加採用（現状2ソースとも日本語のため翻訳の実利用機会はまだ少ないが、要約プロンプト自体は言語を問わず日本語で出力させるため、将来英語ソースを追加すれば自動的に翻訳としても機能する）
- リトライ・エクスポネンシャルバックオフなどの高度なエラーハンドリング（失敗したら当日は諦めて翌日の実行に任せる）

## アーキテクチャ

新規モジュール `enrich.py` を追加し、既存の2モジュールとは独立した責務を持たせる。

```
[feeds.yaml] → fetch_news.get_all_articles() → [articles: list[dict]]
                                                        │
                                                        ▼
                                          enrich.enrich_articles(articles)
                                          （Gemini APIへ1回のリクエストで全記事を渡す）
                                                        │
                                                        ▼
                                     [enriched articles: summary/star/recommended付き]
                                                        │
                                                        ▼
                                        generate_site.render_html() → docs/index.html
```

`enrich_articles`が例外を投げることはない。失敗時は各記事に`summary=None, star=None, recommended=False`を補って返すため、`generate_site.py`側は「enrichmentが常に付いている」前提でシンプルに書ける。

## コンポーネント

### `enrich.py`

- `enrich_articles(articles: list[dict]) -> list[dict]` — 公開関数。各記事dictのコピーに`summary`, `star`, `recommended`の3キーを追加して返す
- Gemini APIへのアクセスは新規SDKを追加せず、既存の軽量な依存方針を踏襲し `requests` ライブラリで直接REST呼び出しする（`requests`を`requirements.txt`に追加）
- エンドポイント: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}`
  - `model`は`gemini-flash-latest`（Googleが提供する「常に最新の無料Flashモデルを指す」エイリアス。特定バージョンに固定したい場合は定数を変更するだけで済む設計にする）
  - リクエストボディの`generationConfig.response_mime_type`を`application/json`に設定し、モデルにJSON形式での出力を強制する
  - レスポンスは`candidates[0].content.parts[0].text`にJSON文字列が入るので、それを`json.loads`でパースする
- 全記事を1回のAPI呼び出しにまとめて渡す（記事数分の呼び出しをして無料枠を消費しない）。プロンプトには各記事の`source`と`title`のみを渡す（本文は取得していないため要約対象はタイトルベース）
- APIキーは環境変数`GEMINI_API_KEY`から読む。未設定の場合はAPI呼び出し自体を試みずフォールバックする
- レスポンスのJSON配列が「入力記事数と同じ件数」「各要素が`summary`/`star`/`recommended`を持つ辞書」であることを検証し、条件を満たさない場合は`ValueError`を送出してフォールバックさせる
- LLMが指示を守らず`recommended=true`を10件より多く返した場合に備え、`star`降順で上位10件のみ`recommended=true`を維持し、残りは`false`に強制するガードを設ける（LLM出力を無条件に信頼しない）
- タイムアウトは30秒（`requests.post(..., timeout=30)`）

### `generate_site.py`の変更

- `main()`で`get_all_articles()`の結果を`enrich.enrich_articles()`に通してから`render_html()`に渡す

### `templates/index.html.j2`の変更

- タブに「おすすめ」を追加（`data-view="recommended"`）。CSSで`.card`に`data-recommended`属性を持たせ、既存の`is-read`と同様のフィルタリング方式で表示制御する
- `article.summary`が`None`でなければ要約文をカード内に表示、`None`ならその行自体を表示しない（Phase 1相当の見た目にフォールバック）
- `article.star`が`None`でなければ★を`star`個表示(例: `★★★☆☆`)、`None`なら非表示

### ワークフロー・設定の変更

- `.github/workflows/update-news.yml`の`generate_site.py`実行ステップに環境変数`GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}`を追加
- GitHub Secretsに`GEMINI_API_KEY`を登録する必要がある（Google AI Studioで無料のAPIキーを発行してユーザーが設定する、実装時の手動ステップ）
- `requirements.txt`に`requests`を追加

## エラーハンドリング

- `GEMINI_API_KEY`未設定 → API呼び出しをスキップし、警告ログを出してフォールバック
- HTTPエラー・タイムアウト・接続エラー → 例外をキャッチし、警告ログを出してフォールバック
- レスポンスのJSON解析失敗・期待した形と異なる → 同様にフォールバック
- いずれの場合も`generate_site.py`のメインフローは止めない（Phase 1で実装済みの「全フィード失敗時はサイトを更新しない」ロジックとは独立しており、enrichment失敗は「要約なしで更新は続行する」という別の失敗モード）

## テスト方針

`tests/test_enrich.py`を新規作成し、`requests.post`をmonkeypatchして以下をTDDで検証する。

1. 正常なJSONレスポンスが返る場合、各記事に`summary`/`star`/`recommended`が正しく付与される
2. レスポンスのJSON配列が記事数と一致しない、または要素の形式が不正な場合、元の記事に`summary=None, star=None, recommended=False`が付いた状態で返る
3. `requests.post`が例外（タイムアウト等）を送出した場合も同様にフォールバックする
4. 環境変数`GEMINI_API_KEY`が未設定の場合、`requests.post`は一切呼ばれず即座にフォールバックする
5. LLMが11件以上に`recommended=true`を付けて返した場合、`star`降順で上位10件のみが`recommended=true`として残る

`generate_site.py`側のテストは、`enrich_articles`をmonkeypatchして「enrichment付きの記事が正しくテンプレートに渡ること」を確認する統合的なテストを1つ追加する。

## Phase 2 の他サブプロジェクトとの関係

サブプロジェクト3（パスコードロック等）は本スペックの対象外。今回のenrichmentは既読/未読タブ（サブプロジェクト2、実装済み）のクライアント側ロジックには影響しない — サーバー側で生成されるHTMLに`summary`/`star`/`recommended`が追加されるだけで、既読状態の判定は引き続き記事リンクURLをキーにしたlocalStorageのまま変更しない。
