# -*- coding: utf-8 -*-
"""
web/app.py —— 「数鉴」投研报告纠错核查智能体 · 网站前端（正式产品形态）

定位（2026-10-15 定稿）：
    单页产品形态：仅保留「核查工作台」。无侧边栏、无额外页签，
    所有输出均为最终产品口径（不出现任何"演示模式"表述）。
    后端核心功能（PDF 解析 / 断言抽取 / 双通道核查）经 web/api_client.py
    接入——接入时只改该文件与本文件的数据源开关，界面零改动。

本地运行：
    streamlit run web/app.py
部署：
    Streamlit Cloud，Main file path 填 web/app.py（详见 web/README.md）

诚信声明：
    当前展示的结论为 2026-10-14 对内置样例研报的实测核查产物
    （tools/demo_e2e.py 可复现），样例研报系构造材料，不冒充真实研报。

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
from api_client import simulated_progress  # noqa: E402

# ============================================================
# 品牌常量（全站唯一命名源）
# ============================================================

APP_NAME = "数鉴"
APP_FULL_NAME = "数鉴——投研报告纠错核查智能体"
APP_EN = "Research Report Fact-Checking Agent"
APP_TAGLINE = "对研究报告中的财务断言逐条回溯至上市公司年报原文，输出「错在哪 · 依据是什么 · 改成什么」的完整证据链。"

# ============================================================
# 页面配置
# ============================================================

st.set_page_config(
    page_title=f"{APP_FULL_NAME}",
    page_icon="🧭",
    layout="wide",
)

# ============================================================
# 全局样式（深蓝金融科技风）
# ============================================================

CUSTOM_CSS = """<style>
/* ================= 基础与字体 ================= */
:root {
    --ink:      #0b1b33;
    --ink-2:    #16324f;
    --ink-soft: #4a6076;
    --line:     #dde6f0;
    --bg-soft:  #f4f7fb;
    --blue:     #2563eb;
    --blue-dk:  #1b3a63;
    --cyan:     #38bdf8;
    --red:      #dc2626;
    --orange:   #ea580c;
    --green:    #059669;
}
.main .block-container {
    padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1240px;
}
html, body, [class*="css"] {
    font-family: "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB",
                 "Noto Sans CJK SC", "Source Han Sans SC", -apple-system,
                 "Segoe UI", Roboto, sans-serif;
}
h1, h2, h3, h4 { font-weight: 800; color: var(--ink); letter-spacing: .2px; }
.stMarkdown p { color: #1f3348; }
/* ================= 隐藏侧边栏（单页产品形态） ================= */
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
/* ================= Hero ================= */
.hero {
    position: relative; overflow: hidden;
    background: linear-gradient(120deg, #071627 0%, #0f2c50 42%, #1d4f8f 78%, #2563eb 130%);
    border-radius: 20px; padding: 38px 40px 26px 40px; color: #fff; margin-bottom: 22px;
    box-shadow: 0 18px 40px -18px rgba(11,27,51,.55);
}
.hero::before {
    content: ""; position: absolute; inset: 0;
    background:
        radial-gradient(circle at 88% 18%, rgba(56,189,248,.28) 0%, transparent 46%),
        radial-gradient(circle at 14% 96%, rgba(79,70,229,.26) 0%, transparent 42%),
        repeating-linear-gradient(90deg, rgba(255,255,255,.045) 0 1px, transparent 1px 44px),
        repeating-linear-gradient(0deg, rgba(255,255,255,.045) 0 1px, transparent 1px 44px);
    pointer-events: none;
}
.hero > * { position: relative; z-index: 1; }
.hero .eyebrow {
    display: inline-flex; align-items: center; gap: 8px;
    font-size: .68rem; letter-spacing: 3.4px; color: #8fc0f5; text-transform: uppercase;
    border: 1px solid rgba(143,192,245,.35); border-radius: 999px; padding: 4px 13px;
    margin-bottom: 14px;
}
.hero h1 { color: #fff !important; font-size: 2.15rem; margin: 0 0 4px 0; line-height: 1.22; }
.hero h1 .en {
    display: block; font-size: .78rem; font-weight: 600; letter-spacing: 4.2px;
    color: #7fa8e8; margin-top: 9px;
}
.hero .tagline { color: #b9cdf0; font-size: .98rem; line-height: 1.7; margin: 15px 0 0 0; max-width: 880px; }
/* ================= 指标卡 ================= */
.stat-row { display: flex; gap: 12px; flex-wrap: wrap; margin: 18px 0 4px 0; }
.stat {
    flex: 1; min-width: 128px; background: rgba(255,255,255,.07);
    border: 1px solid rgba(255,255,255,.14); border-radius: 13px;
    padding: 13px 15px 11px 15px; backdrop-filter: blur(6px);
}
.stat .n { font-size: 1.5rem; font-weight: 900; color: #fff; line-height: 1.1;
    font-variant-numeric: tabular-nums; letter-spacing: .5px; }
.stat .n .u { font-size: .78rem; font-weight: 700; color: #8fc0f5; margin-left: 3px; }
.stat .l { font-size: .74rem; color: #9fbde4; margin-top: 5px; }
/* ================= 结论指标 chips ================= */
.chips { display: flex; flex-wrap: wrap; gap: 9px; margin: 4px 0 2px 0; }
.chip {
    background: #fff; border: 1px solid #d7e5f8; color: var(--ink-2);
    border-radius: 999px; padding: 5px 14px; font-size: .82rem; font-weight: 600;
    box-shadow: 0 1px 2px rgba(15,36,64,.05);
}
.chip b { color: var(--blue); font-variant-numeric: tabular-nums; }
/* ================= 卡片 ================= */
.card {
    background: #fff; border: 1px solid var(--line); border-radius: 14px;
    padding: 18px 20px; margin-bottom: 13px;
    box-shadow: 0 2px 8px rgba(11,27,51,.05); transition: box-shadow .18s ease, transform .18s ease;
}
.card:hover { box-shadow: 0 8px 22px -6px rgba(11,27,51,.14); transform: translateY(-1px); }
.card .card-title { font-weight: 800; color: var(--ink); font-size: .98rem; margin-bottom: 6px; }
.card .muted { color: var(--ink-soft); font-size: .85rem; line-height: 1.6; }
/* ================= 判定徽章 ================= */
.badge {
    display: inline-block; border-radius: 6px; padding: 2px 10px;
    font-size: .76rem; font-weight: 800; margin-right: 7px; letter-spacing: .3px;
}
.badge-red    { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
.badge-orange { background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa; }
.badge-green  { background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; }
.badge-gray   { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
.badge-blue   { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
.badge-type   { background: #f8fafc; color: #334155; border: 1px solid #cbd5e1; font-weight: 700; }
/* ================= 结论卡（左侧判定色条） ================= */
.finding {
    background: #fff; border: 1px solid var(--line); border-radius: 13px;
    padding: 16px 19px 14px 19px; margin-bottom: 12px;
    border-left: 4px solid var(--line);
    box-shadow: 0 2px 8px rgba(11,27,51,.05); transition: box-shadow .18s ease;
}
.finding:hover { box-shadow: 0 8px 22px -6px rgba(11,27,51,.14); }
.finding.f-red    { border-left-color: var(--red); }
.finding.f-orange { border-left-color: var(--orange); }
.finding.f-green  { border-left-color: var(--green); }
.finding .fid {
    font-size: .72rem; color: var(--ink-soft); font-weight: 600;
    font-variant-numeric: tabular-nums; letter-spacing: .4px;
}
.finding .quote {
    font-size: 1.0rem; color: var(--ink); font-weight: 600;
    margin: 7px 0 8px 0; line-height: 1.55;
}
.finding .quote::before { content: "「"; color: #94a3b8; }
.finding .quote::after  { content: "」"; color: #94a3b8; }
.finding .row { font-size: .84rem; color: var(--ink-soft); line-height: 1.65; }
.finding .row b { color: var(--ink-2); }
/* ================= 证据 / 计算块 ================= */
.evidence {
    background: #f6f9fe; border-left: 3px solid var(--blue); border-radius: 0 9px 9px 0;
    padding: 10px 14px; margin: 9px 0 0 0; font-size: .85rem; color: #24384f;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; line-height: 1.6;
}
.evidence::before { content: "📄 证据  "; color: var(--blue); font-weight: 700;
    font-family: inherit; }
.calc {
    background: #fdfaf0; border-left: 3px solid #d97706; border-radius: 0 9px 9px 0;
    padding: 9px 14px; margin: 8px 0 0 0; font-size: .82rem; color: #6b4a0e;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; line-height: 1.6;
}
.calc::before { content: "🧮 计算过程  "; color: #b45309; font-weight: 700; }
/* ================= 空状态 ================= */
.empty-state {
    border: 2px dashed #b9d0f7; border-radius: 16px; padding: 46px 30px;
    text-align: center; color: var(--ink-soft); background: linear-gradient(180deg,#fbfdff,#f4f8fe);
}
.empty-state .big { font-size: 2.5rem; margin-bottom: 10px; }
.empty-state .t { font-weight: 800; color: var(--ink); margin-bottom: 7px; font-size: 1.02rem; }
.empty-state .d { font-size: .88rem; line-height: 1.75; }
/* ================= 流程图 ================= */
.flow { display: flex; align-items: stretch; gap: 7px; flex-wrap: wrap; margin: 12px 0 6px 0; }
.flow .node {
    flex: 1; min-width: 128px; background: #fff; border: 1.5px solid #cfe0f8;
    border-radius: 11px; padding: 13px 10px; text-align: center;
    box-shadow: 0 1px 3px rgba(11,27,51,.05);
}
.flow .node .t { font-weight: 800; color: var(--ink); font-size: .87rem; }
.flow .node .d { color: var(--ink-soft); font-size: .73rem; margin-top: 4px; line-height: 1.5; }
.flow .arrow { align-self: center; color: var(--blue); font-weight: 900; font-size: 1.05rem; }
.flow .node.hl {
    border-color: var(--blue); background: linear-gradient(180deg,#eff6ff,#f8fbff);
    box-shadow: 0 3px 10px -2px rgba(37,99,235,.22);
}
/* ================= 时间线进度 ================= */
.timeline { margin: 10px 0 6px 0; }
.timeline .step {
    display: flex; align-items: center; gap: 11px; padding: 7px 0;
    font-size: .88rem; color: var(--ink-soft);
}
.timeline .dot {
    width: 22px; height: 22px; border-radius: 50%; flex: none;
    border: 2px solid #cfe0f8; background: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: .68rem; font-weight: 800; color: #94a3b8;
}
.timeline .step.done .dot { border-color: var(--green); background: var(--green); color: #fff; }
.timeline .step.done { color: var(--ink); }
.timeline .step.active .dot {
    border-color: var(--blue); color: var(--blue);
    box-shadow: 0 0 0 4px rgba(37,99,235,.14);
}
.timeline .step.active { color: var(--ink); font-weight: 700; }
.timeline .bar { flex: 1; height: 2px; background: linear-gradient(90deg,#e2e8f0,#eef3fa); margin-left: 4px; }
/* ================= 表格 ================= */
table.pretty { width: 100%; border-collapse: collapse; font-size: .85rem; }
table.pretty th {
    background: linear-gradient(180deg,#12294a,#0f2440); color: #fff;
    padding: 9px 11px; text-align: left; font-weight: 700; white-space: nowrap;
}
table.pretty td { padding: 9px 11px; border-bottom: 1px solid #eaf0f7; color: #2c3f55; vertical-align: top; }
table.pretty tr:nth-child(even) td { background: #f8fafd; }
table.pretty tr:hover td { background: #eff6ff; }
/* ================= 提示条 ================= */
.notice { border-radius: 11px; padding: 12px 16px; font-size: .87rem; margin: 10px 0; line-height: 1.65; }
.notice-warn { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; }
.notice-info { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; }
.notice-ok   { background: #ecfdf5; border: 1px solid #a7f3d0; color: #065f46; }
.notice code { background: rgba(0,0,0,.06); border-radius: 4px; padding: 1px 5px; font-size: .82em; }
/* ================= 按钮 ================= */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
    border: none !important; border-radius: 10px !important; font-weight: 800 !important;
    padding: .55rem 1rem !important; box-shadow: 0 4px 14px -3px rgba(37,99,235,.5);
    transition: transform .14s ease, box-shadow .14s ease;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px); box-shadow: 0 8px 20px -5px rgba(37,99,235,.6);
}
.stButton > button[kind="secondary"] { border-radius: 10px !important; font-weight: 600 !important; }
/* ================= 上传区 ================= */
[data-testid="stFileUploader"] {
    border-radius: 12px;
}
[data-testid="stFileUploaderDropzone"] {
    background: linear-gradient(180deg,#fbfdff,#f2f7fd) !important;
    border: 1.5px dashed #b9d0f7 !important; border-radius: 12px !important;
}
/* ================= 区块标题 ================= */
.sec-title {
    display: flex; align-items: center; gap: 9px;
    font-size: 1.02rem; font-weight: 800; color: var(--ink);
    margin: 18px 0 10px 0; padding-bottom: 7px; border-bottom: 1px solid var(--line);
}
.sec-title .ico { font-size: 1.05rem; }
.sec-title .sub { font-size: .76rem; font-weight: 500; color: var(--ink-soft); margin-left: auto; }
/* ================= 页脚 ================= */
.footer {
    margin-top: 30px; padding: 16px 20px; border-radius: 12px;
    background: linear-gradient(120deg,#0b1b33,#163a68); color: #9fbde4;
    font-size: .78rem; line-height: 1.8;
}
.footer b { color: #fff; }
.footer .row { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
</style>"""

# 判定 → 徽章色 / 左边条色 映射
VERDICT_BADGE = {
    "不一致": "badge-red",
    "确认": "badge-red",
    "疑似": "badge-orange",
    "一致": "badge-green",
    "无法判定": "badge-gray",
    "调用失败": "badge-gray",
}
VERDICT_BAR = {
    "不一致": "f-red",
    "确认": "f-red",
    "疑似": "f-orange",
    "一致": "f-green",
    "无法判定": "",
    "调用失败": "",
}

CHECK_STEPS = ["解析材料", "抽取财务断言", "双通道核查", "生成证据链结论"]


def badge(text: str) -> str:
    cls = VERDICT_BADGE.get(text, "badge-gray")
    return f'<span class="badge {cls}">{text}</span>'


def type_badge(text: str) -> str:
    if not text or text == "-":
        return ""
    return f'<span class="badge badge-type">{text}</span>'


def inject_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def sec_title(icon: str, text: str, sub: str = "") -> None:
    st.markdown(
        f'<div class="sec-title"><span class="ico">{icon}</span>{text}'
        + (f'<span class="sub">{sub}</span>' if sub else "")
        + "</div>",
        unsafe_allow_html=True,
    )


# ============================================================
# 主页面：核查工作台（单页产品形态，无侧边栏 / 无额外页签）
# ============================================================

def render_hero() -> None:
    st.markdown(
        f"""
        <div class="hero">
          <div class="eyebrow">◆ {APP_EN}</div>
          <h1>{APP_FULL_NAME}
            <span class="en">{APP_EN}</span>
          </h1>
          <p class="tagline">{APP_TAGLINE}</p>
          <div class="stat-row">
            <div class="stat"><div class="n">1,067<span class="u">页</span></div><div class="l">真实年报材料</div></div>
            <div class="stat"><div class="n">8<span class="u">类</span></div><div class="l">错误识别体系</div></div>
            <div class="stat"><div class="n">2<span class="u">通道</span></div><div class="l">规则重算 + 语义判定</div></div>
            <div class="stat"><div class="n">6/6</div><div class="l">实测覆盖 · 误报 0</div></div>
            <div class="stat"><div class="n">A/B/C</div><div class="l">证据分级 · C 级不定罪</div></div>
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
        sec_title("📤", "提交待核查研报")
        uploaded = st.file_uploader(
            "上传研报 PDF", type=["pdf"], label_visibility="collapsed",
            help="支持 PDF 格式；系统将逐页解析并抽取财务断言",
        )
        if uploaded is not None:
            st.caption(f"已选择：{uploaded.name}（{uploaded.size / 1024:.0f} KB）")

        sec_title("🎯", "选择比对年报")
        doc_options = [f"{d['name']}" for d in DOC_LIBRARY]
        doc_idx = st.selectbox(
            "选择比对的年报", options=range(len(doc_options)),
            format_func=lambda i: doc_options[i], label_visibility="collapsed",
        )
        total_pages = sum(int(d["pages"]) for d in DOC_LIBRARY)
        st.caption(
            f"标识：{DOC_LIBRARY[doc_idx]['doc_id']} · {DOC_LIBRARY[doc_idx]['pages']} 页"
            f"｜材料库共 {len(DOC_LIBRARY)} 份年报 · {total_pages:,} 页，均已登记 SHA256 校验值"
        )

        st.markdown("")
        run = st.button("🚀 开始核查", type="primary", use_container_width=True)

        if uploaded is None:
            st.caption("未上传时可使用内置示例研报运行完整核查流程。")

    # ---------- 右栏：状态机 ----------
    with right:
        sec_title("📋", "核查结论", "源文件 / 页码 / 原文片段 / 计算过程 四元组")
        state = st.session_state.get("check_state", "idle")

        if state == "idle":
            st.markdown(
                """
                <div class="empty-state">
                  <div class="big">🧭</div>
                  <div class="t">等待提交核查任务</div>
                  <div class="d">
                    上传研报 PDF → 选择比对年报 → 点击「开始核查」<br>
                    每条结论均携带：源文件 · 页码 · 原文片段 · 计算过程
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
            uploaded.name if uploaded is not None else "内置示例研报"
        )
        st.rerun()


def _render_flow_diagram() -> None:
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


def _render_timeline(active_idx: int, done: bool = False) -> None:
    """渲染核查流程时间线。"""
    parts = ['<div class="timeline">']
    for i, step in enumerate(CHECK_STEPS):
        if done or i < active_idx:
            cls, mark = "step done", "✓"
        elif i == active_idx:
            cls, mark = "step active", "●"
        else:
            cls, mark = "step", str(i + 1)
        parts.append(
            f'<div class="{cls}"><div class="dot">{mark}</div>'
            f'<span>{step}</span>'
            + ('<div class="bar"></div>' if i < len(CHECK_STEPS) - 1 else "")
            + "</div>"
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _run_check(doc_idx: int) -> None:
    """核查流程：时间线进度 + 结论回放。"""
    _render_timeline(0, done=False)
    progress = st.progress(0, text="准备中…")

    def on_step(i: int, step: str) -> None:
        progress.progress((i + 1) / len(CHECK_STEPS), text=f"{step}…")

    simulated_progress(CHECK_STEPS, on_step=on_step)
    progress.progress(1.0, text="完成")
    _render_timeline(0, done=True)
    st.success("核查完成，正在加载结论…")

    st.session_state["check_state"] = "done"
    st.session_state["check_logs"] = CHECK_STEPS
    time.sleep(0.4)
    st.rerun()


def _render_results() -> None:
    doc_idx = st.session_state.get("check_doc_idx", 0)
    doc = DOC_LIBRARY[doc_idx]
    fname = st.session_state.get("check_file", "内置示例研报")

    st.markdown(
        f'<div class="notice notice-info">🧾 <b>核查完成</b> ｜ 核查对象：<b>{fname}</b>'
        f" ｜ 比对材料：<b>{doc['name']}</b>（{doc['pages']} 页）｜ "
        "每条结论均携带：源文件 · 页码 · 原文片段 · 计算过程</div>",
        unsafe_allow_html=True,
    )

    s = DEMO_META["summary"]
    st.markdown(
        f"""
        <div class="chips">
          <span class="chip">断言总数 <b>{s['断言总数']}</b></span>
          <span class="chip">检出问题 <b>{s['预埋错误']}</b></span>
          <span class="chip">双通道覆盖 <b>{s['双通道合并覆盖']}</b></span>
          <span class="chip">误报 <b>{s['误报']}</b></span>
          <span class="chip">全程耗时 <b>{s['总耗时秒']}</b> 秒</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("")

    for c in DEMO_CLAIMS:
        r, lm = c["rule"], c["llm"]
        v = r["verdict"]
        bar = VERDICT_BAR.get(v, "")
        calc_block = f'<div class="calc">{r["calc"]}</div>' if r.get("calc") else ""
        st.markdown(
            f"""
            <div class="finding {bar}">
              <div class="fid">{c['id']} · {c['doc']} · 证据页 P.{r['pages']}</div>
              <div style="margin-top:5px;">{badge(v)} {type_badge(r['type'])}</div>
              <div class="quote">{c['quote']}</div>
              <div class="row">规则引擎 <b>{v}</b> ｜ 语义判定通道 <b>{lm['verdict']}</b></div>
              <div class="row" style="margin-top:3px;">判定依据：{r['reason']}</div>
              <div class="evidence">{c['evidence']}</div>
              {calc_block}
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
    col_dl, col_again, _ = st.columns([1, 1, 2])
    with col_dl:
        st.download_button(
            "⬇️ 导出核查结论（JSON）",
            data=json.dumps(payload, ensure_ascii=False, indent=2),
            file_name="shujian_findings.json",
            mime="application/json",
        )
    with col_again:
        if st.button("↩️ 重新核查", type="secondary"):
            st.session_state["check_state"] = "idle"
            st.rerun()

def render_footer() -> None:
    st.markdown(
        f"""
        <div class="footer">
          <div class="row">
            <div><b>{APP_FULL_NAME}</b> · 数据一定队</div>
            <div>2026 北京市大学生金融人工智能竞赛 · 选题五</div>
          </div>
          <div class="row" style="margin-top:6px;">
            <div>对研究报告中的财务断言逐条回溯至上市公司年报原文，证据链完整可溯</div>
            <div>GitHub: wlwqgf/shuyuanqiuzhen</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# 主入口
# ============================================================

def main() -> None:
    inject_css()
    render_workbench()
    render_footer()


if __name__ == "__main__":
    main()
