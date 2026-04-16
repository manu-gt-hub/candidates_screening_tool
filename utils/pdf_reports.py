"""PDF report generation for technical tests, ranking, and evaluations.

Requires ``reportlab`` — import this module only AFTER ``%pip install reportlab``.
"""
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable,
)


# ======================================================================
#  Helpers
# ======================================================================

_MAX_FILENAME_LEN = 80


def _safe_name(name):
    cleaned = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    cleaned = cleaned.replace(" ", "_")
    return cleaned[:_MAX_FILENAME_LEN]


def _score_color(pct):
    if pct >= 70:
        return "#2E7D32"
    elif pct >= 50:
        return "#F57F17"
    return "#C62828"


def _timestamp():
    """Return a filename-safe timestamp: DD_MM_YYYY_HH_MM."""
    return datetime.now().strftime("%d_%m_%Y_%H_%M")


def _logo_elements(logo_path, width, height, doc_width):
    """Return story elements for the logo header, or empty list if logo is unavailable."""
    if not logo_path or not os.path.isfile(logo_path):
        return []
    logo = Image(logo_path, width=width, height=height, kind="proportional")
    ht = Table([[logo]], colWidths=[doc_width])
    ht.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "RIGHT"),
        ("VALIGN", (0, 0), (0, 0), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [ht, Spacer(1, 3 * mm)]


# ======================================================================
#  1. Technical Test PDF  (one per candidate, multi-page)
# ======================================================================

_TEST_STYLES = None

def _get_test_styles():
    global _TEST_STYLES
    if _TEST_STYLES is None:
        base = getSampleStyleSheet()
        _TEST_STYLES = {
            "title": ParagraphStyle(
                "TT_Title", parent=base["Heading1"],
                fontSize=16, fontName="Helvetica-Bold",
                spaceAfter=6, spaceBefore=0, textColor=HexColor("#1B365D"),
            ),
            "instructions": ParagraphStyle(
                "TT_Instr", parent=base["Normal"],
                fontSize=10, fontName="Helvetica-Oblique",
                spaceAfter=10, leading=13, textColor=HexColor("#37474F"),
            ),
            "scenario": ParagraphStyle(
                "TT_Sc", parent=base["Heading2"],
                fontSize=11.5, fontName="Helvetica-Bold",
                spaceBefore=12, spaceAfter=4, textColor=HexColor("#00695C"),
            ),
            "body": ParagraphStyle(
                "TT_Body", parent=base["Normal"],
                fontSize=10, fontName="Helvetica", alignment=TA_JUSTIFY,
                spaceAfter=4, leading=12.5, textColor=HexColor("#333333"),
            ),
            "example": ParagraphStyle(
                "TT_Ex", parent=base["Normal"],
                fontSize=10, fontName="Helvetica-Oblique",
                textColor=HexColor("#CC8400"), spaceAfter=4, leading=12.5,
            ),
            "question": ParagraphStyle(
                "TT_Q", parent=base["Normal"],
                fontSize=10, fontName="Helvetica-Bold",
                spaceAfter=10, leading=12.5, textColor=HexColor("#8B1A1A"),
            ),
        }
    return _TEST_STYLES


def build_technical_test_pdf(candidate_data, output_path, logo_path=None):
    """Generate a PDF technical test for a candidate.

    Content flows across multiple pages automatically via reportlab\'s
    SimpleDocTemplate — no text truncation is applied.

    Returns:
        Path to the generated PDF file.
    """
    S = _get_test_styles()
    name = candidate_data["name"]
    test_data = candidate_data.get("technical_test") or {}
    role = candidate_data.get("candidate_role", "") or candidate_data.get("role", "Technical")

    filename = os.path.join(output_path, f"Technical_Test_{_safe_name(name)}.pdf")
    doc = SimpleDocTemplate(
        filename, pagesize=A4,
        rightMargin=1.5 * cm, leftMargin=1.5 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )
    story = []

    # Header logo (optional)
    story.extend(_logo_elements(logo_path, 6 * cm, 6 * cm, doc.width))

    # Title
    test_title = test_data.get("test_title", f"{role} Screening Test")
    story.append(Paragraph(test_title, S["title"]))

    # Instructions (full text — no truncation)
    instructions = test_data.get("instructions", "")
    if instructions:
        story.append(Paragraph(f"<b>Instructions:</b> {instructions}", S["instructions"]))
    else:
        story.append(Paragraph(
            "<b>Instructions:</b> Answer each scenario clearly and concisely. "
            "If you know specific technologies that apply, use them in your response to solve the proposed scenarios.",
            S["instructions"],
        ))

    # Scenarios (full text — no truncation)
    for i, sc in enumerate(test_data.get("scenarios", []), 1):
        if hasattr(sc, "asDict"):
            sc = sc.asDict()
        num = sc.get("number", i)
        title = sc.get("title", f"Technical Scenario {i}")
        story.append(Paragraph(f"Scenario {num} \u2014 {title}", S["scenario"]))
        if sc.get("description"):
            story.append(Paragraph(sc["description"], S["body"]))
        if sc.get("example"):
            story.append(Paragraph(f"<b>Example:</b> {sc['example']}", S["example"]))
        if sc.get("question"):
            story.append(Paragraph(f"<b>Question:</b> {sc['question']}", S["question"]))

    doc.build(story)
    return filename


# ======================================================================
#  2. Candidate Ranking Report  (single PDF — suggested ranking, no discards)
# ======================================================================

def build_ranking_report_pdf(ranking_rows, output_path, logo_path=None,
                              min_threshold=70, tested_names=None):
    """Generate a ranking summary PDF with colour-coded tiers.

    All candidates appear in a single ranked list.  Colour coding:
      * **Green** (>= *min_threshold*) — recommended for technical test.
      * **Amber** (>= 50 and < *min_threshold*) — borderline; consider for interview.
      * **Red** (< 50) — not recommended at this time.

    Args:
        ranking_rows:  List of Row objects from the ranking query.
        output_path:   Directory for the output PDF.
        logo_path:     Path to logo image (optional; omitted if None or file missing).
        min_threshold: Minimum match % considered "recommended" (default 70).
        tested_names:  Set of candidate names that received a technical test.

    Returns:
        Path to the generated PDF file.
    """
    tested_names = tested_names or set()
    base = getSampleStyleSheet()
    S = {
        "title": ParagraphStyle("RR_Ti", parent=base["Heading1"], fontSize=16, fontName="Helvetica-Bold", spaceAfter=2, textColor=HexColor("#1B365D")),
        "subtitle": ParagraphStyle("RR_Su", parent=base["Normal"], fontSize=9, fontName="Helvetica", textColor=HexColor("#666666"), spaceAfter=10),
        "legend": ParagraphStyle("RR_Lg", parent=base["Normal"], fontSize=8, fontName="Helvetica", textColor=HexColor("#888888"), spaceAfter=2, leading=11),
        "section": ParagraphStyle("RR_Se", parent=base["Heading2"], fontSize=12, fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6, textColor=HexColor("#1a1a1a")),
        "candidate": ParagraphStyle("RR_Cn", parent=base["Normal"], fontSize=10, fontName="Helvetica-Bold", spaceAfter=2),
        "body": ParagraphStyle("RR_Bo", parent=base["Normal"], fontSize=9, fontName="Helvetica", alignment=TA_JUSTIFY, spaceAfter=3, leading=12),
        "techs": ParagraphStyle("RR_Te", parent=base["Normal"], fontSize=8, fontName="Helvetica-Oblique", textColor=HexColor("#555555"), spaceAfter=4, leading=10),
        "gaps": ParagraphStyle("RR_Gp", parent=base["Normal"], fontSize=8, fontName="Helvetica", textColor=HexColor("#999999"), spaceAfter=8, leading=10),
    }

    def _tier_color(pct):
        if pct >= min_threshold:
            return "#2E7D32"
        elif pct >= 50:
            return "#F57F17"
        return "#C62828"

    report_file = os.path.join(output_path, f"Candidate_Ranking_Report_{_timestamp()}.pdf")
    doc = SimpleDocTemplate(report_file, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    story = []

    # Header — logo (optional)
    story.extend(_logo_elements(logo_path, 4 * cm, 4 * cm, doc.width))

    story.append(Paragraph("Candidate Ranking Report", S["title"]))
    story.append(Paragraph(
        f"Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')} \u2014 {len(ranking_rows)} candidate(s) evaluated",
        S["subtitle"],
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#cccccc")))
    story.append(Spacer(1, 2*mm))

    # Legend
    story.append(Paragraph(
        f"<font color='#2E7D32'>\u25cf</font> Recommended (\u2265 {min_threshold}%) &nbsp;&nbsp;"
        f"<font color='#F57F17'>\u25cf</font> Borderline (50\u2013{min_threshold - 1}%) &nbsp;&nbsp;"
        f"<font color='#C62828'>\u25cf</font> Not recommended (&lt; 50%)",
        S["legend"],
    ))
    story.append(Spacer(1, 4*mm))

    # Single ranked list (sorted by score descending)
    sorted_rows = sorted(ranking_rows, key=lambda r: r["ranking_percentage"], reverse=True)

    story.append(Paragraph(f"Suggested Ranking ({len(sorted_rows)} candidates)", S["section"]))

    for r in sorted_rows:
        pct = r["ranking_percentage"]
        color = _tier_color(pct)
        techs = ", ".join(r["key_technologies"][:10]) if r["key_technologies"] else "N/A"
        gaps = ", ".join(r["gaps"][:5]) if r["gaps"] else ""
        name = r["name"]
        has_test = name in tested_names

        # Name + score + seniority + optional badge
        badge_html = "  <font color='#2E7D32'>\u2714 Technical test generated</font>" if has_test else ""
        cand_role = r.get("candidate_role", "") or ""
        cand_seniority = r.get("candidate_seniority", "") or ""
        role_info = f"{cand_role} \u00b7 " if cand_role else ""
        story.append(Paragraph(
            f"{name}  <font color='{color}'><b>{pct:.0f}%</b></font>  "
            f"\u2014  {role_info}{cand_seniority} \u00b7 {r['years_of_experience']}y exp"
            f"{badge_html}",
            S["candidate"],
        ))
        story.append(Paragraph(r["report_summary"] or "", S["body"]))
        story.append(Paragraph(f"Technologies: {techs}", S["techs"]))
        if gaps:
            story.append(Paragraph(f"Gaps: {gaps}", S["gaps"]))

    doc.build(story)
    return report_file


# ======================================================================
#  3. Evaluation Report PDF  (one per candidate)
# ======================================================================

def build_evaluation_report_pdf(ev, output_path):
    """Generate a colour-coded evaluation report for a single candidate.

    Returns:
        Path to the generated PDF file.
    """
    base = getSampleStyleSheet()
    S = {
        "title": ParagraphStyle("EV_Ti", parent=base["Heading1"], fontSize=18, fontName="Helvetica-Bold", spaceAfter=4, textColor=HexColor("#000000")),
        "subtitle": ParagraphStyle("EV_Su", parent=base["Normal"], fontSize=12, fontName="Helvetica-Bold", textColor=HexColor("#333333"), spaceAfter=12),
        "section": ParagraphStyle("EV_Se", parent=base["Heading2"], fontSize=13, fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6, textColor=HexColor("#1a1a1a")),
        "body": ParagraphStyle("EV_Bo", parent=base["Normal"], fontSize=10, fontName="Helvetica", alignment=TA_JUSTIFY, spaceAfter=6, leading=14),
        "bullet": ParagraphStyle("EV_Bu", parent=base["Normal"], fontSize=10, fontName="Helvetica", leftIndent=18, spaceAfter=4, leading=13, bulletIndent=6),
        "score_high": ParagraphStyle("EV_Sh", parent=base["Normal"], fontSize=28, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=HexColor("#2E7D32")),
        "score_mid": ParagraphStyle("EV_Sm", parent=base["Normal"], fontSize=28, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=HexColor("#F57F17")),
        "score_low": ParagraphStyle("EV_Sl", parent=base["Normal"], fontSize=28, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=HexColor("#C62828")),
        "rec_pos": ParagraphStyle("EV_Rp", parent=base["Normal"], fontSize=14, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=HexColor("#2E7D32"), spaceBefore=4),
        "rec_neg": ParagraphStyle("EV_Rn", parent=base["Normal"], fontSize=14, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=HexColor("#C62828"), spaceBefore=4),
        "rec_neu": ParagraphStyle("EV_Rne", parent=base["Normal"], fontSize=14, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=HexColor("#F57F17"), spaceBefore=4),
        "sc_title": ParagraphStyle("EV_St", parent=base["Heading3"], fontSize=11, fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4, textColor=HexColor("#1a1a1a")),
        "feedback": ParagraphStyle("EV_Fb", parent=base["Normal"], fontSize=10, fontName="Helvetica-Oblique", spaceAfter=6, leading=13, textColor=HexColor("#444444")),
    }

    def _score_style(s):
        if s >= 70: return S["score_high"]
        if s >= 50: return S["score_mid"]
        return S["score_low"]

    def _rec_style(r):
        if r in ("Strong Hire", "Hire"): return S["rec_pos"]
        if r in ("No Hire", "Lean No Hire"): return S["rec_neg"]
        return S["rec_neu"]

    name = ev.get("candidate_name", "Unknown")
    fpath = os.path.join(output_path, f"Evaluation_Report_{_safe_name(name)}_{_timestamp()}.pdf")
    doc = SimpleDocTemplate(fpath, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    story = []

    # Header
    story.append(Paragraph("Technical Response Evaluation Report", S["title"]))
    story.append(Paragraph(f"Candidate: {name}", S["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#cccccc")))
    story.append(Spacer(1, 0.4*cm))

    # Score card
    match_pct = ev.get("match_percentage", 0) or 0
    rec = ev.get("overall_recommendation", "N/A") or "N/A"
    lbl_style = ParagraphStyle("lbl", parent=base["Normal"], alignment=TA_CENTER, fontSize=9, textColor=HexColor("#666666"))
    card = Table(
        [[Paragraph(f"{match_pct:.0f}%", _score_style(match_pct)), Paragraph(rec, _rec_style(rec))],
         [Paragraph("Role Match", lbl_style), Paragraph("Recommendation", lbl_style)]],
        colWidths=[doc.width / 2] * 2, rowHeights=[45, 18],
    )
    card.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, HexColor("#dddddd")),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#f9f9f9")),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
    ]))
    story.append(card)
    story.append(Spacer(1, 0.5*cm))

    # Suitability
    story.append(Paragraph("Suitability Assessment", S["section"]))
    story.append(Paragraph(ev.get("suitability_assessment", ""), S["body"]))

    # Highlights
    highlights = ev.get("highlights") or []
    if highlights:
        story.append(Paragraph("Key Highlights", S["section"]))
        for h in highlights:
            story.append(Paragraph(f"\u2022 {h}", S["bullet"]))

    # Scenario evaluations
    scenarios = ev.get("scenario_evaluations") or []
    if scenarios:
        story.append(Paragraph("Scenario-by-Scenario Evaluation", S["section"]))
        for sc in scenarios:
            if hasattr(sc, "asDict"):
                sc = sc.asDict()
            num, title = sc.get("scenario_number", "?"), sc.get("scenario_title", "")
            sc_score = sc.get("score", 0) or 0
            color = _score_color(sc_score)
            story.append(Paragraph(f"Scenario {num} \u2014 {title}  <font color='{color}'><b>[{sc_score:.0f}/100]</b></font>", S["sc_title"]))
            story.append(Paragraph(sc.get("feedback", ""), S["feedback"]))

    # Strengths / Weaknesses / Improvements
    _sections = [
        ("Strengths", "strengths", "\u2713"), ("Weaknesses", "weaknesses", "\u2717"),
        ("Areas for Improvement", "improvement_areas", "\u2192"),
    ]
    for label, key, icon in _sections:
        items = ev.get(key) or []
        if items:
            story.append(Paragraph(label, S["section"]))
            for item in items:
                story.append(Paragraph(f"{icon} {item}", S["bullet"]))

    doc.build(story)
    return fpath
