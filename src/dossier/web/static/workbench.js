(function () {
  function connectJob(jobId) {
    if (!jobId) return;
    var strip = document.getElementById("job-strip");
    if (!strip) return;
    var line = strip.querySelector("[data-job-line]");
    var meta = strip.querySelector("[data-job-meta]");
    var src = new EventSource("/api/jobs/" + encodeURIComponent(jobId) + "/events");
    src.onmessage = function (ev) {
      try {
        var data = JSON.parse(ev.data);
      } catch (e) {
        return;
      }
      if (data.kind === "eof") {
        src.close();
        if (data.status === "done" || data.status === "error") {
          if (document.getElementById("job-result")) refreshJobRegion();
          else window.setTimeout(function () { window.location.reload(); }, 400);
        }
        return;
      }
      strip.classList.remove("idle");
      if (line && data.line) line.textContent = data.line;
      else if (line && data.title) {
        line.textContent = data.title + (data.detail ? " · " + data.detail : "");
      } else if (line && data.text) line.textContent = data.text;
      if (meta) {
        var bits = [];
        if (data.kind) bits.push(data.kind);
        if (typeof data.done === "number") {
          bits.push(data.done + "/" + (data.total || "?"));
        }
        if (data.status) bits.push(data.status);
        meta.textContent = bits.join(" · ");
      }
    };
    src.onerror = function () {
      /* browser retries; leave strip as-is */
    };
  }

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-checks]");
    if (!btn) return;
    var actions = btn.closest(".check-actions");
    if (!actions) return;
    var group = actions.nextElementSibling;
    if (!group || !group.classList.contains("checks")) return;
    var on = btn.getAttribute("data-checks") === "all";
    group.querySelectorAll('input[type="checkbox"]:not(:disabled)').forEach(function (box) {
      box.checked = on;
    });
  });

  function refreshJobRegion() {
    fetch(window.location.href, { headers: { Accept: "text/html" } })
      .then(function (resp) { return resp.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var next = doc.getElementById("job-result");
        var cur = document.getElementById("job-result");
        if (next && cur) cur.replaceWith(next);
        var strip = doc.getElementById("job-strip");
        var curStrip = document.getElementById("job-strip");
        if (strip && curStrip) curStrip.replaceWith(strip);
        ["spec", "question", "posting"].forEach(function (name) {
          var live = document.querySelector("textarea[name='" + name + "']");
          var fresh = doc.querySelector("textarea[name='" + name + "']");
          if (live && fresh && !live.value.trim()) live.value = fresh.value;
        });
        document.querySelectorAll("form button").forEach(function (live) {
          var label = (live.textContent || "").trim();
          var fresh = null;
          doc.querySelectorAll("form button").forEach(function (btn) {
            if ((btn.textContent || "").trim() === label) fresh = btn;
          });
          if (fresh) live.disabled = fresh.disabled;
        });
      })
      .catch(function () { window.location.reload(); });
  }

  document.addEventListener("keydown", function (ev) {
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    var tag = (ev.target && ev.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || ev.target.isContentEditable) return;
    var key = (ev.key || "").toLowerCase();
    if (!key || key.length !== 1) return;
    var target = document.querySelector("[data-key='" + key + "']");
    if (!target) return;
    ev.preventDefault();
    target.click();
  });

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-copy]");
    if (!btn) return;
    var node = document.getElementById(btn.getAttribute("data-copy"));
    if (!node) return;
    var text = node.textContent || "";
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(function () {});
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.body;
    var jobId = root.getAttribute("data-job-id");
    if (jobId) connectJob(jobId);
  });
})();
