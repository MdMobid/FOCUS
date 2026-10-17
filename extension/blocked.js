/**
 * FOCUS Web Guard - Blocked Page Controller
 * Extracts and displays the blocked target URL.
 * Separated to satisfy Chrome & Edge Manifest V3 Content Security Policy (No inline scripts).
 */
document.addEventListener("DOMContentLoaded", () => {
  try {
    const params = new URLSearchParams(window.location.search);
    const targetUrl = params.get("url") || "Restricted URL";
    const displayEl = document.getElementById("url-display");
    if (displayEl) {
      displayEl.textContent = targetUrl;
    }
  } catch (err) {
    console.error("[FOCUS Blocked Page] Error parsing target URL:", err);
  }
});
