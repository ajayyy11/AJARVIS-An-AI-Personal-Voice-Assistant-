(() => {
  "use strict";
  const statusNode = document.getElementById("face-status");
  let retryTimer = null;
  let requestInFlight = false;

  function scheduleNextCheck() {
    window.clearTimeout(retryTimer);
    if (!document.hidden) retryTimer = window.setTimeout(checkFaceAccess, 2000);
  }

  async function checkFaceAccess() {
    if (document.hidden || requestInFlight || !statusNode) return;
    requestInFlight = true;
    try {
      const response = await fetch("/check_access", {
        cache: "no-store",
        credentials: "same-origin",
        headers: { "Accept": "application/json" }
      });
      const data = await response.json();
      if (response.ok && data.access) {
        statusNode.textContent = "Identity recognized. Opening your workspace…";
        window.location.replace("/dashboard");
        return;
      }
      statusNode.textContent = data.error || (
        !data.camera_ready
          ? "Camera unavailable. Connect a camera and restart AJARVIS."
          : "No stable match yet. Keep one face centered in the camera."
      );
    } catch (_error) {
      statusNode.textContent = "Authentication service unavailable. Check that AJARVIS is running.";
    } finally {
      requestInFlight = false;
      scheduleNextCheck();
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      window.clearTimeout(retryTimer);
      return;
    }
    checkFaceAccess();
  });
  document.addEventListener("DOMContentLoaded", checkFaceAccess, { once: true });
})();
