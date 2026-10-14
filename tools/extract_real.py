# -*- coding: utf-8 -*-
"""
tools/extract_real.py —— 真实材料解析（PDF → 逐页文本 + 页面体检 + 页级溯源索引）

与 src/01_extract.py（样本版）的区别：
  1. **不默认渲染每页图片**。真实年报动辄三五百页，逐页渲染会产生
     数 GB 文件；本工具只给"需要 OCR 的页"渲染图片，其余页仅记录统计信号。
  2. **页面分类用真实信号**，不再只用"文字 < 50 字"这一条粗判据：
       · 文字量、栅格图像数量与覆盖率、矢量图形数量与覆盖率、可检测表格数
       · 据此区分 TEXT / TABLE / CHART / SCANNED 四类
  3. 直接产出与 src/common/trace_index.py 兼容的 report.json 与索引，
     每条数据可追溯到原始页码。

用法：
    python tools/extract_real.py data/raw/中国平安2025年报.pdf --doc-id ZGPA-AR-2025
    python tools/extract_real.py data/raw/腾讯2025年报.pdf   --doc-id TX-AR-2025  --render none
    python tools/extract_real.py data/raw/小米集团-W：2025年度报告.pdf --doc-id XM-AR-2025

参数：
    --doc-id    文档标识（见 docs/data_spec.md 命名规则，登记后不得更改）
    --render    给哪些页渲染图片：scanned（默认，仅无文字层页）/ chart（加渲染
                疑似图表页）/ none（完全不渲染）
    --dpi       渲染分辨率，默认 150（OCR 用 150 足够，200 文件会大一倍）

产出（output/<doc_id>/）：
    text/page_XXXX.txt   逐页文本
    images/page_XXXX.png 需 OCR 页的图片（按 --render 决定）
    report.json          页面体检报告（含页面类型与覆盖率信号）
    trace_index.json     页级溯源索引
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    print("缺少依赖，请先安装：pip install pymupdf -i https://mirrors.tencent.com/pypi/simple")
    sys.exit(1)

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 页面类型 → 与 src/common/schema.py 的 PageType 枚举值严格一致（小写）
P_TEXT, P_TABLE, P_CHART, P_SCANNED = "text", "table", "chart", "scanned"

# 文字层可用性判据：真实年报中，"有文字层"不等于"文字可读"。
# 小米集团年报即为例证：409 页文字层全部因 CID 字体缺少 ToUnicode 映射
# 而不可读（PyMuPDF 抽出乱码、pdfplumber 抽出 (cid:NNN)），必须整份走 OCR。
# 判据：文本长度足够时，若不含年报必现的常见词，则判定为不可读。
COMMON_WORDS = [
    "年度", "报告", "報告", "公司", "股东", "股東", "收入", "利润", "利潤",
    "资产", "資產", "人民币", "人民幣", "annual", "report", "revenue", "profit",
]


def text_layer_usable(text: str) -> Optional[bool]:
    """判断文字层是否可读。文本过短时返回 None（难以判定）。"""
    t = (text or "").strip()
    if len(t) < 80:
        return None if not t else True
    if "(cid:" in t or "\ufffd" in t:
        return False
    return any(w.lower() in t.lower() for w in COMMON_WORDS)


# ============================================================
# 单页体检
# ============================================================

def page_stats(page: "fitz.Page") -> Dict[str, Any]:
    """采集一页的真实信号：文字量、图像覆盖率、矢量覆盖率、表格数。"""
    rect = page.rect
    area = max(rect.width * rect.height, 1.0)

    text = page.get_text("text") or ""
    clean = text.strip()

    # 栅格图像：累加"与页面矩形相交后"的可见面积。
    # 两个都必须处理，否则覆盖率会骗人：
    #   ① 旋转/超框图片（如平安的横向图表）bbox 超出页面，不裁剪会算出 >100% 的面积；
    #   ② 整页底图（如腾讯每页都有一张 2545x3485 的全页扫描底图）会让覆盖率恒为 1.0，
    #      把纯文字页误判成图表页。因此区分"整页图"与"局部图"两个信号。
    img_area = 0.0
    n_imgs = 0
    full_page_img = False
    try:
        d = page.get_text("dict")
        for b in d.get("blocks", []):
            if b.get("type") == 1:
                n_imgs += 1
                x0, y0, x1, y1 = b.get("bbox", (0, 0, 0, 0))
                # 与页面矩形求交，负值裁掉
                cx0, cy0 = max(x0, rect.x0), max(y0, rect.y0)
                cx1, cy1 = min(x1, rect.x1), min(y1, rect.y1)
                clipped = max(0.0, cx1 - cx0) * max(0.0, cy1 - cy0)
                img_area += clipped
                if clipped / area >= 0.90:
                    full_page_img = True
    except Exception:
        pass

    # 矢量图形：年报里的柱状图/折线图多为矢量路径，不是图片
    draw_area = 0.0
    n_draw = 0
    try:
        for dr in page.get_drawings():
            n_draw += 1
            r = dr.get("rect")
            if r is not None:
                draw_area += max(0.0, r.width) * max(0.0, r.height)
    except Exception:
        pass

    # 表格检测
    table_count = 0
    try:
        tf = page.find_tables()
        table_count = len(tf.tables)
    except Exception:
        table_count = 0

    return {
        "chars": len(clean),
        "n_images": n_imgs,
        "image_coverage": round(min(img_area / area, 1.0), 4),
        "full_page_image": full_page_img,
        "n_drawings": n_draw,
        "drawing_coverage": round(min(draw_area / area, 1.0), 4),
        "table_count": table_count,
    }


def classify(st: Dict[str, Any], usable: Optional[bool]) -> (str, str):  # type: ignore[valid-type]
    """依据真实信号判定页面类型，并给出人话说明。

    注意：CHART 是"候选"而非结论——含大图的页面可能是产品照片而非数据图表，
    是否承载数值须人工确认。这与项目红线一致：发现可疑，不直接定罪。
    """
    chars = st["chars"]
    img_cov = st["image_coverage"]
    draw_cov = st["drawing_coverage"]
    full_page = st["full_page_image"]

    # 文字层不可读优先判定：这类页必须走 OCR，且不能按"纯文字页"放行
    if usable is False:
        return P_SCANNED, "文字层不可读（CID 编码损坏/无 ToUnicode 映射），数值须经 OCR"
    if chars < 30 and (img_cov >= 0.5 or st["n_images"] > 0):
        return P_SCANNED, "整页为图片、无文字层，数值须经 OCR（证据等级受限于 B/C）"
    if chars < 30:
        return P_SCANNED, "文字极少（空白页/封面/签字页），按无文字层处理，须人工确认"
    # 局部大图（排除整页底图）才是图表候选；整页底图+可读文字层属"扫描版式"，
    # 文字层可正常使用，不能误判为图表页
    if img_cov >= 0.35 and not full_page:
        return P_CHART, f"局部图像覆盖率 {img_cov:.0%}，疑似图表/大图页，是否承载数值须人工确认"
    if draw_cov >= 0.45 and chars < 400:
        return P_CHART, f"矢量图形覆盖率 {draw_cov:.0%}，疑似图表页，数值须反推（C 级证据）"
    if st["table_count"] > 0:
        return P_TABLE, f"检测到 {st['table_count']} 个表格，须核对行列对应关系"
    if full_page:
        return P_TEXT, "整页扫描底图+可读文字层（扫描版式），文字层可直接使用"
    return P_TEXT, ""


# ============================================================
# 主流程
# ============================================================

def extract(pdf_path: Path, doc_id: str, render: str, dpi: int, max_render: int) -> Path:
    out_dir = PROJECT_ROOT / "output" / doc_id
    text_dir = out_dir / "text"
    img_dir = out_dir / "images"
    text_dir.mkdir(parents=True, exist_ok=True)
    if render != "none":
        img_dir.mkdir(parents=True, exist_ok=True)

    print(f"材料：{pdf_path.name}")
    print(f"标识：{doc_id}")
    print(f"产出：{out_dir}")

    doc = fitz.open(str(pdf_path))
    total = doc.page_count

    details: List[Dict[str, Any]] = []
    scanned_pages: List[int] = []
    chart_pages: List[int] = []
    table_pages: List[int] = []
    unreadable_pages: List[int] = []
    rendered = 0
    t0 = time.time()

    for i in range(total):
        page = doc[i]
        st = page_stats(page)
        text = page.get_text("text") or ""
        usable = text_layer_usable(text)
        ptype, note = classify(st, usable)
        if usable is False:
            unreadable_pages.append(i + 1)

        (text_dir / f"page_{i + 1:04d}.txt").write_text(text, encoding="utf-8")

        need_render = (
            (render == "scanned" and ptype == P_SCANNED)
            or (render == "chart" and ptype in (P_SCANNED, P_CHART))
        )
        if need_render and (max_render <= 0 or rendered < max_render):
            try:
                pix = page.get_pixmap(dpi=dpi)
                pix.save(str(img_dir / f"page_{i + 1:04d}.png"))
                rendered += 1
            except Exception as exc:
                note = (note + f"；渲染失败：{exc}").strip("；")
        elif need_render:
            note = (note + f"；已达渲染上限 {max_render} 页，未渲染").strip("；")

        if ptype == P_SCANNED:
            scanned_pages.append(i + 1)
        elif ptype == P_CHART:
            chart_pages.append(i + 1)
        elif ptype == P_TABLE:
            table_pages.append(i + 1)

        details.append({
            "页码": i + 1,
            "文字字数": st["chars"],
            "表格数": st["table_count"],
            "疑似扫描件": ptype == P_SCANNED,
            "页面类型": ptype,
            "文字层可读": usable,
            "图像数": st["n_images"],
            "图像覆盖率": st["image_coverage"],
            "整页底图": st["full_page_image"],
            "矢量图形数": st["n_drawings"],
            "矢量覆盖率": st["drawing_coverage"],
            "说明": note,
        })

        if (i + 1) % 50 == 0 or i + 1 == total:
            el = time.time() - t0
            print(f"  进度 {i + 1}/{total}（已用 {el:.0f} 秒）")

    doc.close()

    report = {
        "文件名": pdf_path.name,
        "文档标识": doc_id,
        "总页数": total,
        "页面明细": details,
        "疑似扫描件页": scanned_pages,
        "疑似图表页": chart_pages,
        "文字层不可读页": unreadable_pages,
        "含表格页数": len(table_pages),
        "解析耗时秒": round(time.time() - t0, 1),
        "解析工具": "tools/extract_real.py（PyMuPDF）",
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---------- 汇总 ----------
    n_text = sum(1 for d in details if d["页面类型"] == P_TEXT)
    print()
    print("=" * 66)
    print(f"处理完成，共 {total} 页，耗时 {report['解析耗时秒']} 秒")
    print(f"  纯文字页       : {n_text}")
    print(f"  含表格页       : {len(table_pages)}")
    print(f"  疑似图表页     : {len(chart_pages)}（图像或矢量为主的页，数值可能不在文字层）")
    print(f"  无文字层页     : {len(scanned_pages)}（须 OCR）")
    print(f"  文字层不可读页 : {len(unreadable_pages)}（CID 编码损坏等，同样须 OCR）")
    if unreadable_pages:
        show = unreadable_pages[:30]
        print(f"    页码：{show}{' ...' if len(unreadable_pages) > 30 else ''}")
    if scanned_pages:
        print(f"    页码：{scanned_pages[:30]}{' ...' if len(scanned_pages) > 30 else ''}")
    if chart_pages:
        print(f"  疑似图表页页码（前 30）：{chart_pages[:30]}{' ...' if len(chart_pages) > 30 else ''}")
    print(f"  已渲染图片页数 : {rendered}")
    print("=" * 66)
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(description="真实材料解析：PDF → 逐页文本 + 页面体检")
    ap.add_argument("pdf", help="PDF 文件路径")
    ap.add_argument("--doc-id", required=True, help="文档标识，如 ZGPA-AR-2025")
    ap.add_argument("--render", choices=["scanned", "chart", "none"], default="scanned",
                    help="给哪些页渲染图片，默认仅无文字层/不可读页")
    ap.add_argument("--dpi", type=int, default=150, help="渲染分辨率，默认 150")
    ap.add_argument("--max-render", type=int, default=0,
                    help="最多渲染多少页，0 表示不限制（防止整份 OCR 时爆磁盘）")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"找不到文件：{pdf_path}")
        return 1

    extract(pdf_path, args.doc_id, args.render, args.dpi, args.max_render)
    return 0


if __name__ == "__main__":
    sys.exit(main())
