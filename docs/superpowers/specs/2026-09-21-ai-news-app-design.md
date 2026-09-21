# AIニュース自動更新アプリ 設計スペック（Phase 1）

## 背景・目的

YouTube動画（Google Antigravityで無料AIニュースアプリを作る内容）を参考に、毎朝自動更新され、スマホのブラウザで閲覧できる個人用AIニュースまとめアプリを作る。

Phase 1のスコープは「RSS取得・一覧化・自動公開」まで。LLMによる要約・日本語化はPhase 2（本スペックの対象外）。

## 要件

- 複数のRSSフィード（AI関連ニュース）から記事を取得する
- 取得元は日本語ソース中心（動作確認済み: ITmedia AI+、AINOW。フィード一覧は設定ファイルで追加しやすくする）
- 毎朝自動的に更新される（GitHub Actionsのcronスケジュール実行）
- スマホのブラウザで見やすいレイアウト（レスポンシブ、ホーム画面追加でアプリ的に使える）
- 完全無料で運用できる（サーバー代・API課金なし）
- 個人利用のGitHubアカウントを新規作成し、GitHub Pagesで公開する

## 非対象（Phase 1では扱わない）

- LLMによる記事要約・日本語翻訳（Phase 2で追加予定）
- 英語ソースの本格採用（Phase 1は日本語ソース中心。追加は設定ファイルに足すだけで対応可能な設計にする）
- 記事の永続的な全文保存・検索機能

## アーキテクチャ

Pythonの静的サイトジェネレーター的スクリプトを GitHub Actions の日次cronジョブから実行し、生成した静的HTMLを GitHub Pages（`docs/`フォルダ）で配信する。サーバー常駐なし。

```
[GitHub Actions cron (毎朝 JST 7時頃)]
        │
        ▼
[fetch_news.py] --読込--> [feeds.yaml]
        │
        │ 各フィードをfeedparserで取得・パース
        │ 失敗したフィードはスキップして継続
        │ タイトル/リンクで重複排除
        │ 公開日時で降順ソート、各ソース上位N件に制限
        ▼
[generate_site.py] --テンプレート--> [templates/index.html.j2]
        │
        │ docs/index.html を生成
        ▼
[git commit & push]（変更があれば）
        │
        ▼
[GitHub Pages が自動デプロイ]
        │
        ▼
[スマホのブラウザで閲覧]
```

全フィードの取得に失敗した場合は、`docs/index.html` を空や壊れた状態で上書きせず、直前の生成結果を保持する（コミットをスキップする）。

## コンポーネント

### `feeds.yaml`
取得元RSSフィードの一覧を保持する設定ファイル。各エントリは `name`（表示用ソース名）と `url`（RSSフィードURL）。新しいソースを増やす場合はここに追記するだけでよい。

初期セット（動作確認済み）:
- ITmedia AI+: `https://rss.itmedia.co.jp/rss/2.0/aiplus.xml`
- AINOW: `https://ainow.ai/feed/`

### `fetch_news.py`
- `feeds.yaml` を読み込み、各フィードを `feedparser` で取得
- 1フィードの取得・パースに失敗しても例外を握りつぶしログに残し、他のフィードの処理を継続する
- 全記事をリンク（正規化したURL）とタイトルで重複排除
- 公開日時（`published_parsed`）で降順ソート
- 各ソースごとに直近上位N件（デフォルト10件）に制限
- 結果を構造化データ（記事リストの辞書）として返す

### `templates/index.html.j2`
- Jinja2テンプレート
- スマホ表示を主眼にした1カラム・レスポンシブレイアウト
- 各記事はカード表示: ソース名、タイトル（リンク）、公開日時
- 最終更新日時をページ上部に表示
- ダークモード対応（`prefers-color-scheme`）は任意だが、CSSは軽量に保つ

### `generate_site.py`
- `fetch_news.py` の結果をテンプレートに渡してレンダリングし、`docs/index.html` に書き出す
- 取得結果が0件（全フィード失敗）の場合は書き出しをスキップし、非ゼロ終了コードでワークフローに失敗を伝える

### `.github/workflows/update-news.yml`
- トリガー: `schedule`（cron、JST 7時頃 = UTC 22時）と `workflow_dispatch`（手動実行）
- ステップ: リポジトリチェックアウト → Python環境セットアップ → 依存インストール（`feedparser`, `jinja2`, `pyyaml`）→ `generate_site.py` 実行 → 変更があれば `docs/index.html` をコミット&プッシュ

### GitHub Pages設定
- リポジトリの Settings → Pages でソースを `main`ブランチの `/docs` フォルダに設定
- 公開URLをスマホのホーム画面に追加することでアプリ的に使える

## エラーハンドリング

- 個別フィードの取得失敗: ログに警告を出し、そのフィードをスキップして処理継続
- 全フィード失敗: サイトを更新せず、ワークフローを失敗として終了（次回の手動確認を促す）
- 重複記事: リンクURL正規化＋タイトル完全一致で判定し除外

## テスト方針

1. ローカル環境で `fetch_news.py` / `generate_site.py` を単体実行し、`feeds.yaml` の2ソースから正しく記事が取得され `docs/index.html` が生成されることを確認する
2. 意図的に不正なフィードURLを混ぜて、1つが失敗しても他のソースの記事が正常に表示されることを確認する
3. GitHub Actions上で `workflow_dispatch` を使い手動トリガーし、Actions実行 → コミット → Pages反映までの一連の流れを確認する
4. スマホの実機ブラウザでPages URLを開き、レイアウト崩れがないことを確認する

## Phase 2（本スペックの対象外、将来の拡張）

- Claude APIを使った記事要約・日本語翻訳ステップの追加
- Anthropic APIキーをGitHub Secretsに保存し、Actionsワークフローに組み込む
- 英語ソースの追加採用
