# -*- coding: utf-8 -*-
"""
src/common/trace_index.py —— 页级溯源索引

解决的问题：
    竞赛要求在"来源定位"上拿分，即每一条判定都必须能回到原始材料的
    具体页码与具体文字。但解析产物是分散的（每页一个 txt、每页一张图），
    没有一个统一的结构能把"全局字符位置 → 第几页 → 哪段文字"关联起来。

本模块建立的机制：
    · 为每份材料生成 trace_index.json，记录每页的形态、字符区间、文本路径、
      图像路径、OCR 可信度；
    · 提供 locate()：给出全局字符区间，回显原文片段与所在页码；
    · 提供 verify_quote()：校验一段引文是否真实存在于指定页面
      —— 这是"引用与来源错误（E6）"的直接检测手段；
    · 提供 find_quote()：反向搜索引文出现在哪一页哪个位置。

设计要点：
    1. **不复制正文**：索引只存路径与偏移，正文仍留在 text/*.txt 中，
       避免索引文件膨胀，也保证正文只有一处来源（单一事实源）。
    2. **全局偏移可重建**：全文 = 各页规范文本以 "\\n" 连接，
       页面的 char_start / char_end 即在此坐标系中的位置，可精确复现。
    3. **引文校验做空白归一化**：PDF 抽取的空格与换行不可靠，
       直接字符串比较会大量误判，故比较前统一去除所有空白字符。

归属：A（队长 · 语义与编排层）
用法：
    python src/common/trace_index.py                     # 自检（使用样本产物）
    python src/common/trace_index.py --build 目录 --doc-id ID
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .schema import PageType, now_iso
except ImportError:  # 允许直接运行本文件
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from common.schema import PageType, now_iso  # type: ignore[no-redef]

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 页面文本与页间分隔符
PAGE_SEPARATOR = "\n"


# ============================================================
# 一、数据结构
# ============================================================


@dataclass
class PageIndex:
    """单页的索引记录。"""

    page_no: int
    page_type: PageType = PageType.TEXT
    text_path: str = ""          # 相对项目根的路径
    image_path: str = ""         # 相对项目根的路径
    char_start: int = 0          # 在全文中的起始偏移
    char_end: int = 0            # 在全文中的结束偏移（不含）
    char_count: int = 0          # 规范文本长度
    has_text_layer: bool = True
    table_count: int = 0
    ocr_confidence: float = -1.0  # 平均可信度；-1 表示未经 OCR
    note: str = ""

    @property
    def span(self) -> Tuple[int, int]:
        return self.char_start, self.char_end

    def to_dict(self) -> Dict[str, Any]:
        return {f.name: _dump(getattr(self, f.name)) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PageIndex":
        kwargs: Dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            value = data[f.name]
            if f.name == "page_type" and not isinstance(value, PageType):
                value = PageType(value)
            kwargs[f.name] = value
        return cls(**kwargs)


@dataclass
class TraceIndex:
    """一份材料的页级溯源索引。"""

    doc_id: str                                    # 材料标识，见 docs/data_spec.md 第一节
    source_file: str = ""                          # 原始文件名
    sha256: str = ""                               # 原始文件哈希
    page_count: int = 0
    extract_dir: str = ""                          # 解析产物目录（相对项目根）
    created_at: str = ""
    pages: List[PageIndex] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_file": self.source_file,
            "sha256": self.sha256,
            "page_count": self.page_count,
            "extract_dir": self.extract_dir,
            "created_at": self.created_at or now_iso(),
            "pages": [p.to_dict() for p in self.pages],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TraceIndex":
        return cls(
            doc_id=data["doc_id"],
            source_file=data.get("source_file", ""),
            sha256=data.get("sha256", ""),
            page_count=data.get("page_count", 0),
            extract_dir=data.get("extract_dir", ""),
            created_at=data.get("created_at", ""),
            pages=[PageIndex.from_dict(p) for p in data.get("pages", [])],
            notes=data.get("notes", []),
        )

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "TraceIndex":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # ---------- 正文读取 ----------

    def page_text(self, page_no: int) -> str:
        """读取指定页面的规范文本（strip 后）。"""
        page = self.get_page(page_no)
        if page is None:
            raise KeyError(f"第 {page_no} 页不在索引中")
        if not page.text_path:
            return ""
        path = PROJECT_ROOT / page.text_path
        if not path.exists():
            # 索引可能被移动到别处，退化为相对索引目录解析
            path = Path(self.extract_dir) / "text" / f"page_{page_no:04d}.txt"
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""

    def full_text(self) -> str:
        """重建全文（各页规范文本以换行连接），与建立索引时的坐标系一致。"""
        return PAGE_SEPARATOR.join(self.page_text(p.page_no) for p in self.pages)

    def get_page(self, page_no: int) -> Optional[PageIndex]:
        for p in self.pages:
            if p.page_no == page_no:
                return p
        return None

    # ---------- 核心能力：定位 ----------

    def locate(self, char_start: int, char_end: int) -> Tuple[int, str]:
        """按全局字符区间定位，返回 (页码, 原文片段)。

        这是"来源定位"的底层能力：任何一条判定只要带着
        (doc_id, char_start, char_end)，就能精确回显原文。
        """
        if char_start < 0 or char_end < char_start:
            raise ValueError(f"非法字符区间 [{char_start}, {char_end})")
        for page in self.pages:
            if page.char_start <= char_start < page.char_end or (
                page.char_start == page.char_end == char_start
            ):
                local_start = char_start - page.char_start
                local_end = min(char_end, page.char_end) - page.char_start
                text = self.page_text(page.page_no)
                return page.page_no, text[local_start:local_end]
        raise IndexError(
            f"字符区间 [{char_start}, {char_end}) 超出范围"
            f"（全文长度 {sum(p.char_count for p in self.pages)}）"
        )

    def locate_in_page(self, page_no: int, char_start: int, char_end: int) -> str:
        """按页内区间定位（页内偏移，从 0 开始）。"""
        text = self.page_text(page_no)
        if char_start < 0 or char_end > len(text):
            raise ValueError(f"页内区间越界：页 {page_no} 长度 {len(text)}")
        return text[char_start:char_end]

    # ---------- 核心能力：引文核验 ----------

    def verify_quote(self, page_no: int, quote: str) -> bool:
        """校验一段引文是否真实存在于指定页面。

        用于检测"引用与来源错误（E6）"：若草稿声称"据年报第 3 页，公司智能装备
        收入 6.82 亿元"，本方法可立刻验证该表述是否真的出现在第 3 页。

        比较前统一去除所有空白字符——PDF 抽取的空格与换行位置并不可靠。
        """
        return _normalize(quote) in _normalize(self.page_text(page_no))

    def find_quote(self, quote: str, max_hits: int = 5) -> List[Tuple[int, int, int]]:
        """在全文范围搜索引文，返回 [(页码, 页内起始, 页内结束)]。

        注意返回的是**页内**偏移；若需全局偏移，加上该页的 char_start。
        """
        needle = _normalize(quote)
        if not needle:
            return []
        hits: List[Tuple[int, int, int]] = []
        for page in self.pages:
            raw = self.page_text(page.page_no)
            if not raw:
                continue
            # 在归一化后的文本上定位，再映射回原文本位置
            mapping = _normalize_with_map(raw)
            pos = mapping["text"].find(needle)
            while pos >= 0 and len(hits) < max_hits:
                start = mapping["index"][pos]
                end = mapping["index"][pos + len(needle) - 1] + 1
                hits.append((page.page_no, start, end))
                pos = mapping["text"].find(needle, pos + 1)
            if len(hits) >= max_hits:
                break
        return hits

    # ---------- 概览 ----------

    def summary(self) -> str:
        by_type: Dict[str, int] = {}
        for p in self.pages:
            by_type[p.page_type.value] = by_type.get(p.page_type.value, 0) + 1
        total_chars = sum(p.char_count for p in self.pages)
        lines = [
            f"文档标识 : {self.doc_id}",
            f"原始文件 : {self.source_file}",
            f"页数     : {self.page_count}",
            f"总字符数 : {total_chars:,}",
            f"页面构成 : " + "，".join(f"{k} {v} 页" for k, v in sorted(by_type.items())),
        ]
        no_text = [p.page_no for p in self.pages if not p.has_text_layer]
        if no_text:
            lines.append(f"无文字层 : 第 {no_text} 页（须经 OCR，证据等级受限于 B/C）")
        return "\n".join(lines)


# ============================================================
# 二、从解析产物构建索引
# ============================================================


def build_from_extract(
    extract_dir: Path,
    doc_id: str,
    source_file: Optional[Path] = None,
    auto_page_type: bool = True,
) -> TraceIndex:
    """从 01_extract.py / src/ingest 的产物目录构建页级溯源索引。

    extract_dir 期望包含：
        text/page_0001.txt   逐页文本
        images/page_0001.png 逐页图片
        report.json          页面体检报告（可选，缺失时按文本推断）
    """
    extract_dir = Path(extract_dir)
    if not extract_dir.is_dir():
        raise FileNotFoundError(f"解析产物目录不存在：{extract_dir}")

    text_dir = extract_dir / "text"
    img_dir = extract_dir / "images"

    # 读取体检报告
    report: Dict[str, Any] = {}
    report_path = extract_dir / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    details = {int(d["页码"]): d for d in report.get("页面明细", [])}

    # 收集页号
    page_numbers = sorted(
        int(m.group(1)) for m in (re.match(r"page_(\d+)\.txt$", f.name) for f in text_dir.glob("page_*.txt")) if m
    ) if text_dir.exists() else sorted(details)

    index = TraceIndex(
        doc_id=doc_id,
        source_file=source_file.name if source_file else report.get("文件名", ""),
        sha256=_sha256(source_file) if source_file and Path(source_file).exists() else "",
        page_count=len(page_numbers),
        extract_dir=_rel(extract_dir),
        created_at=now_iso(),
    )

    offset = 0
    for page_no in page_numbers:
        tf = text_dir / f"page_{page_no:04d}.txt"
        raw = tf.read_text(encoding="utf-8") if tf.exists() else ""
        clean = raw.strip()

        ip = img_dir / f"page_{page_no:04d}.png"
        detail = details.get(page_no, {})
        table_count = int(detail.get("表格数", 0) or 0)

        page = PageIndex(
            page_no=page_no,
            text_path=_rel(tf) if tf.exists() else "",
            image_path=_rel(ip) if ip.exists() else "",
            char_start=offset,
            char_count=len(clean),
            char_end=offset + len(clean),
            has_text_layer=bool(clean),
            table_count=table_count,
        )
        if auto_page_type:
            page.page_type = _infer_page_type(page, detail)
            page.note = _page_note(page)
        index.pages.append(page)
        offset += len(clean) + len(PAGE_SEPARATOR)

    index.notes.append(
        "页面类型由解析产物自动推断（文字量、表格数、图片存在性）；"
        "真实材料到位后须结合图像覆盖率等信息校准，详见 "
        "output/run_logs/01_extract_验证报告.md 发现一。"
    )
    return index


def _infer_page_type(page: PageIndex, detail: Dict[str, Any]) -> PageType:
    """依据现有信号推断页面类型。

    当前为简化版：仅用文字量与表格数。
    正式版须引入图像覆盖率与文字块坐标离散度（见验证报告发现一）。
    """
    if not page.has_text_layer:
        return PageType.SCANNED
    if page.table_count > 0:
        return PageType.TABLE
    if page.char_count < 50:
        # 文字极少但页面有图 → 图表页；无图则视为扫描件
        return PageType.CHART if page.image_path else PageType.SCANNED
    return PageType.TEXT


def _page_note(page: PageIndex) -> str:
    if page.page_type == PageType.SCANNED:
        return "无文字层，证据须经 OCR，等级受限于 B/C"
    if page.page_type == PageType.CHART:
        return "文字稀少且含图片，疑似图表页，数值须反推，一律 C 级证据"
    return ""


# ============================================================
# 三、工具函数
# ============================================================


def _sha256(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _rel(path: Path) -> str:
    """转换为相对项目根的路径，保证索引可移植。"""
    path = Path(path).resolve()
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize(text: str) -> str:
    """去除全部空白字符，用于引文比对。"""
    return re.sub(r"\s+", "", text or "")


def _normalize_with_map(text: str) -> Dict[str, Any]:
    """归一化并保留"归一化位置 → 原文本位置"的映射，用于回推区间。"""
    chars: List[str] = []
    index: List[int] = []
    for i, ch in enumerate(text or ""):
        if ch.isspace():
            continue
        chars.append(ch)
        index.append(i)
    return {"text": "".join(chars), "index": index}


def _dump(value: Any) -> Any:
    from enum import Enum

    if isinstance(value, Enum):
        return value.value
    return value


# ============================================================
# 四、自检
# ============================================================


def _find_sample_extract_dir() -> Optional[Path]:
    """找到样本材料的解析产物目录。"""
    base = PROJECT_ROOT / "output"
    if not base.is_dir():
        return None
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / "text").is_dir() and child.name != "run_logs":
            return child
    return None


def _selftest() -> int:
    print("=" * 72)
    print("trace_index.py 自检 —— 页级溯源索引机制")
    print("=" * 72)

    extract_dir = _find_sample_extract_dir()
    if extract_dir is None:
        print("未找到解析产物目录。请先运行：")
        print('  python src/01_extract.py "data/samples/星野智造_2024年年度报告_节选_合成样本.pdf"')
        return 1

    print(f"解析产物目录：{extract_dir.name}\n")

    index = build_from_extract(
        extract_dir=extract_dir,
        doc_id="SAMPLE-AR-2024",
        source_file=PROJECT_ROOT / "data" / "samples" / f"{extract_dir.name}.pdf",
    )
    print(index.summary())
    print()

    # ---------- 1. 页面清单 ----------
    print("【1】页面索引")
    print("-" * 72)
    print(f"{'页':>3}  {'类型':<9} {'字符区间':<18} {'字数':>5}  说明")
    for p in index.pages:
        print(f"{p.page_no:>3}  {p.page_type.value:<9} "
              f"[{p.char_start:>5}, {p.char_end:>5}){'':<3} {p.char_count:>5}  {p.note}")
    print()

    # ---------- 2. 正查：局部区间 → 原文 ----------
    print("【2】正查 locate()：给定字符区间，回显原文与页码")
    print("-" * 72)
    rev_page = next(p for p in index.pages if p.page_no == 2)
    text2 = index.page_text(2)
    key = "3,856,209,744.60"
    local = text2.find(key)
    if local >= 0:
        g_start = rev_page.char_start + local
        page_no, snippet = index.locate(g_start, g_start + len(key))
        print(f"  全局区间 [{g_start}, {g_start + len(key)})")
        print(f"  → 定位到第 {page_no} 页，回显原文：{snippet}")
        assert page_no == 2 and snippet == key
        print("  ✓ 定位正确")
    print()

    # ---------- 3. 引文核验（正例） ----------
    print("【3】引文核验 verify_quote()：真实存在的引文")
    print("-" * 72)
    ok = index.verify_quote(2, "归属于上市公司股东的净利润（元） 96,412,553.18")
    print(f"  第 2 页是否含该引文：{ok}")
    assert ok, "应能命中"
    # 空白归一化容错测试
    ok2 = index.verify_quote(2, "归属于上市公司股东的净利润（元）96,412,553.18")
    print(f"  空白不同的同一引文也能命中：{ok2}")
    assert ok2
    print("  ✓ 引文核验通过（含空白归一化容错）")
    print()

    # ---------- 4. 引文核验（反例，模拟 E6 引用错误） ----------
    print("【4】引文核验：引用来源不存在的情况（E6 检测）")
    print("-" * 72)
    fake = "公司总资产达 385.62 亿元"   # 该表述只出现在研报草稿，不在年报中
    in_page2 = index.verify_quote(2, fake)
    hits = index.find_quote(fake)
    print(f"  年报第 2 页是否含「{fake}」：{in_page2}")
    print(f"  在整份年报中搜索该引文：{'未找到' if not hits else hits}")
    assert not in_page2 and not hits, "该引文不应出现在年报中"
    print("  ✓ 成功识别出'引用来源不存在'——这正是 E6 类错误的检测方式")
    print()

    # ---------- 5. 反查：引文 → 位置 ----------
    print("【5】反查 find_quote()：给定引文，找到它出现在哪一页")
    print("-" * 72)
    for q in ["1,240,358,902.35", "加权平均净资产收益率", "毛利率为 28.63%"]:
        hits = index.find_quote(q)
        desc = "，".join(f"第 {p} 页 页内[{s}, {e})" for p, s, e in hits) or "未找到"
        print(f"  「{q}」→ {desc}")
    print()

    # ---------- 6. 落盘与读回 ----------
    print("【6】索引落盘与读回")
    print("-" * 72)
    out = extract_dir / "trace_index.json"
    index.save(out)
    reloaded = TraceIndex.load(out)
    print(f"  已写入：{_rel(out)}")
    print(f"  读回页数：{reloaded.page_count}，文档标识：{reloaded.doc_id}")
    assert reloaded.to_dict() == index.to_dict(), "落盘读回后内容不一致"
    again = reloaded.locate(rev_page.char_start + local, rev_page.char_start + local + len(key))
    print(f"  读回后仍可定位：第 {again[0]} 页 → {again[1]}")
    print("  ✓ 往返一致")

    print()
    print("=" * 72)
    print("自检全部通过。每条数据均可追溯到原始来源页码。")
    print("=" * 72)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="页级溯源索引")
    parser.add_argument("--build", help="从解析产物目录构建索引")
    parser.add_argument("--doc-id", default="", help="文档标识")
    parser.add_argument("--source", default="", help="原始 PDF 路径（用于计算哈希）")
    parser.add_argument("--out", default="", help="索引输出路径（默认写到产物目录下）")
    args = parser.parse_args()

    if args.build:
        extract_dir = Path(args.build)
        index = build_from_extract(
            extract_dir=extract_dir,
            doc_id=args.doc_id or extract_dir.name,
            source_file=Path(args.source) if args.source else None,
        )
        out = Path(args.out) if args.out else extract_dir / "trace_index.json"
        index.save(out)
        print(index.summary())
        print(f"\n索引已写入：{out}")
        return 0

    return _selftest()


if __name__ == "__main__":
    sys.exit(main())
