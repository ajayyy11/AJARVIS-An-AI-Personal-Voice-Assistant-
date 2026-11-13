
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";


    /* PHASE 5 — CONTROLLED TASK PLANNING */
    const automationForm = document.getElementById("automation-form");
    const automationTask = document.getElementById("automation-task");
    const automationPlan = document.getElementById("automation-plan");
    const automationStatus = document.getElementById("automation-status");
    const automationPlanButton = document.getElementById("automation-plan-button");
    const automationActivity = document.getElementById("automation-activity");
    let currentAutomationPlanId = null;

    function automationNode(tag, className, text) {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined && text !== null) node.textContent = String(text);
      return node;
    }

    async function automationRequest(url, method, payload) {
      const response = await fetch(url, {
        method,
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Accept": "application/json"
        },
        body: payload ? JSON.stringify(payload) : undefined
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Automation request failed.");
      return data;
    }

    function renderAutomationPlan(plan) {
      automationPlan.replaceChildren();
      currentAutomationPlanId = plan.plan_id || null;
      const headline = automationNode("p", "automation-intro", plan.goal + " · " + plan.status.toUpperCase());
      automationPlan.appendChild(headline);
      const list = automationNode("div", "automation-step-list");
      plan.steps.forEach((step, index) => {
        const card = automationNode("article", "automation-step");
        card.appendChild(automationNode("h4", "", (index + 1) + ". " + step.summary));
        card.appendChild(automationNode("span", "automation-badge", step.risk_level + " risk"));
        card.appendChild(automationNode("span", "automation-badge", step.status.replaceAll("_", " ")));
        card.appendChild(automationNode("p", "", step.reason));
        if (step.arguments && Object.keys(step.arguments).length) {
          card.appendChild(automationNode("pre", "", "Action details: " + JSON.stringify(step.arguments, null, 2)));
        }
        if (step.result !== null && step.result !== undefined) {
          card.appendChild(automationNode("pre", "", "Result: " + JSON.stringify(step.result)));
        }
        if (step.error) card.appendChild(automationNode("p", "", step.error));
        list.appendChild(card);
      });
      automationPlan.appendChild(list);

      if (plan.approval) {
        const activeStep = plan.steps.find((step) => step.step_id === plan.approval.step_id);
        const approval = automationNode("div", "automation-approval");
        approval.appendChild(automationNode("strong", "", "YOUR APPROVAL IS REQUIRED"));
        approval.appendChild(automationNode("p", "", (activeStep ? activeStep.summary : "A computer-changing action") + ". Review the action details above. Approval expires in about " + plan.approval.expires_in_seconds + " seconds."));
        const actions = automationNode("div", "automation-actions");
        const approve = automationNode("button", "automation-action", "APPROVE THIS STEP");
        approve.type = "button";
        approve.addEventListener("click", () => respondAutomationApproval(plan.approval.approval_id, "approve", approve));
        const reject = automationNode("button", "automation-action", "REJECT & STOP");
        reject.type = "button";
        reject.addEventListener("click", () => respondAutomationApproval(plan.approval.approval_id, "reject", reject));
        actions.append(approve, reject);
        approval.appendChild(actions);
        automationPlan.appendChild(approval);
      } else if (!["completed", "cancelled", "failed", "expired"].includes(plan.status)) {
        const cancel = automationNode("button", "automation-action", "CANCEL PLAN");
        cancel.type = "button";
        cancel.addEventListener("click", () => cancelAutomationPlan(plan.plan_id, cancel));
        automationPlan.appendChild(cancel);
      }
    }

    async function createAutomationPlan(event) {
      event.preventDefault();
      const task = automationTask.value.trim();
      if (!task || automationPlanButton.disabled) return;
      automationPlanButton.disabled = true;
      automationStatus.textContent = "Planning and validating steps…";
      automationPlan.replaceChildren();
      try {
        const data = await automationRequest("/api/automation/plan", "POST", { task });
        renderAutomationPlan(data.plan);
        automationStatus.textContent = data.plan.status === "awaiting_approval"
          ? "Read-only checks are complete. Review the pending action before approving."
          : "Plan status: " + data.plan.status + ".";
        await refreshAutomationActivity();
        await refreshPhase6Workflows();
      } catch (error) {
        automationStatus.textContent = error.message || "Could not create the task plan.";
      } finally {
        automationPlanButton.disabled = false;
      }
    }

    async function respondAutomationApproval(approvalId, decision, button) {
      button.disabled = true;
      automationStatus.textContent = decision === "approve" ? "Executing the approved step…" : "Rejecting the pending step…";
      try {
        const data = await automationRequest("/api/automation/approval/" + encodeURIComponent(approvalId), "POST", { decision });
        renderAutomationPlan(data.plan);
        automationStatus.textContent = data.plan.status === "awaiting_approval"
          ? "Next computer-changing step needs your approval."
          : "Plan status: " + data.plan.status + ".";
        await refreshAutomationActivity();
        await refreshPhase6Workflows();
      } catch (error) {
        automationStatus.textContent = error.message || "Approval could not be processed.";
        button.disabled = false;
      }
    }

    async function cancelAutomationPlan(planId, button) {
      button.disabled = true;
      try {
        const data = await automationRequest("/api/automation/plan/" + encodeURIComponent(planId) + "/cancel", "POST", {});
        renderAutomationPlan(data.plan);
        automationStatus.textContent = "Plan cancelled.";
        await refreshAutomationActivity();
        await refreshPhase6Workflows();
      } catch (error) {
        automationStatus.textContent = error.message || "Plan could not be cancelled.";
        button.disabled = false;
      }
    }

    async function refreshAutomationActivity() {
      try {
        const response = await fetch("/api/automation/activity", { cache: "no-store" });
        if (response.status === 401) { window.location.replace("/login"); return; }
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Activity is unavailable.");
        automationActivity.replaceChildren();
        const events = Array.isArray(data.activity) ? data.activity : [];
        if (!events.length) {
          automationActivity.appendChild(automationNode("p", "automation-intro", "No automation activity recorded yet."));
          return;
        }
        events.slice(0, 12).forEach((entry) => {
          const row = automationNode("div", "automation-event");
          row.appendChild(automationNode("span", "", entry.event_type.replaceAll("_", " ") + (entry.tool_name ? " · " + entry.tool_name : "") + " — " + entry.summary));
          row.appendChild(automationNode("span", "", entry.created_at ? new Date(entry.created_at).toLocaleTimeString() : ""));
          automationActivity.appendChild(row);
        });
      } catch (error) {
        automationActivity.replaceChildren(automationNode("p", "automation-intro", error.message || "Activity history is unavailable."));
      }
    }

    automationForm.addEventListener("submit", createAutomationPlan);
    refreshAutomationActivity();


    /* PHASE 6 — PERSISTENT REMINDERS, NOTIFICATIONS & WORKFLOW HISTORY */
    const reminderForm = document.getElementById("reminder-form");
    const reminderTitle = document.getElementById("reminder-title");
    const reminderDue = document.getElementById("reminder-due");
    const reminderButton = document.getElementById("reminder-create-button");
    const reminderStatus = document.getElementById("reminder-status");
    const reminderList = document.getElementById("reminder-list");
    const remindersEnabled = document.getElementById("reminders-enabled");
    const browserNotificationsEnabled = document.getElementById("browser-notifications-enabled");
    const notificationSettingsStatus = document.getElementById("notification-settings-status");
    const notificationList = document.getElementById("notification-list");
    const workflowStatus = document.getElementById("workflow-status");
    const workflowList = document.getElementById("workflow-list");
    let phase6NotificationPolling = false;

    async function phase6Request(url, method = "GET", payload) {
      const response = await fetch(url, {
        method,
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Accept": "application/json"
        },
        body: payload ? JSON.stringify(payload) : undefined
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "The request could not be completed.");
      return data;
    }

    function phase6Empty(container, message) {
      container.replaceChildren(automationNode("p", "phase6-empty", message));
    }

    function phase6FormatDate(value) {
      if (!value) return "Time unavailable";
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
    }

    async function refreshPhase6Reminders() {
      try {
        const data = await phase6Request("/api/reminders");
        reminderStatus.textContent = "Reminders loaded.";
        reminderList.replaceChildren();
        if (!data.reminders.length) {
          phase6Empty(reminderList, "No active reminders.");
          return;
        }
        data.reminders.forEach((reminder) => {
          const row = automationNode("div", "phase6-item");
          const main = automationNode("div", "phase6-item-main");
          main.appendChild(automationNode("div", "phase6-item-title", reminder.title));
          main.appendChild(automationNode("div", "phase6-item-meta", phase6FormatDate(reminder.due_at) + " · " + reminder.status));
          const actions = automationNode("div", "phase6-actions");
          const complete = automationNode("button", "phase6-small-action", "COMPLETE");
          complete.type = "button";
          complete.addEventListener("click", () => updatePhase6Reminder(reminder.id, "completed", complete));
          const cancel = automationNode("button", "phase6-small-action", "CANCEL");
          cancel.type = "button";
          cancel.addEventListener("click", () => updatePhase6Reminder(reminder.id, "cancelled", cancel));
          actions.append(complete, cancel);
          row.append(main, actions);
          reminderList.appendChild(row);
        });
      } catch (error) {
        reminderStatus.textContent = error.message || "Could not load reminders.";
      }
    }

    async function updatePhase6Reminder(id, status, button) {
      button.disabled = true;
      try {
        await phase6Request("/api/reminders/" + encodeURIComponent(id) + "/status", "POST", { status });
        reminderStatus.textContent = status === "completed" ? "Reminder completed." : "Reminder cancelled.";
        await refreshPhase6Reminders();
      } catch (error) {
        reminderStatus.textContent = error.message || "Could not update reminder.";
        button.disabled = false;
      }
    }

    async function createPhase6Reminder(event) {
      event.preventDefault();
      if (reminderButton.disabled) return;
      const title = reminderTitle.value.trim();
      const localValue = reminderDue.value;
      const due = localValue ? new Date(localValue) : null;
      if (!title || !due || Number.isNaN(due.getTime())) {
        reminderStatus.textContent = "Enter a reminder title and a valid local date/time.";
        return;
      }
      if (due.getTime() <= Date.now()) {
        reminderStatus.textContent = "Choose a future date and time.";
        return;
      }
      reminderButton.disabled = true;
      reminderStatus.textContent = "Saving reminder…";
      try {
        await phase6Request("/api/reminders", "POST", { title, due_at: due.toISOString() });
        reminderTitle.value = "";
        reminderDue.value = "";
        reminderStatus.textContent = "Reminder saved.";
        await refreshPhase6Reminders();
      } catch (error) {
        reminderStatus.textContent = error.message || "Reminder could not be saved.";
      } finally {
        reminderButton.disabled = false;
      }
    }

    async function savePhase6NotificationPreferences() {
      notificationSettingsStatus.textContent = "Saving notification preferences…";
      const wantsBrowser = browserNotificationsEnabled.checked;
      let browserPermissionNote = "";
      if (wantsBrowser) {
        if (!("Notification" in window)) {
          browserNotificationsEnabled.checked = false;
          browserPermissionNote = " This browser does not support desktop notifications; in-app alerts remain enabled.";
        } else {
          if (Notification.permission === "default") {
            const permission = await Notification.requestPermission();
            if (permission !== "granted") {
              browserNotificationsEnabled.checked = false;
              browserPermissionNote = " Browser permission was not granted; in-app alerts remain enabled.";
            }
          } else if (Notification.permission !== "granted") {
            browserNotificationsEnabled.checked = false;
            browserPermissionNote = " Allow notifications in browser site settings to enable desktop alerts; in-app alerts remain enabled.";
          }
        }
      }
      try {
        const data = await phase6Request("/api/notification-preferences", "PUT", {
          reminders_enabled: remindersEnabled.checked,
          browser_notifications_enabled: browserNotificationsEnabled.checked
        });
        remindersEnabled.checked = data.preferences.reminders_enabled;
        browserNotificationsEnabled.checked = data.preferences.browser_notifications_enabled;
        notificationSettingsStatus.textContent = "Preferences saved." + browserPermissionNote;
        await pollPhase6Notifications();
      } catch (error) {
        notificationSettingsStatus.textContent = error.message || "Preferences could not be saved.";
      }
    }

    async function loadPhase6NotificationPreferences() {
      try {
        const data = await phase6Request("/api/notification-preferences");
        remindersEnabled.checked = data.preferences.reminders_enabled;
        browserNotificationsEnabled.checked = data.preferences.browser_notifications_enabled;
        if (browserNotificationsEnabled.checked && (!("Notification" in window) || Notification.permission !== "granted")) {
          browserNotificationsEnabled.checked = false;
          notificationSettingsStatus.textContent = "Browser permission is currently unavailable. In-app alerts remain active.";
        }
      } catch (error) {
        notificationSettingsStatus.textContent = error.message || "Could not load notification settings.";
      }
    }

    function renderPhase6Notifications(items) {
      notificationList.replaceChildren();
      if (!items.length) {
        phase6Empty(notificationList, "No unread notifications.");
        return;
      }
      items.forEach((item) => {
        const row = automationNode("div", "phase6-item");
        const main = automationNode("div", "phase6-item-main");
        main.appendChild(automationNode("div", "phase6-item-title", item.title));
        main.appendChild(automationNode("div", "phase6-item-meta", item.body + " · " + phase6FormatDate(item.created_at)));
        const read = automationNode("button", "phase6-small-action", "MARK READ");
        read.type = "button";
        read.addEventListener("click", async () => {
          read.disabled = true;
          try {
            await phase6Request("/api/notifications/" + encodeURIComponent(item.id) + "/read", "POST", {});
            await pollPhase6Notifications();
          } catch (error) {
            notificationSettingsStatus.textContent = error.message || "Could not mark notification as read.";
            read.disabled = false;
          }
        });
        row.append(main, read);
        notificationList.appendChild(row);
      });
    }

    async function pollPhase6Notifications() {
      if (phase6NotificationPolling) return;
      phase6NotificationPolling = true;
      try {
        const data = await phase6Request("/api/notifications");
        renderPhase6Notifications(data.notifications || []);
        const prefs = data.preferences || {};
        if (prefs.browser_notifications_enabled && "Notification" in window && Notification.permission === "granted") {
          (data.newly_due || []).forEach((item) => {
            try {
              const notification = new Notification(item.title, { body: item.body, tag: "ajarvis-reminder-" + item.id });
              notification.onclick = () => { window.focus(); notification.close(); };
            } catch (_error) {
              notificationSettingsStatus.textContent = "A reminder was saved in the in-app notification centre, but the browser alert could not be shown.";
            }
          });
        }
      } catch (error) {
        notificationSettingsStatus.textContent = error.message || "Reminder notifications could not be refreshed.";
      } finally {
        phase6NotificationPolling = false;
      }
    }

    async function refreshPhase6Workflows() {
      try {
        const data = await phase6Request("/api/automation/workflows");
        workflowList.replaceChildren();
        const workflows = data.workflows || [];
        if (!workflows.length) {
          phase6Empty(workflowList, "No workflow history yet.");
          workflowStatus.textContent = "Workflow history is ready.";
          return;
        }
        workflows.forEach((workflow) => {
          const row = automationNode("div", "phase6-item");
          const main = automationNode("div", "phase6-item-main");
          main.appendChild(automationNode("div", "phase6-item-title", workflow.tools || "AJARVIS workflow"));
          main.appendChild(automationNode("div", "phase6-item-meta", workflow.step_count + " steps · " + workflow.status.replaceAll("_", " ") + " · Updated " + phase6FormatDate(workflow.updated_at)));
          row.appendChild(main);
          workflowList.appendChild(row);
        });
        workflowStatus.textContent = workflows.length + " saved workflow record(s). Interrupted workflows are review-only; create a new plan to continue safely.";
      } catch (error) {
        workflowStatus.textContent = error.message || "Could not load workflow history.";
      }
    }

    reminderForm.addEventListener("submit", createPhase6Reminder);
    remindersEnabled.addEventListener("change", () => {
      if (!remindersEnabled.checked) browserNotificationsEnabled.checked = false;
      savePhase6NotificationPreferences();
    });
    browserNotificationsEnabled.addEventListener("change", () => {
      if (browserNotificationsEnabled.checked && !remindersEnabled.checked) {
        remindersEnabled.checked = true;
        notificationSettingsStatus.textContent = "Reminder alerts are enabled because browser alerts depend on them.";
      }
      savePhase6NotificationPreferences();
    });
    if (!document.hidden) {
      refreshPhase6Reminders();
      loadPhase6NotificationPreferences().then(pollPhase6Notifications).catch(() => {});
      refreshPhase6Workflows();
    }
    window.setInterval(() => {
      if (!document.hidden) pollPhase6Notifications();
    }, 60000);


    /* PHASE 7 — ADVANCED REASONING & PERSONAL INTELLIGENCE */
    const phase7ProjectForm = document.getElementById("phase7-project-form");
    const phase7ProjectStatus = document.getElementById("phase7-project-status");
    const phase7ProjectList = document.getElementById("phase7-project-list");
    const phase7ProjectSelect = document.getElementById("phase7-task-project");
    const phase7TaskForm = document.getElementById("phase7-task-form");
    const phase7TaskStatus = document.getElementById("phase7-task-status");
    const phase7TaskList = document.getElementById("phase7-task-list");
    const phase7Metrics = document.getElementById("phase7-metrics");
    const phase7FocusStatus = document.getElementById("phase7-focus-status");
    const phase7FocusExplanation = document.getElementById("phase7-focus-explanation");
    const phase7Refresh = document.getElementById("phase7-refresh");
    let phase7Projects = [];
    let phase7Tasks = [];
    let phase7IncludeCompleted = false;

    async function phase7Request(url, method = "GET", payload) {
      const response = await fetch(url, {
        method,
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Accept": "application/json"
        },
        body: payload ? JSON.stringify(payload) : undefined
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "The personal intelligence request failed.");
      return data;
    }

    function phase7Empty(container, text) {
      container.replaceChildren(automationNode("p", "phase7-card-meta", text));
    }

    function phase7Date(value) {
      if (!value) return "No due date";
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
    }

    function renderPhase7Metrics(metrics) {
      phase7Metrics.replaceChildren();
      const items = [
        ["ACTIVE PROJECTS", metrics.active_projects || 0],
        ["OPEN TASKS", metrics.open_tasks || 0],
        ["OVERDUE", metrics.overdue_tasks || 0],
        ["IN PROGRESS", metrics.in_progress_tasks || 0]
      ];
      items.forEach(([label, value]) => {
        const card = automationNode("div", "phase7-metric");
        card.appendChild(automationNode("strong", "", value));
        card.appendChild(automationNode("span", "", label));
        phase7Metrics.appendChild(card);
      });
    }

    function renderPhase7Projects() {
      phase7ProjectList.replaceChildren();
      phase7ProjectSelect.replaceChildren();
      phase7ProjectSelect.appendChild(new Option("No project", ""));
      const active = phase7Projects.filter((project) => project.status === "active");
      active.forEach((project) => phase7ProjectSelect.appendChild(new Option(project.name, String(project.id))));
      if (!phase7Projects.length) {
        phase7Empty(phase7ProjectList, "Create a project to organise related tasks and context.");
        return;
      }
      phase7Projects.forEach((project) => {
        const card = automationNode("article", "phase7-card");
        const head = automationNode("div", "phase7-card-head");
        head.appendChild(automationNode("div", "phase7-card-title", project.name));
        head.appendChild(automationNode("span", "phase7-score", project.status.toUpperCase()));
        card.appendChild(head);
        if (project.objective) card.appendChild(automationNode("p", "phase7-card-meta", project.objective));
        if (project.status === "active" || project.status === "paused") {
          const button = automationNode("button", "phase7-action", project.status === "active" ? "PAUSE PROJECT" : "RESUME PROJECT");
          button.type = "button";
          button.addEventListener("click", () => updatePhase7Project(project.id, project.status === "active" ? "paused" : "active", button));
          card.appendChild(button);
        }
        phase7ProjectList.appendChild(card);
      });
    }

    function renderPhase7Tasks() {
      phase7TaskList.replaceChildren();
      const tasks = phase7Tasks;
      if (!tasks.length) {
        phase7Empty(phase7TaskList, phase7IncludeCompleted ? "No tasks recorded yet." : "No open tasks. Add a task or enjoy the clear queue.");
        return;
      }
      tasks.forEach((task) => {
        const card = automationNode("article", "phase7-card");
        const head = automationNode("div", "phase7-card-head");
        head.appendChild(automationNode("div", "phase7-card-title", task.title));
        head.appendChild(automationNode("span", "phase7-score", task.status === "completed" ? "DONE" : "SCORE " + task.priority_score));
        card.appendChild(head);
        card.appendChild(automationNode("p", "phase7-card-meta",
          (task.project_name ? task.project_name + " · " : "") +
          task.priority.toUpperCase() + " · " + task.status.replaceAll("_", " ") +
          " · " + phase7Date(task.due_at) +
          (task.effort_minutes ? " · " + task.effort_minutes + " min" : "")));
        if (task.details) card.appendChild(automationNode("p", "phase7-card-meta", task.details));
        card.appendChild(automationNode("p", "phase7-reason", task.priority_reason));
        if (task.status === "pending" || task.status === "in_progress") {
          const actions = automationNode("div", "phase7-card-actions");
          const start = automationNode("button", "phase7-action", task.status === "in_progress" ? "MOVE TO PENDING" : "START TASK");
          start.type = "button";
          start.addEventListener("click", () => updatePhase7Task(task.id, task.status === "in_progress" ? "pending" : "in_progress", start));
          const done = automationNode("button", "phase7-action", "MARK COMPLETE");
          done.type = "button";
          done.addEventListener("click", () => updatePhase7Task(task.id, "completed", done));
          actions.append(start, done);
          card.appendChild(actions);
        }
        phase7TaskList.appendChild(card);
      });
    }

    async function refreshPhase7Workspace() {
      phase7Refresh.disabled = true;
      phase7FocusStatus.textContent = "Refreshing personal focus…";
      try {
        const [focus, projects, tasks] = await Promise.all([
          phase7Request("/api/personal-intelligence/focus"),
          phase7Request("/api/projects"),
          phase7Request("/api/tasks" + (phase7IncludeCompleted ? "?include_completed=true" : ""))
        ]);
        phase7Projects = projects.projects || [];
        phase7Tasks = tasks.tasks || [];
        renderPhase7Metrics(focus.focus.metrics || {});
        phase7ProjectStatus.textContent = phase7Projects.length + " project(s) in your workspace.";
        phase7FocusExplanation.textContent = focus.focus.prioritisation || "Tasks are ordered by a transparent priority suggestion.";
        renderPhase7Projects();
        renderPhase7Tasks();
        phase7FocusStatus.textContent = phase7Tasks.length
          ? "Focus updated. Your highest-scoring open task appears first."
          : "Focus updated. No matching tasks yet.";
      } catch (error) {
        phase7FocusStatus.textContent = error.message || "Personal focus could not be refreshed.";
      } finally {
        phase7Refresh.disabled = false;
      }
    }

    async function createPhase7Project(event) {
      event.preventDefault();
      const button = document.getElementById("phase7-project-submit");
      const name = document.getElementById("phase7-project-name").value.trim();
      const objective = document.getElementById("phase7-project-objective").value.trim();
      button.disabled = true;
      phase7ProjectStatus.textContent = "Creating project…";
      try {
        await phase7Request("/api/projects", "POST", { name, objective });
        phase7ProjectForm.reset();
        phase7ProjectStatus.textContent = "Project created.";
        await refreshPhase7Workspace();
      } catch (error) {
        phase7ProjectStatus.textContent = error.message || "Project could not be created.";
      } finally {
        button.disabled = false;
      }
    }

    async function updatePhase7Project(id, status, button) {
      button.disabled = true;
      try {
        await phase7Request("/api/projects/" + encodeURIComponent(id) + "/status", "POST", { status });
        phase7ProjectStatus.textContent = "Project status updated.";
        await refreshPhase7Workspace();
      } catch (error) {
        phase7ProjectStatus.textContent = error.message || "Project could not be updated.";
        button.disabled = false;
      }
    }

    async function createPhase7Task(event) {
      event.preventDefault();
      const button = document.getElementById("phase7-task-submit");
      const title = document.getElementById("phase7-task-title").value.trim();
      const details = document.getElementById("phase7-task-details").value.trim();
      const project = phase7ProjectSelect.value;
      const dueValue = document.getElementById("phase7-task-due").value;
      const due = dueValue ? new Date(dueValue) : null;
      const effortValue = document.getElementById("phase7-task-effort").value;
      const effort = effortValue ? Number(effortValue) : null;
      if (due && Number.isNaN(due.getTime())) {
        phase7TaskStatus.textContent = "Enter a valid due date/time.";
        return;
      }
      button.disabled = true;
      phase7TaskStatus.textContent = "Saving task…";
      try {
        await phase7Request("/api/tasks", "POST", {
          title, details,
          project_id: project ? Number(project) : null,
          priority: document.getElementById("phase7-task-priority").value,
          due_at: due ? due.toISOString() : null,
          effort_minutes: effort
        });
        phase7TaskForm.reset();
        phase7TaskStatus.textContent = "Task saved. Focus has been recalculated.";
        await refreshPhase7Workspace();
      } catch (error) {
        phase7TaskStatus.textContent = error.message || "Task could not be saved.";
      } finally {
        button.disabled = false;
      }
    }

    async function updatePhase7Task(id, status, button) {
      button.disabled = true;
      try {
        await phase7Request("/api/tasks/" + encodeURIComponent(id) + "/status", "POST", { status });
        phase7TaskStatus.textContent = "Task status updated.";
        await refreshPhase7Workspace();
      } catch (error) {
        phase7TaskStatus.textContent = error.message || "Task could not be updated.";
        button.disabled = false;
      }
    }

    phase7ProjectForm.addEventListener("submit", createPhase7Project);
    phase7TaskForm.addEventListener("submit", createPhase7Task);
    phase7Refresh.addEventListener("click", refreshPhase7Workspace);
    document.querySelectorAll("[data-phase7-filter]").forEach((button) => {
      button.addEventListener("click", () => {
        phase7IncludeCompleted = button.dataset.phase7Filter === "all";
        document.querySelectorAll("[data-phase7-filter]").forEach((item) => item.classList.toggle("active", item === button));
        refreshPhase7Workspace();
      });
    });
    refreshPhase7Workspace();

    /* PHASE 4 — PERSONAL MEMORY MANAGER */
    const memoryForm = document.getElementById("memory-form");
    const memoryList = document.getElementById("memory-list");
    const memoryStatus = document.getElementById("memory-status");
    const saveMemoryButton = document.getElementById("save-memory-btn");

    async function loadPersonalMemories() {
      memoryStatus.textContent = "Loading saved memories…";
      memoryList.replaceChildren();
      try {
        const response = await fetch("/api/memories", { cache: "no-store" });
        if (response.status === 401) { window.location.replace("/login"); return; }
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Could not load personal memories.");
        const memories = Array.isArray(data.memories) ? data.memories : [];
        if (!memories.length) {
          memoryStatus.textContent = "No saved memories yet. Add a preference above or tell AJARVIS to remember something.";
          return;
        }
        memoryStatus.textContent = memories.length + " saved memor" + (memories.length === 1 ? "y" : "ies");
        memories.forEach((entry) => {
          const card = document.createElement("article");
          card.className = "memory-entry";
          const head = document.createElement("div");
          head.className = "memory-entry-head";
          const key = document.createElement("strong");
          key.textContent = entry.key;
          const remove = document.createElement("button");
          remove.type = "button";
          remove.className = "memory-delete";
          remove.textContent = "DELETE";
          remove.setAttribute("aria-label", "Delete memory " + entry.key);
          remove.addEventListener("click", () => deletePersonalMemory(entry.key, remove));
          const value = document.createElement("p");
          value.textContent = entry.value;
          const updated = document.createElement("small");
          updated.textContent = entry.updated_at ? "Updated " + new Date(entry.updated_at).toLocaleString() : "Saved memory";
          head.append(key, remove);
          card.append(head, value, updated);
          memoryList.appendChild(card);
        });
      } catch (error) {
        memoryStatus.textContent = error.message || "Personal memory is unavailable.";
      }
    }

    async function deletePersonalMemory(key, button) {
      if (!window.confirm("Delete the saved memory '" + key + "'?")) return;
      button.disabled = true;
      try {
        const response = await fetch("/api/memories/" + encodeURIComponent(key), {
          method: "DELETE",
          headers: { "X-CSRF-Token": csrfToken }
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Could not delete memory.");
        memoryStatus.textContent = "Memory deleted.";
        await loadPersonalMemories();
      } catch (error) {
        memoryStatus.textContent = error.message || "Could not delete memory.";
        button.disabled = false;
      }
    }

    memoryForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (saveMemoryButton.disabled) return;
      const key = document.getElementById("memory-key").value.trim();
      const value = document.getElementById("memory-value").value.trim();
      saveMemoryButton.disabled = true;
      memoryStatus.textContent = "Saving memory…";
      try {
        const response = await fetch("/api/memories", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
          body: JSON.stringify({ key, value })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Could not save memory.");
        memoryForm.reset();
        memoryStatus.textContent = "Saved '" + data.memory.key + "'.";
        await loadPersonalMemories();
      } catch (error) {
        memoryStatus.textContent = error.message || "Could not save memory.";
      } finally {
        saveMemoryButton.disabled = false;
      }
    });

    document.getElementById("refresh-memory-btn").addEventListener("click", loadPersonalMemories);
    if (!document.hidden) loadPersonalMemories();

    /* CLOCK */
    function updateClock() {
      const now = new Date();
      document.getElementById("clock").textContent = now.toLocaleTimeString();
    }
    setInterval(updateClock, 1000);
    updateClock();

    /* Shared real host telemetry for the live HUD. */
    function updateMeter(id,value){
      const el=document.getElementById(id),pct=Math.max(0,Math.min(100,Number(value)||0));
      el.style.width=pct+"%";el.setAttribute("aria-valuenow",String(Math.round(pct)));
    }
    async function updateSystemStats(){
      const updated=document.getElementById("telemetry-updated");
      try{
        const response=await fetch("/system_stats",{cache:"no-store",headers:{"Accept":"application/json"}});
        if(response.status===401){window.location.replace("/login");return;}
        const data=await response.json();if(!response.ok)throw new Error(data.error||"Telemetry unavailable");
        document.querySelector(".cpu").textContent="CPU: "+data.cpu+"% · "+data.cpu_cores+" logical cores";
        document.querySelector(".ram").textContent="RAM: "+data.memory+"% ("+data.memory_used_gb+" / "+data.memory_total_gb+" GB)";
        document.querySelector(".disk").textContent="Disk: "+data.disk+"% ("+data.disk_used_gb+" / "+data.disk_total_gb+" GB)";
        const battery=data.battery;
        document.querySelector(".battery").textContent=battery?"Battery: "+battery.percent+"% · "+(battery.plugged?"charging":"on battery"):"Battery: not available";
        document.getElementById("uptime-status").textContent="Uptime: "+data.uptime;
        document.getElementById("processor-status").textContent="Processor: "+String(data.processor||data.platform||"Unknown").slice(0,35)+(data.cpu_frequency_mhz?" · "+data.cpu_frequency_mhz+" MHz":"");
        updateMeter("cpu-meter",data.cpu);updateMeter("memory-meter",data.memory);updateMeter("disk-meter",data.disk);
        updated.textContent="Updated "+new Date(data.timestamp).toLocaleTimeString();
      }catch(error){updated.textContent="Telemetry offline · "+String(error.message||"retrying");}
    }
    if (!document.hidden) updateSystemStats();
    window.setInterval(() => {
      if (!document.hidden) updateSystemStats();
    }, 5000);

    /* VOICE SYSTEM - STARK PROTOCOL MODE */

    const core = document.querySelector(".core");



    /* BATTERY STATUS */
    if (navigator.getBattery) {
      navigator.getBattery().then(battery => {
        const updateBattery = () => {
          const pct = Math.round(battery.level * 100);
          const plug = battery.charging ? "⚡" : "🔋";
          document.querySelector(".battery").textContent = `Battery: ${plug} ${pct}%`;
        };
        updateBattery();
        battery.addEventListener('levelchange', updateBattery);
        battery.addEventListener('chargingchange', updateBattery);
      });
    }

    /* COMMAND HISTORY - fetch every 5s */
    function refreshHistory() {
      fetch('/command_history')
        .then(res => res.json())
        .then(data => {
          const log = document.getElementById("history-log");
          log.replaceChildren();
          const history = data.history || [];
          if (history.length === 0) {
            const emptyState = document.createElement("span");
            emptyState.style.color = "#546e7a";
            emptyState.textContent = "No commands yet.";
            log.appendChild(emptyState);
            return;
          }
          history.slice().reverse().forEach(entry => {
            const item = document.createElement("div");
            item.style.cssText = "border-left:2px solid #00f0ff;padding-left:8px;";
            const commandText = document.createElement("span");
            commandText.style.color = "#00f0ff";
            commandText.textContent = "▶ " + String(entry.command ?? "");
            const responseText = document.createElement("span");
            responseText.style.color = "#b2ebf2";
            responseText.textContent = String(entry.response ?? "");
            item.append(commandText, document.createElement("br"), responseText);
            log.appendChild(item);
          });
        });
    }
    if (!document.hidden) refreshHistory();
    window.setInterval(() => {
      if (!document.hidden) refreshHistory();
    }, 5000);

    /* USAGE ANALYTICS — dependency-free SVG renderer. */
    function updateAnalytics() {
      const root = document.getElementById("usageChart");
      if (!root) return;
      fetch("/analytics")
        .then((response) => {
          if (!response.ok) throw new Error("Analytics unavailable");
          return response.json();
        })
        .then((data) => {
          const labels = Array.isArray(data.labels) ? data.labels : [];
          const values = Array.isArray(data.data)
            ? data.data.map((value) => Math.max(0, Number(value) || 0))
            : [];
          const width = 720, height = 270;
          const left = 42, right = 16, top = 14, bottom = 54;
          const plotWidth = width - left - right;
          const plotHeight = height - top - bottom;
          const maxValue = Math.max(1, ...values);
          const step = values.length ? plotWidth / values.length : plotWidth;
          const namespace = "http://www.w3.org/2000/svg";
          const svg = document.createElementNS(namespace, "svg");
          svg.setAttribute("viewBox", "0 0 " + width + " " + height);
          svg.setAttribute("role", "img");
          svg.setAttribute("aria-label", "Usage analytics bar chart");
          svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

          const add = (tag, attrs, text) => {
            const element = document.createElementNS(namespace, tag);
            Object.entries(attrs || {}).forEach(([key, value]) => element.setAttribute(key, String(value)));
            if (text !== undefined) element.textContent = String(text);
            svg.appendChild(element);
            return element;
          };

          for (let tick = 0; tick <= 4; tick += 1) {
            const y = top + plotHeight - (plotHeight * tick / 4);
            add("line", { x1: left, x2: width - right, y1: y, y2: y, stroke: "rgba(0,240,255,.14)", "stroke-width": 1 });
            add("text", { x: left - 8, y: y + 4, "text-anchor": "end", fill: "#b2ebf2", "font-size": 11 }, Math.round(maxValue * tick / 4));
          }

          values.forEach((value, index) => {
            const barWidth = Math.max(3, step * .58);
            const barHeight = value / maxValue * plotHeight;
            const x = left + index * step + (step - barWidth) / 2;
            const y = top + plotHeight - barHeight;
            add("rect", { x, y, width: barWidth, height: Math.max(0, barHeight), rx: 3, fill: "rgba(0,240,255,.4)", stroke: "#00f0ff", "stroke-width": 1 });
            const label = String(labels[index] ?? "").slice(0, 18);
            add("text", { x: x + barWidth / 2, y: height - 27, "text-anchor": "middle", fill: "#00f0ff", "font-size": 10 }, label);
          });

          root.replaceChildren(svg);
          root.setAttribute("aria-label", "Usage analytics chart with " + values.length + " bars");
        })
        .catch(() => {
          root.textContent = "Usage analytics are temporarily unavailable.";
        });
    }
    if (!document.hidden) updateAnalytics();
    window.setInterval(() => {
      if (!document.hidden) updateAnalytics();
    }, 15000);

    document.addEventListener("visibilitychange", () => {
      if (document.hidden) return;
      refreshPhase6Reminders();
      refreshPhase6Workflows();
      loadPhase6NotificationPreferences().then(pollPhase6Notifications).catch(() => {});
      loadPersonalMemories();
      updateSystemStats();
      refreshHistory();
      updateAnalytics();
    });

    const username = document.body.dataset.user || "";
    const initialActive = document.body.dataset.active === "true";

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const bars = document.querySelectorAll(".bar");
    const aiStatus = document.querySelector(".ai-status");
    const transcriptBox = document.getElementById("transcript-box");
    const textInput = document.getElementById("text-command-input");
    const sendBtn = document.getElementById("send-command-btn");
    const voiceLanguageSelect = document.getElementById("local-voice-language");
    const voiceOutputToggle = document.getElementById("local-voice-output");
    const stopSpeechButton = document.getElementById("local-stop-speech");
    let recognition = null;
    let shouldListen = true;
    let recognitionBlocked = false;
    let recognitionStarting = false;
    let recognitionActive = false;
    let recognitionStartWatchdog = null;
    let recognitionRestartTimer = null;
    let lastHandledResultIndex = -1;
    let lastAcceptedTranscript = "";
    let lastAcceptedTranscriptAt = 0;
    let speechHold = false;
    let speechGeneration = 0;
    let state = initialActive ? "activated" : "idle";

    // Keep every recognition start behind one guarded entry point. This prevents
    // overlapping starts from onend, TTS completion, command completion, and taps.
    function startRecognitionSafely() {
      if (!recognition || !shouldListen || recognitionBlocked || speechHold
          || commandInProgress || recognitionStarting || recognitionActive) return false;

      if (recognitionRestartTimer) {
        window.clearTimeout(recognitionRestartTimer);
        recognitionRestartTimer = null;
      }

      recognitionStarting = true;
      try {
        recognition.start();
        if (recognitionStartWatchdog) window.clearTimeout(recognitionStartWatchdog);
        recognitionStartWatchdog = window.setTimeout(() => {
          if (recognitionStarting && !recognitionActive) {
            recognitionStarting = false;
            aiStatus.textContent = "Voice input did not start";
            const statusText = document.getElementById("mic-status");
            if (statusText) {
              statusText.style.display = "block";
              statusText.textContent = "VOICE INPUT DID NOT START — CHECK BROWSER MICROPHONE PERMISSION";
            }
          }
        }, 5000);
        return true;
      } catch (error) {
        recognitionStarting = false;
        if (recognitionStartWatchdog) {
          window.clearTimeout(recognitionStartWatchdog);
          recognitionStartWatchdog = null;
        }
        if (error && error.name !== "InvalidStateError") {
          console.warn("Speech recognition start failed:", error);
          aiStatus.textContent = "Voice input failed to start";
          const statusText = document.getElementById("mic-status");
          if (statusText) {
            statusText.style.display = "block";
            statusText.textContent = "VOICE INPUT FAILED — CHECK MICROPHONE PERMISSION";
          }
        }
        return false;
      }
    }

    function scheduleRecognitionRestart(delay = 450) {
      if (!recognition || !shouldListen || recognitionBlocked || speechHold || commandInProgress) return;
      if (recognitionRestartTimer) window.clearTimeout(recognitionRestartTimer);
      recognitionRestartTimer = window.setTimeout(() => {
        recognitionRestartTimer = null;
        startRecognitionSafely();
      }, delay);
    }

    try {
      const savedLanguage = window.localStorage.getItem("ajarvis.local.voice.language");
      if (savedLanguage && Array.from(voiceLanguageSelect.options).some((option) => option.value === savedLanguage)) {
        voiceLanguageSelect.value = savedLanguage;
      }
      voiceOutputToggle.checked = window.localStorage.getItem("ajarvis.local.voice.output") !== "false";
    } catch (_error) {
      // The voice controls still work if browser storage is restricted.
    }

    voiceLanguageSelect.addEventListener("change", () => {
      if (recognition) {
        recognition.lang = voiceLanguageSelect.value;
        // Re-arm after a permission/language failure or restart with the new locale.
        const shouldRestart = recognitionBlocked;
        recognitionBlocked = false;
        shouldListen = true;
        if (shouldRestart) {
          startRecognitionSafely();
        } else if (!speechHold) {
          try { recognition.stop(); } catch (_error) {}
        }
      }
      try { window.localStorage.setItem("ajarvis.local.voice.language", voiceLanguageSelect.value); } catch (_error) {}
      showToast("Voice language set to " + voiceLanguageSelect.options[voiceLanguageSelect.selectedIndex].text + ".");
    });
    voiceOutputToggle.addEventListener("change", () => {
      try { window.localStorage.setItem("ajarvis.local.voice.output", voiceOutputToggle.checked ? "true" : "false"); } catch (_error) {}
      if (!voiceOutputToggle.checked) stopSpokenReply();
      showToast(voiceOutputToggle.checked ? "Spoken replies enabled." : "Spoken replies muted.");
    });

    function stripWakePhrase(value) {
      return String(value || "").replace(
        /^(?:(?:hey|hi|hello|okay|ok)[,]?\s+)?(?:a\.?\s*j\.?\s*a\.?\s*r\.?\s*v\.?\s*i\.?\s*s\.?|j\.?\s*a\.?\s*r\.?\s*v\.?\s*i\.?\s*s\.?|ajarvis|jarvis)\b[\s,.:;!?-]*/i,
        ""
      ).trim();
    }

    function stopSpokenReply() {
      speechGeneration += 1;
      speechHold = false;
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      if (stopSpeechButton) stopSpeechButton.disabled = true;
      if (recognition && shouldListen && !recognitionBlocked) {
        scheduleRecognitionRestart(350);
      }
    }

    stopSpeechButton.addEventListener("click", stopSpokenReply);

    // Serialize voice requests so recognition cannot dispatch overlapping commands.
    let commandInProgress = false;
    async function processCommand(command) {
      if (commandInProgress) return null;
      commandInProgress = true;
      aiStatus.textContent = "Processing...";
      if ("speechSynthesis" in window && window.speechSynthesis.speaking) {
        speechGeneration += 1;
        speechHold = false;
        window.speechSynthesis.cancel();
        if (stopSpeechButton) stopSpeechButton.disabled = true;
      }
      if (recognition && shouldListen && !recognitionBlocked && !speechHold) {
        try { recognition.stop(); } catch (_error) {}
      }

      try {
        const res = await fetch('/command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
          body: JSON.stringify({ command })
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.response || data.error || "The command could not be processed.");
        }
        if (typeof data.response !== "string") {
          throw new Error("The server returned an invalid response.");
        }
        if (typeof data.active === "boolean") {
          state = data.active ? "activated" : "idle";
          core.style.boxShadow = data.active ? "0 0 140px #00ffff" : "0 0 40px #00ffff";
        }
        aiStatus.textContent = data.response.substring(0, 60) + (data.response.length > 60 ? '...' : '');
        speak(data.response);
        showToast(data.response);
        refreshHistory();
        return data.response;
      } catch (error) {
        aiStatus.textContent = "Command failed";
        showToast(error.message || "Could not reach AJARVIS. Check the connection and try again.");
        return null;
      } finally {
        commandInProgress = false;
        if (!speechHold && recognition && shouldListen && !recognitionBlocked) {
          scheduleRecognitionRestart(450);
        }
      }
    }

    async function executeTextCommand() {
      const command = textInput.value.trim();
      if (!command || sendBtn.disabled) return;

      transcriptBox.textContent = `"${command}" (Type)`;
      textInput.value = "";
      sendBtn.disabled = true;

      try {
        // Text and voice commands share the same explicit activation gate.
        const response = await processCommand(command);
        // processCommand returns null when fetch/server processing fails. Keep
        // the user's draft available for retry, but never overwrite newer text
        // they may have started typing while the request was in flight.
        if (response === null && !textInput.value.trim()) {
          textInput.value = command;
        }
      } finally {
        sendBtn.disabled = false;
      }
    }

    textInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") executeTextCommand();
    });
    sendBtn.addEventListener("click", executeTextCommand);

    if (SpeechRecognition) {
      recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = false;
      recognition.lang = voiceLanguageSelect.value || "en-IN";

      // idle → greeted → activated

      recognition.onstart = () => {
        recognitionStarting = false;
        recognitionActive = true;
        lastHandledResultIndex = -1;
        if (recognitionStartWatchdog) {
          window.clearTimeout(recognitionStartWatchdog);
          recognitionStartWatchdog = null;
        }
        aiStatus.textContent = state === "activated" ? "System Active" : (state === "greeted" ? "Awaiting Activation" : "Standby");
        const statusText = document.getElementById('mic-status');
        if(statusText) statusText.style.display = 'none';
        
        // Prevent WebRTC visualizer from locking the mic on mobile devices
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        if(!isMobile) {
            startMicReactiveSystem().catch(e => console.log(e));
        }
      };

      recognition.onerror = (event) => {
        recognitionStarting = false;
        recognitionActive = false;
        if (recognitionStartWatchdog) {
          window.clearTimeout(recognitionStartWatchdog);
          recognitionStartWatchdog = null;
        }
        const errorCode = String(event.error || "unknown");
        const statusText = document.getElementById("mic-status");
        if (errorCode === "not-allowed" || errorCode === "service-not-allowed") {
          recognitionBlocked = true;
          shouldListen = false;
          aiStatus.textContent = "Microphone permission required";
          if (statusText) statusText.textContent = "ALLOW MICROPHONE ACCESS TO USE VOICE";
          showToast("Microphone access is blocked. Allow it in your browser's site settings, then tap the core to retry.");
        } else if (errorCode === "audio-capture") {
          // Stop the automatic restart loop until an input device is reconnected.
          // The user can retry explicitly by tapping the reactor after checking the device.
          recognitionBlocked = true;
          shouldListen = false;
          aiStatus.textContent = "Microphone not found";
          if (statusText) statusText.textContent = "CONNECT A MICROPHONE OR HEADSET, THEN TAP THE CORE TO RETRY";
          showToast("No microphone input is available. Connect or select a microphone, then tap the core to retry.");

        } else if (errorCode === "language-not-supported") {
          recognitionBlocked = true;
          shouldListen = false;
          aiStatus.textContent = "Speech language unavailable";
          if (statusText) statusText.textContent = "SELECT ANOTHER VOICE LANGUAGE";
          showToast("This browser cannot recognize speech in the selected language. Choose another language below.");
        } else if (errorCode === "network") {
          recognitionBlocked = true;
          shouldListen = false;
          aiStatus.textContent = "Speech service unavailable";
          if (statusText) statusText.textContent = "CHECK CONNECTION AND TAP CORE TO RETRY";
          showToast("The browser speech service could not be reached. Check connectivity and tap the core to retry.");
        } else if (errorCode === "no-speech") {
          aiStatus.textContent = state === "activated" ? "System Active" : "No speech detected";
        } else if (errorCode !== "aborted") {
          aiStatus.textContent = "Voice input error";
          showToast("Voice input failed (" + errorCode + "). You can change the voice language or use the text command box.");
        }
        if (!shouldListen || recognitionBlocked) stopMicReactiveSystem();
      };

      recognition.onend = () => {
        recognitionStarting = false;
        recognitionActive = false;
        if (recognitionStartWatchdog) {
          window.clearTimeout(recognitionStartWatchdog);
          recognitionStartWatchdog = null;
        }
        if (!shouldListen || recognitionBlocked) stopMicReactiveSystem();
        scheduleRecognitionRestart(450);
      };

      recognition.onresult = async (event) => {
        const results = event.results;
        const startIndex = Number.isInteger(event.resultIndex)
          ? Math.max(0, event.resultIndex)
          : Math.max(0, results.length - 1);
        let transcript = "";

        for (let resultIndex = startIndex; resultIndex < results.length; resultIndex += 1) {
          const result = results[resultIndex];
          if (!result || !result.isFinal || resultIndex <= lastHandledResultIndex) continue;
          lastHandledResultIndex = resultIndex;

          const candidate = String(result[0]?.transcript || "")
            .trim()
            .replace(/\s+/g, " ")
            .toLowerCase();
          if (!candidate) continue;

          const now = Date.now();
          if (candidate === lastAcceptedTranscript && now - lastAcceptedTranscriptAt < 1800) continue;
          lastAcceptedTranscript = candidate;
          lastAcceptedTranscriptAt = now;
          transcript = candidate;
        }

        if (!transcript) return;
        console.log("Heard:", transcript);
        transcriptBox.textContent = `"${transcript}"`;

        /* =========================
           STATE 1 — IDLE
        ==========================*/
        if (state === "idle") {
          const startsWithWakePhrase =
            /^(?:(?:hey|hi|hello|okay|ok)[,]?\s+)?(?:ajarvis|jarvis)\b/i.test(transcript);

          if (startsWithWakePhrase) {
            const wakeCommand = stripWakePhrase(transcript);

            // Preserve the activation gate, but don't discard activation when
            // it is spoken in the same utterance as the wake phrase.
            if (/^system activate\b/i.test(wakeCommand)) {
              const activationReply = await processCommand(wakeCommand);
              if (activationReply && activationReply.toLowerCase().includes("activating system")) {
                state = "activated";
                core.classList.add("activate-ring");
                setTimeout(() => core.classList.remove("activate-ring"), 3600);
                aiStatus.textContent = "System Active";
                core.style.boxShadow = "0 0 140px #00ffff";
              }
            } else {
              state = "greeted";
              aiStatus.textContent = "Awaiting Activation";
              speak("Hello " + username + ". Awaiting system activation.");
              core.style.boxShadow = "0 0 100px #00ffff";
            }
          }

          return;
        }

        /* =========================
           STATE 2 — GREETED
        ==========================*/
        if (state === "greeted") {
          const activationCommand = stripWakePhrase(transcript) || transcript;
          if (/system activate/i.test(activationCommand)) {
            const activationReply = await processCommand("system activate");
            if (activationReply && activationReply.toLowerCase().includes("activating system")) {
              state = "activated";
              core.classList.add("activate-ring");
              setTimeout(() => core.classList.remove("activate-ring"), 3600);
              aiStatus.textContent = "System Active";
              core.style.boxShadow = "0 0 140px #00ffff";
            }
          }
          return;
        }

        /* =========================
           STATE 3 — ACTIVATED
        ==========================*/
        if (state === "activated") {

          // 🔴 Shutdown
          if (transcript.includes("system deactivate") ||
            transcript.includes("system shutdown") ||
            transcript.includes("system shut down")) {
            core.classList.add("shutdown-effect");
            setTimeout(() => {
              core.classList.remove("shutdown-effect");
            }, 1000);

            // Keep the browser state and server authorization in sync.
            await processCommand("system deactivate");
            state = "idle";
            aiStatus.textContent = "Standby";
            core.style.boxShadow = "0 0 40px #00ffff";
            return;
          }

          // 🔵 Normal Commands
          processCommand(transcript);

        }

      };

      // Handle mobile browsers requiring a physical tap to start audio
      document.getElementById('ai-core').addEventListener('click', () => {
        shouldListen = true;
        recognitionBlocked = false;
        recognition.lang = voiceLanguageSelect.value || "en-IN";
        if (speechHold || ("speechSynthesis" in window && window.speechSynthesis.speaking)) {
          speechGeneration += 1;
          speechHold = false;
          if ("speechSynthesis" in window) window.speechSynthesis.cancel();
          if (stopSpeechButton) stopSpeechButton.disabled = true;
        }
        startRecognitionSafely();
        const statusText = document.getElementById('mic-status');
        if (statusText) statusText.textContent = 'INITIALIZING...';

        // Also resume AudioContext for the visualizer if suspended.
        if (audioContext && audioContext.state === 'suspended') {
          audioContext.resume();
        }
      });
    } else {
      aiStatus.textContent = "Speech recognition unavailable";
      const statusText = document.getElementById("mic-status");
      if (statusText) statusText.textContent = "SPEECH UNAVAILABLE — USE TEXT COMMANDS";
    }

    /* Text to Speech Helper. Pause recognition during playback to avoid
       AJARVIS transcribing its own voice as the next command. */
    function speak(text) {
      if (!("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined"
          || !voiceOutputToggle.checked || !String(text ?? "").trim()) {
        return;
      }

      speechGeneration += 1;
      const generation = speechGeneration;
      speechHold = true;
      if (recognition && shouldListen && !recognitionBlocked) {
        try { recognition.stop(); } catch (_error) {}
      }

      // Replace queued speech so old utterances cannot overlap new replies.
      window.speechSynthesis.cancel();
      const speech = new SpeechSynthesisUtterance(String(text ?? "").trim().slice(0, 1800));
      const language = voiceLanguageSelect.value || "en-IN";
      speech.lang = language;
      speech.rate = 0.98;
      speech.pitch = 0.94;
      const voices = window.speechSynthesis.getVoices();
      const exactVoice = voices.find((voice) => voice.lang.toLowerCase() === language.toLowerCase());
      const sameLanguageVoice = voices.find((voice) => voice.lang.toLowerCase().startsWith(language.split("-")[0].toLowerCase()));
      if (exactVoice || sameLanguageVoice) speech.voice = exactVoice || sameLanguageVoice;

      const finishSpeech = () => {
        if (generation !== speechGeneration) return;
        speechHold = false;
        if (stopSpeechButton) stopSpeechButton.disabled = true;
        if (recognition && shouldListen && !recognitionBlocked) {
          scheduleRecognitionRestart(450);
        }
      };
      speech.onstart = () => {
        if (stopSpeechButton) stopSpeechButton.disabled = false;
      };
      speech.onend = finishSpeech;
      speech.onerror = finishSpeech;
      if (stopSpeechButton) stopSpeechButton.disabled = false;
      window.speechSynthesis.speak(speech);
    }

    /* Toast Notification */
    function showToast(message) {
      const container = document.getElementById('toast-container');
      const toast = document.createElement('div');
      toast.className = 'toast';

      const label = document.createElement('div');
      label.className = 'toast-label';
      label.textContent = 'A.JARVIS';

      const body = document.createElement('div');
      body.textContent = String(message ?? '');

      toast.append(label, body);
      container.appendChild(toast);

      // Auto dismiss after 4s
      setTimeout(() => {
        toast.classList.add('hide');
        setTimeout(() => toast.remove(), 400);
      }, 4000);
    }

    /* MIC REACTIVE EFFECT
       SpeechRecognition may restart many times during a single voice session.
       Keep exactly one analyser stream/context and release every resource on exit. */
    let audioContext = null;
    let analyser = null;
    let microphone = null;
    let microphoneStream = null;
    let dataArray = null;
    let audioStartPromise = null;
    let audioFrameId = null;
    let audioGeneration = 0;

    async function startMicReactiveSystem() {
      if (audioContext && audioContext.state !== "closed") {
        if (audioContext.state === "suspended") {
          try { await audioContext.resume(); } catch (_error) {}
        }
        return;
      }
      if (audioStartPromise) return audioStartPromise;

      const generation = audioGeneration;
      audioStartPromise = (async () => {
        let stream = null;
        let context = null;
        try {
          if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error("Microphone visualizer is unavailable in this browser.");
          }
          stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          if (generation !== audioGeneration) {
            stream.getTracks().forEach((track) => track.stop());
            return;
          }

          const AudioContextClass = window.AudioContext || window.webkitAudioContext;
          if (!AudioContextClass) throw new Error("Audio visualization is not supported in this browser.");
          context = new AudioContextClass();
          const nextAnalyser = context.createAnalyser();
          const nextMicrophone = context.createMediaStreamSource(stream);
          nextAnalyser.fftSize = 256;
          const nextDataArray = new Uint8Array(nextAnalyser.frequencyBinCount);
          nextMicrophone.connect(nextAnalyser);

          if (generation !== audioGeneration) {
            stream.getTracks().forEach((track) => track.stop());
            try { await context.close(); } catch (_error) {}
            return;
          }

          microphoneStream = stream;
          audioContext = context;
          analyser = nextAnalyser;
          microphone = nextMicrophone;
          dataArray = nextDataArray;
          animateVoice();
        } catch (error) {
          if (stream) stream.getTracks().forEach((track) => track.stop());
          if (context && context.state !== "closed") {
            try { await context.close(); } catch (_error) {}
          }
          throw error;
        }
      })();

      try {
        await audioStartPromise;
      } finally {
        audioStartPromise = null;
      }
    }

    function stopMicReactiveSystem() {
      audioGeneration += 1;
      if (audioFrameId !== null) {
        window.cancelAnimationFrame(audioFrameId);
        audioFrameId = null;
      }
      if (microphone) {
        try { microphone.disconnect(); } catch (_error) {}
        microphone = null;
      }
      if (microphoneStream) {
        microphoneStream.getTracks().forEach((track) => track.stop());
        microphoneStream = null;
      }
      const context = audioContext;
      audioContext = null;
      analyser = null;
      dataArray = null;
      if (context && context.state !== "closed") {
        context.close().catch(() => {});
      }
    }

    window.addEventListener("pagehide", stopMicReactiveSystem);

    function animateVoice() {
      if (!analyser || !dataArray || !audioContext || audioContext.state === "closed") return;
      audioFrameId = window.requestAnimationFrame(animateVoice);
      analyser.getByteFrequencyData(dataArray);

      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }

      const volume = sum / dataArray.length;
      const glowStrength = 40 + volume * 0.8;
      core.style.boxShadow = `0 0 ${glowStrength}px #00ffff`;

      const scale = 1 + volume / 600;
      core.style.transform = `scale(${scale})`;

      bars.forEach((bar, i) => {
        const height = 15 + (dataArray[i] / 255) * 60;
        bar.style.height = height + "px";
      });
    }

  