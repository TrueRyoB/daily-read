// Paper deletion from the history list (plan/07-troubleshooting-
// backlog.md): frees the paper's own storage (original PDF, TEI, figures,
// content.json). Cross-paper-reusable state (known terms, the glossary
// heuristic's in-memory proper-noun cache) is untouched server-side --
// neither lives under that paper's storage directory.
(function () {
  const list = document.querySelector(".paper-list");
  if (!list) return;

  const i18n = window.__indexI18n || {};

  list.addEventListener("click", (event) => {
    const btn = event.target.closest(".paper-delete-btn");
    if (!btn) return;
    if (!window.confirm(i18n.deleteConfirm)) return;
    fetch(`/papers/${btn.dataset.paperId}`, { method: "DELETE" })
      .then((res) => (res.ok ? location.reload() : Promise.reject(res)))
      .catch(() => {});
  });
})();
