# -*- coding: utf-8 -*-
"""
脚本 01：把 PDF 拆成「文字」和「图片」两部分。

作用：
  研报和年报里，有些内容是有文字层的（可以直接复制），
  有些其实是图片（扫描件、图表、截图表格）。
  这个脚本帮你一次性看清楚：哪几页能直接读文字，哪几页必须靠图像处理。

用法：
  python 01_extract.py 数据/你的文件.pdf

产出：
  output/xxx_text/   每页一个 .txt 文件
  output/xxx_images/ 每页一张 .png 图片
  output/xxx_report.json  一份体检报告：每页有多少文字、有没有表、是不是疑似扫描件
"""

import json
import sys
from pathlib import Path

def check_deps():
    """检查依赖有没有装好，没装就给出人话提示。"""
    missing = []
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        missing.append("pdfplumber")
    try:
        import fitz  # noqa: F401  (PyMuPDF)
    except ImportError:
        missing.append("pymupdf")
    if missing:
        print("=" * 60)
        print("缺少依赖，请先执行这条命令安装：")
        print()
        print("  pip install " + " ".join(missing) + " -i https://pypi.tuna.tsinghua.edu.cn/simple")
        print()
        print("=" * 60)
        sys.exit(1)

check_deps()

import fitz          # PyMuPDF：负责把页面画成图片
import pdfplumber    # 负责抽文字和表格


def extract(pdf_path: str):
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"找不到文件：{pdf_path}")
        print("小提示：路径里有空格的话，要用英文双引号把整个路径包起来。")
        sys.exit(1)

    base = pdf_path.stem
    out_dir = Path("output") / base
    text_dir = out_dir / "text"
    img_dir = out_dir / "images"
    text_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    print(f"正在处理：{pdf_path.name}")

    report = {"文件名": pdf_path.name, "总页数": 0, "页面明细": [], "疑似扫描件页": []}

    with pdfplumber.open(str(pdf_path)) as pdf:
        total = len(pdf.pages)
        report["总页数"] = total
        doc = fitz.open(str(pdf_path))

        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []

            # 文字少于 50 个字，基本可以断定这一页是图片（扫描件或纯图表页）
            is_scanned = len(text.strip()) < 50

            # 存文字
            (text_dir / f"page_{i:04d}.txt").write_text(text, encoding="utf-8")

            # 存图片（dpi=200 足够 OCR 用，再高文件会很大）
            pix = doc[i - 1].get_pixmap(dpi=200)
            pix.save(str(img_dir / f"page_{i:04d}.png"))

            report["页面明细"].append({
                "页码": i,
                "文字字数": len(text.strip()),
                "表格数": len(tables),
                "疑似扫描件": is_scanned,
            })
            if is_scanned:
                report["疑似扫描件页"].append(i)

            if i % 10 == 0 or i == total:
                print(f"  进度 {i}/{total}")

        doc.close()

    # 存体检报告
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    scanned = report["疑似扫描件页"]
    print()
    print("=" * 60)
    print(f"处理完成，共 {total} 页")
    print(f"文字已存到：{text_dir}")
    print(f"图片已存到：{img_dir}")
    if scanned:
        print(f"⚠ 有 {len(scanned)} 页几乎没有文字，需要靠 OCR 处理：{scanned[:20]}")
        print("  → 下一步：python 02_ocr.py")
    else:
        print("✓ 所有页面都有文字层，可以直接读文本")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python 01_extract.py <PDF文件路径>")
        print("示例：python 01_extract.py data/raw/某公司2024年年度报告.pdf")
        sys.exit(1)
    extract(sys.argv[1])
