// Minimal vanilla JS glossary popover -- no framework, no build step.
// Reads the glossary entries embedded by paper.html and shows one on
// click/tap/Enter of a .gloss span.
(function () {
  const dataEl = document.getElementById("glossary-data");
  const popover = document.getElementById("glossary-popover");
  if (!dataEl || !popover) return;

  const entries = JSON.parse(dataEl.textContent || "[]");
  const byTerm = new Map(entries.map((e) => [e.term, e]));

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function renderPopover(entry) {
    const contexts = (entry.contexts || []).map((c) => `<li>${escapeHtml(c)}</li>`).join("");
    const definitionHtml = entry.definition
      ? `<span class="gp-def">${escapeHtml(entry.definition)}</span>`
      : "";
    const sourceLabels = {
      concordance: "本文中の用例をまとめたものです（辞書的な定義ではありません）",
      bundled_dictionary: "一般的な略語辞書による補足説明です",
      in_text_definition: "本文中の定義に基づく用語です",
    };
    const sourceLabel = sourceLabels[entry.source] || sourceLabels.in_text_definition;
    popover.innerHTML =
      '<button type="button" class="gp-close" aria-label="閉じる">×</button>' +
      `<span class="gp-term">${escapeHtml(entry.term)}</span>` +
      definitionHtml +
      (contexts ? `<ul class="gp-contexts">${contexts}</ul>` : "") +
      `<span class="gp-source">${sourceLabel}</span>`;
  }

  function showPopoverNear(target, entry) {
    renderPopover(entry);
    popover.hidden = false;
    const rect = target.getBoundingClientRect();
    const width = popover.offsetWidth;
    const left = Math.max(16, Math.min(rect.left, window.innerWidth - width - 16));
    popover.style.left = `${left}px`;
    popover.style.top = `${rect.bottom + window.scrollY + 8}px`;
  }

  function hidePopover() {
    popover.hidden = true;
  }

  document.addEventListener("click", (event) => {
    const gloss = event.target.closest(".gloss");
    if (gloss) {
      const entry = byTerm.get(gloss.dataset.term);
      if (entry) {
        showPopoverNear(gloss, entry);
        event.stopPropagation();
      }
      return;
    }
    if (event.target.closest(".glossary-popover")) {
      if (event.target.classList.contains("gp-close")) hidePopover();
      return;
    }
    hidePopover();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hidePopover();
    if ((event.key === "Enter" || event.key === " ") && event.target.classList.contains("gloss")) {
      event.preventDefault();
      event.target.click();
    }
  });
})();
