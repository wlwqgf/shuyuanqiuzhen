# -*- coding: utf-8 -*-
"""
src.ingest —— 材料解析入口层

职责：把 PDF 变成机器可处理的结构化产物。
    · 文字层抽取（pdfplumber）
    · 表格结构抽取
    · 页面渲染为图片（PyMuPDF，可切换 pypdfium2）
    · 扫描件页识别（文字量低于阈值即判定需 OCR）
    · 生成页级溯源索引（写入 common/trace_index.py）

边界（重要）：
    本层**不做任何金融判断**。它只回答"这一页上有什么文字、有什么表格、
    是不是扫描件"，不回答"这页上的数字对不对"。

owner：A
"""

__all__ = ["extract"]
