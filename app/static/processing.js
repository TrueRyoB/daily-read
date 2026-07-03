// Polls GET /papers/{id}/status every ~2s while a paper is processing
// (plan/05-f). No fake ETA -- an indeterminate spinner + elapsed-seconds
// counter is the honest signal here (see plan/05-user-feedback-round2.md
// for why a page-count-based estimate was rejected). Vanilla JS, same
// style as reader.js: no framework, no build step.
(function () {
  const panel = document.querySelector(".processing-panel");
  if (!panel) return;

  const paperId = panel.dataset.paperId;
  if (panel.dataset.initialStatus === "error") return; // nothing to poll

  const elapsedEl = panel.querySelector('[data-role="elapsed"]');
  const notifyButton = panel.querySelector('[data-role="notify-button"]');
  let notifyRequested = false;
  const pollIntervalMs = 2000;

  function updateTitle(elapsedSeconds) {
    if (document.hidden) {
      document.title = `(${elapsedSeconds}秒) 処理中… — daily-read`;
    }
  }

  function poll() {
    fetch(`/papers/${paperId}/status`)
      .then((res) => res.json())
      .then((data) => {
        if (data.status === "processing") {
          if (elapsedEl) elapsedEl.textContent = data.elapsed_seconds;
          updateTitle(data.elapsed_seconds);
          setTimeout(poll, pollIntervalMs);
          return;
        }
        if (data.status === "done") {
          if (notifyRequested && "Notification" in window && Notification.permission === "granted") {
            new Notification("論文の処理が完了しました");
          }
          location.reload();
          return;
        }
        // status === "error": the reload picks up processing.html's error branch.
        location.reload();
      })
      .catch(() => {
        // Transient network hiccup -- keep trying rather than freezing the UI.
        setTimeout(poll, pollIntervalMs);
      });
  }

  if (notifyButton) {
    notifyButton.addEventListener("click", () => {
      if (!("Notification" in window)) {
        notifyButton.disabled = true;
        notifyButton.textContent = "この端末は通知に対応していません";
        return;
      }
      Notification.requestPermission().then((permission) => {
        notifyRequested = permission === "granted";
        notifyButton.disabled = true;
        notifyButton.textContent = notifyRequested ? "通知をオンにしました" : "通知が許可されませんでした";
      });
    });
  }

  poll();
})();
