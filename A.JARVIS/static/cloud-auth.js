
    const authMode = document.body.dataset.authMode || "login";
    const form = document.getElementById("authForm");
    const errorNode = document.getElementById("authError");
    const submitButton = document.getElementById("submitButton");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorNode.textContent = "";
      submitButton.disabled = true;
      submitButton.textContent = authMode === "login" ? "Signing in…" : "Creating account…";
      const payload = {
        username: document.getElementById("username").value.trim(),
        password: document.getElementById("password").value
      };
      try {
        const response = await fetch(authMode === "login" ? "/api/auth/login" : "/api/auth/register", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          credentials: "same-origin",
          body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Authentication failed.");
        window.location.assign("/dashboard");
      } catch (error) {
        errorNode.textContent = error.message || "Could not connect to AJARVIS.";
      } finally {
        submitButton.disabled = false;
        submitButton.textContent = authMode === "login" ? "Sign in" : "Create account";
      }
    });
  