/* ═══════════════════════════════════════════════════════════════════════════
   CardioScan AI — Real-Time ECG Monitor Engine  (v2 — fixed)

   Root-cause fixes over v1:
   1. _toY: replaced EMA-of-abs-deviation (decays to 0 → gain blow-up) with
      peak/trough envelope (instant attack, very slow decay).  Signal always
      fills ~45 % of canvas height, never clips.
   2. Rendering: min-max column accumulator.  When sweepSec is large (≥ 6 s)
      pxPerSample < 1 — multiple samples land in the same pixel column and the
      old line-per-sample code produced solid green fills.  Now we accumulate
      the signal envelope per CSS-pixel column and draw one segment per column
      (the same technique real GE/Philips monitors use).
   3. DPR: all drawing in CSS px via ctx.setTransform(dpr,0,0,dpr,0,0) —
      eliminates double-scaling on repeated resize calls.
   4. Drain rate: time-based (drain ≈ elapsed × sampleRate samples/frame,
      × 1.5 headroom) so the write-head stays in sync with wall clock.
   ═══════════════════════════════════════════════════════════════════════════ */

"use strict";

/* ── ECG Display Engine ──────────────────────────────────────────────────── */
class ECGDisplay {
  constructor(gridCanvas, traceCanvas, opts = {}) {
    this._gc = gridCanvas;
    this._tc = traceCanvas;

    this.sweepSec   = opts.sweepSec   || 8;
    this.sampleRate = opts.sampleRate || 250;

    this._dpr  = window.devicePixelRatio || 1;
    this._cssW = 0;
    this._cssH = 0;

    /* Column min/max buffer (CSS pixel coordinates, one entry per column) */
    this._colHigh = null;   // smallest Y value seen in this column (top of signal)
    this._colLow  = null;   // largest  Y value seen in this column (bottom)

    /* Write head */
    this._writeX  = 0;      // fractional CSS px position
    this._lastCol = -1;     // last integer column written

    /* Signal envelope (peak/trough tracking) */
    this._baseline = null;
    this._sigHigh  = null;  // peak envelope (fast attack, slow decay)
    this._sigLow   = null;  // trough envelope

    /* Sample queue and timing */
    this._queue         = [];
    this._paused        = false;
    this._lastFrameMs   = null;
    this._raf           = null;

    /* Appearance */
    this.TRACE_COLOR = "#00ff7f";
    this.BG_COLOR    = "#030d18";
    this.ERASER_CSS  = 30;   // blank gap (CSS px) ahead of write head

    this._resize();

    /* ResizeObserver fires on initial layout AND subsequent resizes —
       more reliable than window-resize for flex/grid containers. */
    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(() => this._resize());
      ro.observe(this._tc.parentElement || this._tc);
    } else {
      window.addEventListener("resize", () => this._resize());
    }

    this._drawGrid();
    this._raf = requestAnimationFrame((t) => this._frame(t));
  }

  /* ── Public API ──────────────────────────────────────────────────────── */

  push(v, ok) { this._queue.push({ v, ok: !!ok }); }
  pause()     { this._paused = true; }

  resume() {
    this._paused      = false;
    this._queue       = [];
    this._lastFrameMs = null;
    if (!this._raf) this._raf = requestAnimationFrame((t) => this._frame(t));
  }

  reset() {
    this._queue       = [];
    this._writeX      = 0;
    this._lastCol     = -1;
    this._lastFrameMs = null;
    this._baseline    = null;
    this._sigHigh     = null;
    this._sigLow      = null;
    if (this._colHigh) { this._colHigh.fill(NaN); this._colLow.fill(NaN); }
    const tx = this._tc.getContext("2d");
    tx.setTransform(this._dpr, 0, 0, this._dpr, 0, 0);
    tx.clearRect(0, 0, this._cssW, this._cssH);
  }

  destroy() {
    if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null; }
  }

  /* ── Resize ──────────────────────────────────────────────────────────── */

  _resize() {
    const dpr  = this._dpr;
    const wrap = this._tc.parentElement;
    if (!wrap) return;
    const cssW = wrap.clientWidth;
    const cssH = wrap.clientHeight;
    if (!cssW || !cssH) return;           // flex layout not computed yet
    if (cssW === this._cssW && cssH === this._cssH) return;

    this._cssW = cssW;
    this._cssH = cssH;

    for (const cvs of [this._gc, this._tc]) {
      cvs.width        = cssW * dpr;
      cvs.height       = cssH * dpr;
      cvs.style.width  = cssW + "px";
      cvs.style.height = cssH + "px";
      /* setTransform (not scale) — idempotent on repeated resize */
      cvs.getContext("2d").setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    this._pxPerSample = cssW / (this.sweepSec * this.sampleRate);
    this._colHigh     = new Float32Array(cssW).fill(NaN);
    this._colLow      = new Float32Array(cssW).fill(NaN);

    this._drawGrid();
    this.reset();
  }

  /* ── Grid ────────────────────────────────────────────────────────────── */

  _drawGrid() {
    const gx = this._gc.getContext("2d");
    const W  = this._cssW;
    const H  = this._cssH;
    if (!W || !H) return;

    gx.setTransform(this._dpr, 0, 0, this._dpr, 0, 0);
    gx.fillStyle = this.BG_COLOR;
    gx.fillRect(0, 0, W, H);

    /* Minor grid every 10 CSS px */
    gx.strokeStyle = "rgba(0,170,50,0.13)";
    gx.lineWidth   = 0.5;
    gx.beginPath();
    for (let x = 0; x <= W; x += 10) { gx.moveTo(x, 0); gx.lineTo(x, H); }
    for (let y = 0; y <= H; y += 10) { gx.moveTo(0, y); gx.lineTo(W, y); }
    gx.stroke();

    /* Major grid every 50 CSS px */
    gx.strokeStyle = "rgba(0,200,70,0.28)";
    gx.lineWidth   = 0.8;
    gx.beginPath();
    for (let x = 0; x <= W; x += 50) { gx.moveTo(x, 0); gx.lineTo(x, H); }
    for (let y = 0; y <= H; y += 50) { gx.moveTo(0, y); gx.lineTo(W, y); }
    gx.stroke();

    /* Center baseline */
    gx.strokeStyle = "rgba(0,220,80,0.45)";
    gx.lineWidth   = 0.6;
    gx.setLineDash([4, 8]);
    gx.beginPath();
    gx.moveTo(0, H / 2); gx.lineTo(W, H / 2);
    gx.stroke();
    gx.setLineDash([]);

    /* Speed / gain labels */
    gx.font      = "9px Inter, monospace";
    gx.fillStyle = "rgba(0,180,60,0.55)";
    gx.textAlign = "left";
    gx.fillText("25 mm/s", 8, H - 7);
    gx.textAlign = "right";
    gx.fillText("10 mm/mV", W - 8, H - 7);
  }

  /* ── Signal → canvas Y ───────────────────────────────────────────────── */

  _toY(v) {
    const H = this._cssH;

    if (this._baseline === null) {
      /* Bootstrap with ±80 ADC initial window (gives reasonable gain from
         the very first sample regardless of actual signal amplitude). */
      this._baseline = v;
      this._sigHigh  = v + 80;
      this._sigLow   = v - 80;
    }

    /* Baseline: very slow EMA (removes DC drift / breathing wander).
       τ = 1/0.0025 = 400 samples ≈ 1.6 s at 250 Hz. */
    this._baseline += (v - this._baseline) * 0.0025;

    /* Peak envelope — instant attack, very slow decay.
       Decays toward (baseline + 40) so a minimum upward swing is preserved.
       τ_decay ≈ 1/0.0002 = 5 000 samples ≈ 20 s at 250 Hz. */
    if (v > this._sigHigh) {
      this._sigHigh = v;
    } else {
      this._sigHigh += (this._baseline + 40 - this._sigHigh) * 0.0002;
    }

    /* Trough envelope — symmetric. */
    if (v < this._sigLow) {
      this._sigLow = v;
    } else {
      this._sigLow += (this._baseline - 40 - this._sigLow) * 0.0002;
    }

    /* Dynamic range.  Minimum 80 ADC units prevents extreme zoom on flat
       sections (e.g. before lead contact is made). */
    const range = Math.max(this._sigHigh - this._sigLow, 80);
    const mid   = (this._sigHigh + this._sigLow) * 0.5;

    /* Normalise to [-0.5, 0.5] then scale to 45 % of canvas height.
       R-peak (n=+0.5) sits at 27.5 % from top; baseline at 50 %;
       S-trough (n≈-0.1) a little below — matches clinical ECG appearance. */
    const n = Math.max(-0.5, Math.min(0.5, (v - mid) / range));
    return H * 0.5 - n * H * 0.45;
  }

  /* ── Animation loop ──────────────────────────────────────────────────── */

  _frame(ts) {
    if (this._paused) { this._raf = null; return; }

    /* Time-paced drain: consume roughly as many samples as have accumulated
       since the last frame (× 1.5 headroom to recover from bursts). */
    if (this._lastFrameMs === null) this._lastFrameMs = ts;
    const elapsedSec = Math.min((ts - this._lastFrameMs) / 1000, 0.25); // cap at 250 ms
    this._lastFrameMs = ts;

    const maxDrain = Math.min(
      this._queue.length,
      Math.ceil(elapsedSec * this.sampleRate * 1.5) + 4  // +4 guarantees at least 4
    );
    for (let i = 0; i < maxDrain; i++) {
      const { v, ok } = this._queue.shift();
      this._ingestSample(v, ok);
    }

    this._redraw();
    this._raf = requestAnimationFrame((t) => this._frame(t));
  }

  /* ── Ingest one sample into column buffer ────────────────────────────── */

  _ingestSample(v, ok) {
    if (!this._colHigh) return;   // canvas not sized yet
    const W   = this._cssW;
    const col = Math.floor(this._writeX);

    /* On entering a new pixel column, clear it (erase prior-sweep data). */
    if (col !== this._lastCol) {
      this._colHigh[col] = NaN;
      this._colLow[col]  = NaN;
      this._lastCol = col;
    }

    if (ok) {
      const y = this._toY(v);
      if (isNaN(this._colHigh[col])) {
        this._colHigh[col] = y;
        this._colLow[col]  = y;
      } else {
        if (y < this._colHigh[col]) this._colHigh[col] = y;
        if (y > this._colLow[col])  this._colLow[col]  = y;
      }
    }

    this._writeX += this._pxPerSample;
    if (this._writeX >= W) {
      this._writeX -= W;
      this._lastCol = -1;  // allow clearing col 0 on next wrap
    }
  }

  /* ── Redraw trace canvas from column buffer ──────────────────────────── */

  _redraw() {
    if (!this._colHigh) return;   // canvas not sized yet
    const tx       = this._tc.getContext("2d");
    const W        = this._cssW;
    const H        = this._cssH;
    const writeCol = Math.floor(this._writeX);
    const ERASE    = this.ERASER_CSS;
    const pps      = this._pxPerSample;

    tx.clearRect(0, 0, W, H);

    /* ── Pass 1: connecting polyline (midpoints of each column range) ── */
    tx.save();
    tx.strokeStyle = this.TRACE_COLOR;
    tx.lineWidth   = 1.8;
    tx.lineJoin    = "round";
    tx.lineCap     = "round";
    tx.shadowColor = "rgba(0,255,127,0.40)";
    tx.shadowBlur  = 3;

    tx.beginPath();
    let penDown  = false;
    let prevCol  = -2;

    for (let c = 0; c < W; c++) {
      /* Erase zone: 1 .. ERASE columns ahead of the write head. */
      const ahead = (c - writeCol + W) % W;
      if (ahead >= 1 && ahead <= ERASE) { penDown = false; prevCol = -2; continue; }

      const hi = this._colHigh[c];
      if (isNaN(hi)) { penDown = false; prevCol = -2; continue; }

      const lo  = this._colLow[c];
      const mid = (hi + lo) * 0.5;

      /* Only connect columns that are truly adjacent (≤ 1 apart). */
      if (!penDown || c - prevCol > 1) {
        tx.moveTo(c + 0.5, mid);
        penDown = true;
      } else {
        tx.lineTo(c + 0.5, mid);
      }
      prevCol = c;
    }
    tx.stroke();

    /* ── Pass 2: vertical extent (only when multiple samples per pixel) ──
       Draws a thin vertical segment from column min to max Y, giving the
       signal its proper amplitude envelope at compressed time scales.
       This is what real monitors do and fixes the solid-fill appearance. */
    if (pps < 1.5) {
      tx.lineWidth   = 1.1;
      tx.shadowBlur  = 0;
      tx.strokeStyle = "rgba(0,255,127,0.72)";
      tx.beginPath();

      for (let c = 0; c < W; c++) {
        const ahead = (c - writeCol + W) % W;
        if (ahead >= 1 && ahead <= ERASE) continue;

        const hi = this._colHigh[c];
        const lo = this._colLow[c];
        if (isNaN(hi) || lo - hi < 1.5) continue;  // < 1.5 px: single-point, skip

        tx.moveTo(c + 0.5, hi);
        tx.lineTo(c + 0.5, lo);
      }
      tx.stroke();
    }

    tx.restore();
  }
}


/* ── BPM Calculator ──────────────────────────────────────────────────────── */
class BPMCalc {
  constructor(sampleRate = 250) {
    this.sr       = sampleRate;
    this.REFRACT  = Math.floor(0.33 * sampleRate);  // 330 ms
    this.peaks    = [];
    this.lastPeak = -Infinity;
    this.sampleIdx= 0;
    this.prev     = 512;
    this._emaHigh = 512;
    this._emaLow  = 512;
    this.onPeak   = null;
  }

  add(v, ok) {
    if (!ok) { this.sampleIdx++; this.prev = v; return; }

    if (v > this._emaHigh) this._emaHigh = this._emaHigh * 0.99  + v * 0.01;
    else                   this._emaHigh = this._emaHigh * 0.9995 + v * 0.0005;

    if (v < this._emaLow)  this._emaLow  = this._emaLow  * 0.99  + v * 0.01;
    else                   this._emaLow  = this._emaLow  * 0.9995 + v * 0.0005;

    const thresh = this._emaLow + (this._emaHigh - this._emaLow) * 0.62;

    if (this.prev < thresh && v >= thresh &&
        this.sampleIdx - this.lastPeak > this.REFRACT) {
      this.peaks.push(this.sampleIdx);
      if (this.peaks.length > 12) this.peaks.shift();
      this.lastPeak = this.sampleIdx;
      if (this.onPeak) this.onPeak(this.sampleIdx);
    }

    this.prev = v;
    this.sampleIdx++;
  }

  bpm() {
    if (this.peaks.length < 2) return null;
    let sum = 0;
    for (let i = 1; i < this.peaks.length; i++) sum += this.peaks[i] - this.peaks[i - 1];
    const avg = sum / (this.peaks.length - 1);
    const bpm = Math.round(60 * this.sr / avg);
    return (bpm >= 25 && bpm <= 260) ? bpm : null;
  }

  reset() {
    this.peaks     = [];
    this.lastPeak  = -Infinity;
    this.sampleIdx = 0;
    this._emaHigh  = 512;
    this._emaLow   = 512;
  }
}


/* ── Monitor Controller ──────────────────────────────────────────────────── */
class ECGMonitor {
  constructor() {
    this.display     = null;
    this.bpmCalc     = null;
    this.es          = null;
    this.connected   = false;
    this.sampleCount = 0;
    this.leadOk      = true;
    this.bpm         = null;
    this._paused     = false;
    this._bpmHistory = [];

    this._bindUI();
    this._initDisplay();
    this._startClock();
  }

  _bindUI() {
    this._$bpmVal      = document.getElementById("bpmVal");
    this._$bpmTrend    = document.getElementById("bpmTrend");
    this._$leadStatus  = document.getElementById("leadStatus");
    this._$connStatus  = document.getElementById("connStatus");
    this._$simBadge    = document.getElementById("simBadge");
    this._$sampleCount = document.getElementById("sampleCount");
    this._$clock       = document.getElementById("monClock");
    this._$heartIcon   = document.getElementById("heartIcon");

    document.getElementById("btnConnect")
            .addEventListener("click", () => this._connect());
    document.getElementById("btnDisconnect")
            .addEventListener("click", () => this._disconnect());
    document.getElementById("btnPause")
            .addEventListener("click", () => this._togglePause());
    document.getElementById("btnSweep")
            .addEventListener("change", e => this._setSweep(+e.target.value));
  }

  _initDisplay() {
    const gc  = document.getElementById("ecgGrid");
    const tc  = document.getElementById("ecgTrace");
    const bpm = new BPMCalc(250);

    bpm.onPeak = () => {
      this._flashHeart();
      this.bpm = bpm.bpm();
      this._updateBPM();
    };

    this.display = new ECGDisplay(gc, tc, { sweepSec: 8, sampleRate: 250 });
    this.bpmCalc = bpm;
  }

  _connect() {
    const port = document.getElementById("serialPort").value.trim() || "/dev/ttyUSB0";
    const sim  = document.getElementById("chkSim").checked;

    this._disconnect();
    this.display.reset();
    this.bpmCalc.reset();
    this.sampleCount = 0;
    this.bpm         = null;
    this._bpmHistory = [];

    const url = `/api/ecg-stream?port=${encodeURIComponent(port)}&baud=115200${sim ? "&sim=1" : ""}`;
    this.es = new EventSource(url);

    this.es.onmessage = (e) => {
      let d;
      try { d = JSON.parse(e.data); } catch { return; }

      if (d.status) {
        const map = { connected: ["live", "Connected: " + d.port],
                      simulating: ["simulating", "Simulation"],
                      error: ["error", d.msg || "Serial error"] };
        const [state, text] = map[d.status] || ["idle", d.status];
        this._setStatus(state, text);
        if (this._$simBadge)
          this._$simBadge.style.display = (d.status === "simulating") ? "inline-flex" : "none";
        return;
      }

      if (typeof d.v !== "number") return;

      this.connected = true;
      this.leadOk    = !!d.ok;
      this.sampleCount++;

      if (!this._paused) {
        this.display.push(d.v, d.ok);
        this.bpmCalc.add(d.v, d.ok);
      }

      if (this.sampleCount % 50  === 0) this._updateLeadStatus();
      if (this.sampleCount % 125 === 0) {
        this.bpm = this.bpmCalc.bpm();
        this._updateBPM();
        if (this._$sampleCount)
          this._$sampleCount.textContent = this.sampleCount.toLocaleString();
      }
    };

    this.es.onerror = () => this._setStatus("error", "Stream disconnected");
  }

  _disconnect() {
    if (this.es) { this.es.close(); this.es = null; }
    this.connected = false;
    this._setStatus("idle", "Disconnected");
  }

  _togglePause() {
    const btn = document.getElementById("btnPause");
    if (this._paused) {
      this._paused = false;
      this.display.resume();
      btn.innerHTML = '<i class="fa-solid fa-pause me-1"></i>Pause';
      btn.classList.replace("btn-mon-active", "btn-mon");
    } else {
      this._paused = true;
      this.display.pause();
      btn.innerHTML = '<i class="fa-solid fa-play me-1"></i>Resume';
      btn.classList.replace("btn-mon", "btn-mon-active");
    }
  }

  _setSweep(sec) {
    this.display.sweepSec    = sec;
    this.display._pxPerSample = this.display._cssW / (sec * this.display.sampleRate);
    this.display.reset();
  }

  _setStatus(state, text) {
    const el = this._$connStatus;
    if (!el) return;
    el.className   = `mon-status-badge mon-status-${state}`;
    el.textContent = text;
  }

  _updateBPM() {
    const el = this._$bpmVal;
    if (!el) return;
    if (this.bpm) {
      el.textContent = this.bpm;
      el.className   = "bpm-digital" + (this.bpm < 50 || this.bpm > 120 ? " bpm-abnormal" : "");
      this._bpmHistory.push(this.bpm);
      if (this._bpmHistory.length > 30) this._bpmHistory.shift();
      this._drawSparkline();
    } else {
      el.textContent = "--";
    }
  }

  _updateLeadStatus() {
    const el = this._$leadStatus;
    if (!el) return;
    if (this.leadOk) {
      el.innerHTML = '<i class="fa-solid fa-circle"></i> Lead I';
      el.className = "mon-lead-ok";
    } else {
      el.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> Lead Off';
      el.className = "mon-lead-off";
    }
  }

  _flashHeart() {
    const el = this._$heartIcon;
    if (!el) return;
    el.classList.remove("heart-beat");
    void el.offsetWidth;
    el.classList.add("heart-beat");
  }

  _drawSparkline() {
    const canvas = document.getElementById("bpmSparkline");
    if (!canvas || this._bpmHistory.length < 2) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const vals = this._bpmHistory;
    const lo   = Math.min(...vals) - 5;
    const hi   = Math.max(...vals) + 5;
    const toY  = v => H - ((v - lo) / (hi - lo)) * H;
    const toX  = i => (i / (vals.length - 1)) * W;

    ctx.beginPath();
    ctx.strokeStyle = "#fbbf24";
    ctx.lineWidth   = 1.5;
    ctx.lineJoin    = "round";
    vals.forEach((v, i) => i === 0 ? ctx.moveTo(toX(i), toY(v)) : ctx.lineTo(toX(i), toY(v)));
    ctx.stroke();
  }

  _startClock() {
    const fmt = () => {
      const n = new Date(), z = x => String(x).padStart(2, "0");
      return `${z(n.getHours())}:${z(n.getMinutes())}:${z(n.getSeconds())}`;
    };
    const tick = () => { if (this._$clock) this._$clock.textContent = fmt(); };
    tick();
    setInterval(tick, 1000);
  }
}

/* ── Boot ────────────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  window._ecgMon = new ECGMonitor();
  if (new URLSearchParams(location.search).get("autostart") === "1")
    setTimeout(() => document.getElementById("btnConnect").click(), 500);
});
