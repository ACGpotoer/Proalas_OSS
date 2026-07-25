(function () {
  var STORAGE_KEY = "proalas_fleet_team_tab";

  function activateTeam(root, teamNo) {
    if (!root) return;
    var tabs = root.querySelectorAll(".fleet-team-tab");
    var panels = root.querySelectorAll(".fleet-team-panel");
    tabs.forEach(function (tab) {
      var on = tab.getAttribute("data-team") === String(teamNo);
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
    panels.forEach(function (panel) {
      var on = panel.getAttribute("data-team-panel") === String(teamNo);
      panel.classList.toggle("is-active", on);
      if (on) {
        panel.removeAttribute("hidden");
      } else {
        panel.setAttribute("hidden", "");
      }
    });
    try {
      localStorage.setItem(STORAGE_KEY, String(teamNo));
    } catch (e) {}
  }

  function initFleetPanel(root) {
    if (!root || !root.querySelector(".fleet-team-tab")) return;
    var saved = null;
    try {
      saved = localStorage.getItem(STORAGE_KEY);
    } catch (e) {}
    if (saved && root.querySelector('.fleet-team-tab[data-team="' + saved + '"]')) {
      activateTeam(root, saved);
    }
  }

  document.addEventListener("click", function (e) {
    var tab = e.target.closest(".fleet-team-tab");
    if (!tab) return;
    var root = tab.closest("#pro-fleet-panel");
    if (!root) return;
    activateTeam(root, tab.getAttribute("data-team"));
  });

  document.addEventListener("DOMContentLoaded", function () {
    initFleetPanel(document.getElementById("pro-fleet-panel"));
  });

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (t.id === "pro-fleet-host") {
      initFleetPanel(t.querySelector("#pro-fleet-panel"));
      return;
    }
    if (t.id === "pro-fleet-panel") {
      initFleetPanel(t);
      return;
    }
    if (t.id === "main-pane") {
      initFleetPanel(t.querySelector("#pro-fleet-panel"));
    }
  });
})();
