(function() {
  var currentName = null;
  var cm = null;
  var ta = document.getElementById("yaml-editor");
  var listEl = document.getElementById("dashboard-list");
  var statusMsg = document.getElementById("status-msg");
  var previewFrame = document.getElementById("preview-frame");
  var delBtn = document.getElementById("del-btn");
  var renameBtn = document.getElementById("rename-btn");

  function setStatus(msg, type) {
    statusMsg.textContent = msg;
    statusMsg.className = type || "";
  }

  async function loadList() {
    try {
      var res = await fetch(LIST_URL);
      var list = await res.json();
      listEl.innerHTML = "";
      for (var d of list) {
        var li = document.createElement("li");
        li.textContent = d.name + (d.title ? " \u2014 " + d.title : "");
        li.dataset.name = d.name;
        li.addEventListener("click", function() { selectDashboard(this.dataset.name); });
        if (d.name === currentName) li.classList.add("active");
        listEl.appendChild(li);
      }
      if (list.length === 0) {
        delBtn.style.display = "none";
        renameBtn.style.display = "none";
      }
    } catch(e) {
      setStatus("Failed to load dashboard list", "error");
    }
  }

  async function selectDashboard(name) {
    currentName = name;
    document.querySelectorAll("#dashboard-list li").forEach(function(li) { li.classList.toggle("active", li.dataset.name === name); });
    delBtn.style.display = "";
    renameBtn.style.display = "";
    try {
      var res = await fetch(LIST_URL + "/" + encodeURIComponent(name) + ".yaml");
      var text = await res.text();
      if (cm) {
        cm.setValue(text);
      } else {
        ta.value = text;
      }
      setStatus("Editing: " + name, "");
      refreshPreview();
    } catch(e) {
      setStatus("Failed to load YAML", "error");
    }
  }

  function getYaml() {
    return cm ? cm.getValue() : ta.value;
  }

  async function saveDashboard() {
    if (!currentName) return;
    var yaml = getYaml();
    try {
      var res = await fetch(LIST_URL + "/" + encodeURIComponent(currentName), {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({yaml: yaml})
      });
      if (res.ok) {
        setStatus("Saved", "ok");
        refreshPreview();
        loadList();
      } else {
        var err = await res.json();
        setStatus(err.error || "Save failed", "error");
      }
    } catch(e) {
      setStatus("Save error: " + e.message, "error");
    }
  }

  async function refreshPreview() {
    if (!currentName) return;
    var yaml = getYaml();
    try {
      var res = await fetch(PREVIEW_URL, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({yaml: yaml})
      });
      if (res.ok) {
        var html = await res.text();
        previewFrame.srcdoc = html;
      } else {
        var err = await res.json();
        previewFrame.srcdoc = "<html><body style='background:#111;color:#f88;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;font-size:1.2rem'>" + (err.error || "Preview failed") + "</body></html>";
      }
    } catch(e) {
      previewFrame.srcdoc = "<html><body style='background:#111;color:#f88;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;font-size:1.2rem'>Preview error</body></html>";
    }
  }

  async function addDashboard() {
    var name = prompt("Dashboard name (URL-safe, e.g. living-room):");
    if (!name || !name.match(/^[a-zA-Z0-9_-]+$/)) {
      if (name) setStatus("Invalid name. Use letters, numbers, hyphens, underscores.", "error");
      return;
    }
    try {
      var res = await fetch(LIST_URL, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name: name})
      });
      if (res.ok) {
        await loadList();
        await selectDashboard(name);
        setStatus("Created: " + name, "ok");
      } else {
        var err = await res.json();
        setStatus(err.error || "Create failed", "error");
      }
    } catch(e) {
      setStatus("Create error: " + e.message, "error");
    }
  }

  async function deleteDashboard() {
    if (!currentName || !confirm('Delete "' + currentName + '"?')) return;
    try {
      var res = await fetch(LIST_URL + "/" + encodeURIComponent(currentName), {
        method: "DELETE"
      });
      if (res.ok) {
        currentName = null;
        if (cm) cm.setValue(""); else ta.value = "";
        previewFrame.srcdoc = "<html><body style='background:#111;color:#555;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;font-size:1.2rem'>Preview</body></html>";
        delBtn.style.display = "none";
        renameBtn.style.display = "none";
        setStatus("Deleted", "ok");
        await loadList();
      } else {
        var err = await res.json();
        setStatus(err.error || "Delete failed", "error");
      }
    } catch(e) {
      setStatus("Delete error: " + e.message, "error");
    }
  }

  async function renameDashboard() {
    if (!currentName) return;
    var newName = prompt('New name for "' + currentName + '" (URL-safe):', currentName);
    if (!newName || newName === currentName) return;
    if (!newName.match(/^[a-zA-Z0-9_-]+$/)) {
      setStatus("Invalid name. Use letters, numbers, hyphens, underscores.", "error");
      return;
    }
    try {
      var res = await fetch(LIST_URL + "/" + encodeURIComponent(currentName) + "/rename", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({new_name: newName})
      });
      if (res.ok) {
        currentName = newName;
        await loadList();
        setStatus("Renamed to: " + newName, "ok");
      } else {
        var err = await res.json();
        setStatus(err.error || "Rename failed", "error");
      }
    } catch(e) {
      setStatus("Rename error: " + e.message, "error");
    }
  }

  try {
    cm = CodeMirror.fromTextArea(ta, {
      mode: "yaml",
      theme: "default",
      lineNumbers: true,
      indentUnit: 2,
      tabSize: 2,
      lineWrapping: true,
      autoCloseBrackets: true,
      extraKeys: {"Ctrl-S": function() { saveDashboard(); }}
    });
  } catch(e) {
    cm = null;
    ta.style.display = "";
  }

  document.getElementById("add-btn").addEventListener("click", addDashboard);
  document.getElementById("del-btn").addEventListener("click", deleteDashboard);
  document.getElementById("rename-btn").addEventListener("click", renameDashboard);
  document.getElementById("save-btn").addEventListener("click", saveDashboard);
  document.getElementById("preview-btn").addEventListener("click", refreshPreview);
  document.getElementById("url-btn").addEventListener("click", function(){
    if(!currentName){setStatus("Select a dashboard first","error");return}
    var url = (PUBLIC_BASE || window.location.origin + BASE) + "/d/" + encodeURIComponent(currentName);
    navigator.clipboard.writeText(url).then(function(){
      setStatus("Copied: " + url, "ok");
    }).catch(function(){
      setStatus("Failed to copy URL", "error");
    });
  });

  loadList();
})();
