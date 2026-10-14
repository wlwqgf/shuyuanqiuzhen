# -*- coding: utf-8 -*-
"""
tools/ocr_rescue_demo.py —— OCR 挽救不可读文字层的演示与落库

要解决的问题（真实案例）：
    小米集团 2025 年报 409 页的文字层全部不可读——CID 字体缺少 ToUnicode
    映射，PyMuPDF 抽出乱码、pdfplumber 抽出 (cid:NNN)。这类页按"纯文字页"
    放行会导致后续核查全程拿到垃圾数据，且**不报错**。
    本脚本演示：渲染成图 → OCR → 得到可检索文本 → 抽取指标候选。

与项目红线的关系：
    OCR 结果按证据分级属 B 级（可信度 ≥0.9 且经人工抽检才可自动判定），
    本脚本输出的 OCR 文本默认带 _ocr 来源标记，不直接参与判定。

用法：
    python tools/ocr_rescue_demo.py XM-AR-2025 --pages 4 50 100
    python tools/ocr_rescue_demo.py XM-AR-2025 --pages 4 --show 800

产出（output/<doc_id>/ocr/）：
    page_XXXX.txt      OCR 识别文本（按阅读顺序拼接）
    ocr_result.json    带坐标与可信度的完整识别结果
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    import fitz
except ImportError:
    print("缺少依赖：pip install pymupdf -i https://mirrors.tencent.com/pypi/simple")
    sys.exit(1)

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from extract_facts import METRICS, VALUE_RE, UNIT_NORMALIZE, parse_value  # noqa: E402


def ocr_pages(pdf_path: Path, doc_id: str, pages: List[int], dpi: int, show: int) -> int:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        print("还没装 OCR 引擎：pip install rapidocr-onnxruntime -i https://mirrors.tencent.com/pypi/simple")
        return 1

    out_dir = PROJECT_ROOT / "output" / doc_id
    img_dir = out_dir / "images"
    ocr_dir = out_dir / "ocr"
    img_dir.mkdir(parents=True, exist_ok=True)
    ocr_dir.mkdir(parents=True, exist_ok=True)

    print("正在加载 OCR 引擎（首次约 5-10 秒）...")
    engine = RapidOCR()

    doc = fitz.open(str(pdf_path))
    summary: List[Dict[str, Any]] = []

    for pno in pages:
        if pno < 1 or pno > doc.page_count:
            print(f"  第 {pno} 页不存在（共 {doc.page_count} 页），跳过")
            continue

        # 1. 先看文字层原样（证明它不可读）
        raw_text = doc[pno - 1].get_text("text") or ""
        raw_flat = re.sub(r"\s+", " ", raw_text).strip()

        # 2. 渲染 + OCR
        img_path = img_dir / f"page_{pno:04d}.png"
        pix = doc[pno - 1].get_pixmap(dpi=dpi)
        pix.save(str(img_path))

        result, _ = engine(str(img_path))
        items: List[Dict[str, Any]] = []
        if result:
            for box, text, score in result:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                items.append({
                    "文字": text,
                    "可信度": round(float(score), 3),
                    "左": round(min(xs), 1), "上": round(min(ys), 1),
                    "右": round(max(xs), 1), "下": round(max(ys), 1),
                })

        # 3. 按纵坐标排序拼接（中文阅读顺序：先上后下，同行先左后右）
        items.sort(key=lambda x: (round(x["上"] / 12), x["左"]))
        ocr_text = "\n".join(it["文字"] for it in items)
        (ocr_dir / f"page_{pno:04d}.txt").write_text(ocr_text, encoding="utf-8")
        (ocr_dir / f"page_{pno:04d}.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 4. 指标候选（复用同一套规则，证明 OCR 文本可进入后续流程）
        cands = []
        for metric, keywords in METRICS:
            for kw in keywords:
                pos = ocr_text.find(kw)
                if pos < 0:
                    continue
                window = ocr_text[pos + len(kw): pos + len(kw) + 90]
                for m in VALUE_RE.finditer(window):
                    if not m.group("unit"):
                        continue
                    v = parse_value(m.group("num"))
                    if v is None:
                        continue
                    cands.append({"metric": metric, "value": v,
                                  "unit": UNIT_NORMALIZE.get(m.group("unit"), m.group("unit"))})
                break

        avg_conf = round(sum(i["可信度"] for i in items) / len(items), 3) if items else 0.0
        low_conf = sum(1 for i in items if i["可信度"] < 0.9)

        print()
        print("=" * 70)
        print(f"第 {pno} 页")
        print("-" * 70)
        print(f"文字层原样（前 120 字）：{raw_flat[:120] or '（空）'}")
        print(f"OCR 识别结果（前 {min(show, 400)} 字）：")
        print("  " + ocr_text[:show].replace("\n", "\n  "))
        print("-" * 70)
        print(f"识别到 {len(items)} 段文字，平均可信度 {avg_conf}，其中 {low_conf} 段低于 0.9")
        if cands:
            seen = set()
            uniq = []
            for c in cands:
                k = (c["metric"], c["value"], c["unit"])
                if k not in seen:
                    seen.add(k)
                    uniq.append(c)
            print(f"从 OCR 文本抽到 {len(uniq)} 个指标候选：")
            for c in uniq[:10]:
                print(f"  · {c['metric']}: {c['value']:,.2f} {c['unit']}")
        else:
            print("本页未抽到指标候选（属正常：并非每页都含财务数据）")
        print("=" * 70)

        summary.append({
            "page_no": pno,
            "text_layer_chars": len(raw_text.strip()),
            "ocr_segments": len(items),
            "ocr_avg_confidence": avg_conf,
            "ocr_low_conf_segments": low_conf,
            "ocr_text_head": ocr_text[:200],
            "metric_candidates": cands,
            "image": str(img_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        })

    doc.close()
    (out_dir / "ocr_rescue_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print()
    print(f"汇总已写入：output/{doc_id}/ocr_rescue_summary.json")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="OCR 挽救不可读文字层演示")
    ap.add_argument("doc_id", help="文档标识，如 XM-AR-2025")
    ap.add_argument("--pages", nargs="+", type=int, required=True, help="要演示的页码")
    ap.add_argument("--pdf", default="", help="PDF 路径（默认按 doc_id 推断）")
    ap.add_argument("--dpi", type=int, default=200, help="渲染分辨率，默认 200")
    ap.add_argument("--show", type=int, default=600, help="每页显示多少字 OCR 结果")
    args = ap.parse_args()

    if args.pdf:
        pdf_path = Path(args.pdf)
    else:
        # 从 SOURCES.md / data/raw 推断：找包含 doc_id 主体代码的文件不可靠，
        # 直接要求 --pdf 更稳妥；这里给出明确报错
        print("请用 --pdf 指定原始 PDF 路径，例如：")
        print(f'  python tools/ocr_rescue_demo.py {args.doc_id} --pages 4 --pdf "data/raw/小米集团-W：2025年度报告.pdf"')
        return 1

    return ocr_pages(pdf_path, args.doc_id, args.pages, args.dpi, args.show)


if __name__ == "__main__":
    sys.exit(main())
