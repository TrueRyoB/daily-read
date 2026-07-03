# 課題03: PDF/TEI からのドメイン知識抽出が不足している

対象ファイル: `app/pdf/tei_parse.py`, `app/pdf/grobid_client.py`, `app/pipeline.py`,
`app/models.py`, `app/rendering.py`, `app/templates/paper.html`, `tests/test_tei_parse.py`

## 診断の共通根 (これが全項目に効く本質的な原因)

`tei_parse.py` は GROBID の TEI 出力のうち **`text/body` しか見ていない**。
GROBID は実際には以下も構造化して返しているが、現状すべて未使用・破棄されている:

- `teiHeader/fileDesc/titleStmt` と `sourceDesc/biblStruct` — 論文名・著者
- `teiHeader/profileDesc/abstract` — 要旨
- `text/back/div[@type='bibliography']/listBibl/biblStruct` — 参考文献リスト
- 本文中の `<ref type="bibr" target="#bX">` — 引用マーカーと参考文献IDの対応
- `<div>` のネスト深さ（見出しレベルの正確な情報源。現状は見出しテキストの
  番号付け文字列から正規表現で推測しており、構造情報を捨てている）
- リクエスト時に指定できる `consolidateHeader`/`consolidateCitations`
  パラメータ（後述。GROBID自身が外部照合でメタデータを補完してくれる機能）

つまり「GROBIDがせっかく構造化・補完までしてくれるものを、パイプラインが
本文の段落・見出し・図だけ拾って残りを全部捨てている」のが共通の根本原因。

**⚠️ 方針修正（GROBID公式ドキュメントで検証済み）:** 当初この節には
「`<figure>`内の`<graphic coords>`子要素、および画像本体とキャプションが
別々の`<figure>`要素に分離するケースへの対応」も含めていたが、これは
未検証の推測に基づく誤った前提だった。実際の GROBID 出力例（
[GROBIDドキュメント](https://grobid.readthedocs.io/en/latest/Grobid-service/)
および公開されている実出力サンプルで確認）は次の1要素構造であり、
画像とキャプションが別要素に分割されることはない:

```xml
<figure xml:id="fig_1">
  <head>Figure 1 :</head>
  <label>1</label>
  <figDesc>Figure 1: Network-based analysis of omic data...</figDesc>
  <graphic url="..." coords="12,72.00,178.57,319.30,504.00" type="bitmap" />
</figure>
```

自前で「2要素をマージする」ロジックを設計するのは、GROBIDが既にやって
くれていることを再実装する典型的な車輪の再発明だったため、その設計は
撤回し、03-bを「まず実データで検証してから直す」方針に作り直した
（詳細は03-b参照）。また `processFulltextAssetDocument`（画像を直接zipで
返すAPI）への切り替えも一時検討したが、GROBID公式のFAQで
[非推奨と明記されている](https://github.com/kermitt2/grobid/blob/master/doc/Frequently-asked-questions.md)
ため見送り。現状の「`teiCoordinates=figure`で座標だけ受け取り、PyMuPDFで
自前クロップする」というこのプロジェクトの既存方式は、REST API利用者向けに
GROBID公式が推奨する現行のやり方と一致しており、変更不要と判断した。

## 優先順位

| ID | 内容 | 優先度 | 根拠 |
|---|---|---|---|
| 03-g | GROBIDリクエストパラメータの活用（consolidateHeader/consolidateCitations） | **P0** | 実装コストが最小（HTTPリクエストのパラメータ追加のみ）で、03-a/03-cの精度をGROBID自身に肩代わりさせられる。他項目より先に入れておく価値が高い |
| 03-a | 論文名・著者（+ 要旨）の抽出 | **P0** | 実装が軽い割に、読書体験の信頼性に直結（今どの論文を読んでいるか分からない） |
| 03-b | 画像とキャプション不一致の原因調査・修正 | **P0** | 実データで検証済みの重大なバグ（下記参照）。誤った情報を提示している点で「何もしないより悪い」。ただし原因は未確定のため「調査→修正」の2段構え |
| 03-c | 引用 `[i]` の参考文献リンク化 | P1 | 価値は大きいが実装量も相応。03-bの図表パネルと同じ「本文から分離してパネル化」の設計を再利用できる |
| 03-d | 見出しレベルをdivネスト深さから取得 | P1 | 実装は小さいが、03-e (目次) の前提になる |
| 03-e | Table of Contents 抽出とUI組み込み | P2 | 03-dに依存。UI設計（配置場所）に判断が要る |
| 03-f | Unicode記号の文字化け疑い（新規発見） | P2 | 未確認の根本原因調査が先に必要 |

## 03-g: GROBIDリクエストパラメータの活用

### 背景

[GROBID REST APIドキュメント](https://grobid.readthedocs.io/en/latest/Grobid-service/)
によれば、`processFulltextDocument` は以下のパラメータを受け付ける
（現状 `grobid_client.py` は `teiCoordinates: "figure"` しか指定していない）:

- `consolidateHeader` (0/1/2/3): ヘッダー情報（タイトル・著者等）を
  CrossRef/biblio-glutton経由の外部照合で補完・正規化する。
- `consolidateCitations` (0/1/2): 参考文献エントリを同様に外部照合で
  補完する（**これによりDOIが埋まる可能性が高く、03-cの「引用先URL」を
  自前のDOI解決ロジックなしで得られる**）。
- `generateIDs` (0/1): 文書内の各構成要素に一意なIDを付与させる
  （03-eのTOCアンカーIDを自前生成する代わりに使えないか、実装時に確認する）。

これらを使わずに「タイトルの表記揺れを直す」「引用のDOIを自分で調べる」
ロジックを自作するのは、まさにGROBIDの機能の車輪の再発明にあたる。

### 修正方針

- `grobid_client.py` の `extract_tei` が送る `data` に
  `consolidateHeader=1`（または`3`: 既存論文はDOIを持つことが多いので
  厳密一致のみで十分な可能性もあり、実装時に値を比較検討する）と
  `consolidateCitations=1` を追加する。
- 外部API（CrossRef等）への問い合わせが発生するため、(a) 処理時間が
  伸びる、(b) GROBIDコンテナに外向きインターネット接続が必要になる、
  という2点を踏まえ、環境変数で無効化できるようにする
  （例: `GROBID_CONSOLIDATE=0` でオフ、デフォルトはオン）。
- `generateIDs=1` を試し、`head`/`div` 要素に付与される `xml:id` が
  03-eのTOCアンカーとして安定して使えるか確認する。使えるなら
  03-eで自前ID生成ロジックを書く必要がなくなる。

### テスト

- `grobid_client.py` の単体テスト（httpxのモック）で、送信POSTデータに
  想定のパラメータが含まれることを検証。
- 実データでの効果測定（consolidate有無でのタイトル/著者/DOI取得率の
  比較）は、課題02のDocker環境が整ってから行う。

## 03-a: 論文名・著者・要旨の抽出

### 現状（実データで確認済み）

`_guess_title` (`pipeline.py:92`) は本文中の最初の見出し、なければ最初の段落の
先頭80文字を「タイトル」として使っている。実際に処理済みの3論文で確認したところ:

- `"Introduction"` （本文の最初の見出しを拾っただけ）
- `"INTRODUCTION"` （同上）
- `"arXiv:2010.05234v3 [cs.LG] 25 Dec 2021"` （PDF余白のスタンプ文字列を
  誤って本文の先頭段落として拾ってしまった結果）

3件とも本来のタイトルが一切表示されていない。著者情報は現状どこにも存在しない。

### 修正方針

- GROBID TEI の `teiHeader/fileDesc/titleStmt/title[@level='a' or @type='main']`
  からタイトルを取得する。
- `teiHeader/fileDesc/sourceDesc/biblStruct/analytic/author/persName` から
  著者リストを取得する（`forename`+`surname` を結合）。
- `teiHeader/profileDesc/abstract` から要旨を取得し、`PaperContent` に
  新フィールドとして持たせ、読書ビューの本文冒頭（見出しの直下）に表示する。
- `models.py` に `title` (既存流用), `authors: list[str]`, `abstract: str | None`
  を `PaperContent`/`NormalizedDocument` へ追加。
- `teiHeader` にタイトルが無い/空の場合のみ、既存の `_guess_title` ヒューリスティック
  にフォールバックする（現状のロジックは「保険」として残す）。
- テンプレート `paper.html` の `<header>` に著者行・要旨ブロックを追加。
- 前提として03-g（`consolidateHeader`）を先に入れておくと、
  `teiHeader` 自体の精度（著者名の表記揺れ補正など）がGROBID側で
  上がった状態でこの項目に着手できる。

### テスト

- `tests/test_tei_parse.py` に `teiHeader` を含むフィクスチャを追加し、
  title/authors/abstract が正しく取れることを検証。
- teiHeader が欠落しているケース（既存フィクスチャ相当）で従来のフォールバックが
  維持されることも検証。

## 03-b: 画像とキャプション不一致の原因調査・修正

### 現状（実データで確認済み・最重要バグ）

処理済みのある論文（学位論文、61図表）を検証した結果、**キャプションの重複が
大量発生**していた: 61個の図表に対し重複除去後わずか47種類しかキャプションが
存在せず、同一キャプションが11回・4回・2回と使い回されているケースがあった。
つまり大半の図に「別の図のキャプション」が誤って貼られている。

### 原因分析（当初案は撤回・要調査に変更）

当初この節では「GROBIDが画像とキャプションを別々の`<figure>`要素として
出力しており、それを自前でマージする必要がある」と分析していたが、これは
検証なしの推測だった。GROBID公式ドキュメント・実出力例を確認したところ、
実際のGROBID出力は次のように **1つの`<figure>`要素の中に head/label/
figDesc/graphicがすべて収まる構造** であり、画像とキャプションが別要素に
分裂することは無いと分かった:

```xml
<figure xml:id="fig_1">
  <head>Figure 1 :</head>
  <label>1</label>
  <figDesc>Figure 1: Network-based analysis of omic data...</figDesc>
  <graphic url="..." coords="12,72.00,178.57,319.30,504.00" type="bitmap" />
</figure>
```

つまり「2要素をマージするロジック」を自作するのはGROBIDが既にやっている
ことの車輪の再発明であり、根本的に不要かつ的外れな設計だった。**この構造
自体は現状のコード・既存テストの前提（1要素に全部乗っている）と一致して
いる。** よって実際のバグは別の場所にある。実データ（`content.json`。
生のTEI XMLはこれまで保存していないため未確認）だけから分かっている
範囲では、以下の3つの仮説が残っており、**どれが正しいかは実際の生TEI
XMLを見るまで確定できない**:

1. **coordsの付与位置のズレ**: 上記の実例では `coords` は `<figure>`
   自身ではなく子要素 `<graphic>` に付いている。一方 `_crop_image`
   (`tei_parse.py:131`) は `elem.get("coords")` で `<figure>` 自身の
   属性しか見ていない。この現在のプロジェクトが使っている
   `teiCoordinates=figure` パラメータの場合に実際どちらに`coords`が
   付くのかは、GROBIDのバージョンやパラメータの組み合わせによって
   変わる可能性があり、要検証（`<figure>`側にも付くなら現状で動く。
   だからこそ大半の図で画像自体は取得できていたと考えられる）。
2. **GROBID自身の図表分割・キャプション対応の誤り**: 複数パネルから
   なる図（(a)(b)(c)のような合成図）を、GROBID自身が複数の別々の
   `<figure>`要素として検出しつつ、同じキャプション文を全パネルに
   重複して割り当てている可能性がある。これはGROBIDのモデル自体の
   既知の精度限界であり、クライアント側で直すべきはマージロジックの
   自作ではなく「隣接する`<figure>`が全く同じ`figDesc`を持つ場合は
   同一の論理図として1つにまとめる」程度の軽いデデュープに留めるべき。
3. **自前コードのバグ**: `figure_counter`やcoords解析(`_parse_coords`)側に、
   複数の要素で同じ値を使い回してしまう単純な実装バグがある可能性。

### 修正方針

- **まず実データを見られるようにする**: `pipeline.py`の`_run_pipeline`で
  GROBIDから受け取った生のTEI XMLを `data/papers/<id>/tei.xml` として
  保存する（デバッグ用途。数KB〜数十KB程度でコスト無視できる）。これは
  今後同種の「本当にGROBIDがこう返しているのか」を推測でなく確認しながら
  直すために必須の下準備であり、他の項目（03-c, 03-f）の検証にも使う。
- 課題02のDocker環境を使って実際に論文を1本処理し、保存された生TEIで
  上記1〜3のどれが実際に起きているかを特定してから、対応するピンポイントの
  修正を入れる（座標参照先の修正 / 隣接デデュープ / 自前バグ修正、のうち
  実際に該当するもの）。原因が確定するまで、的外れな大規模ロジックは書かない。

### テスト

- 原因が確定した時点で、実際に観測された構造を再現する最小フィクスチャを
  `tests/test_tei_parse.py` に追加し、回帰テストとする（フィクスチャの内容は
  調査結果次第で決める）。

### 実装した内容（2026-07-03、ライブGROBID未検証の最善努力）

この環境にはDockerが無く、生TEIを実際に取得して1〜3のどれが真因かを
確定させることができなかった。そのため以下を実装した:

- **生TEI保存（下準備）**: `storage.tei_xml_path(paper_id)` を追加し、
  `pipeline.py`が`data/papers/<id>/tei.xml`にGROBIDの生レスポンスを保存する
  ようにした。次に実際のGROBIDで処理した際、ここに保存された生TEIを見れば
  仮説1〜3のどれが正しいか確認できる。
- **仮説1（coordsの付与位置）への対応**: `_figure_coords()`を新設し、
  `<figure>`自身に`coords`が無ければ子要素`<graphic coords="...">`を見るように
  した。どちらのパターンでも動くようになったため、実際にどちらだったかを
  確定させる必要自体を無くす、後方互換的な直し方にした。
- **仮説2（GROBID自身の複数パネル誤割当）への対応**: `_cluster_adjacent_duplicate_figures()`
  を新設。文書順で隣接し、`figDesc`が完全一致する`<figure>`要素の並びを
  1つの論理的な図とみなし、各要素の座標を統合（union）してクロップ、
  キャプションは1つだけ採用するようにした。captionが空の場合はマージしない
  （無関係な図同士を誤って統合しないため）。
- **仮説3（自前のバグ）**: 上記2つの修正の過程でコードを読み直したが、
  `figure_counter`や`_parse_coords`自体に値の使い回しバグは見つからなかった。
  今回のオフラインフィクスチャでは仮説1のみを再現できたため、これが実データの
  主要因かどうかは未確定のまま。

**検証**: `tests/fixtures/sample_fulltext.tei.xml`（coordsが`<graphic>`側に
ある構造）で、仮説1の修正により図が正しく1件抽出されることを確認
（`tests/test_pipeline_golden_fixture.py::test_figure_extracted_when_coords_is_on_graphic_child`）。
`tests/test_tei_parse.py`に隣接重複キャプションのマージ・非マージのユニット
テストも追加。ただしこれらはすべてオフラインの手作りフィクスチャによる検証で、
実際にこの環境で処理された過去の論文（`data/papers/*/`）の重複キャプション
バグが今回の修正で実際に解消するかどうかは、**ライブGROBIDでの再処理による
確認が別途必要**（課題02のDocker環境が使える場所で、ユーザー自身の実行を
推奨）。
- 既存の「1要素に全部乗っている」ケースは正しい前提だったので、そのまま
  回帰テストとして維持する。

## 03-c: 引用 `[i]` の参考文献リンク化

### 現状（実データで確認済み）

ある論文で本文中に `[80]` のような引用が **187箇所** プレーンテキストのまま
存在することを確認。GROBIDはこれを `<ref type="bibr" target="#bX">[80]</ref>`
として意味づけ済みで返しているはずだが、`_clean_text` が全要素を無差別に
テキストへフラット化する際にこの構造情報ごと捨てている。参考文献リスト
（`text/back` 内の `listBibl`）も現状一切パースされていない。

### 修正方針

- 前提として03-gの `consolidateCitations=1` を先に有効化しておく。
  これによりGROBIDが参考文献エントリにDOIを外部照合で埋めてくれる
  可能性が上がり、「引用先URLをどう決めるか」の大部分をGROBID自身に
  肩代わりさせられる（自前でDOI解決APIを叩くようなロジックは書かない）。
- `text/back//listBibl/biblStruct[@xml:id]` をパースし、`BibliographyEntry`
  （id, 表示ラベル, 著者, タイトル, 年, DOI/URL）のリストを作る
  （`models.py` に新規dataclass追加、`NormalizedDocument`/`PaperContent` に
  `bibliography: list[BibliographyEntry]` を追加）。DOIは
  `biblStruct//idno[@type='DOI']` から取得する。
- `_clean_text` で `<ref type="bibr" target="#bX">` に遭遇した際、通常の
  テキストフラット化ではなく、レンダリング時に安全に置換できる**プレースホルダ
  トークン**（例: 制御文字を使った `\x00CITE:bX\x00[80]\x00/CITE\x00` のような、
  実文書に絶対出現しない記号列）を埋め込む。プレースホルダを使う理由は、
  `ContentUnit.text` はプレーン文字列のままにしたい（グロッサリ機構と同じ
  「パース時はプレーンテキスト、レンダー時にHTML化」という既存の設計方針
  (`rendering.py`) を壊さないため。
- `rendering.py` の `render_units`/`_build_annotator` を拡張し、
  `html.escape` 後・グロッサリ置換後に、このプレースホルダを `<a class="citation"
  href="...">` に変換する。リンク先は、対応する `BibliographyEntry` が
  DOI/URLを持てばそれを直接指す外部リンク、無ければ参考文献パネル内の
  該当エントリへのページ内アンカー (`#bib-bX`) にする。
- テンプレートに「参考文献」パネルを新設（課題01で作る図表パネルの独立
  スクロール枠と同じ設計を流用できる）。

### テスト

- `tests/test_tei_parse.py`: `<ref type="bibr">` と `listBibl` を含む
  フィクスチャで、プレースホルダ埋め込みと `BibliographyEntry` 抽出を検証。
- `rendering.py` 用の新規テスト: プレースホルダ→`<a>`変換、
  グロッサリ置換との共存（順序が事故らないこと）を検証。

### 実装した内容（2026-07-03）

計画通り実装した。実装時に気づいた点・計画からの補足:

- **配置場所の設計判断（計画時点で未確定だった部分）**: 参考文献パネルを
  独立した3カラム目にはせず、**01で作った`.figures-panel`（独立スクロール
  枠）に図表と同居させる**設計にした。理由: TOC（03-e）の検討時に
  「3カラムは窮屈になる」という判断をしたのと同じ理由に加え、参考文献への
  ジャンプも「本文のスクロール位置を動かしたくない」という01と同じ要件を
  持つため、01で作った独立スクロール＋減光の仕組みをそのまま流用するのが
  最も一貫性がある。`.figure-card`と参考文献の`<li>`に共通の`.panel-item`
  クラスを導入し、減光/ハイライトCSSを一本化した。
- **モバイル対応（計画時点で未検討だった問題）**: `.figures-panel`は
  モバイルで`display: none`（01の仕様）になるため、参考文献をこのパネルの
  中にしか置かないと**モバイルで参考文献が一切見られなくなる**ことに実装中に
  気づいた。対応として、`.bibliography-mobile`という別セクションを
  記事末尾に追加し、デスクトップでは非表示・モバイルでは表示という
  CSSメディアクエリで切り替えるようにした（Jinjaマクロ`bib_entry()`で
  HTML生成を共通化し、二重管理を避けた）。モバイルの引用リンクはJSで
  横取りせず、ブラウザ標準のページ内アンカーで参考文献セクションまで
  ジャンプする（図表のような「独立スクロール」の概念がモバイルには元々
  無いため、素直なジャンプで十分と判断）。
- **グロッサリ抽出への副作用（実装中に発見・修正）**: プレースホルダの
  生バイト列`\x00CITE:b0\x00[1]\x00/CITE\x00`には単語境界付きの
  リテラル"CITE"が2箇所含まれるため、`pipeline.py`の`full_text`
  （語彙抽出・単語数カウントの入力）をプレースホルダのまま渡すと、
  論文中の引用数だけ"CITE"が出現し、頻出語として誤って語彙候補に
  混入してしまうことに実装中に気づいた。`full_text`組み立て時に
  `CITATION_PLACEHOLDER_RE.sub(r"\2", text)`でプレースホルダをラベル
  （例:"[1]"）に戻してから結合するよう修正した（`ContentUnit.text`自体は
  プレースホルダのまま保持し、`content.json`・レンダリングには影響しない）。
  同じ理由で`_guess_title`のフォールバック処理にも同様の保護を入れた。
- DOIが取れた参考文献は外部リンク（`https://doi.org/...`）、取れなかった
  ものはパネル内のページ内アンカー（`#bib-bX`）にフォールバックする設計を
  そのまま実装。

### 検証状況

- オフラインで検証済み（`pytest`、ゴールデンフィクスチャに`biblStruct`
  2件・引用2箇所を含めて検証）: プレースホルダ埋め込み、参考文献抽出
  （著者・タイトル・年・DOI）、DOIありは外部リンク・DOIなしはページ内
  アンカーになること、グロッサリへの"CITE"混入が起きないこと、旧形式
  （`bibliography`キー無し）の`content.json`でも壊れずに描画されること。
- 実サーバーで、本セッション以前の実データ3件全てに対して200 OK・
  クラッシュ無しで描画されることを確認。
- 未検証（要ブラウザ目視確認、01と同じ制約）: デスクトップでの引用クリック
  →パネル内スクロール・ハイライトという**インタラクティブな挙動そのもの**。

## 03-d: 見出しレベルを div ネスト深さから取得

### 現状

`_walk_body` (`tei_parse.py:63`) は `<div>` のネストを再帰的に平坦化して
`head`/`p`/`figure` を1本の列に yield しているが、その際ネスト深さの情報を
捨てている。そのため `_infer_level` (`tei_parse.py:94`) は見出し**テキスト**の
番号付け（`"1.2.3"` など）だけを頼りに階層を推測しており、"Abstract"や
"Conclusion"のように番号が付かない見出しは実際のネスト深さに関わらず
常に level 1 扱いになる。

### 修正方針・実装した内容（2026-07-03、実装時に当初方針を訂正）

当初「ネスト深さを第一情報源、番号付けテキストを補助に格下げする」と
書いたが、実装時に既存テスト(`test_heading_level_inferred_from_numbering`)を
壊すことに気づき、これは誤りだったと判明した。理由: GROBIDのdivは
「通常フラット」（`tei_parse.py`のモジュールdocstring自身がそう明記している）
なので、"1 Introduction"/"1.2.3 Deep subsection"/"Abstract"が3つとも
**同じ深さの兄弟div**として出てくるケースの方が実際には多い。この場合に
深さを第一情報源にすると、番号付けから本来level 3と分かる見出しまで
一律level 1に潰れてしまい、既存の（正しい）挙動を退行させてしまう。

よって実装は以下の優先順位に訂正した:

1. 見出しテキストに`"1.2.3"`のような番号付けがあれば、それを最優先で使う
   （flatなdiv構造でも正しく階層を判定できる、既存の実績ある方法）。
2. 番号付けが無い見出し（"Abstract"・"Related Work"等）の場合のみ、
   divネスト深さにフォールバックする（今までは無条件でlevel 1固定だった）。

`_walk_body`が`(depth, element)`のタプルを返すように変更し、
`_infer_level(text, nesting_depth)`が上記の優先順位で判定する。

### テスト

- 番号なし見出しがネストしている場合に深さから正しいlevelが出ることを検証
  (`test_unnumbered_heading_level_falls_back_to_div_nesting_depth`)。
- **回帰ガード**: フラットな兄弟div構造で番号付き見出しのlevelが深さに
  引きずられず正しいまま (1/3/1) であることを検証
  (`test_numbering_text_still_wins_over_depth_for_flat_divs`)。
- ゴールデンフィクスチャで"Related Work"（"1 Introduction"の下にネスト、
  番号なし）がlevel 2になることを確認
  (`test_pipeline_golden_fixture.py::test_nested_unnumbered_heading_level_is_correct`)。

## 03-e: Table of Contents 抽出とUI組み込み

03-dで見出しレベルが正確になった前提で実施する。

### 修正方針

- 各見出し `ContentUnit` にレンダー時 `id`（例: `heading-{n}`）を付与
  （現状 `paper.html` の見出しには `id` が一切無く、ジャンプ先にできない）。
- 見出し一覧から `{level, text, anchor_id}` のTOC構造を組み立て、
  読書ビューの先頭付近に折りたたみ式のナビゲーションとして表示する
  （デスクトップでもう1カラム追加するのではなく、本文カラム上部の
  ドロップダウン/ドロワーとして実装するのを既定案とする。図表カラムと
  横並びで3カラムにすると窮屈になるため。UIの詳細配置は実装時に画面で
  見ながら微調整する前提）。

### 保留事項

- TOCを図表パネルと統合したタブUI（「目次 / 図表」切り替え）にするかは
  好みの分かれる部分なので、実装時に両案を試して選ぶ。

### 実装した内容（2026-07-03、タブUI案は不採用）

「両案を試して選ぶ」としていたが、この環境にはブラウザ自動化ツールが無く
見た目を比較検証できないため、**JS実装が要らない・失敗しにくいネイティブな
方式**を選んだ: `<details class="toc"><summary>目次</summary>...</details>`
というブラウザ標準の開閉ウィジェット。タブUI（図表パネルと統合）は
カスタムJSでの表示切り替えが必要になり、この環境で動作を確認できないまま
実装することになるため見送った。

- `rendering.render_units()`が見出しユニットに`anchor_id`（例:
  `"heading-3"`）を付与するようにした。同じ関数内で連番を振っているため、
  本文側の見出し`id`属性とTOCのリンク先が必ず一致する（別々の場所で
  連番を振ると簡単にズレるため、1箇所にまとめた）。
- `rendering.table_of_contents(rendered_units)`を新設し、`main.py`から
  `toc_entries`としてテンプレートに渡した。
- TOCリンクは通常のページ内アンカー（`href="#heading-N"`）。本文カラムは
  （図表カラムと違って）ページの通常スクロールのままなので、ブラウザ標準の
  アンカージャンプで問題ない（JSでのスクロール制御は不要）。

### 検証状況

- オフラインで検証済み（`pytest`）: ゴールデンフィクスチャの3見出し
  （"1 Introduction"=level1, "Related Work"=level2, "2 Method"=level1）が
  正しいレベル・一致するanchor_idでTOCと本文の両方に出ることを確認
  （03-dの見出しレベル修正と組み合わさって正しく動くことも含めて検証）。
  見出しが無い文書ではTOC自体が描画されないことも確認。
- 実サーバーで、本セッション以前の実データ2件に対して200 OK・TOCが描画
  されることを確認（後方互換性チェック）。
- 未検証: `<details>`の開閉自体はブラウザ標準機能でJS不要なため、他の
  項目ほど目視確認の優先度は高くないと判断した。

## 03-f: Unicode記号の文字化け疑い（新規発見・要調査）

### 現状（実データで発見）

ある論文の本文中に `"the humanhand"`（本来 "human hand" の2語だがスペース
欠落）、`"saidjoints"`（同様）、および `�e...�f` という置換文字（U+FFFD相当の
文字化け、おそらく本来は `“ ”` のようなカーブクォート）が確認された。
これは課題として挙げられた「文字自体のparseが出来ない不具合」の修正後にも
残っている別種の不具合の可能性がある。

### 調査結果（2026-07-03、ライブGROBID無しで判明した範囲）

ライブGROBIDは使えなかったが、当該論文の**元PDFファイル自体が
`data/papers/4a3a50ccc362/original.pdf`としてこの環境に既に存在していた**
ため、PyMuPDFで直接テキスト抽出して切り分けることができた。

**`�e`...`�f`（"文字化け"に見えていたもの）についての結論: バグではなかった。**
実際の文字コードを1文字ずつ確認したところ、正体は `U+2018`
(LEFT SINGLE QUOTATION MARK, `'`) と `U+2019`
(RIGHT SINGLE QUOTATION MARK, `'`) という**正当なUnicode文字**だった
（`'Hands from Synthetic Data'`という、カーブクォートで囲まれた
データセット名）。これは以下の3箇所すべてで確認した:

1. 元PDFファイルからPyMuPDFで直接抽出したテキスト（GROBIDを一切経由しない）
2. `data/papers/4a3a50ccc362/content.json`に保存されているテキスト
   （`0x2018`のコードポイントとして正しく保存されている）
3. 実際にサーバーを起動し、`/papers/4a3a50ccc362`のHTTPレスポンスの生バイト列
   （`\xe2\x80\x98`、これは`U+2018`の正しいUTF-8エンコーディング）

つまり**アプリのデータパイプラインは終始正しくUnicodeを扱えていた**。
「文字化け」に見えたのは、この環境のターミナル（Windowsコンソールの
文字コードページ）が`U+2018`/`U+2019`を正しく表示できず、代替表示に
置き換えていただけだった。実際にブラウザで開けば（HTMLの
`<meta charset="utf-8">`が既に正しく設定されているため）正しく
`'Hands from Synthetic Data'`と表示されるはずである。**当アプリの
コードを修正する必要は無いと判断し、クローズする。**

**`"the humanhand"`/`"saidjoints"`（スペース欠落）についての結論: 未解決、
部分的な手がかりのみ判明。** 同じ箇所を元PDFから直接抽出すると
`'human\nhand'`・`'said\njoints'`のように、単語間に**改行文字はあるが
スペースが無い**状態だった。これは元PDFの図キャプション内でこの2語が
改行によって分割されているためで、GROBIDがこの図キャプション
（`<figDesc>`）のXML出力で`<lb/>`相当のマーカーを本文`<p>`と同じように
挿入してくれるかどうかが未確認のまま残っている。本文`<p>`側は既に
`<lb/>`を明示的なスペースとして扱う修正が入っている
（`tei_parse.py`の`_clean_text`）ため、`<figDesc>`でも同じマーカーが
出ていれば既存コードで自動的に解決するはずだが、`<figDesc>`側で
マーカーの出方が異なる可能性も残っている。**ライブGROBIDでこの元PDF
（`data/papers/4a3a50ccc362/original.pdf`）を再処理し、生成される
`tei.xml`（03-bで追加した保存機能）の該当`<figDesc>`を見れば即座に
判明する**が、この環境では確認できないため、ユーザー側でDocker環境が
整った際に再処理して確認することを推奨する。当てずっぽうの修正はしない
という方針を維持し、今回はコード変更を行わなかった。

## 全体の設計原則

「GROBIDが構造化・補完までしてくれる部分は自前で再実装しない」を徹底する。
具体的には:

- リクエストパラメータ（`consolidateHeader`/`consolidateCitations`/
  `generateIDs`/`teiCoordinates`等）で解決できることは、まずパラメータで
  解決する（03-g）。
- TEIの構造（`teiHeader`/`back`/`div`ネスト等）が既に答えを持っている場合は
  それを読む。自前のヒューリスティック（正規表現でのタイトル推測、
  テキストからの見出しレベル推測等）は、GROBIDの構造情報が取れない場合の
  フォールバックとしてのみ残す。
- GROBID自身の出力にモデル精度起因の誤り（複数パネル図のキャプション誤割当
  など）が残る場合は、それを丸ごと直そうとせず、実害を抑える軽いデデュープ/
  防御的処理に留める。
- 未検証の推測だけでロジックを設計しない。本ドキュメントの03-bで一度それを
  やって撤回した反省を踏まえ、以後は生TEI XMLを保存して実データで裏取りして
  から設計する（03-bの「生TEI保存」施策を参照）。

## 全体の検証方法

- 課題02（Docker一本化）の完了後、実際にGROBIDを起動して複数の実論文を処理し、
  保存された生TEI XML（03-bで追加する `tei.xml`）を見ながら本ドキュメントの
  各項目を実データで確認しつつ実装する（現状のdata/配下の古い処理結果は、
  コード修正前・生TEI無しの出力なので参考程度に留める）。

## 参考にした情報源

- [GROBID: Understanding the output (TEI)](https://grobid.readthedocs.io/en/latest/TEI-encoding-of-results/)
- [GROBID: Using the REST API](https://grobid.readthedocs.io/en/latest/Grobid-service/) — `consolidateHeader`/`consolidateCitations`/`generateIDs`/`teiCoordinates`パラメータの仕様
- [GROBID: Frequently asked questions](https://github.com/kermitt2/grobid/blob/master/doc/Frequently-asked-questions.md) — `processFulltextAssetDocument`が非推奨である旨
- 実際の`<figure>`要素構造の例（`<graphic coords="...">`が子要素として付く1要素構造であることの確認）
