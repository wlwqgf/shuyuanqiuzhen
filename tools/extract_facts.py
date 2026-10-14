# -*- coding: utf-8 -*-
"""
tools/extract_facts.py —— 从解析产物中抽取财务指标候选值（带页码与字符偏移）

定位：
    这不是"事实库"，而是**候选清单**。年报中同一指标会因口径不同出现多个值
    （合并/母公司、本期/上期、人民币元/千元/百万元），哪些可用必须由 B 人工
    复核确认。本工具的价值是把"哪一页有哪些数"快速摊开，让人只用判断、不用抄写。

三项针对真实材料的设计（均来自实测踩坑）：
  1. **跨行窗口匹配**：表格型报表中"收入"与"560,118"往往不在同一行
     （腾讯财报概要页即是标签独占一行、数字另起一行），按行匹配会全部漏掉；
  2. **繁简体与英文关键词**：腾讯年报为繁体中文版（"權益持有人應佔盈利"），
     只收简体关键词会漏掉核心指标；
  3. **记录页内字符偏移**：每个候选值都带 page_no + 页内起始偏移，
     可经 trace_index 换成全局偏移，直接回显原文（来源定位）。

用法：
    python tools/extract_facts.py ZGPA-AR-2025
    python tools/extract_facts.py --all

产出（output/facts/）：
    <doc_id>_facts.json  结构化候选（含页码、偏移、原文、解析值）
    <doc_id>_facts.md    人读版（按指标分组）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "output" / "facts"

# ============================================================
# 指标定义：(受控指标名, [触发关键词，覆盖简/繁/英])
# 指标名对齐 docs/data_spec.md 第二节受控词表
# ============================================================

METRICS: List[Tuple[str, List[str]]] = [
    ("营业收入", ["营业收入", "營業總收入", "营业总收入", "revenue"]),
    ("收入", ["收入"]),
    ("归属于母公司股东的净利润", [
        "归属于母公司股东的净利润", "归属于上市公司股东的净利润",
        "归母净利润", "母公司股东应占盈利", "母公司权益持有人应占盈利",
        "权益持有人应占盈利", "net profit attributable",
    ]),
    ("净利润", ["净利润", "年度盈利", "期内盈利", "net profit"]),
    ("经调整净利润", ["经调整净利润", "經調整淨利潤", "non-ifrs", "adjusted net profit"]),
    ("经营盈利", ["经营盈利", "經營盈利", "operating profit"]),
    ("总资产", ["总资产", "资产总计", "資產總計", "资产总额", "total assets"]),
    ("归属于母公司股东权益", [
        "归属于母公司股东权益", "归属于上市公司股东的净资产",
        "归母股东权益", "母公司股东应占权益", "母公司权益持有人应占权益",
        "equity attributable",
    ]),
    ("基本每股收益", ["基本每股收益", "每股基本收益", "每股基本盈利", "basic eps", "earnings per share"]),
    ("加权平均净资产收益率", ["加权平均净资产收益率", "平均净资产收益率", "净资产收益率", "roe"]),
    ("毛利率", ["毛利率", "gross margin", "gross profit margin"]),
    ("经营活动现金流量净额", [
        "经营活动产生的现金流量净额", "经营活动现金流净额",
        "经营活动所得现金净额", "net cash from operating",
    ]),
    ("自由现金流", ["自由现金流", "自由現金流", "free cash flow"]),
    ("研发开支", ["研发开支", "研發開支", "研发费用", "研究及开发费用", "r&d expenses"]),
    # 行业专属
    ("新业务价值", ["新业务价值", "新業務價值", "new business value"]),
    ("核心偿付能力充足率", ["核心偿付能力充足率", "核心偿付能力充足率"]),
    ("综合偿付能力充足率", ["综合偿付能力充足率", "綜合償付能力充足率"]),
    ("智能手机出货量", ["智能手机出货量", "智能手機出貨量", "smartphone shipments"]),
    ("智能电动汽车分部收入", ["智能电动汽车分部收入", "智能电动汽车业务收入", "smart ev"]),
    ("月活跃帐户数", ["月活跃帐户", "月活躍帳戶", "月活跃用户", "mau"]),
]

# 数值与单位：亿元 / 百万元 / 万元 / 千元 / 元 / 美元 / 港元 / 百分数
VALUE_RE = re.compile(
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>%|％|亿美元|亿元|百万美元|百万元|万港元|万欧元|万美元|万元|千元|亿|百万|万|千|元|美元|港元)?"
)

# 关键词之后向前看窗的字符数（含换行——表格中数字常另起一行）
WINDOW = 90

CONTEXT_HINTS = [
    ("合并", ["合并", "本集团", "本公司及子公司", "consolidated"]),
    ("母公司", ["母公司"]),
    ("本期", ["本期", "本报告期", "2025年", "2025 年", "二零二五年"]),
    ("上期", ["上期", "上年", "2024年", "2024 年", "二零二四年", "同比"]),
    ("期末", ["期末", "年末", "12月31日", "十二月三十一日"]),
]

UNIT_NORMALIZE = {
    "%": "%", "％": "%",
    "亿元": "亿元", "亿": "亿元",
    "百万元": "百万元", "百万": "百万元",
    "万元": "万元", "万": "万元",
    "千元": "千元", "千": "千元",
    "元": "元", "美元": "美元", "港元": "港元",
    "亿美元": "亿美元", "百万美元": "百万美元",
    "万美元": "万美元", "万港元": "万港元", "万欧元": "万欧元",
}


def parse_value(num: str) -> Optional[float]:
    try:
        return float(num.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def detect_context(snippet: str) -> List[str]:
    low = snippet.lower()
    return [name for name, kws in CONTEXT_HINTS if any(k.lower() in low for k in kws)]


def scan_doc(doc_id: str) -> Dict[str, Any]:
    text_dir = PROJECT_ROOT / "output" / doc_id / "text"
    if not text_dir.is_dir():
        raise FileNotFoundError(f"找不到解析产物：{text_dir}（先运行 tools/extract_real.py）")

    hits: List[Dict[str, Any]] = []
    for tf in sorted(text_dir.glob("page_*.txt")):
        page_no = int(tf.stem.split("_")[1])
        try:
            page_text = tf.read_text(encoding="utf-8")
        except Exception:
            continue
        if not page_text.strip():
            continue
        low = page_text.lower()
        for metric, keywords in METRICS:
            matched_kw = None
            for kw in keywords:
                if kw.lower() in low:
                    matched_kw = kw
                    break
            if not matched_kw:
                continue
            # 在该指标所有出现位置中，向后看 WINDOW 个字符找"数字+单位"
            start = 0
            while True:
                pos = low.find(matched_kw.lower(), start)
                if pos < 0:
                    break
                start = pos + len(matched_kw)
                window = page_text[pos + len(matched_kw): pos + len(matched_kw) + WINDOW]
                for m in VALUE_RE.finditer(window):
                    unit = m.group("unit")
                    if not unit:
                        continue  # 无单位裸数字歧义太大（可能是年份/页码），跳过
                    value = parse_value(m.group("num"))
                    if value is None:
                        continue
                    snippet = page_text[pos: pos + len(matched_kw) + m.end()]
                    snippet_flat = re.sub(r"\s+", " ", snippet).strip()
                    hits.append({
                        "metric": metric,
                        "keyword": matched_kw,
                        "page_no": page_no,
                        "page_char_start": pos,          # 页内偏移，可经 trace_index 换全局偏移
                        "raw": snippet_flat[:120],
                        "value": value,
                        "unit": UNIT_NORMALIZE.get(unit, unit),
                        "context": detect_context(snippet_flat),
                    })

    return {"doc_id": doc_id, "hit_count": len(hits), "hits": hits}


def summarize(doc_id: str, data: Dict[str, Any]) -> str:
    lines = [
        f"# {doc_id} 财务指标候选清单",
        "",
        "> **性质说明**：以下为程序自动抽取的**候选值**，未经人工复核，不得直接作为事实使用。",
        "> 同一指标出现多个值属正常现象——口径（合并/母公司）、期间（本期/上期）、",
        "> 单位（元/千元/百万元/亿元）不同都会产生不同数值。哪些可用由 B 复核后写入 `bench/facts.md`。",
        "",
    ]
    by_metric: Dict[str, List[Dict[str, Any]]] = {}
    for h in data["hits"]:
        by_metric.setdefault(h["metric"], []).append(h)

    for metric, _ in METRICS:
        items = by_metric.get(metric, [])
        if not items:
            continue
        seen: Dict[Tuple[float, str], Dict[str, Any]] = {}
        for it in items:
            key = (it["value"], it["unit"])
            if key not in seen:
                seen[key] = it
        uniq = list(seen.values())[:12]
        lines.append(f"## {metric}（共 {len(items)} 处命中，去重后前 {len(uniq)} 个值）")
        lines.append("")
        lines.append("| 页码 | 页内偏移 | 数值 | 单位 | 口径提示 | 原文 |")
        lines.append("|---|---|---|---|---|---|")
        for it in uniq:
            ctx = "/".join(it["context"]) or "—"
            raw = it["raw"].replace("|", "｜")
            if len(raw) > 56:
                raw = raw[:56] + "…"
            lines.append(f"| {it['page_no']} | {it['page_char_start']} | {it['value']:,.2f} | {it['unit']} | {ctx} | {raw} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="抽取财务指标候选值（带页码与偏移）")
    ap.add_argument("doc_id", nargs="?", help="文档标识，如 ZGPA-AR-2025")
    ap.add_argument("--all", action="store_true", help="处理 output/ 下所有已解析文档")
    args = ap.parse_args()

    if args.all:
        doc_ids = sorted(
            p.name for p in (PROJECT_ROOT / "output").iterdir()
            if p.is_dir() and (p / "text").is_dir() and p.name != "run_logs"
        )
    elif args.doc_id:
        doc_ids = [args.doc_id]
    else:
        ap.print_help()
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for doc_id in doc_ids:
        print(f"扫描 {doc_id} ...")
        data = scan_doc(doc_id)
        (OUT_DIR / f"{doc_id}_facts.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (OUT_DIR / f"{doc_id}_facts.md").write_text(
            summarize(doc_id, data), encoding="utf-8"
        )
        print(f"  命中 {data['hit_count']} 处 → output/facts/{doc_id}_facts.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
