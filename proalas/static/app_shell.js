(function () {
  var SIDEBAR_KEY = "dap_sidebar_collapsed";
  var sidebar = document.getElementById("app-sidebar");
  var toggle = document.getElementById("sidebar-toggle");
  var mainPane = document.getElementById("main-pane");
  var titleEl = document.getElementById("app-title");
  var subtitleEl = document.getElementById("app-subtitle");

  function setCollapsed(collapsed) {
    if (!sidebar) return;
    sidebar.classList.toggle("app-sidebar--collapsed", collapsed);
    if (toggle) {
      toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      var icon = toggle.querySelector(".sidebar-toggle-icon");
      if (icon) icon.textContent = collapsed ? "›" : "‹";
    }
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
    } catch (e) {}
  }

  if (toggle && sidebar) {
    var saved = false;
    try {
      saved = localStorage.getItem(SIDEBAR_KEY) === "1";
    } catch (e) {}
    setCollapsed(saved);
    toggle.addEventListener("click", function () {
      setCollapsed(!sidebar.classList.contains("app-sidebar--collapsed"));
    });
  }

  function activateNav(btn) {
    document.querySelectorAll(".sidebar-nav-item[data-pane]").forEach(function (el) {
      el.classList.remove("active");
    });
    btn.classList.add("active");
    var device = "";
    var deviceEl = document.querySelector(".sidebar-device");
    if (deviceEl) device = deviceEl.textContent || "";
    if (titleEl && btn.dataset.title) {
      titleEl.textContent = btn.dataset.title + (device ? " · " + device : "");
    }
    if (subtitleEl && btn.dataset.subtitle) {
      subtitleEl.textContent = btn.dataset.subtitle;
    }
    if (mainPane) {
      if (btn.dataset.pane === "original") {
        mainPane.classList.add("main-pane--iframe");
      } else {
        mainPane.classList.remove("main-pane--iframe");
      }
    }
  }

  function loadPane(url, btn) {
    if (!url || !mainPane) return;
    activateNav(btn);
    if (window.htmx && typeof window.htmx.ajax === "function") {
      window.htmx.ajax("GET", url, { target: "#main-pane", swap: "innerHTML" });
      return;
    }
    // CDN/本地 htmx 未加载时的兜底：仍要能切到原版 Alas
    fetch(url, { credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.text();
      })
      .then(function (html) {
        mainPane.innerHTML = html;
        document.body.dispatchEvent(
          new CustomEvent("htmx:afterSwap", { detail: { target: mainPane } })
        );
        if (btn.dataset.pane === "pro") {
          setTimeout(function () {
            processProPane(mainPane);
          }, 30);
        }
      })
      .catch(function (err) {
        mainPane.innerHTML =
          '<p class="error" style="padding:24px">页面加载失败：' +
          String(err) +
          "（请确认原版 Alas WebUI 已在后台启动）</p>";
      });
  }

  document.querySelectorAll(".sidebar-nav-item[data-pane]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      loadPane(btn.dataset.url, btn);
    });
  });

  function focusAlasLockedConfig() {
    var focus = window.__dapFocusAlasConfig;
    if (typeof focus === "function") {
      focus();
      setTimeout(focus, 300);
      return;
    }
    var iframe = document.getElementById("alas-iframe");
    if (iframe) {
      try {
        iframe.contentWindow.postMessage({ type: "dap:focus-config" }, "*");
      } catch (e) {}
    }
  }

  function processProPane(root) {
    if (!root || !window.htmx) return;
    try {
      window.htmx.process(root);
    } catch (e) {}
    // 换入后强制拉取一次带 hx-get 的空槽（revealed 偶发不触发时兜底）
    root.querySelectorAll("[hx-get]").forEach(function (el) {
      if (el.id === "pro-screen-monitor-host" && el.children.length > 1) return;
      try {
        window.htmx.trigger(el, "revealed");
      } catch (e2) {}
    });
  }

  document.body.addEventListener("htmx:afterSwap", function (ev) {
    if (!ev.detail || !ev.detail.target || ev.detail.target.id !== "main-pane") return;
    var active = document.querySelector(".sidebar-nav-item[data-pane].active");
    if (active && active.dataset.pane === "original") {
      setTimeout(focusAlasLockedConfig, 50);
      setTimeout(focusAlasLockedConfig, 600);
    }
    if (active && active.dataset.pane === "pro") {
      setTimeout(function () {
        processProPane(ev.detail.target);
      }, 30);
    }
  });

  // 首次进入：main-pane 自身 hx-load 换入后也处理
  document.body.addEventListener("htmx:load", function () {
    if (mainPane && mainPane.querySelector(".pro-workspace")) {
      processProPane(mainPane);
    }
  });
})();
