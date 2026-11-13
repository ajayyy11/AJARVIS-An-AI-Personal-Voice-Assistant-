(() => {
  "use strict";
  const usernameInput = document.getElementById("username");
  const button = document.getElementById("capture-register-button");
  const csrfNode = document.querySelector('meta[name="csrf-token"]');
  if (!usernameInput || !button || !csrfNode) return;

  async function captureAndRegister() {
    const username = usernameInput.value.trim();
    if (!username) {
      window.alert("Please enter a username.");
      usernameInput.focus();
      return;
    }
    if (button.disabled) return;
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "REGISTERING...";
    button.setAttribute("aria-busy", "true");
    try {
      const response = await fetch("/register", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfNode.content,
          "Accept": "application/json"
        },
        body: JSON.stringify({ username })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || "Registration failed. Please try again.");
      if (data.status !== "success") throw new Error(data.message || "Registration was not completed.");
      window.alert(data.message || "Face registered successfully.");
    } catch (error) {
      console.error("Registration error:", error);
      window.alert(error.message || "Registration failed. Please check the camera and try again.");
    } finally {
      button.disabled = false;
      button.textContent = originalText;
      button.removeAttribute("aria-busy");
    }
  }
  button.addEventListener("click", captureAndRegister);
})();
