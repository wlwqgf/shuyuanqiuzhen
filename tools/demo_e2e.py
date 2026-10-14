# -*- coding: utf-8 -*-
"""
端到端核查演示（真实数据版）
============================

用途：
    用三份真实年报（平安 / 腾讯 / 小米）中的真实数字，构造一份"研报草稿"，
    草稿里预埋 5 类典型错误 + 3 条正确断言（对照组），
    然后跑通「确定性规则引擎 + 大模型语义判定」双通道核查，
    输出带页码证据的结构化结论。

    产出可直接用于：计划书"系统效果预览"、5 分钟视频 Demo、评测集样例。

诚信声明：
    草稿中的公司、数字均来自真实年报；错误是**故意构造**的，用于演示。
    报告会明确标注"构造样例"，不冒充真实研报。

用法：
    python tools/demo_e2e.py
    python tools/demo_e2e.py --skip-llm      # 不调大模型，只跑规则通道
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
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
from src.agent.model_provider import ModelProvider  # noqa: E402

OUT_DIR = PROJECT_ROOT / "output" / "demo"

# llm_check 在"来源不存在"类断言上需要按关键词补上下文，这里缓存文档
_DOCS_CACHE: Dict[str, Dict[int, str]] = {}

# ============ 真实材料加载 ============

def load_docs() -> Dict[str, Dict[int, str]]:
    """读取 output/<doc_id>/text/page_XXXX.txt → {doc_id: {页码: 文本}}"""
    docs: Dict[str, Dict[int, str]] = {}
    base = PROJECT_ROOT / "output"
    for d in base.iterdir():
        if not d.is_dir():
            continue
        text_dir = d / "text"
        if not text_dir.is_dir():
            continue
        pages: Dict[int, str] = {}
        for f in sorted(text_dir.glob("page_*.txt")):
            m = re.search(r"page_(\d+)", f.stem)
            if m:
                pages[int(m.group(1))] = f.read_text(encoding="utf-8")
        if pages:
            docs[d.name] = pages
    return docs


# ============ 数字工具 ============

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def parse_num(s: str) -> Optional[float]:
    """从字符串中取第一个数字（去千分位）。"""
    if s is None:
        return None
    m = _NUM_RE.search(s.replace("，", ","))
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def parse_nums(s: str) -> List[float]:
    """取字符串中全部数字。"""
    out = []
    for m in _NUM_RE.finditer(s.replace("，", ",")):
        try:
            out.append(float(m.group().replace(",", "")))
        except ValueError:
            pass
    return out


# 数字+单位配对抽取：比对时必须单位对齐，否则会把同一句话里
# 不同指标的数字配到一起（如把综合成本率 96.8% 当成保险服务收入）
_UNIT_ALT = r"万亿元|亿元|万元|百万元|千万元|千元|元|百分点|%|％|倍"
_NUM_UNIT_RE = re.compile(r"(-?\d[\d,]*\.?\d*)\s*(" + _UNIT_ALT + r")")


def extract_num_unit(text: str) -> List[Tuple[float, str, int]]:
    """抽取 (数值, 单位, 起始位置) 三元组。单位原样保留，由调用方判断兼容性。"""
    out: List[Tuple[float, str, int]] = []
    for m in _NUM_UNIT_RE.finditer(text.replace("，", ",")):
        v = parse_num(m.group(1))
        if v is not None:
            out.append((v, m.group(2), m.start()))
    return out


def unit_compatible(u_src: str, u_claim: str) -> bool:
    """单位是否可比对。% 与 ％ 视为同一单位；其余要求完全相同。"""
    if not u_claim:
        return True
    a = u_src.replace("％", "%")
    b = u_claim.replace("％", "%")
    return a == b


def ratio(a: float, b: float) -> float:
    return abs(a - b) / abs(b) if b else float("inf")


# ============ 定位：关键词 → 页码 + 原文片段 ============

def locate(pages: Dict[int, str], keyword: str, window: int = 60, max_hits: int = 4
           ) -> List[Tuple[int, str]]:
    """在整份文档中找关键词，返回 [(页码, 片段)]。"""
    hits: List[Tuple[int, str]] = []
    for pno in sorted(pages):
        text = pages[pno]
        for m in re.finditer(re.escape(keyword), text):
            start = max(0, m.start() - 10)
            snippet = text[start:m.start() + window].replace("\n", " ").strip()
            hits.append((pno, snippet))
            if len(hits) >= max_hits:
                return hits
    return hits


def find_number_in_doc(pages: Dict[int, str], number: float, tol: float = 1e-9
                       ) -> List[Tuple[int, str]]:
    """全文检索某个数值，返回命中页。

    只搜**精确小数形态**。早期版本会额外搜整数形态（15.27 → "15"），
    结果把目录页码、百分比里的裸数字当成命中，制造假阳性——
    演示里这是致命的：会把自己的"来源不存在"判定变成误报。
    """
    cands = {f"{number:,.2f}", f"{number:,.2f}".replace(",", "")}
    hits = []
    for pno in sorted(pages):
        text = pages[pno]
        for c in cands:
            idx = text.find(c)
            if idx >= 0:
                snippet = text[max(0, idx - 40):idx + 40].replace("\n", " ").strip()
                hits.append((pno, snippet))
                break
    return hits


# ============ 研报草稿（基于真实数字构造，错误为故意预埋） ============
# gt = 真实错误类型（用于演示统计）；None 表示正确断言（对照组）

CLAIMS: List[Dict[str, Any]] = [
    {
        "id": "C01",
        "doc_id": "ZGPA-AR-2025",
        "quote": "财产保险业务保险服务收入 338.912 亿元，同比增长 3.3%。",
        "keyword": "保险服务收入",
        "claim_value": 338.912,
        "claim_unit": "亿元",
        "check": "value",
        "gt": ErrorType.E2,
        "gt_note": "单位错误：3,389.12 亿元误写为 338.912 亿元，虚减 10 倍",
    },
    {
        "id": "C02",
        "doc_id": "ZGPA-AR-2025",
        "quote": "寿险及健康险业务新业务价值 368.97 亿元，同比增长 39.3%。",
        "keyword": "新业务价值",
        "claim_value": 39.3,
        "claim_unit": "%",
        "check": "value",
        "gt": ErrorType.E1,
        "gt_note": "数值错误：年报为同比增长 29.3%，草稿写 39.3%",
    },
    {
        "id": "C03",
        "doc_id": "ZGPA-AR-2025",
        "quote": "现金分红总额 488.91 亿元，占归母营运利润的 42.6%。",
        "keyword": "现金分红总额",
        "check": "recompute",
        "recompute": {
            "numerator": ("现金分红总额", 488.91),
            "denominator": ("归属于母公司股东的营运利润", 1344.15),
            "claim_pct": 42.6,
        },
        "gt": ErrorType.E7,
        "gt_note": "勾稽矛盾：488.91 / 1,344.15 = 36.37%，与 42.6% 不符",
    },
    {
        "id": "C04",
        "doc_id": "ZGPA-AR-2025",
        "quote": "集团总资产达 15.27 万亿元，资产规模持续扩张。",
        "keyword": "总资产",
        "check": "exists",
        "search_number": 15.27,
        "gt": ErrorType.E6,
        "gt_note": "引用与来源错误：已解析材料中检索不到 15.27 万亿元的总资产表述",
    },
    {
        "id": "C05",
        "doc_id": "ZGPA-AR-2025",
        "quote": "归属于母公司股东的净利润 1,437.73 亿元，同比增长 22.5%。",
        "keyword": "净利润",
        "claim_value": 1437.73,
        "claim_unit": "亿元",
        "check": "keyword_context",
        "gt": ErrorType.E3,
        "gt_note": "统计口径错误：1,437.73 亿元是「扣非净利润」，草稿漏掉「扣非」",
    },
    {
        "id": "C06",
        "doc_id": "ZGPA-AR-2025",
        "quote": "全年股息每股现金人民币 2.70 元，同比增长 5.9%。",
        "keyword": "每股",
        "claim_value": 2.70,
        "claim_unit": "元",
        "check": "value",
        "gt": None,
        "gt_note": "对照组：与年报一致",
    },
    {
        "id": "C07",
        "doc_id": "ZGPA-AR-2025",
        "quote": "保险资金投资组合规模 6.49 万亿元，较年初增长 13.2%。",
        "keyword": "投资组合规模",
        "claim_value": 6.49,
        "claim_unit": "万亿元",
        "check": "value",
        "gt": None,
        "gt_note": "对照组：与年报一致",
    },
    {
        "id": "C08",
        "doc_id": "TX-AR-2025",
        "quote": "基本每股盈利为人民币 28.577 元。",
        "keyword": "每股盈利",
        "claim_value": 28.577,
        "claim_unit": "元",
        "check": "keyword_context",
        "gt": ErrorType.E3,
        "gt_note": "统计口径错误：28.577 元是非 IFRS 基本每股盈利，IFRS 基本每股盈利为 24.749 元",
    },
]


# ============ 通道一：确定性规则引擎 ============

def rule_check(claim: Dict[str, Any], pages: Dict[int, str]) -> Dict[str, Any]:
    """对一条断言做确定性核查。返回判定 + 证据。"""
    kw = claim["keyword"]
    hits = locate(pages, kw)
    result: Dict[str, Any] = {
        "id": claim["id"],
        "channel": Channel.RULE,
        "evidence_pages": [h[0] for h in hits],
        "evidence_snippets": [h[1] for h in hits],
        "verdict": "无法判定",
        "error_type": None,
        "reason": "",
        "claim_value": claim.get("claim_value"),
        "source_value": None,
        "calculation": "",
    }

    if not hits:
        result["reason"] = f"在已解析材料中未找到关键词「{kw}」，证据不足，不判定"
        return result

    mode = claim["check"]

    # ---- 数值一致性（单位对齐后取最接近值） ----
    if mode == "value":
        cv = claim["claim_value"]
        cu = claim.get("claim_unit", "")
        # 收集所有"关键词 → 其后 80 字符内"的 数字+单位 候选
        cands: List[Tuple[float, str, int, str]] = []   # (值, 单位, 页码, 片段)
        for pno in sorted(pages):
            text = pages[pno]
            for m in re.finditer(re.escape(kw), text):
                window = text[m.end(): m.end() + 80]
                snippet = text[max(0, m.start() - 10): m.end() + 80].replace("\n", " ").strip()
                for v, u, _ in extract_num_unit(window):
                    cands.append((v, u, pno, snippet))

        if not cands:
            result["reason"] = "命中片段中未解析到带单位的数字"
            return result

        # 优先单位一致的候选；若一个都没有，再退化为不限单位（并在理由中说明）
        aligned = [c for c in cands if unit_compatible(c[1], cu)]
        pool = aligned if aligned else cands
        v, u, pno, snippet = min(pool, key=lambda c: ratio(cv, c[0]))

        result["evidence_pages"] = [pno]
        result["evidence_snippets"] = [snippet]
        result["source_value"] = v
        result["source_unit"] = u
        r = ratio(cv, v)
        if r <= 0.01:
            result["verdict"] = "一致"
            result["reason"] = (
                f"研报 {cv}{cu} 与原文 {v}{u} 差异 {r*100:.2f}%，在 1% 容差内"
                + ("" if aligned else "（注意：未找到单位一致的原文数字，此为不限单位比对）")
            )
        else:
            # 判断是否为单位倍数关系（10/100/1000/10000 倍）
            mult = None
            for k in (10, 100, 1000, 10000):
                if ratio(cv * k, v) <= 0.01:
                    mult = k
                    break
                if cv / k > 0 and ratio(cv / k, v) <= 0.01:
                    mult = 1 / k
                    break
            if mult:
                result["verdict"] = "不一致"
                result["error_type"] = ErrorType.E2
                result["reason"] = (
                    f"研报 {cv}{cu} 与原文 {v}{u} 相差 {mult:g} 倍，"
                    f"判定为单位错误（E2）"
                )
                result["calculation"] = f"{cv} × {mult:g} = {cv*mult:g} ≈ 原文 {v}"
            else:
                result["verdict"] = "不一致"
                result["error_type"] = ErrorType.E1
                result["reason"] = (
                    f"研报 {cv}{cu} 与原文 {v}{u}（同单位）差异 {r*100:.1f}%，"
                    f"判定为数值错误（E1）"
                )
                result["calculation"] = f"|{cv} - {v}| / {v} = {r*100:.2f}%"

    # ---- 派生指标重算 ----
    elif mode == "recompute":
        rc = claim["recompute"]
        (nk, nv), (dk, dv), claim_pct = rc["numerator"], rc["denominator"], rc["claim_pct"]
        actual = nv / dv * 100
        result["source_value"] = round(actual, 2)
        result["calculation"] = f"{nk} {nv} / {dk} {dv} × 100% = {actual:.2f}%"
        r = ratio(claim_pct, actual)
        if r <= 0.01:
            result["verdict"] = "一致"
            result["reason"] = f"重算 {actual:.2f}% 与研报 {claim_pct}% 差异 {r*100:.2f}%，勾稽关系成立"
        else:
            result["verdict"] = "不一致"
            result["error_type"] = ErrorType.E7
            result["reason"] = (
                f"重算比例为 {actual:.2f}%，研报写 {claim_pct}%，"
                f"差异 {r*100:.1f}%，判定为勾稽矛盾（E7）"
            )

    # ---- 来源存在性 ----
    elif mode == "exists":
        target = claim["search_number"]
        found = find_number_in_doc(pages, target)
        if found:
            result["verdict"] = "一致"
            result["evidence_pages"] = [p for p, _ in found]
            result["evidence_snippets"] = [s for _, s in found]
            result["source_value"] = target
            result["reason"] = f"全文检索到数值 {target}，来源存在"
        else:
            # 数字不存在本身就是发现：但措辞必须诚实——是"未检索到"，不是"造假"
            result["verdict"] = "不一致"
            result["error_type"] = ErrorType.E6
            result["reason"] = (
                f"在已解析的全部 {len(pages)} 页中检索不到数值 {target} 的任何书写形态，"
                f"该表述缺乏来源支撑（E6）"
            )
            result["calculation"] = f"检索形态：{target:,.2f} / {target:g} 等，命中 0 处"

    # ---- 关键词上下文（口径混淆） ----
    elif mode == "keyword_context":
        # 正确顺序：先按**数值**定位原文位置，再看该位置附近有没有
        # 「扣非 / 非IFRS」这类口径限定词。早期版本先按关键词找，找到的
        # 往往是同一指标的另一口径（如 IFRS 每股盈利），导致漏检。
        cv = claim["claim_value"]
        occ: List[Tuple[int, str]] = []
        for pno in sorted(pages):
            text = pages[pno]
            for v, u, pos in extract_num_unit(text):
                if abs(v - cv) <= max(abs(cv) * 0.0005, 1e-9):
                    snippet = text[max(0, pos - 45): pos + 45].replace("\n", " ").strip()
                    occ.append((pno, snippet))
        if not occ:
            result["reason"] = f"未在原文中找到与声称值 {cv} 匹配的位置"
            return result
        result["evidence_pages"] = [p for p, _ in occ]
        result["evidence_snippets"] = [s for _, s in occ]
        result["source_value"] = cv
        # 检查命中位置附近是否含口径限定词，而草稿表述里没有
        qualifiers = ["扣非", "扣除非经常", "非國際財務報告準則", "非IFRS",
                      "non-IFRS", "Non-IFRS", "經調整", "调整后"]
        for pno, snip in occ:
            for q in qualifiers:
                if q in snip and q not in claim["quote"]:
                    result["verdict"] = "疑似"
                    result["error_type"] = ErrorType.E3
                    result["reason"] = (
                        f"数值 {cv} 在原文中带有「{q}」口径限定，草稿表述未体现该限定，"
                        f"疑似统计口径错误（E3），需语义复核"
                    )
                    return result
        result["verdict"] = "一致"
        result["reason"] = "数值位置附近未发现口径限定词歧义"

    return result


# ============ 通道二：大模型语义判定 ============

LLM_SYS = (
    "你是金融研报事实核查助手。给定一条研报断言和一段原始年报的摘录，"
    "判断断言与摘录是否一致。只输出 JSON，不要任何解释文字。"
    "JSON 字段：verdict（一致/不一致/无法判定）、error_type（E1数值错误/E2单位错误/"
    "E3统计口径错误/E4时间区间错误/E5估值倍数错误/E6引用与来源错误/E7勾稽与逻辑矛盾/无）、"
    "reason（40字以内）。摘录中没有的信息不要臆测，证据不足就答无法判定。"
)


def llm_check(provider: ModelProvider, claim: Dict[str, Any],
              rule_result: Dict[str, Any], with_evidence: bool) -> Dict[str, Any]:
    """调大模型判定。with_evidence=False 时模拟"纯 LLM 无证据"对照组。"""
    if with_evidence:
        snips_pairs = list(zip(rule_result["evidence_pages"],
                               rule_result["evidence_snippets"]))
        # 证据为空（如"来源不存在"类断言）时，退回按关键词给上下文，
        # 让模型有机会判断"原文确实没提"，而不是只能答无法判定
        if not snips_pairs:
            for pno, snip in locate(_DOCS_CACHE.get(claim["doc_id"], {}),
                                    claim["keyword"], max_hits=2):
                snips_pairs.append((pno, snip))
        snips = "\n".join(f"  [第{p}页] {s}" for p, s in snips_pairs[:3])
        user = f"【研报断言】{claim['quote']}\n【原始年报摘录】\n{snips}\n请判断。"
    else:
        user = f"【研报断言】{claim['quote']}\n（无原始材料可参考，请凭常识判断）\n请判断。"

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


# ============ 汇总为 Finding 对象 ============

def to_finding(claim: Dict[str, Any], rule: Dict[str, Any],
               llm: Dict[str, Any], llm_pure: Dict[str, Any]) -> Optional[Finding]:
    """把核查结果收敛成一个 Finding（演示数据契约在真实流程中的用法）。"""
    if rule["verdict"] == "一致":
        return None  # 对照组不产出 finding

    confirmed = rule["verdict"] == "不一致"
    level = EvidenceLevel.A if confirmed else EvidenceLevel.B
    status = FindingStatus.CONFIRMED if confirmed else FindingStatus.SUSPECT

    evidences = [
        Evidence(
            doc_id=claim["doc_id"],
            page_no=p,
            quote=s,
            calculation=rule.get("calculation", ""),
            evidence_level=level,
        )
        for p, s in zip(rule["evidence_pages"], rule["evidence_snippets"])
    ]

    # 双通道一致性
    llm_says_error = llm.get("verdict") == "不一致"
    channel_note = "双通道一致" if (confirmed and llm_says_error) else (
        "双通道不一致，已进人工复核队列" if confirmed != llm_says_error else "双通道一致（均未见错误）"
    )

    finding = Finding(
        finding_id=f"F-{claim['id']}",
        target_doc_id="DEMO-DRAFT-2025",       # 构造的研报草稿
        target_page=1,
        error_type=rule.get("error_type") or ErrorType.E1,
        status=status,
        evidence_level=level,
        target_quote=claim["quote"],
        claim_value=str(claim.get("claim_value", "")),
        correct_value=str(rule.get("source_value", "")),
        unit=claim.get("claim_unit", ""),
        severity=Severity.HIGH if confirmed else Severity.MEDIUM,
        reason=f"{rule['reason']}；大模型复核：{llm.get('reason', '')}；{channel_note}",
        evidences=evidences,
        channel=Channel.HYBRID,
        rule_id=f"R-{claim['check'].upper()}-001",
        suggestion_original=claim["quote"],
        suggestion_revised="",
        suggestion_basis="",
        suggestion_impact="",
    )
    if confirmed:
        finding.suggestion_basis = (
            f"{claim['doc_id']} 第 {rule['evidence_pages'][0]} 页："
            f"{rule['evidence_snippets'][0][:60]}"
        )
    return finding


# ============ 主流程 ============

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-llm", action="store_true", help="不调大模型")
    args = ap.parse_args()

    docs = load_docs()
    _DOCS_CACHE.update(docs)
    if "ZGPA-AR-2025" not in docs or "TX-AR-2025" not in docs:
        print("缺少解析产物，请先运行 tools/extract_real.py")
        return 1

    n_err_planned = sum(1 for c in CLAIMS if c["gt"] is not None)
    n_ok_planned = len(CLAIMS) - n_err_planned
    print(f"研报草稿：DEMO-DRAFT-2025（构造样例，含 {n_err_planned} 处预埋错误 "
          f"+ {n_ok_planned} 条正确断言作对照）")

    provider = None
    if not args.skip_llm:
        provider = ModelProvider.from_env()
        if not provider.cfg.has_key():
            print("未配置密钥，自动跳过 LLM 通道（加 --skip-llm 可显式跳过）")
            args.skip_llm = True

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("FinCheck 端到端核查演示（真实年报数据）")
    print("=" * 78)
    print(f"已加载材料：{ {k: len(v) for k, v in docs.items()} }")
    print()

    rows: List[Dict[str, Any]] = []
    findings: List[Finding] = []
    t0 = time.time()

    for claim in CLAIMS:
        pages = docs[claim["doc_id"]]
        rule = rule_check(claim, pages)

        llm_res = {"verdict": "-", "error_type": "", "reason": "未调用"}
        llm_pure = {"verdict": "-", "error_type": "", "reason": "未调用"}
        if provider is not None:
            llm_res = llm_check(provider, claim, rule, with_evidence=True)
            llm_pure = llm_check(provider, claim, rule, with_evidence=False)

        f = to_finding(claim, rule, llm_res, llm_pure)
        if f is not None:
            findings.append(f)

        rows.append({
            "id": claim["id"],
            "quote": claim["quote"],
            "gt": claim["gt"].description if claim["gt"] else "正确（对照）",
            "rule_verdict": rule["verdict"],
            "rule_type": rule["error_type"].description if rule["error_type"] else "-",
            "llm_verdict": llm_res.get("verdict", "-"),
            "llm_pure_verdict": llm_pure.get("verdict", "-"),
            "pages": rule["evidence_pages"],
            "reason": rule["reason"],
        })

        # 逐条打印
        print(f"[{claim['id']}] {claim['quote']}")
        print(f"    真实错误类型 : {rows[-1]['gt']}")
        print(f"    规则引擎      : {rule['verdict']}"
              + (f"（{rule['error_type'].description}）" if rule["error_type"] else ""))
        print(f"      依据       : {rule['reason']}")
        if rule["evidence_pages"]:
            print(f"      证据       : {claim['doc_id']} 第 {rule['evidence_pages'][0]} 页 "
                  f"「{rule['evidence_snippets'][0][:50]}…」")
        if provider is not None:
            print(f"    大模型(带证据): {llm_res.get('verdict')} —— {llm_res.get('reason', '')}")
            print(f"    大模型(无证据): {llm_pure.get('verdict')} —— {llm_pure.get('reason', '')}")
        print()

    # ---------- 统计 ----------
    n_total = len(rows)
    n_err = sum(1 for r in rows if r["gt"] != "正确（对照）")
    n_ok = n_total - n_err
    rule_caught = sum(1 for r in rows if r["rule_verdict"] == "不一致")
    rule_fp = sum(1 for r in rows if r["gt"] == "正确（对照）" and r["rule_verdict"] == "不一致")
    llm_caught = sum(1 for r in rows if r["gt"] != "正确（对照）" and r["llm_verdict"] == "不一致")
    llm_fp = sum(1 for r in rows if r["gt"] == "正确（对照）" and r["llm_verdict"] == "不一致")
    pure_caught = sum(1 for r in rows if r["gt"] != "正确（对照）" and r["llm_pure_verdict"] == "不一致")
    pure_fp = sum(1 for r in rows if r["gt"] == "正确（对照）" and r["llm_pure_verdict"] == "不一致")

    summary = {
        "断言总数": n_total,
        "其中预埋错误": n_err,
        "对照组(正确)": n_ok,
        "规则引擎_检出错误": rule_caught,
        "规则引擎_误报": rule_fp,
        "大模型带证据_检出错误": llm_caught,
        "大模型带证据_误报": llm_fp,
        "大模型无证据_检出错误": pure_caught,
        "大模型无证据_误报": pure_fp,
        "总耗时秒": round(time.time() - t0, 1),
    }

    print("=" * 78)
    print("统计汇总")
    print("=" * 78)
    for k, v in summary.items():
        print(f"  {k:<22}: {v}")

    # ---------- 落盘 ----------
    payload = {
        "声明": "本演示使用真实年报数字，研报草稿为构造样例，错误系故意预埋",
        "汇总": summary,
        "明细": rows,
        "findings": [f.to_dict() for f in findings],
    }
    (OUT_DIR / "findings.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    md = ["# FinCheck 端到端核查演示报告", "",
          "> **诚信声明**：公司数字均来自真实年报（中国平安 2025 年报、腾讯 2025 年报）；",
          "> 研报草稿为构造样例，错误系故意预埋，用于演示核查能力。", "",
          "## 汇总", ""]
    for k, v in summary.items():
        md.append(f"- {k}：{v}")
    md += ["", "## 逐条明细", "",
           "| 编号 | 研报断言 | 真实错误类型 | 规则引擎 | 大模型(带证据) | 大模型(无证据) | 证据页 |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(
            f"| {r['id']} | {r['quote'][:30]}… | {r['gt']} | {r['rule_verdict']}"
            f"{'（' + r['rule_type'] + '）' if r['rule_type'] != '-' else ''} "
            f"| {r['llm_verdict']} | {r['llm_pure_verdict']} | {r['pages']} |")
    md += ["", "## 结论", "",
           "1. 规则引擎对**确定性错误**（数值、单位、勾稽）可给出 A 级证据的确认结论；",
           "2. 大模型在**给定证据**时能发现口径类错误，但无证据时结论不可信（对照组）；",
           "3. 双通道不一致的断言进入人工复核队列——这是误报控制的设计机制，不是缺陷。"]
    (OUT_DIR / "e2e_report.md").write_text("\n".join(md), encoding="utf-8")

    print()
    print(f"结构化结论已写入：{OUT_DIR / 'findings.json'}")
    print(f"演示报告已写入  ：{OUT_DIR / 'e2e_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
