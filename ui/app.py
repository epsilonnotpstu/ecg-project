import sys
import os
import json
import time
import math

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
os.chdir(BASE_DIR)  # scripts use relative paths like raw/esp/

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, send_file, abort, send_from_directory,
    Response, stream_with_context,
)
from db_setup import init_db, get_connection

app = Flask(__name__)
app.secret_key = "cardioscan-secret-key-change-in-prod"

init_db()

# ── Helpers ──────────────────────────────────────────────────────────────────

def _status_class(status: str) -> str:
    if "Normal" in status:
        return "success"
    if "Unknown" in status:
        return "danger"
    return "warning"


app.jinja_env.globals["status_class"] = _status_class


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    conn = get_connection()
    patients = conn.execute("""
        SELECT
            p.*,
            r.bpm      AS last_bpm,
            r.status   AS last_status,
            r.created_at AS last_recording_at
        FROM patients p
        LEFT JOIN recordings r
            ON r.id = (
                SELECT id FROM recordings
                WHERE patient_id = p.id
                ORDER BY created_at DESC
                LIMIT 1
            )
        ORDER BY p.created_at DESC
    """).fetchall()
    total_recordings = conn.execute("SELECT COUNT(*) FROM recordings").fetchone()[0]
    conn.close()
    return render_template("index.html", patients=patients,
                           total_recordings=total_recordings)


@app.route("/patient/new", methods=["GET", "POST"])
def patient_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        age  = request.form.get("age", "").strip()
        gender   = request.form.get("gender", "").strip()
        symptoms = request.form.get("symptoms", "").strip()

        if not name:
            flash("Patient name is required.", "danger")
            return render_template("patient_new.html",
                                   form=request.form)

        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO patients (name, age, gender, symptoms) VALUES (?,?,?,?)",
            (name, int(age) if age.isdigit() else None,
             gender or None, symptoms or None),
        )
        patient_id = cur.lastrowid
        conn.commit()
        conn.close()
        flash(f"Patient <strong>{name}</strong> registered.", "success")
        return redirect(url_for("record", patient_id=patient_id))

    return render_template("patient_new.html", form={})


@app.route("/patient/<int:patient_id>")
def patient_detail(patient_id):
    conn = get_connection()
    patient = conn.execute(
        "SELECT * FROM patients WHERE id=?", (patient_id,)
    ).fetchone()
    if not patient:
        abort(404)
    recordings = conn.execute(
        "SELECT * FROM recordings WHERE patient_id=? ORDER BY created_at DESC",
        (patient_id,),
    ).fetchall()
    conn.close()
    return render_template("patient_detail.html",
                           patient=patient, recordings=recordings)


@app.route("/record/<int:patient_id>")
def record(patient_id):
    conn = get_connection()
    patient = conn.execute(
        "SELECT * FROM patients WHERE id=?", (patient_id,)
    ).fetchone()
    conn.close()
    if not patient:
        abort(404)
    return render_template("record.html", patient=patient,
                           error=None, retry=False)


@app.route("/record/<int:patient_id>/start", methods=["POST"])
def record_start(patient_id):
    import logging
    from record_session import record as do_record
    from filter_signal import process_file
    from bpm_detect import analyze_file

    conn = get_connection()
    patient = conn.execute(
        "SELECT * FROM patients WHERE id=?", (patient_id,)
    ).fetchone()
    conn.close()
    if not patient:
        abort(404)

    duration = int(request.form.get("duration", 15))
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    session_name = f"patient{patient_id}_{timestamp}"

   
    raw_csv, motion_pct = do_record(duration, session_name)

    filtered_csv, compare_plot = process_file(raw_csv)
    result                     = analyze_file(filtered_csv)

    # AI beat classification — non-fatal if model absent or error
    ai = {"available": False, "dominant_class": None,
          "class_distribution": {}, "alert_count": 0, "beats": []}
    try:
        from classify_recording import classify_recording
        ai = classify_recording(raw_csv)
    except Exception as exc:
        logging.warning("classify_recording failed: %s", exc)

    conn = get_connection()
    cur = conn.execute("""



INSERT INTO recordings
          (patient_id, session_name, duration_sec, raw_file, filtered_file,
           compare_plot, bpm_plot, num_peaks, bpm, status, rr_intervals_json,
           ai_available, ai_dominant_class, ai_class_distribution,
           ai_alert_count, ai_beats_json, motion_pct)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        patient_id, session_name, duration,
        raw_csv, filtered_csv, compare_plot, result["plot"],
        result["num_peaks"], result["bpm"], result["status"],
        json.dumps(result["rr_intervals_sec"]),
        int(bool(ai.get("available", False))),
        ai.get("dominant_class"),
        json.dumps(ai.get("class_distribution", {})),
        ai.get("alert_count", 0),
        json.dumps(ai.get("beats", [])),
        motion_pct,
    ))




    recording_id = cur.lastrowid
    conn.commit()
    conn.close()

    if result["bpm"] is None:
        return render_template(
            "record.html", patient=patient,
            error="Signal quality too low — not enough R-peaks detected. "
                  "Check electrode placement and try again.",
            retry=True,
        )

    return redirect(url_for("result", recording_id=recording_id))


@app.route("/result/<int:recording_id>")
def result(recording_id):
    conn = get_connection()
    recording = conn.execute(
        "SELECT * FROM recordings WHERE id=?", (recording_id,)
    ).fetchone()
    if not recording:
        abort(404)
    patient = conn.execute(
        "SELECT * FROM patients WHERE id=?", (recording["patient_id"],)
    ).fetchone()
    report = conn.execute(
        "SELECT * FROM reports WHERE recording_id=?", (recording_id,)
    ).fetchone()
    conn.close()

    rr = json.loads(recording["rr_intervals_json"]) if recording["rr_intervals_json"] else []
    ai_class_dist = json.loads(recording["ai_class_distribution"]) if recording["ai_class_distribution"] else {}
    ai_beats      = json.loads(recording["ai_beats_json"])          if recording["ai_beats_json"]          else []
    return render_template("result.html",
                           recording=recording, patient=patient,
                           rr_intervals=rr, report=report,
                           ai_class_dist=ai_class_dist,
                           ai_beats=ai_beats,
                           motion_pct=recording["motion_pct"])


@app.route("/report/<int:recording_id>")
def report(recording_id):
    from report_generator import generate_report

    conn = get_connection()
    recording = conn.execute(
        "SELECT * FROM recordings WHERE id=?", (recording_id,)
    ).fetchone()
    if not recording:
        conn.close()
        abort(404)
    patient  = conn.execute(
        "SELECT * FROM patients WHERE id=?", (recording["patient_id"],)
    ).fetchone()
    existing = conn.execute(
        "SELECT * FROM reports WHERE recording_id=?", (recording_id,)
    ).fetchone()

    if existing and os.path.exists(existing["pdf_file"]):
        pdf_path = existing["pdf_file"]
    else:
        reports_dir = os.path.join(BASE_DIR, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        out = os.path.join(reports_dir,
                           f"{recording['session_name']}_report.pdf")
        pdf_path = generate_report(dict(patient), dict(recording), out)
        conn.execute(
            "INSERT INTO reports (recording_id, pdf_file) VALUES (?,?)",
            (recording_id, pdf_path),
        )
        conn.commit()

    conn.close()
    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=f"ecg_report_{recording['session_name']}.pdf",
        mimetype="application/pdf",
    )


@app.route("/media/<path:filepath>")
def media(filepath):
    allowed = ("raw", "filtered", "reports")
    parts = filepath.replace("\\", "/").split("/")
    if not parts or parts[0] not in allowed:
        abort(403)
    safe = os.path.normpath(os.path.join(BASE_DIR, filepath))
    if not safe.startswith(os.path.normpath(BASE_DIR) + os.sep):
        abort(403)
    if not os.path.isfile(safe):
        abort(404)
    return send_from_directory(BASE_DIR, filepath)


@app.route("/monitor")
def monitor():
    patient_id = request.args.get("patient_id", type=int)
    conn = get_connection()
    patients = conn.execute(
        "SELECT id, name FROM patients ORDER BY name"
    ).fetchall()
    patient = None
    if patient_id:
        patient = conn.execute(
            "SELECT * FROM patients WHERE id=?", (patient_id,)
        ).fetchone()
    conn.close()
    return render_template("monitor.html",
                           patients=patients,
                           patient=patient,
                           patient_id=patient_id)


# ── ECG sample simulator (Gaussian P-QRS-T model) ─────────────────────────
def _ecg_sim(t_sec, bpm=72):
    period = 60.0 / bpm
    ph = (t_sec % period) / period       # 0..1 within one beat
    # (amplitude, center_phase, width_phase)
    waves = [
        ( 0.09,  0.10, 0.026),           # P
        (-0.05,  0.22, 0.009),           # Q
        ( 1.00,  0.245, 0.0065),         # R
        (-0.18,  0.27, 0.009),           # S
        ( 0.28,  0.45, 0.055),           # T
    ]
    v = sum(a * math.exp(-((ph - c) ** 2) / (2 * w * w)) for a, c, w in waves)
    v += 0.018 * math.sin(2 * math.pi * 0.12 * t_sec)  # baseline wander
    return max(0, min(1023, int(512 + v * 85)))


@app.route("/api/ecg-stream")
def ecg_stream():
    import serial as _serial
    port     = request.args.get("port", "/dev/ttyUSB0")
    baud     = int(request.args.get("baud", "115200"))
    simulate = request.args.get("sim", "0") == "1"

    def generate():
        if not simulate:
            try:
                ser = _serial.Serial(port, baud, timeout=1)
                time.sleep(1.5)
                yield f"data: {json.dumps({'status': 'connected', 'port': port})}\n\n"

                while True:
                    try:
                        raw = ser.readline().decode("utf-8", errors="ignore").strip()
                    except _serial.SerialException:
                        yield f"data: {json.dumps({'status': 'error', 'msg': 'Serial disconnected'})}\n\n"
                        break

                    if not raw:
                        continue

                    parts = raw.split(",")
                    if len(parts) >= 3:
                        try:
                            ts  = int(parts[0])
                            val = int(parts[1])
                            ok  = int(parts[2])
                            yield f"data: {json.dumps({'v': val, 'ok': ok, 't': ts})}\n\n"
                        except ValueError:
                            continue

            except Exception as exc:
                yield f"data: {json.dumps({'status': 'error', 'msg': str(exc)})}\n\n"
                simulate = True

        if simulate:
            yield f"data: {json.dumps({'status': 'simulating'})}\n\n"
            t   = 0.0
            dt  = 1.0 / 125.0
            t0  = time.time()
            idx = 0
            while True:
                val = _ecg_sim(t, bpm=72)
                yield f"data: {json.dumps({'v': val, 'ok': 1, 't': idx * 8, 'sim': True})}\n\n"
                idx += 1
                t   += dt
                nxt  = t0 + idx * dt
                slp  = nxt - time.time()
                if slp > 0:
                    time.sleep(slp)

    resp = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
    )
    resp.headers["Cache-Control"]     = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"]        = "keep-alive"
    return resp

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
