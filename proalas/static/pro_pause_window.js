(function () {
  function parseHHMM(text) {
    var m = /^(\d{1,2}):(\d{2})$/.exec((text || "").trim());
    if (!m) return null;
    var h = parseInt(m[1], 10);
    var mi = parseInt(m[2], 10);
    if (h > 23 || mi > 59) return null;
    return h * 60 + mi;
  }

  function formatHHMM(minutes) {
    minutes = Math.max(0, Math.min(1439, minutes | 0));
    var h = (minutes / 60) | 0;
    var m = minutes % 60;
    return (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m;
  }

  function initPauseWindow(root) {
    if (!root || root.dataset.pauseInit === "1") return;
    root.dataset.pauseInit = "1";

    var track = root.querySelector("#pro-pause-track");
    var rangeA = root.querySelector("#pro-pause-range-a");
    var rangeB = root.querySelector("#pro-pause-range-b");
    var thumbStart = root.querySelector("#pro-pause-thumb-start");
    var thumbEnd = root.querySelector("#pro-pause-thumb-end");
    var labelStart = root.querySelector("#pro-pause-start-label");
    var labelEnd = root.querySelector("#pro-pause-end-label");
    var msgEl = root.querySelector("#pro-pause-message");
    if (!track || !rangeA || !rangeB || !thumbStart || !thumbEnd) return;

    var startMin = parseHHMM(root.dataset.start) ?? 22 * 60;
    var endMin = parseHHMM(root.dataset.end) ?? 8 * 60;

    function pct(minutes) {
      return (minutes / 1440) * 100;
    }

    function setSegment(el, leftPct, widthPct) {
      el.style.left = leftPct + "%";
      el.style.width = Math.max(0, widthPct) + "%";
      el.style.display = widthPct > 0 ? "block" : "none";
    }

    function render() {
      var pStart = pct(startMin);
      var pEnd = pct(endMin);
      if (startMin <= endMin) {
        setSegment(rangeA, pStart, pEnd - pStart);
        rangeB.style.display = "none";
      } else {
        // 跨午夜：start→24:00 与 0:00→end 两段，避免单条宽度超过 100%
        setSegment(rangeA, pStart, 100 - pStart);
        setSegment(rangeB, 0, pEnd);
      }
      thumbStart.style.left = pStart + "%";
      thumbEnd.style.left = pEnd + "%";
      if (labelStart) labelStart.textContent = formatHHMM(startMin);
      if (labelEnd) labelEnd.textContent = formatHHMM(endMin);
    }

    function minuteFromClientX(clientX) {
      var rect = track.getBoundingClientRect();
      var ratio = (clientX - rect.left) / rect.width;
      ratio = Math.max(0, Math.min(1, ratio));
      return Math.round((ratio * 1440) / 15) * 15;
    }

    function bindThumb(thumb, which) {
      var dragging = false;
      function onMove(e) {
        if (!dragging) return;
        var min = minuteFromClientX(e.clientX);
        if (which === "start") {
          startMin = min;
        } else {
          endMin = min;
        }
        render();
      }
      function onUp() {
        dragging = false;
        document.removeEventListener("pointermove", onMove);
        document.removeEventListener("pointerup", onUp);
      }
      thumb.addEventListener("pointerdown", function (e) {
        e.preventDefault();
        dragging = true;
        thumb.setPointerCapture(e.pointerId);
        document.addEventListener("pointermove", onMove);
        document.addEventListener("pointerup", onUp);
      });
    }

    bindThumb(thumbStart, "start");
    bindThumb(thumbEnd, "end");
    render();

    function showMsg(text, ok) {
      if (!msgEl) return;
      msgEl.hidden = false;
      msgEl.textContent = text;
      msgEl.classList.toggle("pro-pause-foot--ok", !!ok);
      msgEl.classList.toggle("pro-pause-foot--err", !ok);
    }

    function postPause(url) {
      return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start: formatHHMM(startMin),
          end: formatHHMM(endMin),
        }),
      }).then(function (r) {
        return r.json().then(function (data) {
          return { status: r.status, data: data };
        });
      });
    }

    function refreshPausePanel() {
      if (window.htmx) {
        htmx.ajax("GET", "/app/pro/pause-window", {
          target: "#pro-pause-window-host",
          swap: "innerHTML",
        });
      }
    }

    var nowBtn = root.querySelector("#pro-pause-now-btn");
    if (nowBtn) {
      nowBtn.addEventListener("click", function () {
        nowBtn.disabled = true;
        fetch("/app/pro/pause/now", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ hours: 5 }),
        })
          .then(function (r) {
            return r.json().then(function (data) {
              return { data: data };
            });
          })
          .then(function (res) {
            var text =
              res.data.message ||
              res.data.error ||
              (res.data.ok ? "已立刻暂停 5 小时" : "操作失败");
            showMsg(text, !!res.data.ok);
            if (res.data.ok) refreshPausePanel();
          })
          .catch(function () {
            showMsg("请求失败", false);
          })
          .finally(function () {
            nowBtn.disabled = false;
          });
      });
    }

    var todayBtn = root.querySelector("#pro-pause-today-btn");
    if (todayBtn) {
      todayBtn.addEventListener("click", function () {
        todayBtn.disabled = true;
        postPause("/app/pro/pause/today")
          .then(function (res) {
            var text = res.data.message || res.data.error || (res.data.ok ? "已暂停" : "操作失败");
            showMsg(text, res.data.ok);
            if (res.data.ok) refreshPausePanel();
          })
          .catch(function () {
            showMsg("请求失败", false);
          })
          .finally(function () {
            todayBtn.disabled = false;
          });
      });
    }

    var dailyBtn = root.querySelector("#pro-pause-daily-btn");
    if (dailyBtn) {
      dailyBtn.addEventListener("click", function () {
        dailyBtn.disabled = true;
        postPause("/app/pro/pause/daily")
          .then(function (res) {
            showMsg(res.data.message || res.data.error || "已保存", !!res.data.ok);
            if (res.data.ok) refreshPausePanel();
          })
          .catch(function () {
            showMsg("请求失败", false);
          })
          .finally(function () {
            dailyBtn.disabled = false;
          });
      });
    }

    var cancelDailyBtn = root.querySelector("#pro-pause-daily-cancel-btn");
    if (cancelDailyBtn) {
      cancelDailyBtn.addEventListener("click", function () {
        cancelDailyBtn.disabled = true;
        fetch("/app/pro/pause/daily/cancel", { method: "POST" })
          .then(function (r) {
            return r.json().then(function (data) {
              return { data: data };
            });
          })
          .then(function (res) {
            showMsg(res.data.message || "已取消", !!res.data.ok);
            refreshPausePanel();
          })
          .catch(function () {
            showMsg("请求失败", false);
          })
          .finally(function () {
            cancelDailyBtn.disabled = false;
          });
      });
    }
  }

  function scan() {
    var root = document.getElementById("pro-pause-window-card");
    if (root) initPauseWindow(root);
  }

  document.addEventListener("DOMContentLoaded", scan);
  document.body.addEventListener("htmx:afterSwap", function (ev) {
    if (!ev.detail || !ev.detail.target) return;
    var tid = ev.detail.target.id;
    // 整页换入 main-pane（首屏 SSR）或仅刷新暂停槽时都要初始化
    if (tid === "pro-pause-window-host" || tid === "main-pane") {
      scan();
    }
  });
})();
