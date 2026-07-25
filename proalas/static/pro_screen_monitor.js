(function () {
  function toggleMonitor(el) {
    if (!el || !el.classList.contains("pro-screen-monitor")) return;
    var revealed = !el.classList.contains("pro-screen-monitor--revealed");
    el.classList.toggle("pro-screen-monitor--revealed", revealed);
    var host = document.getElementById("pro-screen-monitor-host");
    var viewport = el.closest(".pro-chat-viewport");
    if (host) {
      host.classList.toggle("pro-screen-monitor-host--expanded", revealed);
      host.classList.toggle("pro-screen-monitor-board--expanded", revealed);
    }
    if (viewport) {
      viewport.classList.toggle("pro-chat-viewport--monitor-expanded", revealed);
    }
    var hint = el.querySelector(".pro-screen-monitor-hint");
    if (hint) {
      hint.textContent = revealed ? "再次点击恢复" : "点击放大原图（3×）";
    }
  }

  document.body.addEventListener("click", function (e) {
    var el = e.target.closest(".pro-screen-monitor");
    if (!el || el.classList.contains("pro-screen-monitor--empty")) return;
    e.stopPropagation();
    toggleMonitor(el);
  });

  document.body.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var el = e.target.closest(".pro-screen-monitor");
    if (!el || el.classList.contains("pro-screen-monitor--empty")) return;
    e.preventDefault();
    toggleMonitor(el);
  });
})();
