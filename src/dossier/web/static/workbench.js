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
          window.setTimeout(function () {
            window.location.reload();
          }, 400);
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

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.body;
    var jobId = root.getAttribute("data-job-id");
    if (jobId) connectJob(jobId);
  });
})();
