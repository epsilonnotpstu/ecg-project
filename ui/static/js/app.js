/* CardioScan AI – ui/static/js/app.js */
(function () {
  "use strict";

  /* ── Duration card selector ─────────────────────────────────────────── */
  document.querySelectorAll(".dur-card").forEach(function (card) {
    card.addEventListener("click", function () {
      const radio = document.getElementById(card.dataset.for);
      if (!radio) return;
      document.querySelectorAll(".dur-card").forEach(function (c) {
        c.classList.remove("selected");
      });
      card.classList.add("selected");
      radio.checked = true;
    });
  });

  /* ── Recording form → show overlay + countdown ───────────────────────── */
  const recForm = document.getElementById("recording-form");
  const overlay = document.getElementById("recording-overlay");

  if (recForm && overlay) {
    recForm.addEventListener("submit", function (e) {
      /* validate a duration is chosen */
      const chosen = recForm.querySelector('input[name="duration"]:checked');
      if (!chosen) {
        e.preventDefault();
        alert("Please select a recording duration first.");
        return;
      }

      const dur = parseInt(chosen.value, 10);

      overlay.classList.remove("d-none");
      overlay.style.display = "flex";

      /* start countdown */
      const timerEl = document.getElementById("rec-timer");
      let remaining  = dur;
      if (timerEl) {
        timerEl.textContent = remaining + "s";
        const tick = setInterval(function () {
          remaining -= 1;
          if (remaining <= 0) {
            clearInterval(tick);
            timerEl.textContent = "Processing…";
          } else {
            timerEl.textContent = remaining + "s";
          }
        }, 1000);
      }

      /* disable start button */
      const btn = document.getElementById("start-btn");
      if (btn) {
        btn.disabled = true;
        btn.innerHTML =
          '<span class="spinner-border spinner-border-sm me-2"></span>Starting…';
      }
    });
  }

  /* ── Auto-dismiss flash messages ────────────────────────────────────── */
  document.querySelectorAll(".alert-dismissible").forEach(function (el) {
    setTimeout(function () {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });

  /* ── Bootstrap tooltips ─────────────────────────────────────────────── */
  var ttEls = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  ttEls.map(function (el) {
    return new bootstrap.Tooltip(el);
  });
})();
