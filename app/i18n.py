"""Minimal UI translation table (plan/05-h): papers are read in English but
the UI was Japanese-only, which felt inconsistent. No external i18n
library -- just a flat dict per locale and a lookup function, matching the
rest of this app's "no framework, no build step" approach.
"""

from __future__ import annotations

DEFAULT_LOCALE = "ja"
SUPPORTED_LOCALES = ("ja", "en")

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ja": {
        "tagline": "論文を読みやすく",
        "lang_toggle_label": "English",
        "upload_heading": "今日読む論文を追加",
        "pdf_file_label": "PDFファイル",
        "or_divider": "または",
        "url_label": "PDFのURL（例: arXivのabsページ）",
        "submit_button": "読みやすく整形する",
        "history_heading": "これまでの論文",
        "status_processing": "処理中",
        "status_error": "処理に失敗",
        "reading_time_meta": "約{minutes}分",
        "empty_state": "まだ論文がありません。上のフォームからPDFかURLを追加してください。",
        "processing_title": "処理中 — daily-read",
        "error_heading": "処理に失敗しました",
        "back_to_top": "トップページに戻る",
        "processing_heading": "論文を処理しています…",
        "elapsed_prefix": "経過時間: ",
        "elapsed_suffix": "秒",
        "processing_hint": "論文の分量やGROBIDの状態によって、数十秒〜数分かかることがあります。このページは自動的に切り替わります。",
        "notify_button": "完了したら通知する",
        "annotation_marker_aria": "メモを表示",
        "reading_meta": "推定読了時間: 約{minutes}分・{words}語",
        "source_prefix": "出典: {source}",
        "glossary_hint": "下線付きの語句をクリックすると、意味・用例が表示されます。",
        "annotation_hint": "本文の一部を選択すると、メモを残せます。",
        "preread_heading": "読む前に確認: 本文で定義されていない頻出語",
        "preread_hint": "この論文で3回以上登場しますが、本文中に定義が見つかりませんでした。読む前に調べておくと理解が早まります。",
        "search_link": "調べる ↗",
        "mark_known": "知っている",
        "toc_heading": "目次（{count}件）",
        "annotations_heading": "メモ（{count}件）",
        "annotation_jump": "本文へ移動",
        "annotation_not_found": "本文中に見つかりません（論文が再処理され、内容が変わった可能性があります）",
        "edit": "編集",
        "delete": "削除",
        "figures_heading": "図表一覧",
        "bibliography_heading": "参考文献",
        "annotation_add_button": "+ メモを追加",
        "gp_close_aria": "閉じる",
        "gp_source_concordance": "本文中の用例をまとめたものです（辞書的な定義ではありません）",
        "gp_source_bundled": "一般的な略語辞書による補足説明です",
        "gp_source_intext": "本文中の定義に基づく用語です",
        "gp_know": "知っている（今後表示しない）",
        "ap_save": "保存",
        "ap_cancel": "キャンセル",
        "ap_note_placeholder": "メモを入力",
        "ap_confirm_delete": "このメモを削除しますか？",
        "calendar_nav_label": "カレンダー",
        "calendar_heading": "{year}年{month}月",
        "calendar_prev": "← 前月",
        "calendar_next": "次月 →",
        "calendar_weekdays": "日,月,火,水,木,金,土",
        "interpretation_add_button": "＋ 解釈を記録",
        "interpretation_date_label": "日付",
        "interpretation_papers_label": "関連論文（任意・複数選択可）",
        "interpretation_memo_label": "備忘録",
        "interpretation_memo_placeholder": "読んで考えたこと・気づいたことを書く",
        "interpretation_links_label": "リンク（任意）",
        "interpretation_add_link": "＋ リンクを追加",
        "interpretation_save": "保存",
        "interpretation_cancel": "キャンセル",
        "interpretation_delete": "削除",
        "interpretation_delete_confirm": "この記録を削除しますか？",
        "interpretation_overflow": "他{count}件",
        "interpretation_day_modal_close": "閉じる",
        "interpretation_no_papers": "関連論文なし",
    },
    "en": {
        "tagline": "Make papers easier to read",
        "lang_toggle_label": "日本語",
        "upload_heading": "Add a paper to read today",
        "pdf_file_label": "PDF file",
        "or_divider": "or",
        "url_label": "PDF URL (e.g. an arXiv abs page)",
        "submit_button": "Make it readable",
        "history_heading": "Papers so far",
        "status_processing": "Processing",
        "status_error": "Failed",
        "reading_time_meta": "~{minutes} min",
        "empty_state": "No papers yet. Add a PDF or URL using the form above.",
        "processing_title": "Processing — daily-read",
        "error_heading": "Processing failed",
        "back_to_top": "Back to the top page",
        "processing_heading": "Processing the paper…",
        "elapsed_prefix": "Elapsed: ",
        "elapsed_suffix": "s",
        "processing_hint": "Depending on the paper's size and GROBID's load, this can take anywhere from tens of seconds to a few minutes. This page will switch automatically.",
        "notify_button": "Notify me when done",
        "annotation_marker_aria": "Show note",
        "reading_meta": "Estimated reading time: ~{minutes} min · {words} words",
        "source_prefix": "Source: {source}",
        "glossary_hint": "Click an underlined term to see its meaning and examples.",
        "annotation_hint": "Select part of the text to leave a note.",
        "preread_heading": "Before you read: frequent terms not defined in the text",
        "preread_hint": "These appear 3+ times in this paper but no definition was found in the text. Looking them up first may help.",
        "search_link": "Look up ↗",
        "mark_known": "I know this",
        "toc_heading": "Table of contents ({count})",
        "annotations_heading": "Notes ({count})",
        "annotation_jump": "Jump to text",
        "annotation_not_found": "Not found in the text (the paper may have been reprocessed and the wording changed).",
        "edit": "Edit",
        "delete": "Delete",
        "figures_heading": "Figures",
        "bibliography_heading": "References",
        "annotation_add_button": "+ Add note",
        "gp_close_aria": "Close",
        "gp_source_concordance": "A summary of how this term is used in the text (not a dictionary definition).",
        "gp_source_bundled": "A supplementary explanation from a general abbreviation dictionary.",
        "gp_source_intext": "Based on a definition found in the text.",
        "gp_know": "I know this (don't show again)",
        "ap_save": "Save",
        "ap_cancel": "Cancel",
        "ap_note_placeholder": "Enter a note",
        "ap_confirm_delete": "Delete this note?",
        "calendar_nav_label": "Calendar",
        "calendar_heading": "{month_name} {year}",
        "calendar_prev": "← Previous",
        "calendar_next": "Next →",
        "calendar_weekdays": "Sun,Mon,Tue,Wed,Thu,Fri,Sat",
        "interpretation_add_button": "+ Log an interpretation",
        "interpretation_date_label": "Date",
        "interpretation_papers_label": "Related papers (optional, multiple)",
        "interpretation_memo_label": "Memo",
        "interpretation_memo_placeholder": "What you thought or noticed while reading",
        "interpretation_links_label": "Links (optional)",
        "interpretation_add_link": "+ Add link",
        "interpretation_save": "Save",
        "interpretation_cancel": "Cancel",
        "interpretation_delete": "Delete",
        "interpretation_delete_confirm": "Delete this entry?",
        "interpretation_overflow": "{count} more",
        "interpretation_day_modal_close": "Close",
        "interpretation_no_papers": "No related papers",
    },
}

# Keys reader.js needs client-side (glossary/annotation popovers built by
# JS at runtime, not by Jinja) -- embedded as JSON in paper.html rather
# than duplicated as a second hardcoded dict in the JS file.
JS_KEYS = (
    "gp_close_aria",
    "gp_source_concordance",
    "gp_source_bundled",
    "gp_source_intext",
    "gp_know",
    "ap_save",
    "ap_cancel",
    "ap_note_placeholder",
    "ap_confirm_delete",
    "edit",
    "delete",
    "annotation_marker_aria",
    "annotation_jump",
    "annotation_not_found",
    "annotation_add_button",
)


def resolve_locale(raw: str | None) -> str:
    return raw if raw in SUPPORTED_LOCALES else DEFAULT_LOCALE


def translator(locale: str):
    """Returns a `t(key, **kwargs)` callable bound to `locale`, for
    injection into a single request's Jinja context."""
    table = TRANSLATIONS[resolve_locale(locale)]

    def t(key: str, **kwargs) -> str:
        text = table.get(key, key)
        return text.format(**kwargs) if kwargs else text

    return t


def js_translations(locale: str) -> dict[str, str]:
    table = TRANSLATIONS[resolve_locale(locale)]
    return {key: table[key] for key in JS_KEYS}
