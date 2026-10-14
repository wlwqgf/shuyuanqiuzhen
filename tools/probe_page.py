# -*- coding: utf-8 -*-
"""
tools/probe_page.py —— 单页解析探针

用途：
    诊断某个 PDF 的指定页面能被哪些解析引擎正确读取。
    当抽取结果出现"数字串行""表格错位"时，用本工具定位是
    "文字层本身缺失"还是"抽取方式选错了"。

为什么需要它：
    财务数据的准确性是本项目的生命线。真实年报里表格的排布方式五花八门，
    靠单一引擎（只抽文字）必然出错。本工具用于在正式开发前，
    对每一类页面确定"该用哪个引擎、哪种抽取方式"。

对比的四种抽取方式：
    1. pdfplumber  extract_text()     —— 按阅读顺序抽纯文字
    2. pdfplumber  extract_tables()   —— 基于线条/对齐推断表格
    3. PyMuPDF     get_text("text")   —— 另一套文字抽取实现
    4. PyMuPDF     find_tables()      —— 基于版面分析的表格检测

用法：
    python tools/probe_page.py data/samples/某年报.pdf --page 2

归属：A（队长 · 语义与编排层）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass


def _hr(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def probe(pdf_path: Path, page_no: int) -> int:
    if not pdf_path.exists():
        print(f"找不到文件：{pdf_path}")
        return 1

    print(f"文件：{pdf_path.name}")
    print(f"页码：第 {page_no} 页")

    # ---------- 1. pdfplumber 文字 ----------
    _hr("① pdfplumber  extract_text()　按阅读顺序抽纯文字")
    try:
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as pdf:
            if page_no > len(pdf.pages):
                print(f"该文件只有 {len(pdf.pages)} 页")
                return 1
            page = pdf.pages[page_no - 1]
            text_plumber = page.extract_text() or ""
            tables_plumber = page.extract_tables() or []
        print(f"字符数：{len(text_plumber.strip())}")
        print("-" * 72)
        print(text_plumber.strip() or "（空——该页没有文字层）")
    except Exception as exc:
        print(f"执行失败：{exc}")
        text_plumber, tables_plumber = "", []

    # ---------- 2. pdfplumber 表格 ----------
    _hr("② pdfplumber  extract_tables()　基于线条/对齐推断表格")
    print(f"识别到表格数：{len(tables_plumber)}")
    for i, table in enumerate(tables_plumber, 1):
        print(f"\n  表 {i}（{len(table)} 行）")
        for row in table[:12]:
            cells = [(c or "").replace("\n", " ").strip() for c in row]
            print("    | " + " | ".join(cells))

    # ---------- 3. PyMuPDF 文字 ----------
    _hr("③ PyMuPDF  get_text('text')　另一套文字抽取实现")
    try:
        import pymupdf

        doc = pymupdf.open(str(pdf_path))
        page = doc[page_no - 1]
        text_mupdf = page.get_text("text")
        print(f"字符数：{len(text_mupdf.strip())}")
        print("-" * 72)
        print(text_mupdf.strip() or "（空——该页没有文字层）")

        # ---------- 4. PyMuPDF 表格 ----------
        _hr("④ PyMuPDF  find_tables()　基于版面分析的表格检测")
        try:
            finder = page.find_tables()
            tables = finder.tables
            print(f"识别到表格数：{len(tables)}")
            for i, table in enumerate(tables, 1):
                data = table.extract()
                print(f"\n  表 {i}（{len(data)} 行）")
                for row in data[:12]:
                    cells = [(c or "").replace("\n", " ").strip() for c in row]
                    print("    | " + " | ".join(cells))
        except Exception as exc:
            print(f"表格检测不可用：{exc}")
        doc.close()
    except Exception as exc:
        print(f"执行失败：{exc}")

    _hr("结论提示")
    print("若 ① 出现数字串行（不同列的文字被交错拼接），说明该页必须用表格方式抽取；")
    print("若 ① 与 ③ 都为空，说明该页没有文字层，只能走 OCR（图像处理）路径。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="单页解析探针")
    parser.add_argument("pdf", help="PDF 文件路径")
    parser.add_argument("--page", type=int, default=1, help="页码（从 1 开始）")
    args = parser.parse_args()
    return probe(Path(args.pdf), args.page)


if __name__ == "__main__":
    sys.exit(main())
