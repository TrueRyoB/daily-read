// plan/05-h: UI strings reader.js builds dynamically (popovers assembled
// as HTML strings, not server-rendered) come from paper.html's embedded
// #i18n-data JSON rather than being hardcoded per-locale here.
const I18N = JSON.parse(document.getElementById("i18n-data")?.textContent || "{}");

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
      concordance: I18N.gp_source_concordance,
      bundled_dictionary: I18N.gp_source_bundled,
      in_text_definition: I18N.gp_source_intext,
    };
    const sourceLabel = sourceLabels[entry.source] || sourceLabels.in_text_definition;
    popover.innerHTML =
      `<button type="button" class="gp-close" aria-label="${I18N.gp_close_aria}">×</button>` +
      `<span class="gp-term">${escapeHtml(entry.term)}</span>` +
      definitionHtml +
      (contexts ? `<ul class="gp-contexts">${contexts}</ul>` : "") +
      `<span class="gp-source">${sourceLabel}</span>` +
      `<button type="button" class="gp-know" data-term="${escapeHtml(entry.term)}">${I18N.gp_know}</button>`;
  }

  function markTermKnown(term) {
    fetch("/glossary/known-terms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ term }),
    })
      .then((res) => {
        if (!res.ok) return;
        document.querySelectorAll(`.gloss[data-term="${CSS.escape(term)}"]`).forEach((span) => {
          span.replaceWith(document.createTextNode(span.textContent));
        });
        byTerm.delete(term);
      })
      .catch(() => {});
    hidePopover();
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
    if (event.target.classList.contains("mark-known")) {
      markTermKnown(event.target.dataset.term);
      event.target.closest("li")?.remove();
      return;
    }
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
      if (event.target.classList.contains("gp-know")) markTermKnown(event.target.dataset.term);
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

// Figure jump + citation links: mobile shows a modal for figures (no page
// scroll at all) and lets citation links use their native anchor jump to
// the mobile reference list; desktop scrolls only inside the independent
// .figures-panel column (shared by figure cards and bibliography entries)
// and highlights the target -- see plan/01-figure-panel-scroll.md and
// plan/03-pdf-domain-extraction-gaps.md#03-c. Separate IIFE from the
// glossary popover above: unrelated concerns, independent DOM elements.
(function () {
  const figuresDataEl = document.getElementById("figures-data");
  const modal = document.getElementById("figure-modal");
  if (!figuresDataEl || !modal) return;

  const figures = JSON.parse(figuresDataEl.textContent || "[]");
  const figureById = new Map(figures.map((f) => [f.figure_id, f]));
  const bibliographyDataEl = document.getElementById("bibliography-data");
  const bibliographyByBibId = new Map(
    (bibliographyDataEl ? JSON.parse(bibliographyDataEl.textContent || "[]") : []).map((b) => [b.bib_id, b])
  );
  const figuresPanel = document.querySelector(".figures-panel");
  const modalImg = modal.querySelector("img");
  const modalCaption = modal.querySelector("figcaption");
  const isMobileLayout = () => window.matchMedia("(max-width: 860px)").matches;

  function showModal(figure) {
    modalImg.src = figure.image_url;
    modalImg.alt = figure.label;
    modalCaption.textContent = figure.caption || figure.label;
    modal.hidden = false;
  }

  function hideModal() {
    modal.hidden = true;
  }

  // plan/07-troubleshooting-backlog.md#a-2: on a narrow screen, jumping to
  // the reference list is easy to miss entirely. Toggle the citation's own
  // visible text between "[1]" and the full reference instead -- no
  // scrolling, no separate section to find.
  function toggleCitationLabel(link, bibId) {
    const entry = bibliographyByBibId.get(bibId);
    if (!entry) return;
    if (link.dataset.expanded === "true") {
      link.textContent = link.dataset.originalLabel;
      link.dataset.expanded = "false";
    } else {
      link.dataset.originalLabel = link.dataset.originalLabel || link.textContent;
      link.textContent = entry.label;
      link.dataset.expanded = "true";
    }
  }

  // Used for both figure-jump targets (figure cards) and citation targets
  // (bibliography entries) -- both live as .panel-item children of the
  // same independently-scrolling .figures-panel column.
  function scrollToPanelItem(elementId) {
    if (!figuresPanel) return false;
    const target = document.getElementById(elementId);
    if (!target) return false;
    figuresPanel.querySelectorAll(".panel-item.is-active").forEach((el) => el.classList.remove("is-active"));
    target.classList.add("is-active");
    // getBoundingClientRect deltas, not offsetTop: robust regardless of
    // which element ends up as target's offsetParent.
    const delta = target.getBoundingClientRect().top - figuresPanel.getBoundingClientRect().top;
    figuresPanel.scrollTop += delta;
    return true;
  }

  document.addEventListener("click", (event) => {
    const jumpLink = event.target.closest(".figure-jump");
    if (jumpLink) {
      event.preventDefault(); // never let the browser jump/scroll the page itself
      const figureId = jumpLink.getAttribute("href").slice(1);
      const figure = figureById.get(figureId);
      if (!figure) return;
      // plan/07-troubleshooting-backlog.md#a-1: the desktop panel image is
      // too small to read comfortably -- open the same large modal mobile
      // already gets. Desktop additionally still highlights/scrolls the
      // panel copy, so the "independent side column" context (plan/01)
      // isn't lost, just no longer the only way to see the figure.
      if (!isMobileLayout()) scrollToPanelItem(figureId);
      showModal(figure);
      return;
    }
    // Clicking the (small) panel thumbnail itself also opens the same
    // large modal -- desktop only; mobile never shows this panel at all.
    const panelFigureCard = event.target.closest(".figure-card");
    if (panelFigureCard && !isMobileLayout()) {
      const figure = figureById.get(panelFigureCard.id);
      if (figure) showModal(figure);
      return;
    }
    const citationLink = event.target.closest(".citation");
    if (citationLink) {
      const href = citationLink.getAttribute("href") || "";
      // Only in-page bibliography anchors ("#bib-b0") are handled here;
      // an external DOI/URL href should open normally.
      if (href.startsWith("#")) {
        // href is "#bib-b0" -- strip both the "#" and the "bib-" prefix to
        // get the raw id ("b0") shared by both the desktop element
        // ("bib-b0") and the mobile one ("bib-mobile-b0"). Previously this
        // kept the "bib-" prefix and re-prepended "bib-mobile-", producing
        // "bib-mobile-bib-b0" -- a nonexistent id, so the mobile branch's
        // `if (el)` check always failed silently (no scroll, no
        // preventDefault, so the browser's own anchor-jump to the hidden
        // desktop copy ran instead -- exactly the "URL changes, nothing
        // visibly happens" symptom reported in
        // plan/07-troubleshooting-backlog.md#a-2).
        const bibId = href.slice(1).replace(/^bib-/, "");
        if (isMobileLayout()) {
          toggleCitationLabel(citationLink, bibId);
          event.preventDefault();
        } else if (scrollToPanelItem("bib-" + bibId)) {
          event.preventDefault();
        }
      }
      return;
    }
    if (event.target.closest(".figure-modal-content")) {
      if (event.target.classList.contains("figure-modal-close")) hideModal();
      return;
    }
    if (event.target.closest("#figure-modal")) {
      hideModal(); // backdrop click
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideModal();
  });
})();

// Reader annotations (plan/05-g): select text inside a single
// paragraph/heading to leave a margin note, like writing on a printed
// paper. Selection is deliberately restricted to one block -- see
// plan/05-user-feedback-round2.md#05-g for why cross-block anchoring was
// scoped out. Independent IIFE: unrelated DOM/state from the two above.
(function () {
  const article = document.querySelector(".reader");
  const dataEl = document.getElementById("annotations-data");
  const addBtn = document.getElementById("annotation-add-btn");
  const popover = document.getElementById("annotation-popover");
  if (!article || !dataEl || !addBtn || !popover) return;

  const paperId = article.dataset.paperId;
  const annotationsById = new Map(
    JSON.parse(dataEl.textContent || "[]").map((a) => [String(a.id), a])
  );
  let pendingSelection = null; // {quote, prefix, suffix, blockEl}

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function blockContext(blockEl, quote, approxStart) {
    const full = blockEl.textContent;
    let idx = full.indexOf(quote, Math.max(0, approxStart - quote.length));
    if (idx === -1) idx = full.indexOf(quote);
    if (idx === -1) return { prefix: "", suffix: "" };
    return {
      prefix: full.slice(Math.max(0, idx - 40), idx),
      suffix: full.slice(idx + quote.length, idx + quote.length + 40),
    };
  }

  function closestBlock(node) {
    const el = node.nodeType === 1 ? node : node.parentElement;
    return el ? el.closest("h2, h3, h4, p") : null;
  }

  function hideAddButton() {
    addBtn.hidden = true;
  }

  function hidePopover() {
    popover.hidden = true;
    popover.dataset.mode = "";
  }

  function positionNear(rect) {
    const width = popover.offsetWidth || 280;
    const left = Math.max(16, Math.min(rect.left, window.innerWidth - width - 16));
    popover.style.left = `${left}px`;
    popover.style.top = `${rect.bottom + window.scrollY + 8}px`;
  }

  document.addEventListener("mouseup", (event) => {
    if (event.target.closest("#annotation-popover, #annotation-add-btn, .annotations-queue")) return;

    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
      hideAddButton();
      pendingSelection = null;
      return;
    }
    const range = selection.getRangeAt(0);
    const startBlock = closestBlock(range.startContainer);
    const endBlock = closestBlock(range.endContainer);
    const quote = selection.toString().trim();
    if (!startBlock || startBlock !== endBlock || !startBlock.closest(".reader-body") || !quote) {
      hideAddButton();
      pendingSelection = null;
      return;
    }

    const { prefix, suffix } = blockContext(startBlock, quote, range.startOffset);
    pendingSelection = { quote, prefix, suffix, blockEl: startBlock };

    const rect = range.getBoundingClientRect();
    addBtn.hidden = false;
    addBtn.style.left = `${Math.max(8, rect.left)}px`;
    addBtn.style.top = `${rect.bottom + window.scrollY + 6}px`;
  });

  addBtn.addEventListener("click", () => {
    if (!pendingSelection) return;
    popover.innerHTML =
      `<p class="ap-quote">「${escapeHtml(pendingSelection.quote)}」</p>` +
      `<textarea class="ap-textarea" placeholder="${I18N.ap_note_placeholder}" rows="3"></textarea>` +
      '<div class="ap-actions">' +
      `<button type="button" class="ap-save">${I18N.ap_save}</button>` +
      `<button type="button" class="ap-cancel">${I18N.ap_cancel}</button>` +
      "</div>";
    popover.dataset.mode = "compose";
    popover.hidden = false;
    positionNear(pendingSelection.blockEl.getBoundingClientRect());
    popover.querySelector(".ap-textarea")?.focus();
    hideAddButton();
  });

  function insertMarker(blockEl, annotationId) {
    blockEl.classList.add("annotated-block");
    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = "annotation-marker";
    marker.dataset.annotationId = annotationId;
    marker.setAttribute("aria-label", I18N.annotation_marker_aria);
    marker.textContent = "\u{1F4DD}";
    blockEl.insertBefore(marker, blockEl.firstChild);
  }

  function queueList() {
    return document.querySelector('[data-role="annotation-list"]');
  }

  function updateQueueVisibility() {
    const list = queueList();
    const countEl = document.querySelector('[data-role="annotation-count"]');
    const details = document.querySelector(".annotations-queue");
    if (!list || !countEl || !details) return;
    countEl.textContent = list.children.length;
    details.hidden = list.children.length === 0;
  }

  function addQueueEntry(annotation, found) {
    const list = queueList();
    if (!list) return;
    const li = document.createElement("li");
    li.className = "annotation-queue-item";
    li.dataset.annotationId = annotation.id;
    li.innerHTML =
      `<p class="annotation-quote">「${escapeHtml(annotation.quote)}」</p>` +
      `<p class="annotation-note-text">${escapeHtml(annotation.note)}</p>` +
      '<div class="annotation-queue-actions">' +
      (found
        ? `<button type="button" class="annotation-jump" data-annotation-id="${annotation.id}">${I18N.annotation_jump}</button>`
        : `<span class="annotation-not-found">${I18N.annotation_not_found}</span>`) +
      `<button type="button" class="annotation-edit" data-annotation-id="${annotation.id}">${I18N.edit}</button>` +
      `<button type="button" class="annotation-delete" data-annotation-id="${annotation.id}">${I18N.delete}</button>` +
      "</div>";
    list.appendChild(li);
    updateQueueVisibility();
  }

  function saveNewAnnotation() {
    const textarea = popover.querySelector(".ap-textarea");
    const note = textarea ? textarea.value.trim() : "";
    const selection = pendingSelection;
    if (!note || !selection) return;
    fetch(`/papers/${paperId}/annotations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quote: selection.quote, prefix: selection.prefix, suffix: selection.suffix, note }),
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((annotation) => {
        annotationsById.set(String(annotation.id), annotation);
        insertMarker(selection.blockEl, annotation.id);
        addQueueEntry(annotation, true);
        hidePopover();
        window.getSelection()?.removeAllRanges();
        pendingSelection = null;
      })
      .catch(() => {});
  }

  function showViewPopover(annotationId, anchorEl) {
    const annotation = annotationsById.get(String(annotationId));
    if (!annotation) return;
    popover.innerHTML =
      `<p class="ap-quote">「${escapeHtml(annotation.quote)}」</p>` +
      `<p class="ap-note">${escapeHtml(annotation.note)}</p>` +
      '<div class="ap-actions">' +
      `<button type="button" class="ap-edit" data-annotation-id="${annotation.id}">${I18N.edit}</button>` +
      `<button type="button" class="ap-delete" data-annotation-id="${annotation.id}">${I18N.delete}</button>` +
      "</div>";
    popover.dataset.mode = "view";
    popover.hidden = false;
    positionNear(anchorEl.getBoundingClientRect());
  }

  function showEditPopover(annotationId) {
    const annotation = annotationsById.get(String(annotationId));
    if (!annotation) return;
    popover.innerHTML =
      `<p class="ap-quote">「${escapeHtml(annotation.quote)}」</p>` +
      `<textarea class="ap-textarea" rows="3">${escapeHtml(annotation.note)}</textarea>` +
      '<div class="ap-actions">' +
      `<button type="button" class="ap-save-edit" data-annotation-id="${annotation.id}">${I18N.ap_save}</button>` +
      `<button type="button" class="ap-cancel">${I18N.ap_cancel}</button>` +
      "</div>";
    popover.dataset.mode = "edit";
    popover.hidden = false;
  }

  function saveEdit(annotationId) {
    const textarea = popover.querySelector(".ap-textarea");
    const note = textarea ? textarea.value.trim() : "";
    if (!note) return;
    fetch(`/papers/${paperId}/annotations/${annotationId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((updated) => {
        annotationsById.set(String(updated.id), updated);
        const li = document.querySelector(`.annotation-queue-item[data-annotation-id="${updated.id}"]`);
        const noteEl = li ? li.querySelector(".annotation-note-text") : null;
        if (noteEl) noteEl.textContent = updated.note;
        hidePopover();
      })
      .catch(() => {});
  }

  function deleteAnnotation(annotationId) {
    if (!window.confirm(I18N.ap_confirm_delete)) return;
    fetch(`/papers/${paperId}/annotations/${annotationId}`, { method: "DELETE" })
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then(() => {
        annotationsById.delete(String(annotationId));
        document.querySelectorAll(`.annotation-marker[data-annotation-id="${annotationId}"]`).forEach((marker) => {
          const block = marker.closest(".annotated-block");
          marker.remove();
          if (block && !block.querySelector(".annotation-marker")) block.classList.remove("annotated-block");
        });
        const li = document.querySelector(`.annotation-queue-item[data-annotation-id="${annotationId}"]`);
        if (li) li.remove();
        updateQueueVisibility();
        hidePopover();
      })
      .catch(() => {});
  }

  document.addEventListener("click", (event) => {
    const marker = event.target.closest(".annotation-marker");
    if (marker) {
      showViewPopover(marker.dataset.annotationId, marker);
      event.stopPropagation();
      return;
    }
    const jumpBtn = event.target.closest(".annotation-jump");
    if (jumpBtn) {
      const target = document.querySelector(`.annotation-marker[data-annotation-id="${jumpBtn.dataset.annotationId}"]`);
      const block = target ? target.closest(".annotated-block") : null;
      if (block) {
        block.scrollIntoView({ behavior: "smooth", block: "center" });
        block.classList.add("annotation-flash");
        setTimeout(() => block.classList.remove("annotation-flash"), 1500);
      }
      return;
    }
    const editBtn = event.target.closest(".annotation-edit, .ap-edit");
    if (editBtn) {
      showEditPopover(editBtn.dataset.annotationId);
      return;
    }
    const deleteBtn = event.target.closest(".annotation-delete, .ap-delete");
    if (deleteBtn) {
      deleteAnnotation(deleteBtn.dataset.annotationId);
      return;
    }
    if (event.target.closest("#annotation-popover")) {
      if (event.target.classList.contains("ap-save")) saveNewAnnotation();
      if (event.target.classList.contains("ap-cancel")) hidePopover();
      if (event.target.classList.contains("ap-save-edit")) saveEdit(event.target.dataset.annotationId);
      return;
    }
    if (event.target.closest("#annotation-add-btn")) return;
    hidePopover();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hidePopover();
      hideAddButton();
    }
  });
})();

// Offline resilience on mobile (plan/07-troubleshooting-backlog.md#b-6):
// once this paper's page/figures/assets are cached, the reader can keep
// going through a network dropout (e.g. a subway tunnel) instead of
// losing the page. Deliberately keeps only the most recently opened
// paper -- caches.delete() evicts whatever was cached before every time.
// Desktop is unaffected: this whole IIFE no-ops there.
(function () {
  const CACHE_NAME = "current-offline-paper";
  const isMobileLayout = () => window.matchMedia("(max-width: 860px)").matches;
  if (!isMobileLayout() || !("serviceWorker" in navigator) || !("caches" in window)) return;

  const indicator = document.getElementById("offline-ready-indicator");
  navigator.serviceWorker.register("/sw.js").catch(() => {});

  const figuresDataEl = document.getElementById("figures-data");
  const figures = figuresDataEl ? JSON.parse(figuresDataEl.textContent || "[]") : [];
  const urlsToCache = [
    window.location.pathname,
    "/static/reader.js",
    "/static/styles.css",
    "/static/fonts/AtkinsonHyperlegible-Regular.woff2",
    "/static/fonts/AtkinsonHyperlegible-Bold.woff2",
    "/static/fonts/AtkinsonHyperlegible-Italic.woff2",
  ].concat(figures.map((f) => f.image_url));

  caches
    .delete(CACHE_NAME)
    .then(() => caches.open(CACHE_NAME))
    .then((cache) => cache.addAll(urlsToCache))
    .then(() => {
      if (indicator) indicator.hidden = false;
    })
    .catch(() => {
      // A network hiccup mid-cache (or an offline first load) shouldn't
      // show a false "available offline" claim -- indicator just stays
      // hidden.
    });
})();

// Related papers (OpenAlex, opt-in) -- plan/07-troubleshooting-backlog.md#b-7.
// The button POSTs to kick off a background job, then this polls for the
// result. On load it also checks the status once in case a previous visit
// already started (or finished) the job, so returning to the page doesn't
// lose the result or require clicking the button again.
(function () {
  const section = document.querySelector('[data-role="related-papers"]');
  if (!section) return;

  const paperId = section.dataset.paperId;
  const button = section.querySelector('[data-role="related-papers-button"]');
  const statusEl = section.querySelector('[data-role="related-papers-status"]');
  const listEl = section.querySelector('[data-role="related-papers-list"]');
  const pollIntervalMs = 3000;

  function renderResults(results) {
    listEl.innerHTML = "";
    if (!results.length) {
      statusEl.hidden = false;
      statusEl.textContent = I18N.related_papers_empty;
      return;
    }
    statusEl.hidden = true;
    for (const item of results) {
      const li = document.createElement("li");
      li.className = "related-paper-item";
      const titleEl = document.createElement("span");
      titleEl.className = "related-paper-title";
      if (item.url) {
        const link = document.createElement("a");
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = item.title;
        titleEl.appendChild(link);
      } else {
        titleEl.textContent = item.title;
      }
      const metaEl = document.createElement("span");
      metaEl.className = "related-paper-meta";
      const authors = item.authors && item.authors.length ? item.authors.join(", ") : "";
      const year = item.year || I18N.related_papers_unknown_year;
      const citation = I18N.related_papers_citation_count.replace("{count}", item.citation_count);
      metaEl.textContent = [authors, year, citation].filter(Boolean).join(" · ");
      li.appendChild(titleEl);
      li.appendChild(metaEl);
      listEl.appendChild(li);
    }
  }

  function poll() {
    fetch(`/papers/${paperId}/related-papers`)
      .then((res) => res.json())
      .then((data) => {
        if (data.status === "processing") {
          statusEl.hidden = false;
          statusEl.textContent = I18N.related_papers_loading;
          setTimeout(poll, pollIntervalMs);
          return;
        }
        if (data.status === "done") {
          renderResults(data.results || []);
          return;
        }
        if (data.status === "error") {
          statusEl.hidden = false;
          statusEl.textContent = I18N.related_papers_error;
          return;
        }
        // "not_started": show the button, nothing to poll yet.
        button.hidden = false;
      })
      .catch(() => {
        setTimeout(poll, pollIntervalMs);
      });
  }

  button.addEventListener("click", () => {
    button.hidden = true;
    statusEl.hidden = false;
    statusEl.textContent = I18N.related_papers_loading;
    fetch(`/papers/${paperId}/related-papers`, { method: "POST" })
      .then(() => setTimeout(poll, pollIntervalMs))
      .catch(() => {
        statusEl.textContent = I18N.related_papers_error;
      });
  });

  poll();
})();
