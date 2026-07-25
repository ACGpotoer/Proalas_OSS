(function () {
  var canvas = document.getElementById("login-terminal-canvas");
  if (!canvas) return;

  var ctx = canvas.getContext("2d");
  if (!ctx) return;

  var snippets = [
    "$ python alas.py --config 0D001",
    "INFO Scheduler: Start task `Commission`",
    "[OCR_OIL 0.031s] 14395",
    "[OCR_COIN 0.028s] 88210",
    "[BUILD_CUBE_COUNT] 1295",
    "[Event_PT] 42200",
    "ProalasBoatMessage nav 1/2: (980, 560)",
    "log_resource_sync -> UserData.json",
    "IO_Core ws_alas connected",
    "hx-post /pro/chat/message",
    "PlanMode=conservative",
    "device.screenshot()",
    "ui_goto_main()",
    "logger.attr('BOAT_RATE', 0.802)",
    "docker compose up -d proalas",
    "SELECT device_id FROM devices",
    "git fetch origin master",
    "MuMuPlayer12 nx_main",
  ];

  var fontSize = 13;
  var columns = 0;
  var drops = [];
  var speeds = [];
  var rafId = 0;
  var running = false;

  function isZen() {
    return document.documentElement.getAttribute("data-theme") === "zen";
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function shouldAnimate() {
    return !isZen() && !prefersReducedMotion();
  }

  function resize() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = window.innerWidth;
    var h = window.innerHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    columns = Math.max(8, Math.floor(w / (fontSize * 0.62)));
    drops = [];
    speeds = [];
    for (var i = 0; i < columns; i += 1) {
      drops[i] = Math.random() * -h;
      speeds[i] = 0.35 + Math.random() * 0.9;
    }
  }

  function pickSnippet() {
    return snippets[(Math.random() * snippets.length) | 0];
  }

  function draw() {
    if (!running) return;
    var w = canvas.clientWidth;
    var h = canvas.clientHeight;
    ctx.fillStyle = "rgba(8, 8, 10, 0.12)";
    ctx.fillRect(0, 0, w, h);
    ctx.font = fontSize + "px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

    for (var i = 0; i < columns; i += 1) {
      var x = (i / columns) * w + (Math.random() * 4 - 2);
      var y = drops[i];
      var text = pickSnippet();
      var shade = 40 + ((i * 17 + (y | 0)) % 120);
      var alpha = 0.08 + (i % 5) * 0.04;
      if (Math.random() < 0.018) {
        ctx.fillStyle = "rgba(244, 244, 245, " + (0.35 + Math.random() * 0.25) + ")";
      } else {
        ctx.fillStyle = "rgba(" + shade + ", " + shade + ", " + (shade + 8) + ", " + alpha + ")";
      }
      ctx.fillText(text.slice(0, 28), x, y);
      drops[i] += fontSize * speeds[i];
      if (drops[i] > h + 120) {
        drops[i] = -Math.random() * h * 0.4;
        speeds[i] = 0.35 + Math.random() * 0.9;
      }
    }
    rafId = requestAnimationFrame(draw);
  }

  function stop() {
    running = false;
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
    try {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    } catch (e) {
      /* ignore */
    }
  }

  function start() {
    if (running || !shouldAnimate()) return;
    running = true;
    resize();
    rafId = requestAnimationFrame(draw);
  }

  function syncToTheme() {
    if (shouldAnimate()) {
      start();
    } else {
      stop();
    }
  }

  window.addEventListener("resize", function () {
    if (running) resize();
  });
  window.addEventListener("proalas-theme-change", syncToTheme);

  syncToTheme();
})();
