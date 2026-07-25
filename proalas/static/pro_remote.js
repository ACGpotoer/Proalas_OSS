(function () {
  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  async function postJson(url, body) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try {
      data = await resp.json();
    } catch (e) {}
    return { ok: resp.ok && data.ok !== false, status: resp.status, data: data };
  }

  async function startRemote() {
    const btn = qs("#remote-start-btn");
    const oldText = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = "准备中约1分钟…";
    }
    try {
      const r = await postJson("/app/pro/remote/start", {});
      if (!r.ok) {
        alert((r.data && (r.data.error || r.data.message)) || "开启远控失败");
        return;
      }
      if (r.data && r.data.reused) {
        alert((r.data && r.data.message) || "远控已在进行中，将打开已有页面");
      }
      const url = (r.data && r.data.view_url) || "";
      if (url) {
        window.open(url, "_blank", "noopener");
      } else {
        alert((r.data && r.data.message) || "已开启");
      }
    } catch (e) {
      alert("网络错误：" + e);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = oldText || "临时远控通道";
      }
    }
  }

  async function stopRemote() {
    const shell = qs(".remote-shell");
    const ticket = shell ? shell.getAttribute("data-ticket") : "";
    const r = await postJson("/app/pro/remote/stop", { ticket: ticket || "" });
    alert((r.data && (r.data.message || r.data.error)) || (r.ok ? "已结束" : "结束失败"));
    if (r.ok) {
      window.location.href = "/app";
    }
  }

  function tickCountdown() {
    const el = qs("#remote-left");
    if (!el || el.getAttribute("data-ticking") === "1") return;
    el.setAttribute("data-ticking", "1");
    let n = parseInt(el.textContent || "0", 10);
    if (isNaN(n)) return;
    const timer = setInterval(function () {
      n -= 1;
      el.textContent = String(Math.max(0, n));
      if (n <= 0) {
        clearInterval(timer);
        alert("远控已到期");
        window.location.href = "/app";
      }
    }, 1000);
  }

  // 截图监控区每 5s HTMX 换血，不能只绑 DOMContentLoaded；用委托。
  document.addEventListener("click", function (ev) {
    const t = ev.target;
    if (!t || !t.closest) return;
    if (t.closest("#remote-start-btn")) {
      ev.preventDefault();
      startRemote();
      return;
    }
    if (t.closest("#remote-stop")) {
      ev.preventDefault();
      stopRemote();
    }
  });

  document.addEventListener("DOMContentLoaded", tickCountdown);
})();
