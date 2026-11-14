"""Bước 8: report_final.md → Word (.docx), định dạng Times New Roman 13, A4, bảng kẻ khung, có mục lục."""
import sys
from pathlib import Path

import pypandoc
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

ROOT = Path(__file__).resolve().parents[1]
src, out = ROOT / "report" / "report_final.md", Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "report" / "BaoCao_DT01.docx"
tmp = ROOT / "report" / "_tmp.docx"
pypandoc.convert_file(str(src), "docx", outputfile=str(tmp),
                      extra_args=["--from=markdown+tex_math_dollars", "--toc", "--toc-depth=2",
                                  f"--resource-path={ROOT / 'report'}", "-M", "toc-title=Mục lục"])
d = Document(str(tmp))
for s in d.sections:
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.left_margin, s.right_margin, s.top_margin, s.bottom_margin = Cm(3), Cm(2), Cm(2), Cm(2)


def set_font(style, size=None, bold=None):
    style.font.name = "Times New Roman"
    rpr = style.element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts"); rpr.append(rf)
    for k in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(k), "Times New Roman")
    for k in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        if rf.get(qn(k)) is not None:
            del rf.attrib[qn(k)]
    if size:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold


names = {s.name for s in d.styles}
for n, sz in [("Normal", 13), ("Body Text", 13), ("First Paragraph", 13), ("Compact", 12), ("Title", 17), ("Subtitle", 13),
              ("Date", 12), ("Heading 1", 15), ("Heading 2", 13), ("Heading 3", 13), ("Image Caption", 11),
              ("Table Caption", 11), ("Source Code", 10)]:
    if n in names:
        st = d.styles[n]
        set_font(st, sz, True if n.startswith("Heading") or n == "Title" else None)
        if n.startswith("Heading") or n == "Title":
            st.font.color.rgb = None
if "Source Code" in names:  # mã giả giữ font đơn cách
    d.styles["Source Code"].font.name = "Consolas"
for n in ("Body Text", "First Paragraph"):
    if n in names:
        pf = d.styles[n].paragraph_format
        pf.line_spacing, pf.space_after = 1.3, Pt(6)
for t in d.tables:
    tblPr = t._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "4"); e.set(qn("w:color"), "808080")
        b.append(e)
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    tblPr.append(b)
    ncol = len(t.columns)
    size = 10 if ncol <= 6 else 9
    for i, row in enumerate(t.rows):
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(0)
                for r in p.runs:
                    r.font.size = Pt(size)
                    if i == 0:
                        r.font.bold = True
d.save(str(out))
tmp.unlink()
print("saved", out)
