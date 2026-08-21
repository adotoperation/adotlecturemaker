import os
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register Windows Native Korean Font (Malgun Gothic)
FONT_NAME = "MalgunGothic"

def register_fonts():
    try:
        regular_path = "C:/Windows/Fonts/malgun.ttf"
        bold_path = "C:/Windows/Fonts/malgunbd.ttf"
        if os.path.exists(regular_path):
            pdfmetrics.registerFont(TTFont("MalgunGothic", regular_path))
        if os.path.exists(bold_path):
            pdfmetrics.registerFont(TTFont("MalgunGothicBold", bold_path))
        
        pdfmetrics.registerFontFamily(
            'MalgunGothic',
            normal='MalgunGothic',
            bold='MalgunGothicBold',
            italic='MalgunGothic',
            boldItalic='MalgunGothicBold'
        )
    except Exception as e:
        print("Font registration warning:", e)

register_fonts()

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont(FONT_NAME, 8)
        self.setFillColor(colors.HexColor("#64748b"))
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)

        # Header bar
        self.line(36, 815, 559, 815)
        self.drawString(36, 820, "강의용 교안")

        # Footer bar (Clean Page Number ONLY)
        self.line(36, 30, 559, 30)
        self.drawRightString(559, 18, f"{self._pageNumber}")
        self.restoreState()

color_map = {
    'blue': '#2563eb',
    'rose': '#e11d48',
    'emerald': '#059669',
    'indigo': '#4f46e5',
    'amber': '#0f172a',
    'slate': '#0f172a'
}

def create_token_tables_for_sentence(tokens, style_word, style_sub, max_width=515):
    """
    Splits sentence tokens into multiple horizontal table rows if total width > max_width.
    Calculates exact colWidths based on character length so text NEVER wraps vertically!
    """
    rows_of_tokens = []
    current_row = []
    current_width = 0

    for t in tokens:
        txt = t.get('text', '')
        sub = t.get('sub_tag', '')
        if txt.strip() == '/':
            w = 16
        else:
            max_chars = max(len(txt), len(sub))
            w = max(24, max_chars * 6.2 + 8)

        if current_width + w > max_width and current_row:
            rows_of_tokens.append(current_row)
            current_row = [(t, w)]
            current_width = w
        else:
            current_row.append((t, w))
            current_width += w

    if current_row:
        rows_of_tokens.append(current_row)

    tables = []
    for r_tokens in rows_of_tokens:
        row_words = []
        row_subs = []
        col_widths = []

        for t, w in r_tokens:
            txt = t.get('text', '')
            sub = t.get('sub_tag', '')
            col_widths.append(w)

            if txt.strip() == '/':
                w_html = "<font color='#9333ea'><b>/</b></font>"
                s_html = ""
            else:
                c_hex = color_map.get(t.get('color'), '#0f172a')
                u_tag = "<u>" if t.get('underline') else ""
                u_close = "</u>" if t.get('underline') else ""
                
                if sub == '접속부사' or t.get('is_conjunction'):
                    w_html = f"<font color='#0284c7'><b>△ {txt}</b></font>"
                else:
                    w_html = f"{u_tag}<font color='{c_hex}'><b>{txt}</b></font>{u_close}"

                s_html = f"<font color='{c_hex}' size=7><b>{sub}</b></font>" if sub else ""

            row_words.append(Paragraph(w_html, style_word))
            row_subs.append(Paragraph(s_html, style_sub))

        t_table = Table([row_words, row_subs], colWidths=col_widths)
        t_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('PADDING', (0, 0), (-1, -1), 1),
            ('LEFTPADDING', (0, 0), (-1, -1), 1),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
        ]))
        tables.append(t_table)

    return tables

def create_handout_pdf(analysis_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()

    style_main_title = ParagraphStyle(
        'MainTitle',
        parent=styles['Heading1'],
        fontName=FONT_NAME,
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=4
    )

    style_badge = ParagraphStyle(
        'Badge',
        fontName=FONT_NAME,
        fontSize=9,
        leading=11,
        textColor=colors.white
    )

    style_summary_label = ParagraphStyle(
        'SummaryLabel',
        fontName=FONT_NAME,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#e11d48')
    )

    style_summary_content = ParagraphStyle(
        'SummaryContent',
        fontName=FONT_NAME,
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#0f172a')
    )

    style_token_word = ParagraphStyle(
        'TokenWord',
        fontName=FONT_NAME,
        fontSize=8,
        leading=10,
        alignment=1, # Center
        textColor=colors.HexColor('#0f172a')
    )

    style_token_sub = ParagraphStyle(
        'TokenSub',
        fontName=FONT_NAME,
        fontSize=7,
        leading=9,
        alignment=1, # Center
        textColor=colors.HexColor('#0f172a')
    )

    style_chunk_kr = ParagraphStyle(
        'ChunkKR',
        fontName=FONT_NAME,
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#065f46')
    )

    story = []

    page_title = analysis_data.get('title') or ""
    if page_title:
        doc_heading = page_title if page_title.endswith("강의용 교안") else f"{page_title} 강의용 교안"
    else:
        doc_heading = "강의용 교안"

    s_info = analysis_data.get('summary_info') or {}

    # ================= PAGE 1: 60% 대형 감성 삽화 & 중하단 지문 핵심 정리 =================
    story.append(Paragraph(f"<b>{doc_heading}</b>", style_main_title))
    story.append(Spacer(1, 4))

    img_path = os.path.join(os.path.dirname(__file__), "static", "illustration.jpg")
    if os.path.exists(img_path):
        # 60% Page Height Illustration (~310pt)
        ghibli_img = Image(img_path, width=523, height=310)
        story.append(ghibli_img)
    else:
        fallback_box = Table([[Paragraph("<b>[삽화 60%]</b>", style_summary_content)]], colWidths=[523], rowHeights=[280])
        fallback_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(fallback_box)

    story.append(Spacer(1, 8))

    sum_header = Table(
        [[Paragraph("<b>지문 핵심 정리</b>", style_badge), Paragraph("<b>핵심 주제, 어휘 및 3단 내용 요약</b>", style_summary_content)]],
        colWidths=[85, 438]
    )
    sum_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#e11d48')),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(sum_header)
    story.append(Spacer(1, 3))

    sum_subj_val = s_info.get('subject', '원격 근무 젊은 직원의 직장 적응 어려움과 유연한 선택지 제공의 필요성')
    sum_kw_val = s_info.get('keywords', '① remotely (원격으로)  ② difficulty (어려움)  ③ fluid (유연한)')
    
    summary_pts = s_info.get('summary', [
        '① 원격 근무를 한 젊은 직원들은 나이 많은 동료보다 업무량 관리 및 대인 관계 형성 어려움 보고.',
        '② 적절한 작업 공간 부족과 적응 시간 부족으로 인한 재택근무의 어려움 존재.',
        '③ 경직된 하이브리드 구조 대신 일상적 근무 장소를 스스로 선택할 수 있는 유연한 옵션 필요.'
    ])
    sum_pts_val = "<br/>".join(summary_pts)

    sum_table_data = [
        [Paragraph("<b>주제</b>", style_summary_label), Paragraph(sum_subj_val, style_summary_content)],
        [Paragraph("<b>핵심어휘</b>", style_summary_label), Paragraph(sum_kw_val, style_summary_content)],
        [Paragraph("<b>세 줄 요약</b>", style_summary_label), Paragraph(sum_pts_val, style_summary_content)]
    ]

    sum_box = Table(sum_table_data, colWidths=[65, 458])
    sum_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#fca5a5')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#ffe4e6')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 3.5),
    ]))
    story.append(sum_box)

    # PAGE BREAK strictly after Page 1
    story.append(PageBreak())

    # ================= PAGE 2+: 전 문장 구문 분석 & 1:1 직독직해 =================
    story.append(Paragraph(f"<b>{doc_heading}</b>", style_main_title))
    story.append(Spacer(1, 6))

    sentences = analysis_data.get('sentences', [])

    for s in sentences:
        s_blocks = []
        
        header_text = f"<b><font color='#ffffff'>구문 분석</font></b>  <font color='#94a3b8'>문장 {s.get('index', 1)}</font>"
        header_table = Table(
            [[Paragraph(header_text, style_summary_content)]],
            colWidths=[523]
        )
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#e11d48')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
        ]))
        s_blocks.append(header_table)
        s_blocks.append(Spacer(1, 3))

        tokens = s.get('tokens', [])
        if tokens:
            token_tables = create_token_tables_for_sentence(tokens, style_token_word, style_token_sub, max_width=523)
            for tt in token_tables:
                s_blocks.append(tt)
                s_blocks.append(Spacer(1, 2))

        chunk_kr = s.get('chunk_korean', '')
        if chunk_kr:
            formatted_kr = chunk_kr.replace('/', " <font color='#9333ea'><b>/</b></font> ")
            kr_p = Paragraph(f"<b><font color='#047857'>[직독직해]</font></b> {formatted_kr}", style_chunk_kr)
            kr_table = Table([[kr_p]], colWidths=[523])
            kr_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ecfdf5')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#a7f3d0')),
                ('PADDING', (0, 0), (-1, -1), 4),
            ]))
            s_blocks.append(kr_table)

        s_blocks.append(Spacer(1, 8))
        story.append(KeepTogether(s_blocks))

    vocab = analysis_data.get('vocabulary', [])
    if vocab:
        v_cells = []
        for item in vocab[:10]:
            w_text = f"• <b>{item.get('word')}</b> : {item.get('meaning')}"
            v_cells.append(Paragraph(w_text, style_summary_content))
        
        v_rows = []
        for i in range(0, len(v_cells), 2):
            left = v_cells[i]
            right = v_cells[i+1] if i+1 < len(v_cells) else Paragraph("", style_summary_content)
            v_rows.append([left, right])
        
        v_table = Table(v_rows, colWidths=[261, 262])
        v_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        
        vocab_block = [
            Paragraph("<b><font color='#0f172a'>주요 어휘 및 구문 정리</font></b>", style_summary_content),
            Spacer(1, 3),
            v_table
        ]
        story.append(KeepTogether(vocab_block))

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()

create_lecture_handout_pdf = create_handout_pdf
