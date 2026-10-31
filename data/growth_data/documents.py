"""Export four presentation PDFs from the canonical Markdown knowledge sources."""

import os
from pathlib import Path
from xml.sax.saxutils import escape


def export_guides(root,font=None):
    from reportlab import rl_config
    rl_config.invariant=1
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,HRFlowable
    from reportlab.lib.pagesizes import A4
    candidates=[font,os.environ.get("GROWTH_PDF_FONT"),"/System/Library/Fonts/Supplemental/Arial.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    selected=next((Path(p) for p in candidates if p and Path(p).is_file()),None)
    if selected is None:raise ValueError("Cần font Unicode hỗ trợ tiếng Việt: dùng --font hoặc GROWTH_PDF_FONT")
    pdfmetrics.registerFont(TTFont("GrowthUnicode",str(selected)))
    body=ParagraphStyle("body",fontName="GrowthUnicode",fontSize=11,leading=17,textColor=colors.HexColor("#222222"),spaceAfter=12)
    title=ParagraphStyle("title",parent=body,fontSize=22,leading=29,spaceAfter=18,textColor=colors.HexColor("#13254A"))
    meta=ParagraphStyle("meta",parent=body,fontSize=9,leading=13,textColor=colors.HexColor("#5B616B"))
    root=Path(root);out=root/"pdf";out.mkdir(parents=True,exist_ok=True)
    outputs=[]
    for source in sorted((root/"knowledge").glob("*_demo.md")):
        text=source.read_text(encoding="utf-8")
        main=text.split("---",2)[-1].strip()
        heading,*paragraphs=main.split("\n\n")
        story=[Paragraph("GROWTH AGENTS / DATA SERVICE",meta),Spacer(1,12),Paragraph(escape(heading.lstrip("# ")),title),
               Paragraph(f"Tài liệu: {escape(source.stem)} · Phiên bản 1 · Hiệu lực 18/10/2026",meta),
               HRFlowable(width="100%",thickness=1,color=colors.HexColor("#D2461A")),Spacer(1,16)]
        for p in paragraphs:story.append(Paragraph(escape(p).replace("\n","<br/>"),body))
        story.extend([Spacer(1,16),Paragraph("Nguồn chuẩn: Markdown cùng tên trong knowledge/. Các quy tắc được code kiểm tra; tài liệu này giải thích quy tắc.",meta)])
        target=out/source.with_suffix(".pdf").name
        def footer(canvas,doc):
            canvas.setFont("GrowthUnicode",8);canvas.setFillColor(colors.HexColor("#5B616B"))
            canvas.drawString(48,30,"sàn·demo · Dữ liệu và chính sách giả lập")
            canvas.drawRightString(A4[0]-48,30,f"Trang {doc.page}")
        SimpleDocTemplate(str(target),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=40,bottomMargin=50,title=heading.lstrip("# "),author="Growth Agents").build(story,onFirstPage=footer,onLaterPages=footer)
        outputs.append(target)
    return outputs
