# 課題02: 起動フローの自動化（1コマンドで環境構築・終了）

対象ファイル（新規）: `Dockerfile`, `docker-compose.yml`, `README.md`（更新）

## 現状の問題

毎回アプリを開くのに以下の手作業が必要で、かつ複数ターミナルをまたぐ:

1. (WSLに入る、想定されているケースがある)
2. `docker run ... grobid/grobid:0.9.0-crf` を別ターミナルで起動
3. GROBIDの起動完了を手動で確認 (`curl .../api/isalive`)
4. 別ターミナルで venv を有効化し `uvicorn app.main:app --reload` を起動

## 確定した方針（ユーザー合意済み）

- **Docker一本化。** アプリ本体もコンテナ化し、`docker-compose` で GROBID と
  app の2サービスをまとめて管理する。
- ローカル venv + `uvicorn --reload` によるこれまでの開発手順は撤去し、
  Docker 経由の開発体験に一本化する（`./app` をボリュームマウントして
  `uvicorn --reload` をコンテナ内で使うことで、コード編集の即時反映は維持する）。
- 起動: `docker compose up -d --build` の1コマンド。
- 終了: `docker compose down` の1コマンド。`data/` はホストにバインドマウント
  するため、コンテナを終了・削除してもデータは失われない。

## 実装案

### `Dockerfile`（新規、リポジトリルート）

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -e ".[dev]"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

- 実装時に `pymupdf` が `python:3.11-slim` 上で追加の apt パッケージなしで
  動くか要確認（多くの場合バンドル済みで問題ないはずだが、ビルドして
  `import fitz` を確認する）。

### `docker-compose.yml`（新規、リポジトリルート）

```yaml
services:
  grobid:
    image: grobid/grobid:0.9.0-crf
    init: true
    ports:
      - "8070:8070"
    ulimits:
      core: 0

  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      GROBID_URL: http://grobid:8070
    volumes:
      - ./app:/app/app
      - ./data:/app/data
    depends_on:
      - grobid
```

- GROBID起動には数十秒かかる（モデルロード）。app側は起動時ではなく
  PDF処理リクエスト時に初めてGROBIDへ接続するため、`depends_on` による
  起動順序保証のみで実用上は問題ない想定。厳密なヘルスチェック
  （`condition: service_healthy`）を付けるかは、grobidイメージ内に
  `curl`/`wget` が入っているか実装時に確認してから決める（stretch）。

### README更新

- 「セットアップ」「使い方」セクションを以下に置き換える:
  ```bash
  docker compose up -d --build   # 初回・起動
  docker compose down            # 終了
  ```
- venvベースの手順は削除し、「Docker Desktop（またはWSL2上のDocker Engine）が
  必要」という前提のみ明記する。
- ブラウザで `http://localhost:8000` を開く、という利用手順自体は変更なし。

## 検証方法

- `docker compose up -d --build` 実行後、`http://localhost:8000` が開けること、
  `curl http://localhost:8070/api/isalive` が `true` を返すことを確認。
- PDFを1件アップロードして最後まで処理が通ることを確認（GROBID連携の疎通確認）。
- `docker compose down` → `docker compose up -d` で再起動し、`data/` 配下の
  過去論文が消えずに履歴一覧に残っていることを確認。
- `./app` 配下のファイルを編集し、コンテナ再ビルドなしで変更が反映される
  （`--reload` が効く）ことを確認。

## 実装した内容（2026-07-03）

計画通り `Dockerfile`・`docker-compose.yml` を作成し、READMEを
Docker一本化の手順に置き換えた。

### 検証状況（重要な制約）

**この作業環境には`docker`コマンド自体が存在しない**（`docker: command
not found`を確認済み）ため、`docker compose up -d --build`を実際に実行して
GROBID+appが起動することは検証できていない。以下の範囲までを検証した:

- `docker-compose.yml`をPythonの`yaml.safe_load`でパースし、構文として
  正しいこと、計画通りの構造（サービス名・ポート・volumes・環境変数）に
  なっていることを確認。
- `Dockerfile`は計画通りの内容で作成したが、実際にビルドして
  `python:3.11-slim`上で`pymupdf`が追加パッケージ無しで動くか（計画時点で
  「要確認」としていた点）は、この環境ではビルドできないため未検証のまま。
- テストスイート（`pytest`）はGROBID/Dockerを一切必要としないため、
  今回の変更後も全件パスすることを確認済み（README更新は非コード変更、
  Dockerfile/docker-compose.ymlは新規ファイルでテストに影響しない）。

**ユーザー側でDocker環境がある場所で、実際に`docker compose up -d --build`
を実行して起動確認をしていただく必要がある。** 特に以下を確認いただきたい:
- ビルドが成功し`pymupdf`が正しく動くか
- `http://localhost:8000`が開けるか
- PDFを1件アップロードして最後まで処理が通るか（GROBID疎通確認）
- `docker compose down` → `up`で再起動しても`data/`の過去論文が残っているか

## 未確定・保留事項（優先度低）

- リポジトリ直下の `get-docker.sh`（Docker Engine公式インストールスクリプト、
  未追跡ファイル）は、Docker CLI/Desktopが前提の本方針では不要になる可能性が
  高い。削除するかどうかはユーザー判断待ち（誤って必要なファイルを消さないよう、
  現時点では触れない）。
- 起動を1コマンドよりさらに簡略化する `start.ps1` のようなラッパー
  （例: 起動後に既定ブラウザで `localhost:8000` を自動オープン）は、
  `docker compose up -d` 自体が既に「コマンド一つ」の要件を満たすため、
  現時点ではスコープ外（要望があれば追加）。
