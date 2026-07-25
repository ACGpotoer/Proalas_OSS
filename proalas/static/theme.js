(function () {
  function readCookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  function normalizePref(p) {
    if (p === "light" || p === "dark" || p === "auto" || p === "zen") return p;
    return "auto";
  }

  function effectiveTheme(pref) {
    if (pref === "light" || pref === "dark" || pref === "zen") return pref;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyFromPref(pref) {
    pref = normalizePref(pref);
    document.documentElement.setAttribute("data-theme-pref", pref);
    document.documentElement.setAttribute("data-theme", effectiveTheme(pref));
    try {
      window.dispatchEvent(
        new CustomEvent("proalas-theme-change", {
          detail: { pref: pref, theme: effectiveTheme(pref) },
        })
      );
    } catch (e) {
      /* ignore */
    }
  }

  function persistPref(pref) {
    document.cookie =
      "proalas_theme=" +
      encodeURIComponent(normalizePref(pref)) +
      ";path=/;max-age=31536000;SameSite=Lax";
  }

  function syncSelects(pref) {
    pref = normalizePref(pref);
    document.querySelectorAll(".theme-select").forEach(function (sel) {
      sel.value = pref;
    });
  }

  window.proalasSetTheme = function (pref) {
    persistPref(pref);
    applyFromPref(pref);
    syncSelects(pref);
  };

  var initial = normalizePref(readCookie("proalas_theme") || "auto");
  applyFromPref(initial);

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
    var pref = document.documentElement.getAttribute("data-theme-pref") || "auto";
    if (normalizePref(pref) === "auto") {
      document.documentElement.setAttribute("data-theme", effectiveTheme("auto"));
      try {
        window.dispatchEvent(
          new CustomEvent("proalas-theme-change", {
            detail: { pref: "auto", theme: effectiveTheme("auto") },
          })
        );
      } catch (e) {
        /* ignore */
      }
    }
  });

  function wireSelects() {
    document.querySelectorAll(".theme-select").forEach(function (sel) {
      sel.value = document.documentElement.getAttribute("data-theme-pref") || "auto";
      sel.addEventListener("change", function () {
        window.proalasSetTheme(this.value);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireSelects);
  } else {
    wireSelects();
  }
})();
