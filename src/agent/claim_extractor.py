# -*- coding: utf-8 -*-
"""
src/agent/claim_extractor.py —— 研报财务断言抽取（大模型通道）

职责：
    把一份研报的逐页文本，抽取成"可核查的财务断言"列表。
    每条断言携带：原文句子 / 指标名 / 数值 / 单位 / 页码，
    直接喂给双通道核查流程（src/agent/pipeline.py）。

设计要点：
  1. 只抽取**含具体数值的指标陈述**——没有数字的句子无法核查，抽了也是噪声。
  2. 数值必须原样保留书写形态（千分位、百分比），由下游 parse_num 统一解析，
     抽取阶段不做任何四舍五入或改写。
  3. 页码必须来自输入标注，不允许模型臆测——证据锚定的第一环。
  4. 输出强制 JSON 数组；解析失败抛异常，不静默返回空列表
     （空列表会被误读成"研报没有断言"）。

用法：
    from src.agent.claim_extractor import extract_claims
    claims = extract_claims(provider, pages, max_claims=30)

归属：A（队长 · 语义与编排层）
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 每批喂给模型的页数：一批太小则调用次数过多，太大则超出上下文且
# 模型容易漏抽。研报正文页文字量适中，6 页一批在 GLM-4-Flash 上实测稳定。
BATCH_PAGES = 6

# 单批最多抽取条数：防止模型把一句话拆成十几条碎片
BATCH_MAX_CLAIMS = 12

EXTRACT_SYS = (
    "你是金融研报分析助手，任务是精确抽取研报中可核查的财务断言。"
    "只输出 JSON 数组，不要输出任何解释文字或 Markdown 代码块标记。"
    "数组中每个元素是一条断言，字段如下："
    "quote：断言所属的原句（必须逐字摘自输入，保留数字与单位）；"
    "metric：该句陈述的财务指标名称（如 保险服务收入、新业务价值、总资产）；"
    "value：句中该指标的数值，填数字（去掉千分位逗号，百分数填去掉%号的数字）；"
    "unit：单位，从 亿元/万元/元/%/倍/个百分点 中选择，句中未标注单位则填空字符串；"
    "page：该句所在的页码，必须原样取输入中标注的【第N页】。"
    "规则："
    "1. 只抽取含具体数值的指标陈述，没有数字的句子一律跳过；"
    "2. 同一指标不同报告期各算一条；"
    "3. 无法确定指标名或数值的句子跳过，不要臆测；"
    "4. 每批最多抽取 {max_claims} 条，超出时优先保留数值最明确的；"
    "5. 没有任何可抽内容时输出空数组 []。"
)


def _batch_text(pages: Dict[int, str], pnos: List[int]) -> str:
    """把若干页拼成一批输入文本，每页带页码标注。"""
    parts = []
    for p in pnos:
        text = (pages.get(p) or "").strip()
        if text:
            parts.append(f"【第{p}页】\n{text}")
    return "\n\n".join(parts)


def _parse_claims_json(raw: str, allowed_pages: set) -> List[Dict[str, Any]]:
    """把模型输出解析为断言列表，做字段级清洗。

    清洗规则（宁缺毋滥）：
      - quote/metric 必须是非空字符串；
      - value 必须能转成 float，否则丢弃该条（没有数值无法核查）；
      - page 必须在允许页码集合内，否则丢弃（防止模型臆测页码）；
      - unit 统一成全角/半角归一化后的字符串。
    """
    text = (raw or "").strip()
    # 部分型号即使要求 JSON 也会带 ```json 围栏，先剥掉
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise ValueError(f"模型输出不是 JSON 数组：{text[:120]}")
    arr = json.loads(text[start:end + 1])
    if not isinstance(arr, list):
        raise ValueError("模型输出 JSON 不是数组")

    out: List[Dict[str, Any]] = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote", "")).strip()
        metric = str(item.get("metric", "")).strip()
        if not quote or not metric:
            continue
        try:
            value = float(str(item.get("value", "")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        try:
            page = int(item.get("page", 0))
        except (TypeError, ValueError):
            continue
        if page not in allowed_pages:
            continue
        unit = str(item.get("unit", "")).strip()
        out.append({
            "quote": quote,
            "metric": metric,
            "value": value,
            "unit": unit,
            "page": page,
        })
    return out


def extract_claims(provider, pages: Dict[int, str],
                   max_claims: int = 30,
                   batch_pages: int = BATCH_PAGES,
                   log: Optional[Any] = None) -> List[Dict[str, Any]]:
    """从研报逐页文本中抽取财务断言。

    参数：
        provider     ：ModelProvider 实例（真实模型；mock 不得用于正式抽取）
        pages        ：{页码: 文本}
        max_claims   ：总共最多抽取多少条（防止一次抽爆上下文与预算）
        batch_pages  ：每批页数
        log          ：可选回调 log(str)，用于 Web 界面显示进度

    返回：
        [{"quote", "metric", "value", "unit", "page"}, ...]
        按页码排序；抽不到时返回空列表（调用方应提示"未抽取到断言"）。
    """
    claims: List[Dict[str, Any]] = []
    seen_quotes = set()

    all_pnos = sorted(p for p, t in pages.items() if (t or "").strip())
    batches = [all_pnos[i:i + batch_pages] for i in range(0, len(all_pnos), batch_pages)]

    for bi, pnos in enumerate(batches, 1):
        if len(claims) >= max_claims:
            break
        batch = _batch_text(pages, pnos)
        if not batch:
            continue
        if log:
            log(f"正在抽取第 {bi}/{len(batches)} 批（第 {pnos[0]}–{pnos[-1]} 页）的财务断言…")

        sys_prompt = EXTRACT_SYS.format(max_claims=BATCH_MAX_CLAIMS)
        try:
            raw = provider.chat(
                [{"role": "system", "content": sys_prompt},
                 {"role": "user", "content": batch}],
                temperature=0.0,
                json_mode=True,
            )
            batch_claims = _parse_claims_json(raw, set(pnos))
        except Exception as exc:
            if log:
                log(f"第 {bi} 批抽取失败：{exc}")
            continue

        for c in batch_claims:
            key = c["quote"]
            if key in seen_quotes:
                continue
            seen_quotes.add(key)
            claims.append(c)
            if len(claims) >= max_claims:
                break

    claims.sort(key=lambda c: c["page"])
    return claims
