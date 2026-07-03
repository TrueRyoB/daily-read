# daily-read

論文を読みやすくするために、読む前にかかる「高負荷な前処理」を自動で取り除くローカルWebアプリです。

## 目的

論文を読むとき、内容そのものより先に次のような負荷がかかりがちです。

- **類推負荷**: 文脈に強く依存する専門用語・略語を、出てくるたびに意味を推測し直す
- **視線移動負荷**: 二段組レイアウトのジグザグ読み、本文と図表の往復、読みにくいフォント

daily-read は PDF ファイルまたは PDF が掲載された URL を受け取り、これらの負荷を事前に取り除いた読書ビューを生成します。

- 二段組を一段組に正規化し、自然な読み順の1本の文章として読める
- 図表を本文から分離し、右側（または末尾）のパネルにまとめ、本文中にはジャンプリンクのみ残す
- 可読性重視のフォント（Atkinson Hyperlegible）・広めの行間・目に優しい配色
- 本文中で定義されている略語（例: “Support Vector Machine (SVM)”）を自動検出し、クリックで定義を表示
- 本文未定義でも頻出する専門語は、登場する文脈（用例）をまとめてクリックで表示

外部の有料APIは一切使用せず、すべてローカルで完結します（運用コストはほぼゼロ）。

## セットアップ・起動

[Docker Desktop](https://www.docker.com/products/docker-desktop/)（またはWSL2上のDocker Engine）が必要です。GROBIDサービスとアプリ本体をまとめて1コマンドで起動します。

```bash
cd daily-read  # このリポジトリのルート
docker compose up -d --build
```

初回はGROBIDイメージの取得とアプリのビルドで数分かかります。起動確認: `curl http://localhost:8070/api/isalive` が `true` を返せばGROBIDの準備完了です（モデルロードで起動直後は数十秒かかることがあります。アプリ自体はPDFアップロード時に初めてGROBIDへ接続するため、多少前後しても問題ありません）。

終了する場合は次の1コマンドです。`data/` はホストにバインドマウントされているため、コンテナを終了・削除しても処理済みの論文データは消えません。

```bash
docker compose down
```

`./app` はボリュームマウントされているため、コード編集はコンテナ再ビルド無しで即座に反映されます（`uvicorn --reload`）。依存パッケージ（`pyproject.toml`）を変更した場合のみ `docker compose up -d --build` で再ビルドしてください。

GROBIDを別ホスト/ポートで動かす場合は環境変数 `GROBID_URL`（デフォルト `http://grobid:8070`、`docker-compose.yml`で設定済み）で向き先を変更できます。

GROBIDへのリクエストはデフォルトで `GROBID_CONSOLIDATE=0`（`docker-compose.yml`で設定済み）、つまりCrossRef/biblio-glutton経由の外部照合（consolidation）を無効化した、完全ローカルの抽出です。これは意図的な選択です: 外部API照合を有効にすると所要時間がPDFのサイズではなく参考文献の件数・外部APIの応答速度に依存するようになり、小さい論文でもGROBIDの180秒タイムアウトに達することが実際に確認されたため（`app/pdf/grobid_client.py`参照）。タイトル表記ゆれの補正や引用リンクのDOI自動補完の精度を優先したい場合は、環境変数 `GROBID_CONSOLIDATE=1` で有効化できます（`docker-compose.yml`の`app.environment`を書き換えてください。処理時間が伸び、GROBIDコンテナに外向きの通信が必要になります）。

読書ビューの「読む前に確認」欄にある「調べる」リンクは、デフォルトでGoogle検索を開きます。他の検索エンジンを使いたい場合は環境変数 `SEARCH_ENGINE_URL_TEMPLATE`（`{query}`をクエリ文字列の差し込み位置として含む必要があります。例: `https://duckduckgo.com/?q={query}`）で変更できます。ページのリンクからブラウザの既定検索エンジンを呼び出す標準的な方法は存在しないため、この環境変数での明示指定という形にしています。

## 使い方

ブラウザで `http://localhost:8000` を開くと、以下の画面が表示されます。

1. **論文の追加**: トップページのフォームから、PDFファイルをアップロードするか、PDFのURL（arXivのabsページなど）を入力して送信します。
2. **自動整形**: 送信すると自動で二段組の正規化・図表分離・用語抽出が行われ、完了すると読書ビューにリダイレクトされます。
3. **読書ビュー**: 単一カラムの読みやすいレイアウトで本文が表示されます。
   - 下線付きの語句をクリックすると、用語の意味または用例がポップアップ表示されます
   - 本文中の `図を見る` リンクから、該当する図表にジャンプできます
4. **履歴**: トップページには、これまでに処理した論文の一覧（タイトル・推定読了時間・処理日）が表示され、いつでも読み直せます。

### 対応するURLの形式

- PDFへの直リンク（`.pdf` で終わるURL）
- arXivのabsページ（例: `https://arxiv.org/abs/xxxx.xxxxx`）→ 自動でPDFのURLに解決
- 上記以外の論文掲載ページ → ページ内から最初に見つかったPDFリンクを辿ってダウンロード

## 用語抽出の仕組み

デフォルトでは、LLMを使わない完全ローカル・無料のヒューリスティック方式で用語を抽出します（`app/glossary/heuristic.py`）。

1. 本文中で `Full Name (ABBR)` の形式で定義されている略語を最優先で検出し、その定義文をそのまま提示
2. 本文中に定義がなくても3回以上登場する専門語は、登場する全ての文脈（用例）を集約して提示（権威ある定義ではなく用例集である旨をUI上に明示）
3. 一般的なCS/ML略語の補助辞書（`app/glossary/dictionaries/common_abbreviations.json`）でも補完

この方式に不満が出た場合は、`app/glossary/llm.py` にLLMベースの実装を追加し、環境変数 `GLOSSARY_STRATEGY=llm` を設定するだけで切り替えられます（`pipeline.py` など他のコードは変更不要です）。

## テスト

テストはGROBID/Dockerを一切必要とせず、ローカルのPythonだけで完結します（オフラインのフィクスチャでGROBID呼び出しをモックしています）。

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash)。PowerShellなら .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pytest tests/
```

すでに`docker compose up`している場合は、コンテナ内でも実行できます: `docker compose exec app python -m pytest tests/`

## ディレクトリ構成

```
Dockerfile           アプリ本体のコンテナイメージ定義
docker-compose.yml   grobid + app の2サービスをまとめて起動する定義
app/
  pdf/           GROBID連携によるPDF構造抽出(本文/見出し/図表caption/参考文献の分離)とTEI→読書ビュー変換
  glossary/      用語抽出（ヒューリスティック実装 + LLM切り替え用の設計）
  ingestion/     PDFファイル/URLの解決
  pipeline.py    上記を統合する処理フロー
  main.py        FastAPIアプリ本体（履歴一覧・アップロード・読書ビュー）
  templates/     Jinja2テンプレート
  static/        CSS・フォント・JS
data/            処理済み論文のPDF原本・生TEI・図表・SQLiteインデックス（gitignore対象）
tests/           ユニットテスト（GROBID不要、オフラインで完結）
```
