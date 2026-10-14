# -*- coding: utf-8 -*-
"""
src/common/schema.py —— 数据契约（全项目统一的数据模型）

这是整个项目的"公共地基"，也是 A 与 B 之间唯一的接口。所有模块
（解析层、规则层、视觉层、语义层、评测层）都使用这里定义的数据结构，
不得各自另立字段。

设计原则：
    1. **无证据不判定**：Finding 必须携带至少一条 Evidence，否则校验不通过。
    2. **红线写入代码**：C 级证据（图表反推 / 低可信 OCR）不得进入
       confirmed 状态——这条业务规则由 validate() 强制，而不是写在文档里
       靠人自觉遵守。
    3. **字段可追溯**：每条事实与结论都带 doc_id + page_no + 字符区间，
       保证任何数据都能回到原始来源页码。
    4. **序列化稳定**：to_dict() / from_dict() 保证落盘与读回一致，
       便于评测框架独立读取。

冻结约定：
    本文件于 2026-10-13 12:00 冻结。此后任何字段变更需 A、B 双签确认。

字段规范文档：docs/data_spec.md
归属：A（队长 · 语义与编排层）
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, get_args, get_origin, get_type_hints

# ============================================================
# 一、枚举：受控词表
# ============================================================


class EvidenceLevel(str, Enum):
    """证据等级。决定一条判定能否自动生效——这是本项目控制误报的核心机制。"""

    A = "A"
    B = "B"
    C = "C"

    @property
    def can_auto_judge(self) -> bool:
        """A、B 级可自动判定；C 级只能报"疑似"并进入人工复核队列。"""
        return self.value in ("A", "B")

    @property
    def description(self) -> str:
        return {
            "A": "文字层直接命中，可直接引用原文",
            "B": "OCR 识别且可信度 ≥0.9，并经人工抽检通过",
            "C": "图表像素反推或 OCR 可信度 <0.9，仅可报疑似",
        }[self.value]


class ErrorType(str, Enum):
    """七类错误，全队统一口径。"""

    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"
    E5 = "E5"
    E6 = "E6"
    E7 = "E7"

    @property
    def description(self) -> str:
        return {
            "E1": "数值错误",
            "E2": "单位错误",
            "E3": "统计口径错误",
            "E4": "时间区间错误",
            "E5": "估值倍数错误",
            "E6": "引用与来源错误",
            "E7": "勾稽与逻辑矛盾",
        }[self.value]


class Channel(str, Enum):
    """判定来源通道。双通道不一致时进人工复核队列。"""

    RULE = "rule"
    LLM = "llm"
    HYBRID = "hybrid"


class FindingStatus(str, Enum):
    """核查结论的状态。C 级证据只能落在 SUSPECT 或 PENDING。"""

    CONFIRMED = "confirmed"   # 已确认存在错误
    SUSPECT = "suspect"       # 疑似，待人工复核
    PENDING = "pending"       # 待复核（证据不足暂不判定）
    REJECTED = "rejected"     # 已排除，不构成错误


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def description(self) -> str:
        return {"high": "严重（影响投资判断）", "medium": "中等", "low": "轻微"}[self.value]


class PageType(str, Enum):
    """页面形态。解析层据此决定用哪种抽取方式。"""

    TEXT = "text"          # 纯文字
    TABLE = "table"        # 表格（线框或留白对齐）
    CHART = "chart"        # 图表
    SCANNED = "scanned"    # 扫描件，无文字层
    MIXED = "mixed"        # 图文混排


class ExtractMethod(str, Enum):
    """该条数据的抽取方式，用于判定证据等级。"""

    TEXT_LAYER = "text_layer"        # 文字层直读 → 通常 A 级
    TABLE_PARSER = "table_parser"    # 表格结构解析 → 通常 A 级
    OCR = "ocr"                      # 光学识别 → B 级或 C 级
    CHART_REVERSE = "chart_reverse"  # 图表数值反推 → 一律 C 级
    MANUAL = "manual"                # 人工录入 → 需登记复核人


class PeriodType(str, Enum):
    ANNUAL = "annual"                # 年度（期间数）
    QUARTERLY = "quarterly"          # 季度
    HALF_YEAR = "half_year"          # 半年度
    TTM = "ttm"                      # 滚动十二个月
    POINT_IN_TIME = "point_in_time"  # 时点数（如总资产、净资产）


class StatementBasis(str, Enum):
    """报表口径。同一指标在合并与母公司口径下数值不同，混淆即 E3 错误。"""

    CONSOLIDATED = "合并"
    PARENT = "母公司"
    UNKNOWN = "未标注"


class AccountingStandard(str, Enum):
    """会计准则。跨准则双重披露是 E3 错误的高发区。"""

    CAS = "中国企业会计准则"
    IFRS = "国际财务报告准则"
    US_GAAP = "美国公认会计原则"
    UNKNOWN = "未标注"


class ReviewStatus(str, Enum):
    NOT_REVIEWED = "not_reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"   # 升级处理


# ============================================================
# 二、证据
# ============================================================


@dataclass
class Evidence:
    """证据四元组：源文件 / 页码 / 原文片段 / 计算过程。

    这是本项目"来源定位"评分项的实现载体——每一条判定都必须能落到
    这里的一个具体页面上，不允许出现"根据年报可知"这类无锚点表述。
    """

    # ---- 必填 ----
    doc_id: str          # 源文件标识（见 docs/data_spec.md 第一节）
    page_no: int         # 页码，从 1 开始
    quote: str           # 原文片段（逐字摘录，不得改写）

    # ---- 选填 ----
    char_start: int = -1     # 在全文中的字符起始偏移，-1 表示未记录
    char_end: int = -1       # 在全文中的字符结束偏移（不含）
    calculation: str = ""    # 计算过程（如 "1240358902.35 / 1102450633.21 - 1 = 12.51%"）
    page_type: PageType = PageType.TEXT
    evidence_level: EvidenceLevel = EvidenceLevel.A
    image_path: str = ""     # 若证据来自图片页，记录页面图片路径

    def __post_init__(self) -> None:
        if self.page_no < 1:
            raise ValueError(f"page_no 必须 ≥ 1，当前为 {self.page_no}")
        if not str(self.quote).strip():
            raise ValueError("quote 不能为空：无证据不判定")

    def locate(self) -> str:
        """人类可读的定位串，用于写入报告与界面展示。"""
        span = f"，字符区间 [{self.char_start}, {self.char_end})" if self.char_start >= 0 else ""
        return f"{self.doc_id} 第 {self.page_no} 页{span}"


# ============================================================
# 三、财务事实（解析层的产出）
# ============================================================


@dataclass
class FinancialFact:
    """从原始材料中抽取的一条财务事实。

    这是"原始材料"侧的数据单元。语义层用它与被核查草稿中的表述比对，
    规则层用它做勾稽、单位、口径的确定性校验。
    """

    # ---- 必填 ----
    fact_id: str          # 事实唯一标识，建议 f"{doc_id}-p{page_no}-{序号:03d}"
    doc_id: str           # 来源文件标识
    page_no: int          # 来源页码
    metric_name: str      # 指标名称（须使用受控词表，见 docs/data_spec.md 第二节）
    value_raw: str        # 原文形态的数值（保留千分位、单位后缀等原始写法）

    # ---- 选填 ----
    entity: str = ""                    # 主体名称（公司名）
    value_num: Optional[float] = None   # 数值化结果，用于计算比对
    unit: str = "元"                    # 单位：元 / 万元 / 亿元 / % / 元/股 / 倍
    currency: str = "CNY"               # 币种
    period: str = ""                    # 期间，如 "2024" / "2024Q3" / "2024-12-31"
    period_type: PeriodType = PeriodType.POINT_IN_TIME
    basis: StatementBasis = StatementBasis.UNKNOWN
    accounting_standard: AccountingStandard = AccountingStandard.UNKNOWN
    statement: str = ""                 # 所属报表，如 "合并资产负债表"
    section: str = ""                   # 所属章节/小节
    char_start: int = -1                # 在来源页全文中的字符起始偏移
    char_end: int = -1
    evidence_text: str = ""             # 该事实所在的原文句段
    evidence_level: EvidenceLevel = EvidenceLevel.A
    extract_method: ExtractMethod = ExtractMethod.TEXT_LAYER
    confidence: float = 1.0             # 抽取置信度，0~1
    table_ref: str = ""                 # 表格编号/位置，如 "page2/table1/row3"
    truncated: bool = False             # ⚠ 越界截断标记。详见验证报告"发现三"
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.page_no < 1:
            raise ValueError(f"page_no 必须 ≥ 1，当前为 {self.page_no}")
        if not str(self.metric_name).strip():
            raise ValueError("metric_name 不能为空")
        if not str(self.value_raw).strip():
            raise ValueError("value_raw 不能为空")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError(f"confidence 必须在 0~1 之间，当前为 {self.confidence}")
        if not self.created_at:
            self.created_at = now_iso()

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        return _jsonable(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FinancialFact":
        return _build(cls, data)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    # ---------- 业务校验 ----------

    def validate(self) -> List[str]:
        """返回问题清单；空列表表示通过。"""
        issues: List[str] = []
        if self.value_num is None:
            issues.append("value_num 为空，无法参与数值比对（若原文确实无数值，请改用占位说明）")
        if self.truncated:
            issues.append("该事实被标记为疑似截断，不得直接用于判定错误")
        if self.extract_method == ExtractMethod.CHART_REVERSE and self.evidence_level != EvidenceLevel.C:
            issues.append("图表反推的数值必须标记为 C 级证据")
        if self.extract_method == ExtractMethod.MANUAL and self.evidence_level == EvidenceLevel.A:
            issues.append("人工录入的数据不应直接标为 A 级，须经复核")
        return issues


# ============================================================
# 四、核查结论（系统的最终产出）
# ============================================================


@dataclass
class Finding:
    """一条核查结论——本系统对外交付的核心数据单元。

    四个评分项在字段上的落点：
        识别准确性与覆盖率 → error_type + severity
        误报控制           → evidence_level + status + evidences（强制证据）
        来源定位           → target_page + evidences[].page_no/char 区间
        修改建议可执行性   → suggestion_original / revised / basis / impact
    """

    # ---- 必填 ----
    finding_id: str                              # 结论唯一标识
    target_doc_id: str                           # 被核查草稿的文件标识
    target_page: int                             # 草稿中出现问题的页码
    error_type: ErrorType                        # 七类之一
    status: FindingStatus                        # 结论状态
    evidence_level: EvidenceLevel                # 支撑本结论的最高证据等级

    # ---- 选填 ----
    target_quote: str = ""                       # 草稿中的原文片段
    target_char_start: int = -1
    target_char_end: int = -1
    severity: Severity = Severity.MEDIUM
    claim_value: str = ""                        # 草稿中的值（原文形态）
    correct_value: str = ""                      # 正确值
    unit: str = ""
    delta: str = ""                              # 差异描述，如 "虚增 0.01 亿元"
    reason: str = ""                             # 判定理由（面向评审的可读说明）
    evidences: List[Evidence] = field(default_factory=list)
    rule_id: str = ""                            # 命中的规则编号（规则通道）
    channel: Channel = Channel.RULE
    model_info: Dict[str, Any] = field(default_factory=dict)  # 若经大模型判定，记录厂商与型号

    # ---- 改写建议（四段式，对应"可执行性"评分项）----
    suggestion_original: str = ""                # 原文
    suggestion_revised: str = ""                 # 建议改为
    suggestion_basis: str = ""                   # 依据
    suggestion_impact: str = ""                  # 影响范围

    # ---- 人工复核 ----
    review_status: ReviewStatus = ReviewStatus.NOT_REVIEWED
    reviewer: str = ""
    review_note: str = ""

    # ---- 溯源 ----
    run_id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.target_page < 1:
            raise ValueError(f"target_page 必须 ≥ 1，当前为 {self.target_page}")
        if not self.created_at:
            self.created_at = now_iso()

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        return _jsonable(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Finding":
        return _build(cls, data)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    # ---------- 业务校验：红线由代码强制 ----------

    def validate(self) -> List[str]:
        """返回问题清单；空列表表示通过。

        这里把项目红线写成可执行的校验，而不是文档里的一句口号：
        "图像处理负责发现可疑，不负责定罪。"
        """
        issues: List[str] = []

        # 1) 无证据不判定
        if not self.evidences:
            issues.append("缺少证据：每条结论至少需要一条 Evidence（无证据不判定）")
        else:
            for i, ev in enumerate(self.evidences, 1):
                if ev.page_no < 1:
                    issues.append(f"第 {i} 条证据页码无效")
                if not str(ev.quote).strip():
                    issues.append(f"第 {i} 条证据缺少原文片段")

        # 2) C 级证据不得自动判定 —— 这是"误报控制"的核心红线
        if self.evidence_level == EvidenceLevel.C and self.status == FindingStatus.CONFIRMED:
            issues.append(
                "红线违规：C 级证据（图表反推 / 低可信 OCR）不得直接判定为 confirmed，"
                "只能报 suspect 或 pending"
            )

        # 3) 结论状态与证据等级须一致
        if self.status == FindingStatus.CONFIRMED and self.evidence_level == EvidenceLevel.C:
            issues.append("证据等级与结论状态不匹配")

        # 4) 可执行性：确认存在错误时必须给出具体改写建议
        if self.status == FindingStatus.CONFIRMED:
            if not self.suggestion_revised.strip():
                issues.append("已确认错误但未给出建议改写文本，不满足'修改建议可执行性'要求")
            if not self.suggestion_basis.strip():
                issues.append("已确认错误但未给出改写依据")

        # 5) 至少要有值可比对
        if not self.claim_value.strip() and not self.correct_value.strip():
            issues.append("claim_value 与 correct_value 不能同时为空")

        # 6) 经大模型判定的，必须记录模型身份（可追溯要求）
        if self.channel in (Channel.LLM, Channel.HYBRID) and not self.model_info:
            issues.append("经大模型判定但未记录模型信息（厂商/型号），不满足可追溯要求")

        return issues

    @property
    def is_actionable(self) -> bool:
        """是否为可交付的结论：校验通过且不属于被排除项。"""
        return not self.validate() and self.status != FindingStatus.REJECTED

    def best_evidence_level(self) -> EvidenceLevel:
        """返回全部证据中最高的等级（A > B > C），用于派生 evidence_level。"""
        if not self.evidences:
            return EvidenceLevel.C
        order = {EvidenceLevel.A: 0, EvidenceLevel.B: 1, EvidenceLevel.C: 2}
        return sorted(self.evidences, key=lambda e: order[e.evidence_level])[0].evidence_level


# ============================================================
# 五、执行日志（可追溯性要求）
# ============================================================


@dataclass
class TraceRecord:
    """一条执行轨迹。竞赛要求完整记录文件访问、工具调用、计算过程与结果生成。"""

    run_id: str
    step: str                       # 步骤名，如 "ingest.extract" / "agent.verify"
    action: str                     # 动作描述
    status: str = "ok"              # ok / error / skip
    doc_id: str = ""
    page_no: int = 0
    detail: Dict[str, Any] = field(default_factory=dict)
    model_info: Dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return _jsonable(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TraceRecord":
        return _build(cls, data)


# ============================================================
# 六、工具函数
# ============================================================


def now_iso() -> str:
    """统一时间戳格式，便于跨机器比对。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _jsonable(value: Any) -> Any:
    """递归转换为可 JSON 序列化的结构（枚举转字符串，dataclass 转 dict）。"""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {f.name: _jsonable(getattr(value, f.name)) for f in fields(value)}
    return value


def _coerce(tp: Any, value: Any) -> Any:
    """按类型注解把原始值转换为目标类型（处理枚举、嵌套 dataclass、列表、Optional）。"""
    if value is None:
        return None

    origin = get_origin(tp)

    # Optional[T] / Union[T, None]
    if origin is Union:
        args = [a for a in get_args(tp) if a is not type(None)]
        return _coerce(args[0], value) if args else value

    # List[T]
    if origin in (list, List):
        args = get_args(tp)
        inner = args[0] if args else Any
        if isinstance(value, (list, tuple)):
            return [_coerce(inner, v) for v in value]
        return value

    # Dict[str, Any]
    if origin in (dict, Dict):
        return value

    # 枚举
    if isinstance(tp, type) and issubclass(tp, Enum):
        try:
            return tp(value)
        except ValueError:
            return value

    # 嵌套 dataclass
    if hasattr(tp, "__dataclass_fields__") and isinstance(value, dict):
        return _build(tp, value)

    return value


def _build(cls: Any, data: Dict[str, Any]) -> Any:
    """按 dataclass 定义从 dict 构造实例，忽略多余字段，缺失字段用默认值。"""
    hints = get_type_hints(cls)
    kwargs: Dict[str, Any] = {}
    for f in fields(cls):
        if f.name in data:
            kwargs[f.name] = _coerce(hints.get(f.name, Any), data[f.name])
    return cls(**kwargs)


def dump_jsonl(records: List[Any], path: Path) -> int:
    """把一批对象以 JSON Lines 格式落盘（每行一个对象，便于流式读取与 diff）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            payload = rec.to_dict() if hasattr(rec, "to_dict") else rec
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return len(records)


def load_jsonl(path: Path, cls: Optional[Any] = None) -> List[Any]:
    """读取 JSON Lines；传入 cls 时自动构造为对应 dataclass。"""
    path = Path(path)
    if not path.exists():
        return []
    out: List[Any] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            out.append(cls.from_dict(data) if cls is not None else data)
    return out


# ============================================================
# 七、自检
# ============================================================


def _selftest() -> int:
    print("=" * 72)
    print("schema.py 自检 —— 数据契约可用性与红线校验")
    print("=" * 72)

    # ---------- 1. 财务事实 ----------
    fact = FinancialFact(
        fact_id="SAMPLE-AR-2024-p2-001",
        doc_id="SAMPLE-AR-2024",
        page_no=2,
        metric_name="营业收入",
        value_raw="1,240,358,902.35",
        entity="星野智造股份有限公司",
        value_num=1240358902.35,
        unit="元",
        period="2024",
        period_type=PeriodType.ANNUAL,
        basis=StatementBasis.CONSOLIDATED,
        accounting_standard=AccountingStandard.CAS,
        statement="合并利润表",
        evidence_text="营业收入（元） 1,240,358,902.35",
        evidence_level=EvidenceLevel.A,
        extract_method=ExtractMethod.TABLE_PARSER,
        table_ref="page2/table1/row1",
    )
    print("\n【1】FinancialFact 构造成功")
    print(fact.to_json())

    problems = fact.validate()
    print(f"校验结果：{'通过' if not problems else problems}")

    # ---------- 2. 反序列化一致性 ----------
    roundtrip = FinancialFact.from_dict(json.loads(fact.to_json()))
    same = roundtrip.to_dict() == fact.to_dict()
    print(f"\n【2】序列化往返一致性：{'通过' if same else '失败'}")
    assert isinstance(roundtrip.period_type, PeriodType), "枚举未还原为枚举类型"
    assert isinstance(roundtrip.basis, StatementBasis), "枚举未还原为枚举类型"

    # ---------- 3. 合规结论 ----------
    good = Finding(
        finding_id="F-0001",
        target_doc_id="SAMPLE-REPORT",
        target_page=1,
        error_type=ErrorType.E2,
        status=FindingStatus.CONFIRMED,
        evidence_level=EvidenceLevel.A,
        target_quote="公司总资产达 385.62 亿元",
        claim_value="385.62 亿元",
        correct_value="38.56 亿元",
        unit="亿元",
        delta="单位错误，虚增 10 倍",
        reason="年报合并资产负债表列示总资产 3,856,209,744.60 元，即 38.56 亿元。",
        evidences=[
            Evidence(
                doc_id="SAMPLE-AR-2024",
                page_no=2,
                quote="总资产（元） 3,856,209,744.60",
                char_start=1024,
                char_end=1054,
                calculation="3,856,209,744.60 元 / 1e8 = 38.56 亿元",
                evidence_level=EvidenceLevel.A,
            )
        ],
        rule_id="R-UNIT-001",
        channel=Channel.RULE,
        suggestion_original="公司总资产达 385.62 亿元，资产结构稳健",
        suggestion_revised="公司总资产达 38.56 亿元，资产结构稳健",
        suggestion_basis="年报合并资产负债表：总资产 3,856,209,744.60 元",
        suggestion_impact="影响资产规模表述，不影响结论方向",
    )
    print("\n【3】合规的 Finding（A 级证据 + confirmed）")
    print(f"校验结果：{'通过' if not good.validate() else good.validate()}")
    assert not good.validate(), "合规结论不应报错"
    assert good.is_actionable

    # ---------- 4. 红线：C 级证据不得 confirmed ----------
    bad = Finding.from_dict(good.to_dict())
    bad.finding_id = "F-0002"
    bad.evidence_level = EvidenceLevel.C
    bad.status = FindingStatus.CONFIRMED
    bad.evidences = [
        Evidence(
            doc_id="SAMPLE-AR-2024",
            page_no=5,
            quote="（图表反推）2024年营业收入柱高对应约 15.0",
            calculation="柱高像素比值 × 纵轴刻度",
            page_type=PageType.CHART,
            evidence_level=EvidenceLevel.C,
        )
    ]
    issues = bad.validate()
    print("\n【4】红线校验：C 级证据 + confirmed 应被拒绝")
    for it in issues:
        print(f"    · {it}")
    assert any("红线违规" in i for i in issues), "红线未被强制"
    assert not bad.is_actionable

    # ---------- 5. 无证据不判定 ----------
    no_evi = Finding.from_dict(good.to_dict())
    no_evi.evidences = []
    print("\n【5】无证据结论应被拒绝")
    for it in no_evi.validate():
        print(f"    · {it}")
    assert no_evi.validate(), "无证据结论必须被拒绝"

    # ---------- 6. JSONL 落盘与读回 ----------
    tmp = Path("output/_selftest_schema.jsonl")
    n = dump_jsonl([good, bad], tmp)
    back = load_jsonl(tmp, Finding)
    print(f"\n【6】JSONL 落盘/读回：写入 {n} 条，读回 {len(back)} 条，"
          f"{'一致' if len(back) == 2 else '不一致'}")
    tmp.unlink(missing_ok=True)

    print("\n" + "=" * 72)
    print("自检全部通过。")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
