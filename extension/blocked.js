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
        .then((data) => {
          if (data && data.status === "approved") {
            btnAsk.textContent = "✓ Auto-Approved by Parent!";
            btnAsk.style.background = "#193d2c";
            btnAsk.style.borderColor = "#2f7a55";
            if (toastBox) {
              toastBox.textContent = "✓ Auto-Approved by Parent Policy! Loading website in 1.5s...";
              toastBox.style.background = "#13241c";
              toastBox.style.borderColor = "#1f523a";
              toastBox.style.color = "#7de0ae";
              toastBox.style.display = "block";
            }
            setTimeout(() => {
              if (targetUrl && targetUrl !== "Restricted URL") {
                window.location.href = targetUrl;
              } else {
                window.location.reload();
              }
            }, 1500);
          } else if (data && data.status === "rejected") {
            btnAsk.textContent = "✕ Request Declined";
            btnAsk.style.background = "#3e1b15";
            btnAsk.style.borderColor = "#752d21";
            if (toastBox) {
              toastBox.textContent = "✕ Access request was declined by parent policy.";
              toastBox.style.background = "#2a1515";
              toastBox.style.borderColor = "#5c2525";
              toastBox.style.color = "#f87171";
              toastBox.style.display = "block";
            }
          } else {
            btnAsk.textContent = "✓ Website Request Dispatched";
            btnAsk.style.background = "#193d2c";
            btnAsk.style.borderColor = "#2f7a55";
            if (toastBox) {
              toastBox.textContent = "✓ Request sent to parent. They can approve it from their dashboard.";
              toastBox.style.display = "block";
            }
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
