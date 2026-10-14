# -*- coding: utf-8 -*-
"""
src/common/logging_util.py —— 统一执行日志（trace.jsonl）

竞赛要求：
    "完整记录文件访问、工具调用、计算过程和结果生成情况，确保数据来源可核验、
     执行过程可追溯、运行结果可复现。"

本模块提供唯一日志出口。所有模块的关键动作都必须经此写入，
不得各自 print 散落信息。

为什么用 JSON Lines：
    · 增量追加，不必把历史读进内存；
    · 每行一条独立记录，可用 diff 逐行比对两次运行的差异；
    · 结构化，便于评测框架统计耗时、失败率、模型调用次数。

归属：A（队长 · 语义与编排层）
用法：
    from src.common.logging_util import TraceLogger

    logger = TraceLogger()                      # 默认写 output/trace.jsonl
    logger.log("ingest.extract", "解析第 2 页表格", doc_id="SAMPLE-AR-2024", page_no=2,
               detail={"rows": 9, "cols": 3})

    with logger.timer("agent.verify", "语义核验", doc_id="RPT-001"):
        ...  # 自动记录耗时
"""

from __future__ import annotations

import json
import random
import string
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

try:
    from .schema import TraceRecord, now_iso
except ImportError:  # 允许直接运行本文件
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from common.schema import TraceRecord, now_iso  # type: ignore[no-redef]

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_PATH = PROJECT_ROOT / "output" / "trace.jsonl"


def new_run_id() -> str:
    """生成运行标识：时间 + 随机后缀，便于在同一天内区分多次运行。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{stamp}-{suffix}"


class TraceLogger:
    """执行日志写入器。每条记录同时进入内存列表与落盘文件。"""

    def __init__(self, path: Optional[Path] = None, run_id: Optional[str] = None,
                 echo: bool = False):
        self.path = Path(path) if path else DEFAULT_TRACE_PATH
        self.run_id = run_id or new_run_id()
        self.echo = echo          # 是否同时打印到屏幕
        self.records: List[TraceRecord] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---------- 写入 ----------

    def log(
        self,
        step: str,
        action: str,
        status: str = "ok",
        doc_id: str = "",
        page_no: int = 0,
        detail: Optional[Dict[str, Any]] = None,
        model_info: Optional[Dict[str, Any]] = None,
        elapsed_ms: int = 0,
    ) -> TraceRecord:
        """写入一条执行记录，并返回该记录对象。"""
        record = TraceRecord(
            run_id=self.run_id,
            step=step,
            action=action,
            status=status,
            doc_id=doc_id,
            page_no=page_no,
            detail=detail or {},
            model_info=model_info or {},
            elapsed_ms=elapsed_ms,
        )
        self.records.append(record)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        if self.echo:
            flag = {"ok": "✓", "error": "✗", "skip": "·"}.get(status, "·")
            extra = f" [{doc_id} p{page_no}]" if doc_id else ""
            print(f"  {flag} {step} · {action}{extra}")
        return record

    def log_error(self, step: str, action: str, error: Exception, **kwargs: Any) -> TraceRecord:
        """记录一次失败。异常信息完整写入，便于复盘。"""
        detail = dict(kwargs.pop("detail", {}) or {})
        detail["error_type"] = type(error).__name__
        detail["error_message"] = str(error)[:1000]
        return self.log(step, action, status="error", detail=detail, **kwargs)

    # ---------- 计时 ----------

    @contextmanager
    def timer(self, step: str, action: str, **kwargs: Any) -> Iterator[None]:
        """上下文管理器：自动记录耗时，异常时记为 error 并继续抛出。"""
        started = time.perf_counter()
        try:
            yield
        except Exception as exc:  # noqa: BLE001
            self.log_error(step, action, exc,
                           elapsed_ms=int((time.perf_counter() - started) * 1000), **kwargs)
            raise
        else:
            self.log(step, action,
                     elapsed_ms=int((time.perf_counter() - started) * 1000), **kwargs)

    # ---------- 统计 ----------

    def stats(self) -> Dict[str, Any]:
        total = len(self.records)
        errors = sum(1 for r in self.records if r.status == "error")
        by_step: Dict[str, int] = {}
        for r in self.records:
            by_step[r.step] = by_step.get(r.step, 0) + 1
        return {
            "run_id": self.run_id,
            "total": total,
            "errors": errors,
            "elapsed_ms": sum(r.elapsed_ms for r in self.records),
            "by_step": by_step,
            "path": str(self.path),
        }

    def summary(self) -> str:
        s = self.stats()
        lines = [
            f"运行标识 : {s['run_id']}",
            f"记录条数 : {s['total']}（失败 {s['errors']} 条）",
            f"累计耗时 : {s['elapsed_ms']} ms",
            f"日志文件 : {s['path']}",
        ]
        if s["by_step"]:
            lines.append("步骤分布 : " + "，".join(f"{k}×{v}" for k, v in sorted(s["by_step"].items())))
        return "\n".join(lines)


def read_trace(path: Optional[Path] = None, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """读取日志（可按 run_id 过滤）。"""
    path = Path(path) if path else DEFAULT_TRACE_PATH
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if run_id and data.get("run_id") != run_id:
                continue
            out.append(data)
    return out


# ============================================================
# 自检
# ============================================================


def _selftest() -> int:
    print("=" * 72)
    print("logging_util.py 自检 —— 执行日志可追溯性")
    print("=" * 72)

    tmp = PROJECT_ROOT / "output" / "_selftest_trace.jsonl"
    tmp.unlink(missing_ok=True)
    logger = TraceLogger(path=tmp)

    logger.log("ingest.extract", "解析 PDF 页面",
               doc_id="SAMPLE-AR-2024", page_no=2,
               detail={"rows": 9, "cols": 3, "engine": "pdfplumber"})

    with logger.timer("agent.verify", "语义核验", doc_id="RPT-001", page_no=1):
        time.sleep(0.05)

    with logger.timer("rules.check", "勾稽校验", doc_id="SAMPLE-AR-2024", page_no=2,
                      model_info={"vendor": "深度求索 DeepSeek", "model": "deepseek-chat"}):
        pass

    # 故意制造一次失败，验证异常记录
    try:
        with logger.timer("ingest.extract", "解析损坏文件", doc_id="BROKEN"):
            raise FileNotFoundError("模拟：文件不存在")
    except FileNotFoundError:
        pass

    print()
    print(logger.summary())
    print()
    print("【写入内容】")
    print("-" * 72)
    for rec in read_trace(tmp):
        print(json.dumps(rec, ensure_ascii=False))

    records = read_trace(tmp)
    assert len(records) == 4, f"应写入 4 条，实际 {len(records)}"
    assert sum(1 for r in records if r["status"] == "error") == 1, "失败记录未写入"
    assert any(r["elapsed_ms"] > 0 for r in records), "耗时未记录"
    assert any(r["model_info"] for r in records), "模型身份未记录"

    print()
    print("=" * 72)
    print("自检通过：文件访问、工具调用、耗时、失败原因、模型身份均可追溯。")
    print("=" * 72)
    tmp.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(_selftest())
