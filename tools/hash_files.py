# -*- coding: utf-8 -*-
"""
tools/hash_files.py —— 原始材料哈希登记辅助工具

职责：
  计算指定目录下所有 PDF 的 SHA256、文件大小、页数，
  输出登记表草稿，便于填入 data/raw/SOURCES.md。

为什么需要哈希：
  原始材料因体积与版权原因不入库，评审方需按链接自行下载。
  哈希是"你拿到的是同一份文件"的唯一硬证据，也是可复现性的前提。

用法：
    python tools/hash_files.py data/raw
    python tools/hash_files.py data/raw --prefix SAMPLE      # 指定 doc_id 前缀
    python tools/hash_files.py data/samples --stdout         # 只打印

归属：A（队长 · 语义与编排层）
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date
from pathlib import Path
from typing import List

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass


def sha256_of(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """分块计算文件哈希，避免大文件一次性读入内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def page_count(path: Path) -> str:
    """尽力读取 PDF 页数；失败则返回 '-'，不因单个文件损坏中断整批处理。"""
    try:
        import fitz  # PyMuPDF

        with fitz.open(str(path)) as doc:
            return str(doc.page_count)
    except Exception:
        try:
            from pypdfium2 import PdfDocument

            pdf = PdfDocument(str(path))
            n = len(pdf)
            pdf.close()
            return str(n)
        except Exception:
            return "-"


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def main() -> int:
    parser = argparse.ArgumentParser(description="计算材料文件哈希与页数")
    parser.add_argument("target", help="目标目录")
    parser.add_argument("--stdout", action="store_true", help="只打印，不写文件")
    parser.add_argument("--out", default=None, help="输出 Markdown 路径（默认写到目标目录下的 HASHES.md）")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.is_dir():
        print(f"目录不存在：{target}")
        return 1

    files: List[Path] = sorted(
        [p for p in target.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"]
    )
    if not files:
        print(f"在 {target} 下没有找到 PDF 文件。")
        return 0

    lines = [
        f"# 材料哈希登记（{target.as_posix()}）",
        "",
        f"生成日期：{date.today().isoformat()}",
        "",
        "| 文件名 | 大小 | 页数 | SHA256 |",
        "|---|---|---|---|",
    ]
    print(f"共发现 {len(files)} 个 PDF：\n")
    for path in files:
        size = path.stat().st_size
        digest = sha256_of(path)
        pages = page_count(path)
        rel = path.relative_to(target).as_posix()
        lines.append(f"| {rel} | {human_size(size)} | {pages} | `{digest}` |")
        print(f"  {rel}")
        print(f"    大小 {human_size(size)} ｜ 页数 {pages}")
        print(f"    SHA256 {digest}")

    text = "\n".join(lines) + "\n"
    if args.stdout:
        print("\n" + text)
        return 0

    out = Path(args.out) if args.out else target / "HASHES.md"
    out.write_text(text, encoding="utf-8")
    print(f"\n登记表已写入：{out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
