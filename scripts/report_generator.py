import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    Table, TableStyle, HRFlowable,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Palette ─────────────────────────────────────────────────────────────────
C_BLUE   = colors.HexColor("#2563eb")
C_DARK   = colors.HexColor("#1e293b")
C_BG     = colors.HexColor("#f8fafc")
C_BORDER = colors.HexColor("#e2e8f0")
C_GRAY   = colors.HexColor("#64748b")
C_OK     = colors.HexColor("#16a34a")
C_WARN   = colors.HexColor("#d97706")
C_ERR    = colors.HexColor("#dc2626")
C_VIOLET = colors.HexColor("#7c3aed")
C_VBG    = colors.HexColor("#f5f3ff")

_BASE_STYLES = getSampleStyleSheet()


def _p(text, **kw):
    """Quick Paragraph factory — kwargs become ParagraphStyle attributes."""
    style = ParagraphStyle("_", parent=_BASE_STYLES["Normal"], **kw)
    return Paragraph(text, style)


def _resolve(path):
    if path and not os.path.isabs(path):
        return os.path.join(BASE_DIR, path)
    return path or ""


def _status_color(status: str):
    if "Normal" in status:
        return C_OK
    if "Unknown" in status:
        return C_ERR
    return C_WARN


def _fmt_date(ts: str) -> str:
    try:
        dt = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%B %d, %Y  %I:%M %p")
    except Exception:
        return str(ts)


def generate_report(patient: dict, recording: dict, output_path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    W = doc.width

    # ── Derived values ───────────────────────────────────────────────────────
    status = recording.get("status", "Unknown")
    sc     = _status_color(status)
    bpm    = recording.get("bpm")
    bpm_txt = f"{bpm:.1f}" if bpm else "—"
    num_peaks = str(recording.get("num_peaks") or "—")
    duration  = str(recording.get("duration_sec") or "—")
    src       = str(recording.get("source_type") or "ESP").upper()
    rec_date  = _fmt_date(recording.get("created_at", ""))
    rep_date  = datetime.now().strftime("%B %d, %Y  %I:%M %p")

    _GMAP = {"M": "Male", "F": "Female", "O": "Other",
             "male": "Male", "female": "Female", "other": "Other"}
    name     = str(patient.get("name") or "—")
    age      = str(patient.get("age") or "—")
    gender   = _GMAP.get(str(patient.get("gender") or ""), str(patient.get("gender") or "—"))
    symptoms = str(patient.get("symptoms") or "None reported")

    LBL = dict(fontSize=8,  textColor=C_GRAY, fontName="Helvetica")
    VAL = dict(fontSize=11, textColor=C_DARK, fontName="Helvetica-Bold")

    story = []

    # ── Header banner ────────────────────────────────────────────────────────
    banner = Table(
        [[_p("<b>CardioScan AI</b>  ·  ECG Analysis Report",
             fontSize=18, textColor=colors.white,
             fontName="Helvetica-Bold", alignment=TA_CENTER)]],
        colWidths=[W],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_BLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(banner)
    story.append(Spacer(1, 4 * mm))
    story.append(_p(f"Generated: {rep_date}  |  Recording: {rec_date}",
                    fontSize=8, textColor=C_GRAY, alignment=TA_RIGHT))
    story.append(Spacer(1, 6 * mm))

    def section(title):
        story.append(_p(f"<b>{title}</b>", fontSize=11, textColor=C_BLUE))
        story.append(HRFlowable(width="100%", thickness=1, color=C_BORDER, spaceAfter=4))

    # ── Patient Info ──────────────────────────────────────────────────────────
    section("Patient Information")

    cw  = W / 4
    cws = [cw * 0.65, cw * 1.35, cw * 0.65, cw * 1.35]
    rows  = [
        [_p("Full Name", **LBL), _p(name, **VAL), _p("Age", **LBL), _p(age, **VAL)],
        [_p("Gender", **LBL), _p(gender, **VAL), _p("Recorded", **LBL), _p(rec_date, fontSize=9, textColor=C_DARK, fontName="Helvetica-Bold")],
    ]
    ts = [
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, C_BG]),
        ("GRID",           (0, 0), (-1, -1), 0.5, C_BORDER),
        ("TOPPADDING",     (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 7),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 8),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]
    if symptoms and symptoms != "None reported":
        rows.append([_p("Symptoms / Notes", **LBL),
                     _p(symptoms, fontSize=10, textColor=C_DARK),
                     _p(""), _p("")])
        ts.append(("SPAN", (1, len(rows) - 1), (3, len(rows) - 1)))

    pt = Table(rows, colWidths=cws)
    pt.setStyle(TableStyle(ts))
    story.append(pt)
    story.append(Spacer(1, 6 * mm))

    # ── Analysis Results ──────────────────────────────────────────────────────
    section("ECG Analysis Results")

    # BPM highlight box
    bpm_box = Table(
        [
            [_p(f"<b>{bpm_txt}</b>",  fontSize=46, textColor=sc,
                fontName="Helvetica-Bold", alignment=TA_CENTER)],
            [_p(f"<b>{status}</b>",   fontSize=13, textColor=sc, alignment=TA_CENTER)],
            [_p("Beats Per Minute",   fontSize=8,  textColor=C_GRAY, alignment=TA_CENTER)],
        ],
        colWidths=[W],
    )
    bpm_box.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_BG),
        ("BOX",           (0, 0), (-1, -1), 2, sc),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(bpm_box)
    story.append(Spacer(1, 4 * mm))

    # Metrics row
    cw6 = W / 6
    m_row = [
        _p("R-Peaks Detected", **LBL), _p(num_peaks, **VAL),
        _p("Duration",         **LBL), _p(f"{duration} sec", **VAL),
        _p("Source",           **LBL), _p(src, **VAL),
    ]
    mt = Table([m_row], colWidths=[cw6] * 6)
    mt.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.white),
        ("GRID",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(mt)
    story.append(Spacer(1, 6 * mm))

    # ── Waveform Images ───────────────────────────────────────────────────────
    section("Signal Waveforms")

    def add_img(path, caption):
        abs_path = _resolve(path)
        if abs_path and os.path.exists(abs_path):
            story.append(_p(caption, fontSize=9, textColor=C_GRAY, alignment=TA_CENTER))
            story.append(Spacer(1, 2 * mm))
            story.append(Image(abs_path, width=W, height=52 * mm))
            story.append(Spacer(1, 5 * mm))

    add_img(recording.get("compare_plot", ""), "Raw vs Filtered Signal Comparison")
    add_img(recording.get("bpm_plot",     ""), "Filtered Signal with R-Peak Detection")

    story.append(Spacer(1, 4 * mm))

    # ── Disclaimer ────────────────────────────────────────────────────────────
    disc = Table(
        [[_p(
            "<b>&#9888; Medical Disclaimer:</b> AI-assisted screening prototype. "
            "Not a substitute for professional medical diagnosis. "
            "Please consult a cardiologist for clinical evaluation.",
            fontSize=9, textColor=C_VIOLET,
        )]],
        colWidths=[W],
    )
    disc.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_VBG),
        ("BOX",           (0, 0), (-1, -1), 1, C_VIOLET),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
    ]))
    story.append(disc)

    doc.build(story)
    return output_path
