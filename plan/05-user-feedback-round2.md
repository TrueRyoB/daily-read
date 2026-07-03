# 課題05: 実データでの使用後フィードバック（第2弾）

前回15チケット完了後、ユーザーが実際にDockerでアプリを動かし
（`data/papers/5480fbc25054/`が実データ）、ブラウザで使ってみて出た
フィードバック。一部は本日の実データ（生TEI・content.json）を直接調査し、
原因を特定済み。

**進め方**: オートモードで実装するが、各タスク完了ごとに`pytest tests/`を
実行し報告する。

## 優先順位・実装順序

| ID | 内容 | 規模 |
|---|---|---|
| 05-a | 引用リンクの不具合修正（重複ID・複数引用の分断ラベル） | 小 |
| 05-b | 図表の文中参照リンク化 + 「図を見るボタン」削除 | 中 |
| 05-c | 語彙抽出フィルタリング改善（見逃し一般語・固有名詞除外） | 小〜中 |
| 05-d | 「調べる」リンクの文脈化 + 検索エンジン設定可能化 | 小 |
| 05-e | 「30分」表現の削除（README〜UI全体） | 極小 |
| 05-f | 論文読み込み中の進捗表示・完了通知（同期→非同期化） | 大 |
| 05-g | 読者コメント/注釈機能 | 大 |
| 05-h | UI日英切替 | 中〜大 |
| 05-i | （提案のみ・実装しない）スマホ通勤UX | - |

## 05-a: 引用リンクの不具合修正 ✅ 実装完了（2026-07-03）

計画通り実装。`pytest tests/`59件全パス。実データ
（`data/papers/5480fbc25054/tei.xml`）に直接`parse_tei()`を実行し、
`[1,16]`が`\x00CITE:b0,b15\x00[1,16]\x00/CITE\x00`という1つの
プレースホルダに正しくマージされることを確認済み。

（注: 同フォルダの`content.json`は本日の修正**前**に生成されたキャッシュ
のため、サーバー起動して既存データを見ても古い分断ラベルのままに見える
— これは想定通りの挙動で、再処理すれば新しいロジックが反映される。
バグではない。）

### 元の計画

**現象**: 引用リンクを押しても何も起こらない。

**実データで特定した原因（2つ、`data/papers/5480fbc25054/`で確認済み）**:

1. **重複ID**: `paper.html`の`bib_entry`マクロが`in_panel`の値に関わらず
   常に同じ`id="bib-{{entry.bib_id}}"`を出力しており、デスクトップの
   `.figures-panel`とモバイル専用の`.bibliography-mobile`の両方で同じIDが
   使われる（無効なHTML）。デスクトップは`getElementById`の「最初の
   一致が返る」挙動でたまたま動くが、モバイルはネイティブアンカー
   ジャンプに任せているため、`display:none`側の要素へ飛ぼうとして失敗する。
2. **複数引用のラベル分断**: `[1, 16]`のような複数引用はGROBIDが
   `<ref target="#b0">[1,</ref><ref target="#b15">16]</ref>`の2要素に
   分割して返す。現状は個々の`<ref>`をそのまま独立リンクにするため、
   `[1,` `16]`という分断ラベルの2つの別リンクになる。

**修正方針**:
1. モバイル側のみ`id="bib-mobile-{{entry.bib_id}}"`に変更。`reader.js`の
   モバイル分岐を、デスクトップと同様に明示的な`getElementById`+
   `scrollIntoView`+`preventDefault`方式に変更（ネイティブブラウザ挙動
   への依存をやめ、常にJSが制御する設計に統一）。
2. `tei_parse.py`に、隣接する`<ref type="bibr">`の並びを1つの引用に
   まとめる後処理を追加。`models.py`の`citation_placeholder`を複数bib_id
   対応に拡張（`\x00CITE:b0,b15\x00[1, 16]\x00/CITE\x00`）。
   `rendering.py`の`_citation_link`はbib_idをカンマ分割し、複数ある
   場合は1件目を代表リンク先とする。

## 05-b: 図表の文中参照リンク化 + 「図を見る」ボタン削除 ✅ 実装完了（2026-07-03）

計画通り`parse_tei`を2パス構成にリファクタし実装。`pytest tests/`63件
全パス。実データ（`data/papers/5480fbc25054/tei.xml`）で検証したところ、
本文中の12箇所の"Figure N"言及すべてが正しい図表IDにリンクされることを
確認（前方参照「Figure 1 below」のケースも含む）。副次的に、
`.citation`にCSSスタイルが1つも定義されていなかったことにも気づき
（03-c実装時の見落とし）、`.figure-jump`と共通のインラインリンク
スタイルを追加した。「図を見る」テキストは完全に削除され、
`figures_by_id`（テンプレートで未使用になった変数）も併せて削除した。

### 元の計画

**実データで確認した構造**: GROBIDは本文中に
`<ref type="figure" target="#fig_0">1</ref>`（可視ラベルは数字のみ）を
返し、`<figure xml:id="fig_0">`という形で図表要素にGROBID独自のxml:idを
振っている。

**修正方針**:
1. `parse_tei`を「本文走査と図表構築を同時に1パスで行う」構成から、
   **先に図表クラスタリング＋GROBIDのxml:id→当アプリの`figure_id`の
   対応表を確定させてから本文を構築する2パス構成**にリファクタする
   （"as shown in Figure 3 below"のような前方参照に対応するため）。
2. `<ref type="figure">`/`<ref type="table">`を引用と同じ
   `citation_placeholder`の仕組みで扱い、`<a class="figure-mention" href="#{{figure_id}}">`
   に変換。クリック時の挙動は既存の`.figure-jump`と共通化する
   （デスクトップ: パネル内スクロール+ハイライト、モバイル: モーダル）。
3. `paper.html`の`figure_ref`ユニットに対応する「図を見る」リンクを削除。
   文中で言及されない図表は側パネルには残るが文中からは辿れなくなる
   （ユーザーの明示的な指示に沿うトレードオフとして許容）。

## 05-c: 語彙抽出フィルタリング改善 ✅ 実装完了（2026-07-03）

計画通り実装。`pytest tests/`68件全パス。実データ
（`data/papers/5480fbc25054/tei.xml`）で著者名除外フィルタの効果を検証し、
参考文献著者「Woods」が実際に語彙候補から除外されることを確認済み
（この論文自体はteiHeaderに自身の著者情報が無かったため、参考文献側の
著者81名のみが除外対象になった — この論文固有の事情で、機能自体は
正しく動作している）。

実装中、新設した`FIGREF`プレースホルダ（05-b）にも、03-cで見つけた
"CITE"と同じ語彙混入リスクがあることに気づき（同じ単語境界付きリテラルの
問題）、`pipeline.py`の`_strip_placeholders`ヘルパーに統合して両方を
一度に防ぐよう修正した。

`common_english_words.txt`への単語追加時、既存語との重複が5件
（based, described, given, provided, shown）発生していたことにも
`sort | uniq -d`で気づき、削除して整合性を保った。

### 元の計画

**フィードバック**: 固有名詞（人名等）が未定義語として括られる／
PhD・Prof・Experimental・Marked（受動態）等の一般語を弾けていない／
"DNA Origami"の複合語グルーピングは素晴らしい（現状維持）。

**修正方針**:
1. `common_english_words.txt`に見逃し語（PhD, Prof, Experimental,
   Marked, Related, Based, Proposed, Applied, Combined, Shown, Given,
   Used, Required, Associated, Estimated, Assumed, Obtained, Presented,
   Described, Compared, Provided, Determined, Selected, Included等）を
   追加。語尾ステミングによる一般化は誤爆リスク（Method→Meth等）のため
   見送り、単語追加で対応（04-fと同じ判断基準）。
2. `content.bibliography[].authors`と`content.authors`に一致する候補語を
   頻出語彙候補から除外する（汎用NER導入は見送り、既存パース済みデータの
   再利用で対応。データセット名等の固有名詞までは拾えない既知の限界あり）。
   `heuristic.py`の`extract()`に著者名リストを渡す引数を追加。

## 05-d: 「調べる」リンクの文脈化 + 検索エンジン設定可能化 ✅ 実装完了（2026-07-03）

計画通り実装。`pytest tests/`72件全パス。`rendering.search_url(term,
paper_title)`を新設し、`main.py`からJinjaコンテキストに関数として渡し
`paper.html`側で直接呼ぶ形にした（Jinja側で文字列組み立てをしない）。
検索エンジンは`SEARCH_ENGINE_URL_TEMPLATE`環境変数（`{query}`プレース
ホルダ必須）で差し替え可能。READMEにも追記済み。

**Bing固定問題は未解決のまま**（05-dの計画時点の診断メモ参照）。ユーザーの
環境切り分け待ち。

### 元の計画

**修正方針（文脈化）**: 検索クエリに論文タイトルを付与する:
`"{term}" {paper.title}`。タイトルは既に取得済みのデータであり追加の
推論ロジック無しで文脈を機械的に付与できる。

**検索エンジンについて（技術的制約）**: Webページのリンクから
「ブラウザの既定の検索エンジン」を呼び出す標準的な方法は存在しない。
現状の実装はGoogle固定であり、Bingを指定した箇所は無い。

**Bing固定トラブルシューティング（診断済み・要ユーザー確認）**: ユーザー
環境で検索リンククリック時にBingへ飛ぶ現象が報告されたが、コード上の
原因ではなく、Windows/Edgeの「検索の強化」機能等、OS/ブラウザ側で
Google等へのリンクをBingへ強制リダイレクトする設定に起因している可能性が
高いと判断した（この場合アプリ側のURL変更では解決しない）。**この診断は
未確定・未解決のまま記録している** — 後日、実際にユーザー環境で
`edge://settings/search`等を確認し、原因が確定次第、このメモを更新して
必要な対応（例: 検索エンジンを環境変数で切り替え可能にする、等）を取る。

対応として、検索エンジンをアプリの環境変数
（`SEARCH_ENGINE_URL_TEMPLATE`、デフォルトGoogle）で設定可能にする案を
実装する（DBを使った設定UIより実装コストが低い）。

## 05-e: 「30分」表現の削除（README〜UI全体、確定） ✅ 実装完了（2026-07-03）

3箇所すべて削除・置換した: `app/templates/paper.html`の読了時間表示
（「（30分目標のXX%）」部分のみ削除）、`app/templates/base.html`のサイト
タグライン（「毎朝30分で論文を読む」→「論文を読みやすく」）、
`README.md`冒頭の説明文（「毎朝30分で論文を読む習慣を続けるために」→
「論文を読みやすくするために」）。回帰防止テストを2件追加
（読書ビュー・トップページ双方で"30分"が出現しないことを確認）。
`pytest tests/`73件全パス。プロジェクト名`daily-read`自体は計画通り
スコープ外として変更していない。

### 元の計画

ユーザー指示: 「30分表現は、readmeからUIまですべて削除してください」。
以下すべてを対象とする:
- `app/templates/paper.html`の「（30分目標のXX%）」
- `app/templates/base.html`のサイトタグライン「毎朝30分で論文を読む」
- `README.md`冒頭の「毎朝30分で論文を読む習慣を続けるために」等の記述
- 他に「30分」を前提にした文言があれば同様に削除し、「論文を読みやすくする」
  という趣旨に沿った文言に置き換える

プロジェクト名`daily-read`自体の改名は今回のスコープ外とする
（「30分」という具体的な時間目標の削除が指示の対象であり、プロジェクト名
変更は別途相談が必要な大きな決定のため）。

## 05-f: 論文読み込み中の進捗表示・完了通知 ✅ 実装完了（2026-07-03）

Plan agentの設計通り実装。`pytest tests/`86件全パス（新規12件）。
実データ2件（既存の"done"論文）に対して`/papers/{id}/status`が正しく
`{"status":"done"}`を返すことをサーバー起動して確認済み。

**設計上の重要な工夫**: `pipeline.process_upload`/`process_url`
（同期・ブロッキング版）はそのまま残し、新たに`start_upload_processing`/
`start_url_processing`（非同期版、`main.py`から呼ぶ）を追加する形にした。
これにより、既存の60件超のテストが一切変更不要だった（同期APIの挙動を
完全に維持したまま、実運用の`main.py`だけを非同期版に切り替えた）。
両者は`_process_pdf(paper_id, pdf_bytes)`という「`papers`テーブルに
一切触れないコア処理」を共有し、同期版はINSERT、非同期版はUPDATE
（`mark_paper_done`/`mark_paper_error`）で結果を反映する設計にした。

`threading.Event`でテスト側から`extract_tei`をブロックし、「処理中」→
「完了/エラー」の状態遷移を実際のHTTPリクエスト経由でエンドツーエンド
検証するテストも追加（`TestClient`は`threading.Thread`を応答生成と
同期させないため、これが可能だった — `BackgroundTasks`だったら不可能
だったはずで、この設計判断の正しさを裏付けている）。

### 元の計画（Plan agentによる詳細設計・要点）
- `threading.Thread(daemon=True)`で実行方式を非同期化（`BackgroundTasks`は
  テストで「処理中」状態を観測できなくなるため却下、asyncio化は変更が
  大きすぎるため却下）。
- `papers.status`カラムを再利用（`processing→done/error`）、
  `error_message`カラムを追加（`ALTER TABLE`簡易マイグレーション）。
- 正確なETAは計算不可能と判断し、不定形スピナー+経過秒数のみ表示。
  `GET /papers/{id}/status`を2秒間隔でポーリング（SSE/WebSocket不要）。
- 完了通知は`document.title`常時更新をベースラインとし、Notification API
  はボタンクリック起点のopt-in強化とする。
- GROBIDタイムアウトも`RuntimeError`化。バックグラウンドスレッド内の
  例外は必ず`papers.status='error'`に変換する。
- 影響ファイル: `app/db.py`、`app/pipeline.py`（`start_processing`/
  `_process_in_background`に分割）、`app/main.py`、新規
  `app/templates/processing.html`、新規`app/static/processing.js`、
  `app/pdf/grobid_client.py`。
- テスト: `threading.Thread`は`TestClient`内で完走しないため、むしろ
  「処理中」状態を意図的に観測できる（`extract_tei`を`threading.Event`で
  ブロックしてポーリング確認）。

## 05-g: 読者コメント/注釈機能 ✅ 実装完了（2026-07-03）

Plan agentの設計通り実装。`pytest tests/`106件全パス（新規7件、
`test_annotations_route.py`）。バックエンド（`db.py`のCRUD、
`rendering.py`の`match_annotations`/`annotations_json`、`main.py`の
POST/PUT/DELETEエンドポイント）は既に完了・テスト済みだった状態から、
`paper.html`のマークアップ、`reader.js`の3つ目のIIFE（テキスト選択→
ポップオーバー→保存/編集/削除）、`styles.css`のスタイルを実装して完成させた。

**テスト作成時に見つけた設計上の注意点**: ゴールデンTEIフィクスチャの
`abstract`テキストは`content.abstract`として直接レンダリングされ、
`content.units`（`match_annotations`が検索する対象）には含まれない。
最初、abstract内の文言でアノテーションのテストを書いたところ「見つから
ない」扱いになってしまった（バグではなく仕様通り — アノテーションは
本文の段落/見出しユニットにのみ付けられる）。本文中の段落から選んだ
文言に差し替えて解決。実際のブラウザ利用でも同様に、abstractやヘッダー
部分のテキストを選択してもメモは追加できない（`.reader-body`配下のみが
対象）— この既知の制限はUI側の`.annotation-hint`の位置（`.reader-body`
の外、ヘッダー内）とは矛盾しないが、将来abstractにもメモを許可したく
なった場合は`match_annotations`の対象を広げる必要がある。

**フロントエンド実装の要点**:
- `mouseup`イベントで選択範囲を捕捉し、開始/終了ノードの
  `closest("h2, h3, h4, p")`が一致する場合のみ「+ メモを追加」ボタンを
  表示（複数ブロックにまたがる選択は計画通り弾く）。
- `quote`確定時に前後最大40文字を`blockEl.textContent`から算出して
  `prefix`/`suffix`として送信（ネストしたインライン要素をまたぐ複雑な
  オフセット計算はせず、`indexOf`ベースのベストエフォート — 前後文脈が
  多少ずれても`match_annotations`側の「quoteのみ一致」フォールバックが
  吸収する設計のため、過剰な精度は不要と判断）。
- 新規メモは追加のページリロード無しでその場でマーカー（📝ボタン）と
  キューへのエントリをDOMに直接挿入する。編集・削除も同様に、対応する
  キュー項目・マーカーだけを更新/削除する（サーバー再取得なし）。
- ポップオーバー・追加ボタン・グロッサリポップオーバー・図表モーダルは
  それぞれ独立した`document.addEventListener("click", ...)`を持つ
  別々のIIFEとして共存させ、既存の2つ（グロッサリ・図表）のクリック
  ハンドラのパターン（自分の関心のある要素以外はno-op、最後に
  「それ以外ならポップオーバーを閉じる」というフォールスルー）を踏襲した。

### 元の計画

Plan agentによる詳細設計（要点）:
- 永続化はSQLite新規`annotations`テーブル（`id, paper_id, quote, prefix,
  suffix, note, created_at, updated_at`）。`content.json`には触れない
  設計にし、再処理してもメモが消えないようにする。
- アンカリング粒度は「1段落/見出し内のみ」（複数ブロックにまたがる選択は
  クライアント側で弾く）。
- 保存時に前後最大40文字(`prefix`/`suffix`)も保存し、表示時に「前後込み
  完全一致→quoteのみ一致」の2段階フォールバックで該当ブロックを探す
  （`rendering.py`に純粋関数`match_annotations`を追加）。見つからない
  場合はクラッシュさせず状態フラグを立てるのみ（削除しない）。
- ハイライトはブロック単位（正確な文字範囲を`<mark>`で囲まない、既存の
  `.gloss`/`.citation`スパンをまたぐ分割処理を避けるため）。
- 「キュー」UIは`.figures-panel`ではなく`.toc`と同じ`<details>`ブロックに
  する（モバイルでも追加コード無しで機能するため）。
- 新規/変更ファイル: `app/db.py`、`app/rendering.py`、`app/main.py`
  （POST/PUT/DELETE `/papers/{id}/annotations[/{id}]`）、
  `app/templates/paper.html`、`app/static/reader.js`（新規IIFE）、
  `app/static/styles.css`。`models.py`/`pipeline.py`/`storage.py`は
  変更不要。
- テスト: DB層CRUD、`match_annotations`純粋関数テスト（前後込み一致・
  quoteのみフォールバック・見つからない場合のフラグ）、ルートレベル
  （**再処理でcontent.jsonの文言が変わってもクラッシュせず「見つからない」
  表示になること**が最重要）。

## 05-h: UI日英切替 ✅ 実装完了（2026-07-03）

計画通り実装。`pytest tests/`111件全パス（新規5件、`test_i18n.py`）。
`app/i18n.py`に`TRANSLATIONS`辞書と`translator(locale)`/
`js_translations(locale)`を実装。`main.py`に`_locale_context`/`_render`
ヘルパーを追加し、`index`/`read_paper`の2ルートを`_render`経由に変更
（`?lang=`クエリパラメータが最優先、次にCookie、デフォルトはja。
`?lang=`が指定された場合のみCookieを更新——ほとんどのリンクは`?lang=`を
持たないため、Cookieが無いとページ遷移のたびに日本語へ戻ってしまう）。
`base.html`のヘッダーに切替リンク（現在のロケールの反対の言語名を表示、
クリックで`?lang=`を切り替え）を追加。

`reader.js`が動的に組み立てるポップオーバー文言（グロッサリ・注釈)は、
`paper.html`に埋め込んだ`<script id="i18n-data">`のJSON経由で受け取る
（JS内に2つ目の辞書を手書きで重複させない設計）。

**未対応として意図的にスコープ外**: `processing.html`の
`paper.error_message`（GROBIDタイムアウト等、`grobid_client.py`側で
生成される例外メッセージ）は翻訳していない。診断用メッセージであり、
パイプライン全体の例外文言をロケール対応させるコストに見合わないと
判断（05-dの「実装コストから必要十分な範囲を考える」という判断基準と
同じ）。同様に、`main.py`の`HTTPException`のdetail文言（バリデーション
エラー等）も未対応。

### 元の計画

現状スコープ: テンプレート・`main.py`のJA文字列約27箇所、`reader.js`内
約5箇所（05-bで「図を見る」削除後はさらに減る）。

**修正方針**:
1. `app/i18n.py`（新規）に`TRANSLATIONS = {"ja": {...}, "en": {...}}`の
   単純な辞書（外部i18nライブラリは導入しない）。
2. Jinja側は`{{ t('key') }}`のテンプレートグローバル関数を`main.py`から
   各`TemplateResponse`のコンテキストに注入。
3. ロケール切り替えはCookie方式（`?lang=en`）。`base.html`ヘッダーに
   切替リンクを追加。
4. `reader.js`内のJA文字列も同様の小さな辞書ルックアップに置き換える。

## 05-i（提案のみ・実装しない）: スマホで通勤中に見れるUX

ユーザー自身が「実装ではなく機能提案に留めて」と明示。実装しない。

このアプリはPC上でDocker一式（GROBID+FastAPI）をホストする前提の
アーキテクチャであり、外出先のスマホから使うには(a)自宅/職場PCの常時
起動+ポート開放、(b)クラウドへのGROBID込みデプロイ、のいずれかが必要。
前者はセキュリティ/電気代の観点で非現実的、後者はGROBID（JVMベース、
モデルロードに数十秒・相応のメモリ要）のホスティングコストが「$0運用」
という既存方針と衝突する。処理済み論文の読み取り専用ビューだけを軽量な
静的ページとして書き出す妥協案はあり得るが、別アーキテクチャの話になる
ため、今回は提案の記録に留める。

## 検証方法

各タスク完了ごとに`pytest tests/`をフルスイート実行。この環境は
ブラウザ自動化・Dockerが無いため、インタラクティブな挙動（テキスト
選択・ポーリング・通知・検索エンジンリダイレクト等）は既存の制約と
同様、サーバー側データ/HTML配線の確認までに留め、ユーザー自身の
ブラウザでの確認をお願いする。
