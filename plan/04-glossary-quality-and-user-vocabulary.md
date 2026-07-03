# 課題04: 頻出語彙抽出の質と、利用者ごとの既知語彙の扱い

対象ファイル: `app/glossary/heuristic.py`, `app/glossary/base.py`, `app/db.py`,
`app/main.py`, `app/pipeline.py`, `app/rendering.py`, `app/templates/paper.html`,
`app/static/reader.js`, `app/static/styles.css`（新規: `app/glossary/dictionaries/common_english_words.txt` 等）

## ユーザーの指摘の整理

1. 英語の頻出（一般）語彙は知ってて当然なので、glossaryに含めない。
2. 業界の頻出用語は、利用者が既に知っている場合は出さなくてよい。
   自動判定は無理なので、**手動でopt-outできる仕組み**にする。
3. 頻出だが未定義（定義もbundled辞書もヒットしない）語彙は、放置せず
   **本文を読む前に利用者自身に調べさせる**導線を作る。タイトルと本文の
   間の新しいカラム（セクション）として提示する案。
4. 3で利用者が調べた（＝既知になった）語彙は保存し、**以後のどの論文でも
   二度と聞かないようにする**。

2と4は実質「同じ永続ストア」で解決できる（後述）。

## 実データで確認した現状の問題（追加で発見したものを含む）

処理済みのある論文の `content.json` を確認したところ:

```
concordance | GNN         | (定義なし)
concordance | GNNs        | (定義なし)   ← GNNと別カウントされ重複
concordance | Practical Tutorial | (定義なし)
concordance | Ward        | (定義なし)   ← 参考文献リストの著者姓
concordance | Joyner      | (定義なし)   ← 同上
concordance | Lickfold    | (定義なし)   ← 同上
concordance | Rowe        | (定義なし)   ← 同上
concordance | Guo         | (定義なし)   ← 同上
concordance | CoRR        | (定義なし)   ← 論文誌の略称（プレプリントサーバ名）
concordance | Various     | (定義なし)   ← ただの一般英単語
concordance | Proceedings | (定義なし)   ← 論文集を指す一般語
concordance | IEEE        | (定義なし)   ← 学会名。ドメイン知識というより固有名詞
concordance | Graphs      | (定義なし)   ← ただの一般英単語
```

ユーザーが指摘した「一般英語」「業界用語の要不要」「未定義語の放置」に加え、
以下2点も実データから確認できた:

- **参考文献リストのノイズ混入**: `Ward`/`Joyner`/`Lickfold`/`Rowe`/`Guo`/`CoRR`は
  いずれも参考文献リストの著者名・誌名で、読者が調べるべき「専門用語」ではない。
  これは課題03-c（参考文献のTEI構造化）が入れば `text/back` が本文から
  正しく分離され、多くはこの問題ごと解消する見込みだが、GROBID自身が
  本文/後注を誤分類するケースも残り得るため、glossary側にも軽い防御線を
  入れておく（後述04-e）。
- **単複表記のゆれで同じ語が重複カウントされる**: `GNN`と`GNNs`が別エントリに
  なっている。ユーザーへの表示上も無駄だが、後述の「既知語彙」照合キーにも
  影響するため、正規化を1箇所で共通化しておく必要がある（後述04-f）。

## 優先順位

| ID | 内容 | 優先度 |
|---|---|---|
| 04-a | 一般英単語のフィルタリング | P1 |
| 04-b | 永続的な「既知語彙」ストア（opt-out + 予習カラムからの確定、共通基盤） | P1 |
| 04-c | 「読む前に確認」カラムの新設（頻出・未定義語彙） | P1 |
| 04-g | 見出し直後の本文定義が検出されない回帰（新規発見・オフライン検証で実測） | **P1** |
| 04-e | 参考文献リストのノイズ混入への防御（新規発見） | P2（03-cと連動） |
| 04-f | 表記ゆれ（単複等）の正規化統一（新規発見） | P2 |

## 04-g: 見出し直後の本文定義が検出されない回帰（新規発見）

### 現状（オフライン検証で実測済み。`tests/test_pipeline_golden_fixture.py`参照）

`pipeline.py`の`full_text = " ".join(u.text for u in normalized.units if u.kind in
("heading", "paragraph"))`は見出しと段落をただの半角スペースで連結するため、
「見出しの直後の文がその場でアクロニムを定義している」という、論文で
非常によくあるパターン（例:「1 Introduction\nGraph Neural Network (GNN)
models have become...」）で、見出しテキストが定義文の直前に文の区切りなく
くっついてしまう。

`heuristic.py`の`_DEFINITION_RE`は「大文字始まりの単語が連続して`(XXX)`に
続く」パターンを最大6語まで貪欲にマッチするため、見出し末尾の単語
（上記例では"Introduction"）まで定義フレーズに巻き込んでしまい、
`_initials("Introduction Graph Neural Network")` = `"IGNN"` が
アクロニム`"GNN"`と一致せず、**マッチごと静かに捨てられる**。

実際にオフラインのゴールデンフィクスチャ(`tests/fixtures/sample_fulltext.tei.xml`)
で実測したところ、"Graph Neural Network (GNN)"という教科書的に理想的な
定義文があるにもかかわらず、直前に見出し"1 Introduction"があるだけで
glossaryに一切出てこないことを確認した。`heuristic.py`のdocstringが
「in-text定義は最も信頼できるシグナルで、常に#2（concordance）より優先する」
と明言している、まさにその最重要シグナルが、見出し直後という頻出レイアウトで
静かに壊れているため、実害は大きいと判断しP1とした。

### 修正方針・実装した内容（2026-07-03）

`pipeline.py`側で直した。改行(`\n`)ではなく **ピリオド+スペース(`". "`)** で
`full_text`を組み立てるように変更（`" ".join(...)` → `". ".join(...)`）。

改行ではダメな理由: `_DEFINITION_RE`/`_CANDIDATE_RE`はいずれも`\s`
（空白文字クラス）を使っており、`\s`は改行にもマッチするため、区切り文字を
改行に変えるだけでは貪欲マッチは何も変わらず素通りしてしまう。ピリオドの
ような非空白文字を挟んで初めて、大文字始まりの単語が連続するという
regexの前提条件が崩れ、見出し側の単語を定義フレーズに巻き込まなくなる。

heuristic.py側（見出し行をまたいだマッチを禁止する案）ではなく
pipeline.py側で直した理由: `heuristic.py`の`extract()`は1本のフラット文字列
しか受け取らず、どこが見出しでどこが段落かという単位境界の情報を持たない
（そもそも持たせる設計にすると`GlossaryExtractor`のインターフェースを
変える必要があり、LLM版実装(`llm.py`)にも影響する）。単位境界の情報を
知っているのはpipeline.py側なので、そこで境界を保存する形にした。

### テスト

- `tests/test_glossary_heuristic.py::test_definition_immediately_after_heading_without_punctuation_is_missed`
  — heuristic.py単体でこの正規表現の脆さ自体を再現・固定（区切りが無いと
  検出されない／ピリオドを挟むと検出される、の両方を確認）。
- `tests/test_pipeline_golden_fixture.py::test_in_text_definition_immediately_after_heading_is_detected`
  — パイプライン全体でGNNが`in_text_definition`として検出されることを確認。

## 04-a: 一般英単語のフィルタリング

### 方針

- 頻出候補語のうち **単語1語だけの候補** が一般英単語である場合は除外する。
  複数語からなる候補（例: "Random Forest", "Neural Network", "Gradient
  Descent"）は、個々の単語が一般語であっても組み合わせ自体が専門用語になる
  ため対象外とする（単語ごとにフィルタすると価値のある複合語まで消えてしまう）。
### 実装した内容（2026-07-03、リスト調達方法を計画から変更）

`app/glossary/dictionaries/common_english_words.txt`を新規追加した。

**当初案からの変更点**: 当初は`google-10000-english`系の頻出英単語リストを
そのまま同梱する想定だったが、実装時にライセンス条文を確認したところ
（[first20hours/google-10000-english](https://github.com/first20hours/google-10000-english)
のLICENSE.md）、LDCライセンス＋部分的MIT＋fair useの組み合わせで
「個人・研究利用は許可、商用利用は非推奨」という条件付きだった。本アプリ
自体は個人用途で問題ないが、リポジトリを自由に公開・共有する前提と
相性が悪いと判断し、**サードパーティ配布物をそのまま同梱するのは避けた**。
代わりに、一般的な英語語彙知識から独自に約450語（機能語＋汎用的な
名詞・動詞・形容詞）を手作業でリストアップし、ライセンス上の懸念が
一切ない形にした。より精度の高い頻度判定が必要になった場合の代替案
として`wordfreq`（MIT、purely-Python＋同梱データ）も検討可能だが、
今回は静的リストで十分と判断した。

- `heuristic.py` の `_frequent_candidates` に、既存の `_STRUCTURAL_WORDS`
  チェックと同じ位置で「単語1語かつ一般英単語」の候補を弾く分岐を追加した。

### テスト

- `test_common_single_word_is_excluded_even_when_frequent` — 単語1語の
  一般語候補（"Various"）が弾かれることを確認。
- `test_multiword_phrase_of_common_words_is_not_excluded` — 複数語の専門用語
  候補（"Random Forest"）は個々の単語が一般語でも残ることを確認。

## 04-b: 永続的な「既知語彙」ストア

ユーザー指摘の2と4は同じ仕組みで解決する: **「この語はもう知っている」という
利用者の意思表示を、論文をまたいで永続化し、以後のどの論文でもその語を
glossaryに出さない。**

### データ設計

- `db.py` に新テーブルを追加:
  ```sql
  CREATE TABLE IF NOT EXISTS known_terms (
      term_key TEXT PRIMARY KEY,   -- 正規化キー（小文字化・末尾s除去。04-f参照）
      display_term TEXT NOT NULL,  -- 最後に見た表記（表示用、参考程度）
      marked_at TEXT NOT NULL
  )
  ```
- 正規化キー生成関数は04-fで作る共通関数を使う（`heuristic.py`の重複排除と
  同じロジックを再利用し、実装を2箇所に分散させない）。

### フィルタのタイミングは「表示時」にする（パイプライン時ではなく）

- `content.json` にはこれまで通り抽出した全glossaryエントリをそのまま保存する
  （パイプライン処理自体は既知語彙の状態に依存させない）。
- 既知語彙による除外は **読書ビュー表示時**（`main.py`のペーパー表示ルート、
  もしくは`rendering.py`）に、`known_terms`テーブルと突き合わせて行う。
- 理由: パイプライン時に確定させてしまうと、「後から既知語彙に追加した語」が
  過去に処理済みの論文には反映されない。表示時フィルタにすれば、既知語彙を
  1つ追加した瞬間、過去分も含め全論文でその語が二度と出てこなくなる
  （ユーザーの「今後また重複して聞かないように」という要望に一番忠実）。

### UI / エンドポイント

- 新規エンドポイント: `POST /glossary/known-terms` （body: `{"term": "..."}"`）
  で `known_terms` に追加。
- `reader.js` の glossary ポップオーバー（`.glossary-popover`）に「知っている
  （今後表示しない）」ボタンを追加し、押すと上記エンドポイントを叩いて
  ポップオーバーを閉じ、該当の `.gloss` スパンをその場でプレーンテキスト化する
  （リロードしなくても消えるように）。
- 04-c（予習カラム）の各語にも同じ「知っている／調べた」ボタンを置き、
  同じエンドポイントを叩く。

### 保留事項

- 既知語彙を後から取り消す（間違えて押した場合の取り消しUI）は今回スコープ外。
  必要なら「既知語彙の管理」設定ページを別途起こす。

### 実装した内容（2026-07-03）

計画通りに実装した。`db.py`に`known_terms`テーブル・`mark_term_known()`・
`known_term_keys()`を追加（`is_term_known`単体の関数は作らず、呼び出し側
`rendering.filter_known_terms()`が集合演算で判定する設計にした。個別に
1件ずつ問い合わせるより、表示時に1回`known_term_keys()`で全件取得して
集合で除外する方がクエリ回数が少なく単純）。`main.py`に
`POST /glossary/known-terms`（JSON body `{"term": "..."}"`、`Body(embed=True)`）
を追加。`read_paper`ルートで`content.json`から読んだglossaryを
`rendering.filter_known_terms()`で既知語彙除外してから`render_units`に渡す
設計にし、計画通り表示時フィルタとした。`reader.js`のポップオーバーに
「知っている（今後表示しない）」ボタンを追加し、押すと即座に本文中の
該当`.gloss`スパンをプレーンテキスト化する（リロード不要）。

`app/db.py`が`app/glossary/base.py`の`normalize_term_key`に依存する形になった
（04-fの正規化キーをそのまま再利用）。循環importが無いことを確認済み
（`glossary/base.py`は`app.models`のみに依存し`app.db`には依存しない）。

### テスト

- `tests/test_known_terms.py` — `mark_term_known`/`known_term_keys`の単体
  テスト、単複バリアントが同じキーに正規化されること、同じ語を2回登録しても
  重複しないこと、`rendering.filter_known_terms`の単体テスト。
- `tests/test_paper_view_route.py::test_marking_term_known_hides_it_from_this_and_future_papers`
  — **ユーザー要件の核心を直接検証**: (1) 既に処理済みの論文からリロード無しで
  即座に消える、(2) 既知語彙登録後に処理した別の論文でも最初から出てこない
  （論文をまたいだ抑制が実際に機能することをエンドツーエンドで確認）。

## 04-c: 「読む前に確認」カラムの新設

### 対象データ

既存の`GlossaryEntry.source == "concordance"`（頻出条件は満たすが、
in-text定義もbundled辞書もヒットしなかった語）が、そのままユーザーの言う
「明らかに頻出だが未定義」の語彙に一致する。**新しい抽出ロジックは不要**で、
表示側の扱いを変えるだけでよい。

### UI方針

- `paper.html` の `<header>`（タイトル・出典）と `.reader-layout`（本文+図表）
  の間に新セクションを追加:
  ```html
  <section class="preread-terms">
    <h2>読む前に確認: 本文で定義されていない頻出語</h2>
    <ul>
      {% for entry in preread_terms %}
      <li>
        <span class="preread-term">{{ entry.term }}</span>
        <a href="https://www.google.com/search?q={{ entry.term | urlencode }}" target="_blank" rel="noopener">調べる ↗</a>
        <button type="button" class="mark-known" data-term="{{ entry.term }}">知っている</button>
      </li>
      {% endfor %}
    </ul>
  </section>
  ```
  （検索リンク先を外部の特定サービスに固定するのは軽い決め打きり。実装時に
  「Google検索」で十分か、他の候補（Wikipedia等）にすべきかは好みで調整可）。
- この語は本文中の`.gloss`インライン表示（用例ポップオーバー）からは
  **削除しない**。予習カラムは「読む前に」、インラインは「読んでいる最中に
  文脈を思い出す」という別の用途なので併存させる。
- 「知っている」ボタンは04-bの`known-terms`エンドポイントを叩く（＝
  予習カラムでの確定と、通常のopt-outは同じ永続化先）。

### 実装した内容（2026-07-03）

計画通り、新しい抽出ロジックは追加せず表示側のみで実装した。`main.py`の
`read_paper`で、既知語彙フィルタ後のglossaryから`source == "concordance"`の
ものを`preread_terms`として抽出しテンプレートに渡した。`paper.html`の
`<header>`と`.reader-layout`の間に計画通りのセクションを追加（検索リンクは
Google検索に決め打ち）。「知っている」ボタンは04-bと同じ
`/glossary/known-terms`エンドポイントを叩き、押すと即座にそのリスト項目が
消える（`reader.js`に`.mark-known`クリックの分岐を追加、`.gp-know`と同じ
`markTermKnown()`関数を共有）。計画通り、本文中の`.gloss`インライン表示
からは削除しない（両方が同時に見える）。

### テスト

- `test_preread_section_absent_when_no_undefined_frequent_terms` —
  ゴールデンフィクスチャ（GNNはin_text_definitionのみ）ではセクション自体が
  描画されないことを確認。
- `test_preread_section_lists_frequent_undefined_terms` — 未定義の頻出語
  （"Random Forest"、専用の小さなTEIフィクスチャで用意）が予習カラムに
  出ること、かつ本文中の`.gloss`インラインにも引き続き出ることを確認。
- `test_marking_known_from_preread_section_uses_same_store_as_popover` —
  予習カラム側からの「知っている」も04-bの既知語彙ストアに反映され、
  同じ論文の再表示で両方（予習カラム・インライン）から消えることを確認。

## 04-e: 参考文献リストのノイズ混入への防御（新規発見）

### 方針の訂正（03-c実装後に判明）

当初「主対応は03-c、03-c後に再検証してから追加対応を判断する」としていたが、
03-cを実装して分かったのは、**03-cは`text/body`の扱いを一切変えていない**
ということだった。03-cが新設したのは「`text/back`を別途パースして
参考文献リストを作る」処理であり、`_walk_body(body)`が本文として拾う範囲
そのものは変更していない。そもそも本アプリのコードは元から`text/back`を
本文の語彙抽出には使っていない（`full_text`は`normalized.units`＝body由来
のみ）。つまり「参考文献リストの著者名・媒体名が本文に混入する」という
現象は、**このアプリのコードが`back`を誤って読んでいるからではなく、
GROBID自身がその論文の参考文献セクションを`body`として誤分類している
場合に起きる**（03-bで見た「GROBID自身のモデル精度限界」と同種の問題）。
03-cはこの現象に対して何の緩和にもならないため、「03-c後に再検証」を待たず
今回、防御策を直接実装した。

### 実装した内容（2026-07-03）

`app/glossary/dictionaries/academic_venue_names.txt`を新規追加し
（IEEE/ACM/CoRR/arXiv等の学会・出版社・プレプリントサーバ名、大文字小文字
無視でマッチ）、`heuristic.py`の`_frequent_candidates`で候補全体（04-aの
単語1語限定とは異なり、複数語の場合も含めて）がこのリストに一致したら
除外するようにした。人名の自動判定（"Ward"・"Guo"等）は計画通り見送った
（精度が低くコストに見合わないため）。

### テスト

- `test_academic_venue_names_are_excluded_even_when_frequent` — "IEEE"が
  単独の候補として頻度条件を満たしても除外されることを確認（"The IEEE"の
  ような先頭語付き候補が04-aの`_strip_leading_common_words`で正しく
  "IEEE"単体に剥がれてから判定されることも合わせて検証）。

## 04-f: 表記ゆれの正規化統一（新規発見）

### 実装した内容（2026-07-03）

`normalize_term_key()`を`app/glossary/base.py`に新設した（`heuristic.py`では
なくここに置いた理由: グロッサリ戦略を`GLOSSARY_STRATEGY=llm`に切り替えても
04-bの既知語彙ストアが同じキーで機能し続けるべきなので、特定戦略の実装
ファイルではなく戦略共通の契約モジュールに置くのが適切と判断）。
小文字化 + 末尾`s`の除去のみの簡易ルール（3文字以下や"ss"終わりは除去しない
ガード付き）。

`heuristic.py`の`seen_keys`まわり（in-text定義の重複排除、頻出候補の重複
排除）をこの関数経由に統一した。

**実装中に見つけた副作用**: バンドル辞書(`common_abbreviations.json`)は
`{"LSTM": "Long Short-Term Memory", ...}`のように大文字キーで持っているが、
重複排除キーを小文字正規化キーに変えたことで`self._bundled_dictionary.get(key)`
の突き合わせが壊れる（大文字キー vs 小文字キーで一致しなくなる）ことにテストで
気づいた。`_load_bundled_dictionary()`側もロード時に同じ`normalize_term_key`
でキーを正規化することで解消した。テストを都度実行していなければ気づかず
リリースしていたバグなので、実装のたびに`pytest tests/`を回す運用が
効いた一例。

**残存する制約（既知の限界、意図的にスコープ外）**: この正規化は「両方の
表記が単独で頻度しきい値(3回)を超えている場合」にのみ重複を防げる。
例えば"GNN"が2回・"GNNs"が2回（合計4回だが個別にはしきい値未満）という
ケースは、どちらも頻度不足で最初から候補にならないため今回の修正では
拾えない。頻度カウント自体を正規化キー単位で行う設計に変えれば拾えるが、
実装が複雑になる割に実害の見えている範囲（表示上の重複）を超える対応に
なるため、今回は見送った。

### テスト

- `tests/test_glossary_heuristic.py::test_singular_and_plural_forms_are_not_counted_as_separate_terms`
  — "GNN"と"GNNs"がそれぞれ単独で頻度しきい値を超える文章で、1エントリに
  統合されることを確認。
- 既存の`test_bundled_dictionary_supplies_definition_for_known_abbreviation`
  で、バンドル辞書キーの正規化が壊れていないことも回帰確認済み。

## 全体の検証方法

- 課題02のDocker環境が整い次第、実論文で処理し直し、glossaryのノイズが
  実際に減っていること（一般語・参考文献ノイズの消滅、単複重複の解消）を
  目視確認する。
- 予習カラムと既知語彙のopt-outは、同じ語を含む2本目の論文を処理して、
  1本目で「知っている」を押した語が2本目で出てこないことを確認する
  （これが今回の要望の核心なので、必ずこの回帰確認をする）。
