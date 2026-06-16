/* ═══════════════════════════════════════════════════════════════════════════
   CardioScan AI — Real-Time ECG Monitor Engine
   Two-layer canvas: static grid behind, live trace on top.
   Sweeping phosphor / hospital-monitor style.
   ═══════════════════════════════════════════════════════════════════════════ */

"use strict";

/* ── ECG Display Engine ──────────────────────────────────────────────────── */
class ECGDisplay {
  /**
   * @param {HTMLCanvasElement} gridCanvas  – background grid (drawn once)
   * @param {HTMLCanvasElement} traceCanvas – live ECG trace (swept)
   * @param {object} opts
   *   sweepSec   – seconds of data visible at once (default 8)
   *   sampleRate – Hz expected from source (default 250)
   */
  constructor(gridCanvas, traceCanvas, opts = {}) {
    this._gc  = gridCanvas;
    this._tc  = traceCanvas;
    this._gx  = gridCanvas.getContext("2d");
    this._tx  = traceCanvas.getContext("2d");

    this.sweepSec   = opts.sweepSec   || 8;
    this.sampleRate = opts.sampleRate || 250;

    this._dpr = window.devicePixelRatio || 1;
    this._W   = 0;
    this._H   = 0;

    /* Signal state */
    this._queue    = [];      // pending raw samples { v, ok }
    this._writeX   = 0;      // fractional pixel write-head position
    this._lastX    = 0;
    this._lastY    = null;   // null = pen up
    this._paused   = false;

    /* Auto-scale: EMA of signal min/max for DC-free, gain-adaptive display */
    this._emaBaseline = null;
    this._emaRange    = 80;   // initial expected range (ADC units)

    /* Erase-block width (px) — blank zone ahead of write head */
    this.ERASER_PX = 36;

    this._resize();
    window.addEventListener("resize", () => this._resize());

    /* Grid colour constants */
    this.GRID_MINOR  = "rgba(0,170,50,0.13)";
    this.GRID_MAJOR  = "rgba(0,200,70,0.28)";
    this.GRID_CENTER = "rgba(0,220,80,0.50)";
    this.TRACE_COLOR = "#00ff7f";
    this.BG_COLOR    = "#030d18";

    this._drawGrid();
    this._raf = requestAnimationFrame(() => this._frame());
  }

  /* ── Public API ──────────────────────────────────────────────────────── */

  push(v, ok) {
    this._queue.push({ v, ok: !!ok });
  }

  pause() { this._paused = true; }

  resume() {
    this._paused = false;
    this._queue  = [];   // drop stale samples
    this._raf = requestAnimationFrame(() => this._frame());
  }

  reset() {
    this._queue    = [];
    this._writeX   = 0;
    this._lastY    = null;
    this._lastX    = 0;
    this._emaBaseline = null;
    this._emaRange    = 80;
    // Clear trace canvas
    const tx = this._tx;
    tx.clearRect(0, 0, this._W / this._dpr, this._H / this._dpr);
  }

  destroy() {
    cancelAnimationFrame(this._raf);
  }

  /* ── Resize ──────────────────────────────────────────────────────────── */

  _resize() {
    const dpr  = this._dpr;
    const wrap  = this._tc.parentElement;
    const cssW  = wrap ? wrap.clientWidth  : 800;
    const cssH  = wrap ? wrap.clientHeight : 260;

    if (cssW === this._W / dpr && cssH === this._H / dpr) return;

    this._W = cssW * dpr;
    this._H = cssH * dpr;

    for (const cvs of [this._gc, this._tc]) {
      cvs.width        = this._W;
      cvs.height       = this._H;
      cvs.style.width  = cssW + "px";
      cvs.style.height = cssH + "px";
    }

    // Recalculate pixels per sample
    this._pxPerSample = this._W / (this.sweepSec * this.sampleRate);

    this._drawGrid();
    this.reset();
  }

  /* ── Grid drawing (runs on resize) ──────────────────────────────────── */

  _drawGrid() {
    const gx = this._gx;
    const W  = this._W;
    const H  = this._H;
    const dpr = this._dpr;

    gx.fillStyle = this.BG_COLOR;
    gx.fillRect(0, 0, W, H);

    // 1px minor / 5px major grid at ECG paper proportions
    // Minor: every 10px (1mm at 100dpi ≈ 40ms @ 25mm/s)
    // Major: every 50px (5mm ≈ 200ms @ 25mm/s)
    const minorPx = 10 * dpr;
    const majorPx = 50 * dpr;

    // Minor grid
    gx.save();
    gx.strokeStyle = this.GRID_MINOR;
    gx.lineWidth   = 0.5 * dpr;
    gx.beginPath();
    for (let x = 0; x <= W; x += minorPx) {
      gx.moveTo(x, 0); gx.lineTo(x, H);
    }
    for (let y = 0; y <= H; y += minorPx) {
      gx.moveTo(0, y); gx.lineTo(W, y);
    }
    gx.stroke();

    // Major grid
    gx.strokeStyle = this.GRID_MAJOR;
    gx.lineWidth   = 0.8 * dpr;
    gx.beginPath();
    for (let x = 0; x <= W; x += majorPx) {
      gx.moveTo(x, 0); gx.lineTo(x, H);
    }
    for (let y = 0; y <= H; y += majorPx) {
      gx.moveTo(0, y); gx.lineTo(W, y);
    }
    gx.stroke();

    // Center baseline
    gx.strokeStyle = this.GRID_CENTER;
    gx.lineWidth   = 0.6 * dpr;
    gx.setLineDash([4 * dpr, 6 * dpr]);
    gx.beginPath();
    gx.moveTo(0, H / 2); gx.lineTo(W, H / 2);
    gx.stroke();
    gx.setLineDash([]);

    // ECG paper corner labels (25mm/s, 10mm/mV)
    gx.font         = `${9 * dpr}px Inter, monospace`;
    gx.fillStyle    = "rgba(0,180,60,0.55)";
    gx.textAlign    = "left";
    gx.fillText("25 mm/s", 8 * dpr, H - 7 * dpr);
    gx.textAlign    = "right";
    gx.fillText("10 mm/mV", W - 8 * dpr, H - 7 * dpr);
    gx.restore();
  }

  /* ── Signal value → canvas Y ─────────────────────────────────────────── */

  _toY(v) {
    const H = this._H;
    if (this._emaBaseline === null) this._emaBaseline = v;

    // Adaptive baseline (slow EMA removes DC drift)
    this._emaBaseline = this._emaBaseline * 0.9975 + v * 0.0025;
    const centred = v - this._emaBaseline;

    // Adaptive range (fast EMA of absolute deviation)
    const absC = Math.abs(centred);
    this._emaRange = this._emaRange * 0.997 + absC * 0.003;
    const range = Math.max(this._emaRange * 2.8, 15);

    // Map to canvas Y (invert axis, keep 10% margin)
    const y = H / 2 - (centred / range) * (H * 0.44);
    return Math.max(2 * this._dpr, Math.min(H - 2 * this._dpr, y));
  }

  /* ── Main animation frame ────────────────────────────────────────────── */

  _frame() {
    if (this._paused) return;

    // Drain the sample queue (up to 8 samples per frame — handles bursts)
    const MAX_PER_FRAME = 8;
    for (let i = 0; i < MAX_PER_FRAME && this._queue.length; i++) {
      const { v, ok } = this._queue.shift();
      this._drawSample(v, ok);
    }

    this._raf = requestAnimationFrame(() => this._frame());
  }

  /* ── Draw one sample ─────────────────────────────────────────────────── */

  _drawSample(v, ok) {
    const tx   = this._tx;
    const W    = this._W;
    const H    = this._H;
    const dpr  = this._dpr;
    const x    = this._writeX;
    const eW   = this.ERASER_PX * dpr;

    // ── Erase ahead of write head (reveals grid beneath) ──────────────
    tx.save();
    tx.globalCompositeOperation = "destination-out";   // erase on trace canvas
    const ex = (x + dpr) % W;
    if (ex + eW <= W) {
      tx.fillRect(ex, 0, eW, H);
    } else {
      tx.fillRect(ex, 0, W - ex, H);
      tx.fillRect(0, 0, eW - (W - ex), H);
    }
    tx.globalCompositeOperation = "source-over";

    // ── Draw trace segment ────────────────────────────────────────────
    if (ok) {
      const y = this._toY(v);

      if (
        this._lastY !== null &&
        Math.abs(x - this._lastX) < W * 0.6  // don't join across wrap gap
      ) {
        tx.beginPath();
        tx.strokeStyle = this.TRACE_COLOR;
        tx.lineWidth   = 1.8 * dpr;
        tx.lineCap     = "round";
        tx.lineJoin    = "round";
        // Shadow glow for phosphor feel
        tx.shadowColor = "rgba(0,255,127,0.45)";
        tx.shadowBlur  = 4 * dpr;
        tx.moveTo(this._lastX, this._lastY);
        tx.lineTo(x, y);
        tx.stroke();
      }

      this._lastY = y;
    } else {
      // Lead-off: draw dotted flat line at center
      if (this._lastY !== null && Math.abs(x - this._lastX) < W * 0.6) {
        const cy = H / 2;
        tx.setLineDash([3 * dpr, 6 * dpr]);
        tx.strokeStyle = "rgba(255,200,0,0.5)";
        tx.lineWidth   = 1 * dpr;
        tx.beginPath();
        tx.moveTo(this._lastX, cy);
        tx.lineTo(x, cy);
        tx.stroke();
        tx.setLineDash([]);
      }
      this._lastY = H / 2;
    }

    tx.restore();
    this._lastX = x;

    // ── Advance write head ────────────────────────────────────────────
    this._writeX += this._pxPerSample;
    if (this._writeX >= W) {
      this._writeX -= W;
      this._lastY   = null;    // lift pen on wrap
    }
  }
}

/* ── BPM Calculator ──────────────────────────────────────────────────────── */
class BPMCalc {
  constructor(sampleRate = 250) {
    this.sr        = sampleRate;
    this.REFRACT   = Math.floor(0.33 * sampleRate);   // 330ms refractory
    this.peaks     = [];      // sample indices of detected peaks
    this.lastPeak  = -Infinity;
    this.sampleIdx = 0;
    this.prev      = 512;

    // Adaptive threshold
    this._emaHigh  = 512;
    this._emaLow   = 512;
    this.onPeak    = null;    // callback(sampleIdx)
  }

  add(v, ok) {
    if (!ok) { this.sampleIdx++; this.prev = v; return; }

    // Track slow EMA of high and low
    if (v > this._emaHigh) this._emaHigh = this._emaHigh * 0.99 + v * 0.01;
    else                   this._emaHigh = this._emaHigh * 0.9995 + v * 0.0005;

    if (v < this._emaLow)  this._emaLow  = this._emaLow * 0.99  + v * 0.01;
    else                   this._emaLow  = this._emaLow * 0.9995 + v * 0.0005;

    const thresh = this._emaLow + (this._emaHigh - this._emaLow) * 0.62;

    // Rising edge crossing threshold
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
    const avgRR = sum / (this.peaks.length - 1);
    const bpm   = Math.round(60 * this.sr / avgRR);
    return (bpm >= 25 && bpm <= 260) ? bpm : null;
  }

  reset() {
    this.peaks = [];
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
    this.es          = null;    // EventSource
    this.connected   = false;
    this.simMode     = false;
    this.sampleCount = 0;
    this.leadOk      = true;
    this.bpm         = null;
    this.lastPeakAt  = null;   // for heart animation

    this._bindUI();
    this._initDisplay();
    this._startClock();
  }

  /* ── UI bindings ───────────────────────────────────────────────────── */

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

    this._paused = false;
    this._bpmHistory = [];
  }

  /* ── Init canvases ─────────────────────────────────────────────────── */

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

  /* ── Connect / Disconnect ──────────────────────────────────────────── */

  _connect() {
    const port = document.getElementById("serialPort").value.trim() || "/dev/ttyUSB0";
    const sim  = document.getElementById("chkSim").checked;
    this.simMode = sim;

    this._disconnect();   // close existing connection first
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
        if (d.status === "connected")   this._setStatus("live",       "Connected: " + d.port);
        if (d.status === "simulating")  this._setStatus("simulating", "Simulation");
        if (d.status === "error")       this._setStatus("error",      d.msg || "Serial error");
        if (this._$simBadge) {
          this._$simBadge.style.display = (d.status === "simulating") ? "inline-flex" : "none";
        }
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

      // Update lead status every 50 samples
      if (this.sampleCount % 50 === 0) this._updateLeadStatus();
      if (this.sampleCount % 125 === 0) {
        this.bpm = this.bpmCalc.bpm();
        this._updateBPM();
        if (this._$sampleCount)
          this._$sampleCount.textContent = this.sampleCount.toLocaleString();
      }
    };

    this.es.onerror = () => {
      this._setStatus("error", "Stream disconnected");
    };
  }

  _disconnect() {
    if (this.es) {
      this.es.close();
      this.es = null;
    }
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
    this.display.sweepSec = sec;
    this.display._pxPerSample = this.display._W / (sec * this.display.sampleRate);
    this.display.reset();
  }

  /* ── UI updates ────────────────────────────────────────────────────── */

  _setStatus(state, text) {
    const el = this._$connStatus;
    if (!el) return;
    el.className = `mon-status-badge mon-status-${state}`;
    el.textContent = text;
  }

  _updateBPM() {
    const el = this._$bpmVal;
    if (!el) return;
    if (this.bpm) {
      el.textContent = this.bpm;
      el.className   = "bpm-digital" + (
        this.bpm < 50 || this.bpm > 120 ? " bpm-abnormal" : ""
      );
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
    void el.offsetWidth;   // reflow to restart animation
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
    const toX  = (i) => (i / (vals.length - 1)) * W;

    ctx.beginPath();
    ctx.strokeStyle = "#fbbf24";
    ctx.lineWidth   = 1.5;
    ctx.lineJoin    = "round";
    vals.forEach((v, i) => {
      i === 0 ? ctx.moveTo(toX(i), toY(v)) : ctx.lineTo(toX(i), toY(v));
    });
    ctx.stroke();
  }

  /* ── Clock ─────────────────────────────────────────────────────────── */

  _startClock() {
    const fmt = () => {
      const n = new Date();
      const z = x => String(x).padStart(2, "0");
      return `${z(n.getHours())}:${z(n.getMinutes())}:${z(n.getSeconds())}`;
    };
    const update = () => {
      if (this._$clock) this._$clock.textContent = fmt();
    };
    update();
    setInterval(update, 1000);
  }
}

/* ── Boot ────────────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  window._ecgMon = new ECGMonitor();
  // Auto-connect if URL has ?autostart=1
  if (new URLSearchParams(location.search).get("autostart") === "1") {
    setTimeout(() => document.getElementById("btnConnect").click(), 500);
  }
});
