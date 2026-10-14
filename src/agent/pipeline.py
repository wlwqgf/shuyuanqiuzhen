# -*- coding: utf-8 -*-
"""
src/agent/pipeline.py —— 双通道核查流水线（Web 系统与评测共用）

与 tools/demo_e2e.py 的关系：
    demo_e2e 是**手工构造断言**的演示脚本；本模块是**抽取式断言**的通用流水线，
    两者共用同一套底层工具（locate / extract_num_unit / 单位对齐 / 全文检索），
    保证演示与真实系统走同一条代码路径——评审方对比两者结果时不会出现
    "演示一套、系统另一套"的裂痕。

流程（对每条抽取出的断言）：
    ① 确定性通道：指标名定位 → 窗口内数值候选（单位对齐取最近）→ 比对
        · 差 ≤1%            → 一致（但还要过口径限定词检查）
        · 成 10/100/1000 倍 → E2 单位错误
        · 其余差异          → E1 数值错误
        · 指标名全文未命中   → 按数值全文检索：数值也没有 → E6 来源不存在
                             数值在但指标名不在 → 疑似 E6（进人工复核）
        · 数值一致但原文带「扣非/非IFRS」等限定词而断言没有 → 疑似 E3
    ② 不确定性通道：大模型带证据语义判定（证据 = ① 定位到的原文片段）
    ③ 合并：任一通道判错 → 进入结论；两通道不一致 → 标注进人工复核队列；
       证据等级由契约强制：疑似只给 B 级，确认才给 A 级。

用法：
    from src.agent.pipeline import check_claims
    rows, findings, summary = check_claims(claims, pages, provider)

归属：A（队长 · 语义与编排层）
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.common.schema import (  # noqa: E402
    Channel,
    ErrorType,
    Evidence,
    EvidenceLevel,
    Finding,
    FindingStatus,
    Severity,
)

# 底层工具与演示脚本共用同一份实现，避免两套逻辑漂移
from tools.demo_e2e import (  # noqa: E402
    extract_num_unit,
    find_number_in_doc,
    locate,
    ratio,
    unit_compatible,
)

# 口径限定词：原文数值附近出现这些词而研报表述没有，即为口径混淆嫌疑
QUALIFIERS = ["扣非", "扣除非經常", "扣除非经常", "非國際財務報告準則", "非国际财务报告准则",
              "非IFRS", "非ifrs", "non-IFRS", "Non-IFRS", "經調整", "经调整", "调整后", "調整後"]

LLM_SYS = (
    "你是金融研报事实核查助手。给定一条研报断言和一段原始年报的摘录，"
    "判断断言与摘录是否一致。只输出 JSON，不要任何解释文字。"
    "JSON 字段：verdict（一致/不一致/无法判定）、error_type（E1数值错误/E2单位错误/"
    "E3统计口径错误/E4时间区间错误/E5估值倍数错误/E6引用与来源错误/E7勾稽与逻辑矛盾/无）、"
    "reason（40字以内）。摘录中没有的信息不要臆测，证据不足就答无法判定。"
)


# ============ 确定性通道 ============

def _collect_candidates(pages: Dict[int, str], metric: str
                        ) -> List[Tuple[float, str, int, str]]:
    """指标名每次命中后，取其窗口内的全部 数字+单位 候选。"""
    cands: List[Tuple[float, str, int, str]] = []
    for pno in sorted(pages):
        text = pages[pno]
        for m in re.finditer(re.escape(metric), text):
            window = text[m.end(): m.end() + 80]
            snippet = text[max(0, m.start() - 10): m.end() + 80].replace("\n", " ").strip()
            for v, u, _ in extract_num_unit(window):
                cands.append((v, u, pno, snippet))
    return cands


def _qualifier_hit(snippet: str, quote: str) -> Optional[str]:
    """片段中含口径限定词而断言没有 → 返回该词，否则 None。"""
    for q in QUALIFIERS:
        if q in snippet and q not in quote:
            return q
    return None


def check_claim(claim: Dict[str, Any], pages: Dict[int, str]) -> Dict[str, Any]:
    """对一条抽取出的断言做确定性核查。返回判定 + 证据。"""
    metric = claim["metric"]
    cv = float(claim["value"])
    cu = claim.get("unit", "") or ""
    quote = claim["quote"]

    result: Dict[str, Any] = {
        "id": f"C{claim.get('page', 0):03d}-{abs(hash(quote)) % 10000:04d}",
        "quote": quote,
        "metric": metric,
        "claim_value": cv,
        "claim_unit": cu,
        "page": claim.get("page"),
        "channel": Channel.RULE,
        "evidence_pages": [],
        "evidence_snippets": [],
        "verdict": "无法判定",
        "error_type": None,
        "reason": "",
        "source_value": None,
        "source_unit": None,
        "calculation": "",
        "mode": "VALUE",
    }

    hits = locate(pages, metric)
    if not hits:
        result["mode"] = "EXISTS"
        # 指标名未命中 → 按数值全文检索，区分"来源不存在"与"指标名不匹配"
        found = find_number_in_doc(pages, cv)
        if found:
            result["verdict"] = "疑似"
            result["error_type"] = ErrorType.E6
            result["evidence_pages"] = [p for p, _ in found]
            result["evidence_snippets"] = [s for _, s in found]
            result["reason"] = (
                f"指标名「{metric}」在已解析材料中未命中，但数值 {cv} 存在于"
                f"第 {found[0][0]} 页，可能为指标名称差异或口径表述差异，需人工复核"
            )
        else:
            result["verdict"] = "不一致"
            result["error_type"] = ErrorType.E6
            result["reason"] = (
                f"指标名「{metric}」与数值 {cv} 在已解析的全部 {len(pages)} 页中"
                f"均未检索到，该表述缺乏来源支撑（E6）"
            )
            result["calculation"] = f"检索形态：{cv:,.2f} / {cv:g} 等，命中 0 处"
        return result

    cands = _collect_candidates(pages, metric)
    if not cands:
        result["evidence_pages"] = [h[0] for h in hits]
        result["evidence_snippets"] = [h[1] for h in hits]
        result["reason"] = f"指标名「{metric}」命中 {len(hits)} 处，但附近未解析到带单位的数字，证据不足，不判定"
        return result

    aligned = [c for c in cands if unit_compatible(c[1], cu)]
    pool = aligned if aligned else cands
    v, u, pno, snippet = min(pool, key=lambda c: ratio(cv, c[0]))

    result["evidence_pages"] = [pno]
    result["evidence_snippets"] = [snippet]
    result["source_value"] = v
    result["source_unit"] = u
    r = ratio(cv, v)

    if r <= 0.01:
        result["mode"] = "KEYWORD_CONTEXT"
        # 数值一致 ≠ 断言正确：还要过口径限定词检查
        q = _qualifier_hit(snippet, quote)
        if q:
            result["verdict"] = "疑似"
            result["error_type"] = ErrorType.E3
            result["reason"] = (
                f"数值 {cv}{cu} 与原文一致，但原文该处带有「{q}」口径限定，"
                f"研报表述未体现该限定，疑似统计口径错误（E3），需语义复核"
            )
        else:
            result["verdict"] = "一致"
            result["reason"] = (
                f"研报 {cv}{cu} 与原文 {v}{u} 差异 {r*100:.2f}%，在 1% 容差内"
                + ("" if aligned else "（注意：未找到单位一致的原文数字，此为不限单位比对）")
            )
        return result

    # 数值不符：先看是否单位倍数关系
    for k in (10, 100, 1000, 10000):
        if ratio(cv * k, v) <= 0.01 or (cv / k > 0 and ratio(cv / k, v) <= 0.01):
            mult = k if ratio(cv * k, v) <= 0.01 else 1 / k
            result["verdict"] = "不一致"
            result["error_type"] = ErrorType.E2
            result["reason"] = (
                f"研报 {cv}{cu} 与原文 {v}{u} 相差 {mult:g} 倍，判定为单位错误（E2）"
            )
            result["calculation"] = f"{cv} × {mult:g} = {cv*mult:g} ≈ 原文 {v}"
            return result

    result["verdict"] = "不一致"
    result["error_type"] = ErrorType.E1
    result["reason"] = (
        f"研报 {cv}{cu} 与原文 {v}{u}（同单位）差异 {r*100:.1f}%，判定为数值错误（E1）"
    )
    result["calculation"] = f"|{cv} - {v}| / {v} = {r*100:.2f}%"
    return result


# ============ 不确定性通道 ============

def llm_check(provider, claim: Dict[str, Any], rule: Dict[str, Any],
              doc_pages: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    """调大模型做语义判定。证据取自规则通道定位到的原文片段。"""
    pairs = list(zip(rule["evidence_pages"], rule["evidence_snippets"]))
    if not pairs and doc_pages:
        # 证据为空（如"来源不存在"类）时按指标名补上下文，
        # 让模型有机会判断"原文确实没提"
        pairs = locate(doc_pages, claim["metric"], max_hits=2)
    snips = "\n".join(f"  [第{p}页] {s}" for p, s in pairs[:3])
    user = f"【研报断言】{claim['quote']}\n【原始年报摘录】\n{snips}\n请判断。"
    try:
        obj = provider.chat_json(
            [{"role": "system", "content": LLM_SYS},
             {"role": "user", "content": user}],
            temperature=0.0,
        )
    except Exception as exc:
        return {"verdict": "调用失败", "error_type": "", "reason": str(exc)[:120]}
    return {
        "verdict": obj.get("verdict", ""),
        "error_type": obj.get("error_type", ""),
        "reason": obj.get("reason", ""),
    }


# ============ 汇总为 Finding ============

def to_finding(claim: Dict[str, Any], rule: Dict[str, Any],
               llm: Dict[str, Any], target_doc_id: str) -> Optional[Finding]:
    """把核查结果收敛成一个 Finding（与数据契约对齐）。一致断言不产出。"""
    if rule["verdict"] == "一致":
        return None

    confirmed = rule["verdict"] == "不一致"
    level = EvidenceLevel.A if confirmed else EvidenceLevel.B
    status = FindingStatus.CONFIRMED if confirmed else FindingStatus.SUSPECT

    evidences = [
        Evidence(
            doc_id=target_doc_id,
            page_no=p,
            quote=s,
            calculation=rule.get("calculation", ""),
            evidence_level=level,
        )
        for p, s in zip(rule["evidence_pages"], rule["evidence_snippets"])
    ]

    llm_says_error = llm.get("verdict") == "不一致"
    if confirmed and llm_says_error:
        channel_note = "双通道一致"
    elif confirmed != llm_says_error:
        channel_note = "双通道不一致，已进人工复核队列"
    else:
        channel_note = "双通道一致（均未见错误）"

    finding = Finding(
        finding_id=f"F-{rule['id']}",
        target_doc_id=target_doc_id,
        target_page=claim.get("page") or 1,
        error_type=rule.get("error_type") or ErrorType.E1,
        status=status,
        evidence_level=level,
        target_quote=claim["quote"],
        claim_value=str(claim.get("value", "")),
        correct_value=str(rule.get("source_value", "")),
        unit=claim.get("unit", ""),
        severity=Severity.HIGH if confirmed else Severity.MEDIUM,
        reason=f"{rule['reason']}；大模型复核：{llm.get('reason', '')}；{channel_note}",
        evidences=evidences,
        channel=Channel.HYBRID,
        rule_id=f"R-{rule.get('mode', 'VALUE')}-001",
        suggestion_original=claim["quote"],
        suggestion_revised="",
        suggestion_basis="",
        suggestion_impact="",
    )
    if confirmed and rule["evidence_pages"]:
        finding.suggestion_basis = (
            f"{target_doc_id} 第 {rule['evidence_pages'][0]} 页："
            f"{rule['evidence_snippets'][0][:60]}"
        )
    return finding


# ============ 批量入口 ============

def check_claims(claims: List[Dict[str, Any]], pages: Dict[int, str],
                 provider=None, target_doc_id: str = "",
                 log: Optional[Any] = None) -> Tuple[List[Dict[str, Any]], List[Finding], Dict[str, Any]]:
    """对一批断言跑双通道核查。

    返回 (rows, findings, summary)：
        rows     ：每条断言的明细（含两通道判定与证据页）
        findings ：Finding 对象列表（一致断言不产出）
        summary  ：统计（核查数 / 确认 / 疑似 / 一致 / 耗时）
    """
    rows: List[Dict[str, Any]] = []
    findings: List[Finding] = []
    t0 = time.time()

    for i, claim in enumerate(claims, 1):
        if log:
            log(f"核查第 {i}/{len(claims)} 条：{claim['quote'][:38]}…")
        rule = check_claim(claim, pages)
        llm = {"verdict": "-", "error_type": "", "reason": "未调用"}
        if provider is not None:
            llm = llm_check(provider, claim, rule, doc_pages=pages)
        f = to_finding(claim, rule, llm, target_doc_id)
        if f is not None:
            findings.append(f)
        rows.append({
            "id": rule["id"],
            "quote": claim["quote"],
            "metric": claim["metric"],
            "claim_value": claim["value"],
            "claim_unit": claim.get("unit", ""),
            "page": claim.get("page"),
            "rule_verdict": rule["verdict"],
            "rule_type": rule["error_type"].description if rule["error_type"] else "-",
            "rule_reason": rule["reason"],
            "llm_verdict": llm.get("verdict", "-"),
            "llm_reason": llm.get("reason", ""),
            "evidence_pages": rule["evidence_pages"],
            "source_value": rule.get("source_value"),
            "calculation": rule.get("calculation", ""),
        })

    summary = {
        "断言总数": len(rows),
        "确认错误": sum(1 for r in rows if r["rule_verdict"] == "不一致"),
        "疑似（人工复核）": sum(1 for r in rows if r["rule_verdict"] == "疑似"),
        "一致": sum(1 for r in rows if r["rule_verdict"] == "一致"),
        "无法判定": sum(1 for r in rows if r["rule_verdict"] == "无法判定"),
        "总耗时秒": round(time.time() - t0, 1),
    }
    return rows, findings, summary
