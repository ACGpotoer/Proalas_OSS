(function () {
  function detailEl() {
    return document.getElementById("pro-strategy-detail");
  }

  function openDetail(btn) {
    var root = detailEl();
    if (!root || !btn) return;
    var title = root.querySelector("#pro-strategy-detail-title");
    var body = root.querySelector("#pro-strategy-detail-body");
    var label = btn.getAttribute("data-plan-label") || btn.textContent.trim();
    var desc = btn.getAttribute("data-plan-desc") || "编写中";
    if (title) title.textContent = label;
    if (body) body.textContent = desc;
    root.classList.add("is-open");
    root.setAttribute("aria-hidden", "false");
    var closeBtn = root.querySelector(".pro-strategy-detail-close");
    if (closeBtn) closeBtn.focus();
  }

  function closeDetail() {
    var root = detailEl();
    if (!root) return;
    root.classList.remove("is-open");
    root.setAttribute("aria-hidden", "true");
  }

  function isOpen() {
    var root = detailEl();
    return !!(root && root.classList.contains("is-open"));
  }

  document.addEventListener(
    "click",
    function (e) {
      if (!isOpen()) return;
      if (e.target.closest("[data-strategy-close]")) {
        e.preventDefault();
        e.stopPropagation();
        closeDetail();
      }
    },
    true
  );

  document.body.addEventListener("click", function (e) {
    if (e.target.closest("[data-strategy-close]")) return;

    var btn = e.target.closest(".pro-strategy-btn");
    if (!btn) return;

    var bar = btn.closest(".pro-strategy-buttons");
    if (bar) {
      bar.querySelectorAll(".pro-strategy-btn").forEach(function (b) {
        var active = b === btn;
        b.classList.toggle("pro-strategy-btn--active", active);
        b.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }

    openDetail(btn);
  });

  document.body.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (isOpen()) closeDetail();
  });
})();
