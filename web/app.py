# -*- coding: utf-8 -*-
"""
web/app.py —— 「数证 FinCheck」研报事实核查智能体 · 网站前端

定位（2026-10-14 分工调整后）：
    10/18 前只交付**外观界面与基础交互**：上传区、材料库选择、
    核查流程演示、结论卡片展示、架构与实测证据展示。
    后端核心功能（PDF 解析 / 断言抽取 / 双通道核查）排期 10/18 后接入，
    接口已在 web/api_client.py 预留——接入时只改该文件，本文件零改动。

本地运行：
    streamlit run web/app.py
部署：
    Streamlit Cloud，Main file path 填 web/app.py（详见 web/README.md）

诚信声明：
    演示数据为 2026-10-14 实测产物（tools/demo_e2e.py），
    研报草稿系构造样例，错误故意预埋，不冒充真实研报。

归属：A（队长 · 语义与编排层）
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import streamlit as st

WEB_DIR = Path(__file__).resolve().parent
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from demo_data import DEMO_CLAIMS, DEMO_META, DOC_LIBRARY  # noqa: E402
from api_client import backend_status, simulated_progress  # noqa: E402

# ============================================================
# 页面配置
# ============================================================

st.set_page_config(
    page_title="数证 FinCheck · 研报事实核查智能体",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 全局样式（浅色专业金融风）
# ============================================================

CUSTOM_CSS = """
<style>
/* ---------- 基础 ---------- */
.main .block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1200px; }
h1, h2, h3 { font-weight: 700; color: #0f2440; }
section[data-testid="stSidebar"] { background: #0f2440; }
section[data-testid="stSidebar"] * { color: #dbe4f0 !important; }
section[data-testid="stSidebar"] .stMarkdown { color: #dbe4f0; }

/* ---------- Hero ---------- */
.hero {
    background: linear-gradient(135deg, #0f2440 0%, #1b3a63 60%, #2563eb 100%);
    border-radius: 16px; padding: 34px 38px 30px 38px; color: #ffffff;
    margin-bottom: 18px;
}
.hero h1 { color: #ffffff !important; font-size: 2.0rem; margin: 0 0 6px 0; letter-spacing: 1px; }
.hero .sub { color: #b9cdf0; font-size: 1.02rem; margin: 0 0 18px 0; }
.hero .en { color: #7fa8e8; font-size: 0.8rem; letter-spacing: 3px; text-transform: uppercase; }

/* ---------- 指标 chip ---------- */
.chips { display: flex; flex-wrap: wrap; gap: 10px; margin: 6px 0 2px 0; }
.chip {
    background: #eef4ff; border: 1px solid #c9dcff; color: #1b3a63;
    border-radius: 999px; padding: 5px 14px; font-size: 0.82rem; font-weight: 600;
}
.chip b { color: #2563eb; }

/* ---------- 卡片 ---------- */
.card {
    background: #ffffff; border: 1px solid #e3e9f2; border-radius: 12px;
    padding: 18px 20px; margin-bottom: 14px;
    box-shadow: 0 1px 3px rgba(15,36,64,0.06);
}
.card .card-title { font-weight: 700; color: #0f2440; font-size: 0.98rem; margin-bottom: 4px; }
.card .muted { color: #64748b; font-size: 0.84rem; }

/* ---------- 判定徽章 ---------- */
.badge {
    display: inline-block; border-radius: 6px; padding: 2px 10px;
    font-size: 0.78rem; font-weight: 700; margin-right: 8px;
}
.badge-red    { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
.badge-orange { background: #ffedd5; color: #c2410c; border: 1px solid #fed7aa; }
.badge-green  { background: #d1fae5; color: #047857; border: 1px solid #a7f3d0; }
.badge-gray   { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
.badge-blue   { background: #dbeafe; color: #1d4ed8; border: 1px solid #bfdbfe; }

/* ---------- 证据块 ---------- */
.evidence {
    background: #f8fafc; border-left: 3px solid #2563eb; border-radius: 0 8px 8px 0;
    padding: 10px 14px; margin: 8px 0; font-size: 0.86rem; color: #334155;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}
.calc {
    background: #fefce8; border-left: 3px solid #eab308; border-radius: 0 8px 8px 0;
    padding: 8px 14px; margin: 8px 0; font-size: 0.84rem; color: #713f12;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}

/* ---------- 空状态 ---------- */
.empty-state {
    border: 2px dashed #c9dcff; border-radius: 14px; padding: 46px 30px;
    text-align: center; color: #64748b; background: #fbfdff;
}
.empty-state .big { font-size: 2.4rem; margin-bottom: 8px; }

/* ---------- 架构流程图 ---------- */
.flow { display: flex; align-items: stretch; gap: 8px; flex-wrap: wrap; margin: 10px 0; }
.flow .node {
    flex: 1; min-width: 130px; background: #ffffff; border: 1.5px solid #c9dcff;
    border-radius: 10px; padding: 12px 10px; text-align: center;
}
.flow .node .t { font-weight: 700; color: #0f2440; font-size: 0.86rem; }
.flow .node .d { color: #64748b; font-size: 0.74rem; margin-top: 3px; }
.flow .arrow { align-self: center; color: #2563eb; font-weight: 900; font-size: 1.1rem; }
.flow .node.hl { border-color: #2563eb; background: #eff6ff; }

/* ---------- 表格 ---------- */
table.pretty { width: 100%; border-collapse: collapse; font-size: 0.86rem; }
table.pretty th { background: #0f2440; color: #fff; padding: 8px 10px; text-align: left; font-weight: 600; }
table.pretty td { padding: 8px 10px; border-bottom: 1px solid #e8edf5; color: #334155; vertical-align: top; }
table.pretty tr:nth-child(even) td { background: #f8fafc; }

/* ---------- 提示条 ---------- */
.notice {
    border-radius: 10px; padding: 12px 16px; font-size: 0.88rem; margin: 10px 0;
}
.notice-warn { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; }
.notice-info { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; }
.notice-ok   { background: #ecfdf5; border: 1px solid #a7f3d0; color: #065f46; }
</style>
"""

VERDICT_BADGE = {
    "不一致": "badge-red",
    "确认": "badge-red",
    "疑似": "badge-orange",
    "一致": "badge-green",
    "无法判定": "badge-gray",
    "调用失败": "badge-gray",
}

CHANNEL_LABEL = {"rule": "规则引擎", "llm": "大模型（带证据）", "pure": "大模型（无证据）"}


def badge(text: str) -> str:
    cls = VERDICT_BADGE.get(text, "badge-gray")
    return f'<span class="badge {cls}">{text}</span>'


def inject_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ============================================================
# 侧边栏
# ============================================================

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🔍 数证 FinCheck")
        st.markdown(
            '<p style="color:#7fa8e8;font-size:0.78rem;letter-spacing:2px;">'
            "RESEARCH REPORT FACT CHECKING</p>",
            unsafe_allow_html=True,
        )
        st.divider()

        status = backend_status()
        if status["ready"]:
            st.success("✅ 后端已接入")
        else:
            st.warning("🧪 演示模式")
            st.caption(status["message"])

        st.divider()
        st.markdown("**模型档案**（后端接入后生效）")
        st.selectbox(
            "选择档案",
            options=["glm（智谱 GLM-4-Flash · 免费）", "deepseek（决赛主力）", "mock（离线自检）"],
            index=0,
            label_visibility="collapsed",
        )
        st.caption("密钥仅存于服务端环境变量，不在前端出现。")

        st.divider()
        st.markdown("**材料库**")
        for d in DOC_LIBRARY:
            st.caption(f"· {d['name']}（{d['pages']} 页）")

        st.divider()
        st.caption("数据一定队 · 2026 北京市大学生金融人工智能竞赛 · 选题五")
        st.caption("演示数据为 2026-10-14 实测，构造样例已标注")


# ============================================================
# Tab 1：核查工作台
# ============================================================

CHECK_STEPS = ["解析材料", "抽取财务断言", "双通道核查", "生成证据链结论"]


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
          <div class="en">Research Report Fact-Checking Agent</div>
          <h1>数证 FinCheck · 研报事实核查智能体</h1>
          <p class="sub">对研究报告中的财务断言逐条回溯至上市公司年报原文，
          输出「错在哪 · 依据是什么 · 改成什么」的完整证据链。</p>
          <div class="chips">
            <span class="chip">📚 <b>1,067</b> 页真实年报材料</span>
            <span class="chip">🧭 <b>8</b> 类错误识别体系</span>
            <span class="chip">⚖️ 确定性规则 <b>+</b> 大模型 双通道</span>
            <span class="chip">🎯 实测覆盖 <b>6/6</b> · 误报 <b>0</b></span>
            <span class="chip">🔒 证据分级 · C 级不定罪</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_workbench() -> None:
    render_hero()

    left, right = st.columns([1, 2.1], gap="large")

    # ---------- 左栏：输入区 ----------
    with left:
        st.markdown("#### 📤 提交待核查研报")
        uploaded = st.file_uploader(
            "上传研报 PDF", type=["pdf"], label_visibility="collapsed",
            help="后端接入后支持解析；当前演示模式展示预置结论",
        )
        if uploaded is not None:
            st.caption(f"已选择：{uploaded.name}（{uploaded.size / 1024:.0f} KB）")

        st.markdown("#### 🎯 比对年报")
        doc_options = [f"{d['name']}" for d in DOC_LIBRARY]
        doc_idx = st.selectbox(
            "选择比对的年报", options=range(len(doc_options)),
            format_func=lambda i: doc_options[i], label_visibility="collapsed",
        )
        st.caption(f"标识：{DOC_LIBRARY[doc_idx]['doc_id']} · {DOC_LIBRARY[doc_idx]['pages']} 页")

        st.markdown("")
        run = st.button("🚀 开始核查", type="primary", use_container_width=True)

        status = backend_status()
        if not status["ready"]:
            st.markdown(
                '<div class="notice notice-warn">🧪 <b>演示模式</b>：后端核心功能 '
                "（解析 / 断言抽取 / 双通道核查）排期 10/18 后接入，"
                "接口已预留。当前点击后展示 2026-10-14 实测的预置核查结论。</div>",
                unsafe_allow_html=True,
            )
        if uploaded is None:
            st.caption("提示：当前未上传文件也可以运行——演示模式使用构造的研报草稿。")

    # ---------- 右栏：状态机 ----------
    with right:
        st.markdown("#### 📋 核查结论")
        state = st.session_state.get("check_state", "idle")

        if state == "idle":
            st.markdown(
                """
                <div class="empty-state">
                  <div class="big">🧭</div>
                  <div style="font-weight:700;color:#0f2440;margin-bottom:6px;">
                    等待提交核查任务</div>
                  <div style="font-size:0.88rem;">
                    上传研报 PDF → 选择比对年报 → 点击「开始核查」<br>
                    每条结论都将携带：源文件 / 页码 / 原文片段 / 计算过程
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            _render_flow_diagram()

        elif state == "running":
            _run_check(doc_idx)

        else:  # done
            _render_results()

    if run:
        st.session_state["check_state"] = "running"
        st.session_state["check_doc_idx"] = doc_idx
        st.session_state["check_file"] = (
            uploaded.name if uploaded is not None else "DEMO-DRAFT-2025（构造样例）"
        )
        st.rerun()


def _render_flow_diagram() -> None:
    st.markdown("##### 双通道核查流程")
    st.markdown(
        """
        <div class="flow">
          <div class="node"><div class="t">研报 PDF</div><div class="d">断言输入</div></div>
          <div class="arrow">→</div>
          <div class="node"><div class="t">材料解析</div><div class="d">年报逐页文本</div></div>
          <div class="arrow">→</div>
          <div class="node hl"><div class="t">双通道核查</div><div class="d">规则重算 + 语义判定</div></div>
          <div class="arrow">→</div>
          <div class="node"><div class="t">证据链结论</div><div class="d">页码 + 原文 + 计算</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _run_check(doc_idx: int) -> None:
    """演示模式的模拟流程：进度条 + 阶段日志 + 预置结论回放。"""
    progress = st.progress(0, text="准备中…")
    log_box = st.empty()
    logs: list[str] = []

    def on_step(i: int, step: str) -> None:
        logs.append(f"· {step}…")
        log_box.markdown("\n".join(f"`{l}`" for l in logs[-4:]))
        progress.progress((i + 1) / len(CHECK_STEPS), text=f"{step}…")

    simulated_progress(CHECK_STEPS, on_step=on_step)
    progress.progress(1.0, text="完成")

    st.session_state["check_state"] = "done"
    st.session_state["check_logs"] = logs
    time.sleep(0.3)
    st.rerun()


def _render_results() -> None:
    doc_idx = st.session_state.get("check_doc_idx", 0)
    doc = DOC_LIBRARY[doc_idx]
    fname = st.session_state.get("check_file", "DEMO-DRAFT-2025")

    st.markdown(
        f'<div class="notice notice-info">🧪 <b>演示数据回放</b>：以下为 2026-10-14 '
        f"实测的端到端核查结论（工具 <code>tools/demo_e2e.py</code> 可复现）。"
        f"被核查草稿：<b>{fname}</b>（构造样例）；比对材料：<b>{doc['name']}</b>。</div>",
        unsafe_allow_html=True,
    )

    s = DEMO_META["summary"]
    st.markdown(
        f"""
        <div class="chips">
          <span class="chip">断言总数 <b>{s['断言总数']}</b></span>
          <span class="chip">预埋错误 <b>{s['预埋错误']}</b></span>
          <span class="chip">双通道覆盖 <b>{s['双通道合并覆盖']}</b></span>
          <span class="chip">误报 <b>{s['误报']}</b></span>
          <span class="chip">无证据对照 <b>{s['无证据对照组']}</b></span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("")

    # 结论卡片
    for c in DEMO_CLAIMS:
        r, lm = c["rule"], c["llm"]
        v = r["verdict"]
        st.markdown(
            f"""
            <div class="card">
              <div class="card-title">{badge(v)} {badge(r['type'] if r['type'] != '-' else '—')}
                <span style="color:#64748b;font-weight:400;font-size:0.8rem;">{c['id']} · {c['doc']}</span>
              </div>
              <div style="color:#0f2440;margin:4px 0 2px 0;">「{c['quote']}」</div>
              <div class="muted">真实错误类型：{c['gt']} ｜ 规则引擎：{v} ｜ 大模型（带证据）：{lm['verdict']}</div>
              <div class="muted" style="margin-top:2px;">判定依据：{r['reason']}</div>
              <div class="evidence">📄 证据：{c['evidence']}</div>
              {f'<div class="calc">🧮 计算过程：{r["calc"]}</div>' if r.get("calc") else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 导出
    payload = {
        "声明": DEMO_META["disclaimer"],
        "汇总": s,
        "明细": DEMO_CLAIMS,
    }
    st.download_button(
        "⬇️ 导出核查结论（JSON）",
        data=json.dumps(payload, ensure_ascii=False, indent=2),
        file_name="fincheck_demo_findings.json",
        mime="application/json",
    )
    if st.button("↩️ 重新核查"):
        st.session_state["check_state"] = "idle"
        st.rerun()


# ============================================================
# Tab 2：演示与实测
# ============================================================

def render_demo_tab() -> None:
    st.markdown("#### 🧪 端到端核查演示 · 三通道对照")
    st.markdown(
        f'<div class="notice notice-warn">{DEMO_META["disclaimer"]}</div>',
        unsafe_allow_html=True,
    )

    rows = []
    for c in DEMO_CLAIMS:
        rows.append(
            f"<tr><td>{c['id']}</td><td>{c['quote'][:30]}…</td><td>{c['gt']}</td>"
            f"<td>{badge(c['rule']['verdict'])} {c['rule']['type']}</td>"
            f"<td>{badge(c['llm']['verdict'])}</td>"
            f"<td>{badge(c['pure'])}</td>"
            f"<td>{c['rule']['pages']}</td></tr>"
        )
    st.markdown(
        """
        <table class="pretty">
          <tr><th>编号</th><th>研报断言</th><th>真实错误类型</th>
              <th>规则引擎</th><th>大模型（带证据）</th><th>大模型（无证据）</th><th>证据页</th></tr>
        """ + "".join(rows) + "</table>",
        unsafe_allow_html=True,
    )

    st.markdown("")
    st.markdown("##### 🔑 三组关键实测证据")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            """
            <div class="card">
              <div class="card-title">📕 小米年报 408 页文字层损坏</div>
              <div class="muted">415 页中 408 页 CID 编码损坏，双解析器均读出乱码 → 必须 OCR。
              四页实测平均可信度 0.86 / 0.67 / 0.65 / 0.71，<b>全部 &lt; 0.9</b>。</div>
              <div class="muted" style="margin-top:6px;">→ 实证「图像处理只发现可疑，不定罪」的证据分级设计</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div class="card">
              <div class="card-title">🧠 无证据对照组 0 / 6</div>
              <div class="muted">同一模型、同一批断言，不提供原始年报时，
              6 处预埋错误全部答「无法判定」。</div>
              <div class="muted" style="margin-top:6px;">→ 证明有效性来自证据链而非模型本身，
              这是「双通道 + 证据锚定」架构最直接的实验支撑</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            """
            <div class="card">
              <div class="card-title">🐧 腾讯整页底图修正</div>
              <div class="muted">每页附全页扫描底图，初版规则把 138 页误判为图表页；
              引入整页底图标记后修正为 19 页，与平安 9 页量级一致。</div>
              <div class="muted" style="margin-top:6px;">→ 页面分类器用真实信号，不用粗判据</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# Tab 3：技术架构
# ============================================================

def render_arch_tab() -> None:
    st.markdown("#### 🏗 双通道核查架构")
    st.markdown(
        """
        <div class="flow">
          <div class="node"><div class="t">研报 PDF</div><div class="d">断言输入</div></div>
          <div class="arrow">→</div>
          <div class="node"><div class="t">数据接入层</div><div class="d">PDF 双解析器 · 页面分类<br>OCR 挽救 · 页级溯源索引</div></div>
          <div class="arrow">→</div>
          <div class="node hl"><div class="t">确定性通道</div><div class="d">勾稽重算 · 单位校验<br>口径检查 · 估值重算</div></div>
          <div class="node hl"><div class="t">不确定性通道</div><div class="d">大模型语义判定<br>引用真实性核验</div></div>
          <div class="arrow">→</div>
          <div class="node"><div class="t">结论合并</div><div class="d">一致 → 输出 Finding<br>不一致 → 人工复核队列</div></div>
        </div>
        <div class="notice notice-info">🔒 <b>误报控制红线由代码强制</b>：
        数据契约规定 C 级证据（图表反推 / OCR&lt;0.9）禁止输出「确认」结论、
        无证据禁止判定——不依赖人工自觉。</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("##### ⚖️ 证据分级体系")
    st.markdown(
        """
        <table class="pretty">
          <tr><th>等级</th><th>来源</th><th>能否自动判定</th></tr>
          <tr><td><b>A</b></td><td>原生文字层直命中</td><td>✅ 可确认</td></tr>
          <tr><td><b>B</b></td><td>OCR 且置信度 ≥ 0.9（人工抽检）</td><td>✅ 可确认</td></tr>
          <tr><td><b>C</b></td><td>图表像素反推 / OCR 置信度 &lt; 0.9</td><td>❌ 只报疑似，进人工复核队列</td></tr>
        </table>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("##### 🎯 竞赛评分项 ↔ 技术机制")
    st.markdown(
        """
        <table class="pretty">
          <tr><th>评分项</th><th>对应机制</th><th>实测支撑</th></tr>
          <tr><td>错误识别的准确性与覆盖率</td><td>双通道核查 + 八类错误体系</td><td>6/6 覆盖，2 条对照 0 误报</td></tr>
          <tr><td>误报控制</td><td>证据分级 + 不一致进人工复核 + 无证据不判定</td><td>误报 0；OCR 0.65–0.86 置信度实证分级必要</td></tr>
          <tr><td>来源定位</td><td>页级溯源索引 + 证据四元组</td><td>1,067 页全覆盖，可回显页码与原文</td></tr>
          <tr><td>修改建议的可执行性</td><td>diff 式改写建议，契约强制填依据</td><td>数据契约 validate() 强制</td></tr>
        </table>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("##### 🤖 模型选型（OpenAI 兼容协议，切换零代码改动）")
    st.markdown(
        """
        <table class="pretty">
          <tr><th>阶段</th><th>模型</th><th>说明</th></tr>
          <tr><td>开发期</td><td>智谱 GLM-4-Flash</td><td>官方承诺永久免费，128K 上下文</td></tr>
          <tr><td>决赛交付</td><td>DeepSeek deepseek-chat</td><td>国产、128K、中文金融语料稳定</td></tr>
          <tr><td>离线自检</td><td>本地 mock</td><td>零成本验证链路，严禁用于评测与展示</td></tr>
          <tr><td>现场兜底</td><td>本地 Ollama</td><td>决赛断网时降级演示</td></tr>
        </table>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("##### 📜 合规声明")
    st.markdown(
        """
        <div class="notice notice-warn">第三方依赖清单由脚本自动生成（docs/license.md）。
        其中 PyMuPDF 为 AGPL-3.0，使用范围仅限页面渲染，不修改、不再分发其衍生物；
        宽松许可替代品 pypdfium2（Apache-2.0）已就绪，替换工作量约半小时。
        作品运行时推理引擎为通过标准 API 调用的国产大模型，密钥仅存服务端环境变量，
        不依赖任何桌面客户端，评审方可按说明完整复现。</div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# 主入口
# ============================================================

def main() -> None:
    inject_css()
    render_sidebar()

    tab1, tab2, tab3 = st.tabs(["🔍 核查工作台", "🧪 演示与实测", "🏗 技术架构"])
    with tab1:
        render_workbench()
    with tab2:
        render_demo_tab()
    with tab3:
        render_arch_tab()


if __name__ == "__main__":
    main()
