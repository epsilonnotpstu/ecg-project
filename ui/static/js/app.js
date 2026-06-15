/* CardioScan AI — ui/static/js/app.js */
(function () {
  "use strict";

  /* ── Dark / light theme ─────────────────────────────────────────────── */
  var root = document.documentElement;

  function _setThemeIcon(theme) {
    var icons = document.querySelectorAll(".theme-toggle i");
    icons.forEach(function (ico) {
      ico.className = theme === "dark" ? "fa-solid fa-sun" : "fa-solid fa-moon";
    });
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    localStorage.setItem("cs-theme", theme);
    _setThemeIcon(theme);
  }

  // Sync icon to whatever theme was set by the inline script
  _setThemeIcon(root.getAttribute("data-theme") || "light");

  document.querySelectorAll(".theme-toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var current = root.getAttribute("data-theme") || "light";
      applyTheme(current === "dark" ? "light" : "dark");
    });
  });

  /* ── Duration card selector ─────────────────────────────────────────── */
  document.querySelectorAll(".dur-card").forEach(function (card) {
    card.addEventListener("click", function () {
      var radio = document.getElementById(card.dataset.for);
      if (!radio) return;
      document.querySelectorAll(".dur-card").forEach(function (c) {
        c.classList.remove("selected");
      });
      card.classList.add("selected");
      radio.checked = true;
    });
  });

  /* ── Recording form → overlay + countdown ───────────────────────────── */
  var recForm = document.getElementById("recording-form");
  var overlay = document.getElementById("recording-overlay");

  if (recForm && overlay) {
    recForm.addEventListener("submit", function (e) {
      var chosen = recForm.querySelector('input[name="duration"]:checked');
      if (!chosen) {
        e.preventDefault();
        alert("Please select a recording duration first.");
        return;
      }

      var dur = parseInt(chosen.value, 10);
      overlay.classList.remove("d-none");
      overlay.style.display = "flex";

      var timerEl   = document.getElementById("rec-timer");
      var phaseEl   = document.getElementById("rec-phase");
      var remaining = dur;

      if (timerEl) {
        timerEl.textContent = remaining + "s";
        var tick = setInterval(function () {
          remaining -= 1;
          if (remaining <= 0) {
            clearInterval(tick);
            timerEl.textContent = "0s";
            if (phaseEl) phaseEl.textContent = "AI Analysis & Processing…";
          } else {
            timerEl.textContent = remaining + "s";
          }
        }, 1000);
      }

      var btn = document.getElementById("start-btn");
      if (btn) {
        btn.disabled = true;
        btn.innerHTML =
          '<span class="spinner-border spinner-border-sm me-2"></span>Recording…';
      }
    });
  }

  /* ── Animate AI distribution bars on page load ──────────────────────── */
  function animateBars() {
    document.querySelectorAll(".ai-dist-bar[data-pct]").forEach(function (bar) {
      var pct = parseFloat(bar.getAttribute("data-pct")) || 0;
      setTimeout(function () { bar.style.width = pct + "%"; }, 150);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", animateBars);
  } else {
    animateBars();
  }

  /* ── Auto-dismiss flash messages ────────────────────────────────────── */
  document.querySelectorAll(".alert-dismissible").forEach(function (el) {
    setTimeout(function () {
      var bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });

  /* ── Bootstrap tooltips ─────────────────────────────────────────────── */
  [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    .map(function (el) { return new bootstrap.Tooltip(el); });

})();
