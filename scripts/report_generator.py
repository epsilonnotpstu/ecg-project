import json
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    Table, TableStyle, HRFlowable, KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.graphics import renderPDF

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Palette ──────────────────────────────────────────────────────────────────
C_PRIMARY   = colors.HexColor("#2563eb")
C_PRIMARY_D = colors.HexColor("#1d4ed8")
C_SECONDARY = colors.HexColor("#0ea5e9")
C_DARK      = colors.HexColor("#0f172a")
C_DARK_2    = colors.HexColor("#1e293b")
C_BG        = colors.HexColor("#f8fafc")
C_BORDER    = colors.HexColor("#e2e8f0")
C_GRAY      = colors.HexColor("#64748b")
C_GRAY_L    = colors.HexColor("#94a3b8")
C_OK        = colors.HexColor("#16a34a")
C_OK_L      = colors.HexColor("#f0fdf4")
C_OK_B      = colors.HexColor("#86efac")
C_WARN      = colors.HexColor("#d97706")
C_WARN_L    = colors.HexColor("#fffbeb")
C_WARN_B    = colors.HexColor("#fde68a")
C_ERR       = colors.HexColor("#dc2626")
C_ERR_L     = colors.HexColor("#fef2f2")
C_ERR_B     = colors.HexColor("#fca5a5")
C_VIOLET    = colors.HexColor("#7c3aed")
C_VBG       = colors.HexColor("#f5f3ff")
C_VBR       = colors.HexColor("#c4b5fd")
C_WHITE     = colors.white

# AI class colors
C_AI = {
    "Normal":           colors.HexColor("#16a34a"),
    "Ventricular":      colors.HexColor("#dc2626"),
    "Fusion":           colors.HexColor("#d97706"),
    "Supraventricular": colors.HexColor("#ca8a04"),
    "SVT":              colors.HexColor("#ca8a04"),
    "Unknown":          colors.HexColor("#64748b"),
}
C_AI_BG = {
    "Normal":           colors.HexColor("#f0fdf4"),
    "Ventricular":      colors.HexColor("#fef2f2"),
    "Fusion":           colors.HexColor("#fffbeb"),
    "Supraventricular": colors.HexColor("#fefce8"),
    "SVT":              colors.HexColor("#fefce8"),
    "Unknown":          colors.HexColor("#f8fafc"),
}

_STYLES = getSampleStyleSheet()


def _p(text, **kw):
    style = ParagraphStyle("_", parent=_STYLES["Normal"], **kw)
    return Paragraph(text, style)


def _resolve(path):
    if path and not os.path.isabs(path):
        return os.path.join(BASE_DIR, path)
    return path or ""


def _status_color(status: str):
    s = str(status or "")
    if "Normal" in s:   return C_OK,   C_OK_L,   C_OK_B
    if "Unknown" in s:  return C_ERR,  C_ERR_L,  C_ERR_B
    return C_WARN, C_WARN_L, C_WARN_B


def _ai_color(class_name: str):
    return C_AI.get(class_name, C_AI["Unknown"])


def _ai_bg(class_name: str):
    return C_AI_BG.get(class_name, C_AI_BG["Unknown"])


def _fmt_date(ts: str) -> str:
    try:
        dt = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%B %d, %Y  %I:%M %p")
    except Exception:
        return str(ts)


def _page_template(canvas, doc):
    """Running footer on every page."""
    canvas.saveState()
    W, H = A4
    lm   = 18 * mm
    rm   = W - 18 * mm

    # Thin top accent line
    canvas.setStrokeColor(C_PRIMARY)
    canvas.setLineWidth(2.5)
    canvas.line(lm, H - 10 * mm, rm, H - 10 * mm)

    # Footer separator
    canvas.setStrokeColor(C_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(lm, 16 * mm, rm, 16 * mm)

    # Footer left — branding
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(C_GRAY_L)
    canvas.drawString(lm, 10 * mm, "CardioScan AI  ·  Confidential Medical Record")

    # Footer right — page number
    canvas.drawRightString(rm, 10 * mm, f"Page {doc.page}")

    canvas.restoreState()


def generate_report(patient: dict, recording: dict, output_path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=24 * mm,
    )
    W = doc.width

    # ── Derived values ───────────────────────────────────────────────────────
    status             = recording.get("status", "Unknown")
    sc, sc_l, sc_b     = _status_color(status)
    bpm                = recording.get("bpm")
    bpm_txt            = f"{bpm:.1f}" if bpm else "—"
    num_peaks          = str(recording.get("num_peaks") or "—")
    duration           = str(recording.get("duration_sec") or "—")
    src                = str(recording.get("source_type") or "ESP").upper()
    rec_date           = _fmt_date(recording.get("created_at", ""))
    rep_date           = datetime.now().strftime("%B %d, %Y  %I:%M %p")

    _GMAP = {"M": "Male", "F": "Female", "O": "Other",
             "male": "Male", "female": "Female", "other": "Other"}
    name     = str(patient.get("name") or "—")
    age      = str(patient.get("age") or "—")
    gender   = _GMAP.get(str(patient.get("gender") or ""), str(patient.get("gender") or "—"))
    symptoms = str(patient.get("symptoms") or "None reported")

    # AI data
    ai_available = bool(int(recording.get("ai_available") or 0))
    ai_dominant  = recording.get("ai_dominant_class") or "Unknown"
    ai_dist_raw  = recording.get("ai_class_distribution")
    ai_dist      = json.loads(ai_dist_raw) if ai_dist_raw else {}
    ai_alerts    = int(recording.get("ai_alert_count") or 0)

    # ── Style helpers ────────────────────────────────────────────────────────
    LBL = dict(fontSize=7.5, textColor=C_GRAY,   fontName="Helvetica",
               spaceBefore=0, spaceAfter=0)
    VAL = dict(fontSize=10,  textColor=C_DARK,   fontName="Helvetica-Bold",
               spaceBefore=0, spaceAfter=0)
    HDR = dict(fontSize=11,  textColor=C_PRIMARY, fontName="Helvetica-Bold",
               spaceBefore=6, spaceAfter=2)

    story = []

    # ────────────────────────────────────────────────────────────────────────
    # HEADER BANNER
    # ────────────────────────────────────────────────────────────────────────
    header_rows = [[
        _p("<b>CardioScan AI</b>",
           fontSize=20, textColor=C_WHITE, fontName="Helvetica-Bold"),
        _p("ECG Analysis Report",
           fontSize=11, textColor=colors.HexColor("#bfdbfe"),
           fontName="Helvetica", alignment=TA_RIGHT),
    ]]
    header_tbl = Table(header_rows, colWidths=[W * 0.55, W * 0.45])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_PRIMARY),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 3 * mm))

    # Date strip
    story.append(_p(
        f"Generated: <b>{rep_date}</b>   ·   Recorded: <b>{rec_date}</b>",
        fontSize=7.5, textColor=C_GRAY, alignment=TA_RIGHT,
    ))
    story.append(Spacer(1, 6 * mm))

    # ────────────────────────────────────────────────────────────────────────
    # helper: section header
    # ────────────────────────────────────────────────────────────────────────
    def section(title, icon=""):
        accent = Table(
            [[_p(f"<b>{icon}  {title}</b>" if icon else f"<b>{title}</b>",
                 fontSize=10, textColor=C_PRIMARY, fontName="Helvetica-Bold")]],
            colWidths=[W],
        )
        accent.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("BOX",           (0, 0), (-1, -1), 0, C_BORDER),
            ("LINEBELOW",     (0, 0), (-1, -1), 2, C_PRIMARY),
        ]))
        story.append(accent)
        story.append(Spacer(1, 4 * mm))

    # ────────────────────────────────────────────────────────────────────────
    # PATIENT INFORMATION
    # ────────────────────────────────────────────────────────────────────────
    section("Patient Information")

    cw = W / 4
    cws = [cw * 0.65, cw * 1.35, cw * 0.65, cw * 1.35]
    pt_rows = [
        [_p("Full Name",  **LBL), _p(name,    **VAL),
         _p("Age",        **LBL), _p(f"{age} yrs" if age != "—" else "—", **VAL)],
        [_p("Gender",     **LBL), _p(gender,  **VAL),
         _p("Recorded",   **LBL), _p(rec_date, fontSize=8.5, textColor=C_DARK, fontName="Helvetica-Bold")],
    ]
    pt_style = [
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_WHITE, C_BG]),
        ("GRID",           (0, 0), (-1, -1), 0.4, C_BORDER),
        ("TOPPADDING",     (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 7),
        ("LEFTPADDING",    (0, 0), (-1, -1), 9),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 9),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]
    if symptoms and symptoms != "None reported":
        pt_rows.append([
            _p("Symptoms / Notes", **LBL),
            _p(symptoms, fontSize=9, textColor=C_DARK),
            _p(""), _p(""),
        ])
        pt_style.append(("SPAN", (1, len(pt_rows) - 1), (3, len(pt_rows) - 1)))

    pt = Table(pt_rows, colWidths=cws)
    pt.setStyle(TableStyle(pt_style))
    story.append(pt)
    story.append(Spacer(1, 7 * mm))

    # ────────────────────────────────────────────────────────────────────────
    # ECG ANALYSIS RESULTS
    # ────────────────────────────────────────────────────────────────────────
    section("ECG Analysis Results")

    # BPM highlight box
    bpm_box = Table(
        [
            [_p(f"<b>{bpm_txt}</b>",
                fontSize=48, textColor=sc, fontName="Helvetica-Bold",
                alignment=TA_CENTER)],
            [_p(f"<b>{status}</b>",
                fontSize=13, textColor=sc, fontName="Helvetica-Bold",
                alignment=TA_CENTER)],
            [_p("Beats Per Minute",
                fontSize=8, textColor=C_GRAY, alignment=TA_CENTER)],
        ],
        colWidths=[W],
    )
    bpm_box.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), sc_l),
        ("BOX",           (0, 0), (-1, -1), 2.5, sc),
        ("LINEABOVE",     (0, 0), (-1, 0), 4, sc),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("BORDERRADIUS",  (0, 0), (-1, -1), 6),
    ]))
    story.append(bpm_box)
    story.append(Spacer(1, 4 * mm))

    # Metrics row
    cw6 = W / 6
    m_row = [
        _p("R-Peaks", **LBL), _p(num_peaks, **VAL),
        _p("Duration", **LBL), _p(f"{duration} sec", **VAL),
        _p("Source", **LBL), _p(src, **VAL),
    ]
    mt = Table([m_row], colWidths=[cw6] * 6)
    mt.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_WHITE),
        ("GRID",          (0, 0), (-1, -1), 0.4, C_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 9),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 9),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_BG]),
    ]))
    story.append(mt)
    story.append(Spacer(1, 7 * mm))

    # ────────────────────────────────────────────────────────────────────────
    # AI BEAT CLASSIFICATION
    # ────────────────────────────────────────────────────────────────────────
    if ai_available and ai_dist:
        section("AI Beat Classification (Screening)")

        ai_c   = _ai_color(ai_dominant)
        ai_bg  = _ai_bg(ai_dominant)
        total_beats = sum(ai_dist.values()) if ai_dist else 0

        # Dominant class box
        dom_box = Table(
            [[
                _p(f"Dominant Class:", fontSize=8, textColor=C_GRAY),
                _p(f"<b>{ai_dominant}</b>",
                   fontSize=15, textColor=ai_c, fontName="Helvetica-Bold"),
                _p(f"Total Beats: <b>{total_beats}</b>",
                   fontSize=9, textColor=C_GRAY, alignment=TA_RIGHT),
            ]],
            colWidths=[W * 0.3, W * 0.4, W * 0.3],
        )
        dom_box.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), ai_bg),
            ("BOX",           (0, 0), (-1, -1), 1.5, ai_c),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 12),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(dom_box)
        story.append(Spacer(1, 4 * mm))

        # Distribution table
        dist_data = [[
            _p("<b>Beat Class</b>",  fontSize=8, textColor=C_GRAY, fontName="Helvetica-Bold"),
            _p("<b>Count</b>",       fontSize=8, textColor=C_GRAY, fontName="Helvetica-Bold",
               alignment=TA_CENTER),
            _p("<b>Share (%)</b>",   fontSize=8, textColor=C_GRAY, fontName="Helvetica-Bold",
               alignment=TA_CENTER),
            _p("<b>Classification</b>", fontSize=8, textColor=C_GRAY, fontName="Helvetica-Bold"),
        ]]

        CLASS_DESC = {
            "Normal":           "Sinus rhythm — no anomaly detected",
            "Ventricular":      "Premature ventricular contraction (PVC)",
            "Fusion":           "Fusion beat — mixed origin",
            "Supraventricular": "Supraventricular / atrial ectopic beat",
            "SVT":              "Supraventricular tachycardia",
            "Unknown":          "Unclassified / low-confidence beat",
        }

        row_bgs = []
        for i, (cls, cnt) in enumerate(sorted(ai_dist.items(), key=lambda x: -x[1])):
            pct  = f"{cnt/total_beats*100:.1f}%" if total_beats > 0 else "0%"
            clr  = _ai_color(cls)
            desc = CLASS_DESC.get(cls, cls)
            dist_data.append([
                _p(f"<b>{cls}</b>", fontSize=9, textColor=clr, fontName="Helvetica-Bold"),
                _p(str(cnt), fontSize=9, textColor=C_DARK, alignment=TA_CENTER,
                   fontName="Helvetica-Bold"),
                _p(pct, fontSize=9, textColor=C_DARK, alignment=TA_CENTER),
                _p(desc, fontSize=8.5, textColor=C_GRAY),
            ])
            row_bgs.append(_ai_bg(cls) if cls != "Normal" else C_WHITE)

        dt = Table(dist_data, colWidths=[W * 0.22, W * 0.12, W * 0.12, W * 0.54])
        dt_style = [
            ("BACKGROUND",    (0, 0), (-1, 0), C_BG),
            ("GRID",          (0, 0), (-1, -1), 0.4, C_BORDER),
            ("TOPPADDING",    (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING",   (0, 0), (-1, -1), 9),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 9),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW",     (0, 0), (-1, 0), 1.5, C_BORDER),
        ]
        for i, bg in enumerate(row_bgs):
            dt_style.append(("BACKGROUND", (0, i + 1), (-1, i + 1), bg))
        dt.setStyle(TableStyle(dt_style))
        story.append(dt)
        story.append(Spacer(1, 4 * mm))

        # Alert box
        if ai_alerts > 0:
            alert_box = Table(
                [[_p(
                    f"<b>&#9888; Arrhythmia Alert:</b> "
                    f"{ai_alerts} beat(s) flagged for possible Ventricular or Fusion "
                    f"activity. This is an AI screening signal — "
                    f"<b>please consult a cardiologist</b> for clinical interpretation.",
                    fontSize=9, textColor=C_ERR,
                )]],
                colWidths=[W],
            )
            alert_box.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), C_ERR_L),
                ("BOX",           (0, 0), (-1, -1), 1.5, C_ERR_B),
                ("TOPPADDING",    (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING",   (0, 0), (-1, -1), 12),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ]))
            story.append(alert_box)
            story.append(Spacer(1, 4 * mm))

        story.append(Spacer(1, 3 * mm))

    # ────────────────────────────────────────────────────────────────────────
    # SIGNAL WAVEFORMS
    # ────────────────────────────────────────────────────────────────────────
    section("Signal Waveforms")

    def add_img(path, caption):
        abs_path = _resolve(path)
        if abs_path and os.path.exists(abs_path):
            story.append(_p(caption, fontSize=8, textColor=C_GRAY, alignment=TA_CENTER))
            story.append(Spacer(1, 2 * mm))
            story.append(Image(abs_path, width=W, height=52 * mm))
            story.append(Spacer(1, 5 * mm))

    add_img(recording.get("compare_plot", ""), "Raw vs Filtered Signal Comparison")
    add_img(recording.get("bpm_plot",     ""), "Filtered Signal with R-Peak Detection")

    story.append(Spacer(1, 4 * mm))

    # ────────────────────────────────────────────────────────────────────────
    # MEDICAL DISCLAIMER
    # ────────────────────────────────────────────────────────────────────────
    disc = Table(
        [[_p(
            "<b>&#9888; Medical Disclaimer:</b>  This report is generated by an "
            "AI-assisted screening prototype. It is <b>not a substitute</b> for "
            "professional medical diagnosis. All findings must be verified by a "
            "qualified cardiologist before any clinical decisions are made.",
            fontSize=9, textColor=C_VIOLET,
        )]],
        colWidths=[W],
    )
    disc.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_VBG),
        ("BOX",           (0, 0), (-1, -1), 1.5, C_VBR),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
    ]))
    story.append(disc)

    doc.build(story, onFirstPage=_page_template, onLaterPages=_page_template)
    return output_path
