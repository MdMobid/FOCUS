/**
 * FOCUS Web Guard - Blocked Page Controller
 * Handles target URL display, 'Ask to Allow Website' request dispatch,
 * and automatic instant redirection upon parent approval.
 */
document.addEventListener("DOMContentLoaded", () => {
  let targetUrl = "";
  let hostname = "";

  try {
    const params = new URLSearchParams(window.location.search);
    targetUrl = params.get("url") || "";
    const displayEl = document.getElementById("url-display");
    if (displayEl) {
      displayEl.textContent = targetUrl || "Restricted URL";
    }

    try {
      hostname = new URL(targetUrl).hostname.toLowerCase();
    } catch (e) {
      hostname = targetUrl.replace(/^https?:\/\//, "").split("/")[0].toLowerCase();
    }
  } catch (err) {
    console.error("[FOCUS Blocked Page] Error parsing target URL:", err);
  }

  const btnAsk = document.getElementById("btn-ask-allow-site");
  const toastBox = document.getElementById("toast-notify");

  // Helper to test if hostname is permitted under given rules
  function isTargetAllowed(rules) {
    if (!rules || !rules.focus_mode) return true;
    if (!hostname) return false;
    const allowedSites = rules.allowed_sites || [];
    return allowedSites.some((site) => {
      const clean = site.trim().toLowerCase();
      return hostname === clean || hostname.endsWith("." + clean);
    });
  }

  // Redirect immediately back to the originally blocked URL
  function redirectToTarget() {
    if (targetUrl && targetUrl !== "Restricted URL") {
      window.location.replace(targetUrl);
    } else {
      window.location.reload();
    }
  }

  // Listen for storage rule updates (triggered by background sync when parent approves request)
  try {
    if (typeof chrome !== "undefined" && chrome?.storage?.onChanged) {
      chrome.storage.onChanged.addListener((changes, areaName) => {
        if (areaName === "local" && changes.focus_rules?.newValue) {
          if (isTargetAllowed(changes.focus_rules.newValue)) {
            redirectToTarget();
          }
        }
      });
    }
  } catch (e) { }

  // Initial check: if already approved or focus mode is off, redirect immediately
  try {
    if (typeof chrome !== "undefined" && chrome?.storage?.local) {
      chrome.storage.local.get(["focus_rules"], (res) => {
        if (res && res.focus_rules && isTargetAllowed(res.focus_rules)) {
          redirectToTarget();
        }
      });
    }
  } catch (e) { }

  // Fallback periodic poll to daemon in case tab is in background or storage listener misses
  const checkInterval = setInterval(async () => {
    try {
      const resp = await fetch("http://127.0.0.1:8443/api/rules", { cache: "no-store" });
      if (resp.ok) {
        const rules = await resp.json();
        if (isTargetAllowed(rules)) {
          clearInterval(checkInterval);
          redirectToTarget();
        }
      }
    } catch (e) { }
  }, 2000);

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
              toastBox.textContent = "✓ Auto-Approved by Parent! Opening website now...";
              toastBox.style.background = "#13241c";
              toastBox.style.borderColor = "#1f523a";
              toastBox.style.color = "#7de0ae";
              toastBox.style.display = "block";
            }
            // Instantly redirect to the exact blocked site
            redirectToTarget();
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
              toastBox.textContent = "✓ Request sent to parent. This page will open the website automatically as soon as it is approved.";
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
