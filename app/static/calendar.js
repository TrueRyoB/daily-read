// Interpretation-log calendar (plan/07-troubleshooting-backlog.md#b-4改訂).
// Vanilla JS, no framework -- matches the rest of this app's static assets.
(function () {
  const form = document.getElementById("interpretation-form");
  const dayModal = document.getElementById("calendar-day-modal");
  const entriesDataEl = document.getElementById("calendar-entries-data");
  if (!form || !dayModal || !entriesDataEl) return;

  const entriesByDate = JSON.parse(entriesDataEl.textContent || "{}");
  const i18n = window.__calendarI18n || {};

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // --- Dynamic "+ add link" inputs ---
  const linksContainer = document.querySelector('[data-role="interpretation-links"]');
  const addLinkButton = document.querySelector('[data-role="add-link"]');
  if (linksContainer && addLinkButton) {
    addLinkButton.addEventListener("click", () => {
      const input = document.createElement("input");
      input.type = "url";
      input.name = "links";
      input.placeholder = "https://...";
      linksContainer.appendChild(input);
    });
  }

  // --- Paper picker search filter (plan/07-troubleshooting-backlog.md):
  // a plain checkbox list of every paper doesn't scale once there are more
  // than a handful -- filter which ones are shown, without touching which
  // are checked (a filtered-out-but-checked paper stays checked). ---
  const paperSearchInput = document.querySelector('[data-role="paper-search"]');
  const paperOptions = document.querySelector('[data-role="paper-options"]');
  if (paperSearchInput && paperOptions) {
    paperSearchInput.addEventListener("input", () => {
      const query = paperSearchInput.value.trim().toLowerCase();
      paperOptions.querySelectorAll(".interpretation-paper-option").forEach((label) => {
        const title = label.dataset.title || "";
        label.hidden = query.length > 0 && !title.includes(query);
      });
    });
  }

  // --- Form submission ---
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const paperIds = formData.getAll("paper_ids");
    const links = formData.getAll("links").map((v) => String(v).trim()).filter(Boolean);
    const payload = {
      date: formData.get("date"),
      memo: formData.get("memo") || "",
      paper_ids: paperIds,
      links: links,
    };
    if (!payload.date) return;

    fetch("/interpretations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then(() => {
        window.location.reload();
      })
      .catch(() => {});
  });

  // --- Day detail modal ---
  function renderEntry(entry) {
    const papersHtml = entry.papers && entry.papers.length
      ? entry.papers
          .map((p) => `<a href="/papers/${encodeURIComponent(p.id)}">${escapeHtml(p.title)}</a>`)
          .join(", ")
      : `<span class="calendar-day-modal-no-papers">${escapeHtml(i18n.noPapers || "")}</span>`;
    const linksHtml = (entry.links || [])
      .map((url) => `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a>`)
      .join("<br>");
    return (
      `<div class="calendar-day-modal-entry" data-interpretation-id="${entry.id}">` +
      `<p class="calendar-day-modal-papers">${papersHtml}</p>` +
      (entry.memo ? `<p class="calendar-day-modal-memo">${escapeHtml(entry.memo)}</p>` : "") +
      (linksHtml ? `<p class="calendar-day-modal-links">${linksHtml}</p>` : "") +
      `<button type="button" class="calendar-day-modal-delete" data-interpretation-id="${entry.id}">${escapeHtml(i18n.deleteLabel || "Delete")}</button>` +
      `</div>`
    );
  }

  function showDayModal(date) {
    const entries = entriesByDate[date] || [];
    dayModal.querySelector('[data-role="calendar-day-modal-title"]').textContent = date;
    dayModal.querySelector('[data-role="calendar-day-modal-list"]').innerHTML = entries.map(renderEntry).join("");
    dayModal.hidden = false;
  }

  function hideDayModal() {
    dayModal.hidden = true;
  }

  document.addEventListener("click", (event) => {
    const dayCell = event.target.closest('[data-role="calendar-day-cell"]');
    if (dayCell) {
      showDayModal(dayCell.dataset.date);
      return;
    }
    const deleteButton = event.target.closest(".calendar-day-modal-delete");
    if (deleteButton) {
      if (!window.confirm(i18n.deleteConfirm || "Delete?")) return;
      fetch(`/interpretations/${deleteButton.dataset.interpretationId}`, { method: "DELETE" })
        .then((res) => (res.ok ? res.json() : Promise.reject(res)))
        .then(() => window.location.reload())
        .catch(() => {});
      return;
    }
    if (event.target.closest(".calendar-day-modal-content")) {
      if (event.target.classList.contains("calendar-day-modal-close")) hideDayModal();
      return;
    }
    if (event.target.closest("#calendar-day-modal")) {
      hideDayModal(); // backdrop click
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideDayModal();
  });
})();
