# 課題01: 図表パネルのスクロール挙動

対象ファイル: `app/templates/paper.html`, `app/static/styles.css`, `app/static/reader.js`

## 現状の問題

- **モバイル (`max-width: 860px`)**: `.figures-panel` は `position: static` で本文の
  下に続くだけ。本文中の「図を見る」リンク (`<a class="figure-jump" href="#{{ fig.figure_id }}">`)
  はページ内アンカーなので、クリックするとページ全体が下まで強制スクロールされる。
  読んでいた文章の位置が失われる。
- **デスクトップ**: `.reader-layout` は2カラム CSS Grid。`.figures-panel` に
  `position: sticky` は付いているが、スクロールコンテナはページ全体で1つしかない
  ため、「図を見る」リンクをクリックするとページ全体がスクロールし、本文の読書位置
  がずれてしまう（sticky は効いているが独立スクロールにはなっていない = 壊れている）。

## 確定した方針（ユーザー合意済み）

1. **モバイル: モーダルに一本化。** 本文下の図表一覧セクションは廃止し、本文中の
   「図を見る」リンクを押すとモーダルでその図だけを表示する。本文のスクロール位置は
   一切変化しない。
2. **デスクトップ: 図表カラムを固定高スクロール枠に。** `.figures-panel` を
   `position: sticky` + `height: calc(100vh - <ヘッダー分オフセット>)` +
   `overflow-y: auto` の独立スクロール枠にする。「図を見る」リンクを押すと、
   その枠の中だけがスクロールし、対象の図が枠の一番上に来る。本文カラムのスクロール
   位置には一切影響しない。
3. **デスクトップ: 非アクティブ時は図表カラムを減光。** 図表カラムは読書の邪魔に
   ならないよう、デフォルトで `opacity` を下げておく（未クリック状態）。「図を見る」
   リンクをクリックすると対象の図がハイライト（`opacity: 1` + アクセントカラーの枠線）
   され、他の図は引き続き減光したまま。マウスで図表カラム自体にホバーしている間は
   ブラウズしやすいよう全体を `opacity: 1` に戻し、マウスが離れたら減光状態に復帰する
   （ホバーは CSS の `:hover` のみで実現、アクティブ図のハイライトは JS で管理）。

## 実装案

### データの持ち方

図表のメタデータ（id, 画像パス, ラベル, キャプション）を JSON として埋め込む
（既存の `#glossary-data` パターンを踏襲）。モバイルのモーダルとデスクトップの
スクロール処理の両方から同じデータソースを参照できるようにする。

```html
<script type="application/json" id="figures-data">{{ figures_json | safe }}</script>
```

### HTML

- `.figures-panel` はデスクトップ表示専用として維持（モバイルでは `display: none`）。
- モーダル用のマークアップを追加:
  ```html
  <div id="figure-modal" class="figure-modal" hidden>
    <div class="figure-modal-backdrop"></div>
    <div class="figure-modal-content">
      <button type="button" class="figure-modal-close" aria-label="閉じる">×</button>
      <img src="" alt="" />
      <figcaption></figcaption>
    </div>
  </div>
  ```

### CSS (`styles.css`)

- デスクトップ (`min-width: 861px` 相当):
  - `.figures-panel { position: sticky; top: 1.5rem; max-height: calc(100vh - 3rem); overflow-y: auto; }`
  - `.figure-card { opacity: .55; transition: opacity .2s ease; }`
  - `.figure-card.is-active { opacity: 1; border-color: var(--accent); }`
  - `.figures-panel:hover .figure-card { opacity: 1; }`
- モバイル (`max-width: 860px`):
  - `.figures-panel { display: none; }`
  - `.figure-modal` のスタイル（中央寄せの固定オーバーレイ、背景は半透明の黒、
    画像は `max-width: 90vw; max-height: 80vh;` で contain 表示）。
  - 既存の `.glossary-popover` の配色トーンに合わせる。

### JS (`reader.js`)

- `matchMedia("(max-width: 860px)")` でモバイル/デスクトップを判定。
- `.figure-jump` クリックのハンドラを追加し、常に `preventDefault()`:
  - モバイル: `figures-data` から該当図を引き、モーダルに描画して表示。
    閉じ方は既存の glossary-popover と同じ操作性
    （背景クリック / × ボタン / Esc）に揃える。
  - デスクトップ: `.figures-panel` 内の対象 `#figure-id` 要素に対して
    パネル内だけの `scrollTop` 調整（`element.offsetTop - panel.offsetTop` 等で計算、
    もしくは `scrollIntoView({ block: "start" })` をパネル自身に
    `overflow-y: auto` を持たせた状態で呼ぶことでページ全体ではなく
    パネル内スクロールに閉じ込める）。同時に `is-active` クラスを対象の
    `.figure-card` に付与し、他からは外す。
- 既存の `Escape` キーハンドラを拡張してモーダルも閉じられるようにする。

## 検証方法

- ブラウザの devtools でビューポート幅を切り替えながら手動確認:
  - モバイル幅: 「図を見る」タップ → モーダル表示 → 閉じる → 本文のスクロール位置が
    タップ前と完全に一致していること。
  - デスクトップ幅: 「図を見る」クリック → 図表カラムのみがスクロールし対象の図が
    枠の最上部に来ること → 本文カラムのスクロール位置が変化しないこと →
    対象の図がハイライトされ他は減光していること → 図表カラムにマウスを乗せると
    全体が明るくなること。

## 未確定・保留事項（優先度低、必要なら後で相談）

- アクティブ図のハイライトを一定時間後に自動でフェードアウトさせるか
  （現時点では「次の図がクリックされるまで持続」で実装する想定）。
- デスクトップの図表カラムでも画像をさらに拡大するモーダル（ズーム表示）を
  設けるか（現時点ではスコープ外）。

## 実装した内容（2026-07-03）

計画通りに実装した。差分:

- `.figure-card`の「本文に戻る ↑」リンクは削除した（本文カラムのスクロール
  位置がそもそも動かなくなったため、「戻る」先が意味を持たなくなったため）。
- 図表データは`rendering.figures_json(figures, paper_id)`を新設して
  `main.py`から渡す設計にした（画像URLの組み立て`/papers/{id}/figures/{name}`
  をJinja側の`.split('/')[-1]`ではなくPython側で行い、JSにロジックを
  持ち込まない）。
- デスクトップの図表カラムスクロールは`offsetTop`差分ではなく
  `getBoundingClientRect()`の差分で計算した（`offsetParent`チェーンの
  ブラウザ差異に依存しないため、より頑健）。

### 検証状況（重要な制約）

この環境には**ブラウザ自動化ツール（Playwright/Selenium等）が存在しない**
ため、以下の切り分けで検証した:

- **オフラインで検証済み**（`pytest`）: サーバー側のHTML/データ配線
  （`#figures-data`のJSON内容、`#figure-modal`の存在、「本文に戻る」削除、
  画像URLの組み立て）。
- **実サーバーで軽く確認**: `uvicorn`を実際に起動し、本セッション以前に
  処理済みの実データ（`authors`/`abstract`フィールドを持たない旧形式の
  `content.json`）に対して`/papers/{id}`が200で正しく描画されること、
  静的ファイル(`styles.css`/`reader.js`)が配信されることを確認（テンプレート
  が古いデータ形式でも壊れないことの後方互換性チェック）。
- **未検証（ブラウザでの目視確認が必要）**: モバイルでのモーダル表示、
  デスクトップでの図表カラム独立スクロール・ハイライト・ホバー時の減光解除
  という、この課題の核心である**インタラクティブな挙動そのもの**は、
  実際のブラウザで動かして確認する必要がある。ユーザーに軽くブラウザで
  触っての確認をお願いしたい。
