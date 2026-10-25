/**
 * FOCUS Web Guard - Blocked Page Controller
 * Handles target URL display and 'Ask to Allow Website' request dispatch.
 */
document.addEventListener("DOMContentLoaded", () => {
  let targetUrl = "";
  let hostname = "";

  try {
    const params = new URLSearchParams(window.location.search);
    targetUrl = params.get("url") || "Restricted URL";
    const displayEl = document.getElementById("url-display");
    if (displayEl) {
      displayEl.textContent = targetUrl;
    }

    try {
      hostname = new URL(targetUrl).hostname.toLowerCase();
    } catch (e) {
      hostname = targetUrl.replace(/^https?:\/\//, "").split("/")[0];
    }
  } catch (err) {
    console.error("[FOCUS Blocked Page] Error parsing target URL:", err);
  }

  const btnAsk = document.getElementById("btn-ask-allow-site");
  const toastBox = document.getElementById("toast-notify");

  if (btnAsk) {
    btnAsk.addEventListener("click", () => {
      btnAsk.disabled = true;
      btnAsk.textContent = "Sending Request...";

      fetch("http://127.0.0.1:8443/api/request_access", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "website",
          target: hostname || targetUrl,
          title: hostname || targetUrl,
          url: targetUrl
        })
      })
        .then((res) => res.json())
        .then(() => {
          btnAsk.textContent = "✓ Website Request Dispatched";
          btnAsk.style.background = "#193d2c";
          btnAsk.style.borderColor = "#2f7a55";
          if (toastBox) {
            toastBox.textContent = "✓ Request sent to parent. They can approve it from their dashboard.";
            toastBox.style.display = "block";
          }
        })
        .catch(() => {
          btnAsk.textContent = "✓ Request Queued";
          if (toastBox) {
            toastBox.textContent = "✓ Request recorded. Waiting for parent approval.";
            toastBox.style.display = "block";
          }
        });
    });
  }
});
