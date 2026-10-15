# -*- coding: utf-8 -*-
"""
web/app.py —— 「数鉴」投研报告纠错核查智能体 · 网站前端

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
    initial_sidebar_state="expanded",
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
/* ================= 侧边栏 ================= */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b1b33 0%, #12294a 55%, #163a68 100%);
    border-right: 1px solid rgba(255,255,255,.06);
}
section[data-testid="stSidebar"] > div { padding-top: 1.4rem; }
section[data-testid="stSidebar"] * { color: #c8d8ee !important; }
section[data-testid="stSidebar"] .stMarkdown { color: #c8d8ee; }
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.12); margin: .9rem 0; }
.brand {
    display: flex; align-items: center; gap: 12px; padding: 2px 4px 10px 4px;
}
.brand .mark {
    width: 42px; height: 42px; border-radius: 11px; flex: none;
    background: linear-gradient(135deg, #38bdf8 0%, #2563eb 60%, #4f46e5 100%);
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; font-weight: 900; color: #fff;
    box-shadow: 0 6px 16px rgba(37,99,235,.45);
}
.brand .nm { font-size: 1.28rem; font-weight: 900; color: #fff !important; letter-spacing: 1px; }
.brand .nm small { display: block; font-size: .62rem; font-weight: 500;
    letter-spacing: 2.4px; color: #7fa8e8 !important; margin-top: 2px; }
.sb-block {
    background: rgba(255,255,255,.055); border: 1px solid rgba(255,255,255,.09);
    border-radius: 11px; padding: 11px 13px; margin: 6px 0 12px 0;
}
.sb-block .k { font-size: .68rem; letter-spacing: 1.6px; color: #7fa8e8 !important;
    text-transform: uppercase; margin-bottom: 5px; }
.sb-block .v { font-size: .84rem; line-height: 1.55; }
.pill {
    display: inline-flex; align-items: center; gap: 6px;
    border-radius: 999px; padding: 3px 11px; font-size: .74rem; font-weight: 700;
}
.pill-demo  { background: rgba(234,88,12,.18); color: #fdba74 !important; border: 1px solid rgba(234,88,12,.4); }
.pill-live  { background: rgba(5,150,105,.18); color: #6ee7b7 !important; border: 1px solid rgba(5,150,105,.4); }
.sb-doc {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 7px 10px; border-radius: 8px; margin-bottom: 4px;
    background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.06);
}
.sb-doc .n { font-size: .8rem; }
.sb-doc .p { font-size: .72rem; color: #7fa8e8 !important; font-variant-numeric: tabular-nums; }
/* ================= 自绘页签 ================= */
div[data-baseweb="tab-list"] {
    gap: 6px; background: transparent; border-bottom: 1px solid var(--line);
    padding-bottom: 0;
}
button[data-baseweb="tab"] {
    background: var(--bg-soft) !important; border: 1px solid var(--line) !important;
    border-bottom: none !important; border-radius: 10px 10px 0 0 !important;
    padding: 9px 20px !important; font-weight: 700 !important; color: var(--ink-soft) !important;
    font-size: .9rem !important; transition: all .16s ease;
}
button[data-baseweb="tab"]:hover { background: #e8f0fe !important; color: var(--blue) !important; }
button[data-baseweb="tab"][aria-selected="true"] {
    background: linear-gradient(180deg, #ffffff 0%, #eef4ff 100%) !important;
    color: var(--blue-dk) !important; border-color: #b9d0f7 !important;
    box-shadow: inset 0 3px 0 var(--blue);
}
div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] { display: none !important; }
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

CHANNEL_LABEL = {"rule": "规则引擎", "llm": "大模型（带证据）", "pure": "大模型（无证据）"}

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
# 侧边栏
# ============================================================

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            f"""
            <div class="brand">
              <div class="mark">鉴</div>
              <div class="nm">{APP_NAME}<small>{APP_EN.upper()}</small></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        status = backend_status()
        if status["ready"]:
            st.markdown('<span class="pill pill-live">● 后端已接入</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="pill pill-demo">● 演示模式</span>', unsafe_allow_html=True)
            st.caption(status["message"])

        st.divider()
        st.markdown("**🤖 模型档案**（后端接入后生效）")
        st.selectbox(
            "选择档案",
            options=["glm · 智谱 GLM-4-Flash（免费）", "deepseek · 决赛主力", "mock · 离线自检"],
            index=0,
            label_visibility="collapsed",
        )
        st.caption("密钥仅存于服务端环境变量，不在前端出现。")

        st.divider()
        st.markdown("**📚 材料库**")
        for d in DOC_LIBRARY:
            st.markdown(
                f'<div class="sb-doc"><span class="n">{d["name"]}</span>'
                f'<span class="p">{d["pages"]} 页</span></div>',
                unsafe_allow_html=True,
            )

        st.divider()
        st.markdown(
            f"""
            <div class="sb-block">
              <div class="k">About</div>
              <div class="v"><b style="color:#fff">数据一定队</b> · 2026 北京市大学生<br>
              金融人工智能竞赛 · 选题五<br>
              敖潇文 / 梅睿涵 / 马可</div>
            </div>
            <div style="font-size:.7rem;color:#5f7ea8;line-height:1.7;">
              演示数据为 2026-10-14 实测，构造样例已标注
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# Tab 1：核查工作台
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
            help="后端接入后支持解析；当前演示模式展示预置结论",
        )
        if uploaded is not None:
            st.caption(f"已选择：{uploaded.name}（{uploaded.size / 1024:.0f} KB）")

        sec_title("🎯", "选择比对年报")
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
                "（解析 / 断言抽取 / 双通道核查）排期 10/18 后接入，接口已预留。"
                "当前点击后展示 2026-10-14 实测的预置核查结论。</div>",
                unsafe_allow_html=True,
            )
        if uploaded is None:
            st.caption("提示：未上传文件也可运行——演示模式使用构造的研报草稿。")

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
            uploaded.name if uploaded is not None else "DEMO-DRAFT-2025（构造样例）"
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
    """演示模式的模拟流程：时间线进度 + 预置结论回放。"""
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
    fname = st.session_state.get("check_file", "DEMO-DRAFT-2025")

    st.markdown(
        f'<div class="notice notice-info">🧪 <b>演示数据回放</b>：以下为 2026-10-14 '
        f"实测的端到端核查结论（工具 <code>tools/demo_e2e.py</code> 可复现）。"
        f"被核查草稿：<b>{fname}</b>（构造样例）｜ 比对材料：<b>{doc['name']}</b></div>",
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
              <div class="row">真实错误类型 <b>{c['gt']}</b> ｜ 规则引擎 <b>{v}</b> ｜ 大模型（带证据） <b>{lm['verdict']}</b></div>
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
            file_name="shujian_demo_findings.json",
            mime="application/json",
        )
    with col_again:
        if st.button("↩️ 重新核查", type="secondary"):
            st.session_state["check_state"] = "idle"
            st.rerun()


# ============================================================
# Tab 2：演示与实测
# ============================================================

def render_demo_tab() -> None:
    sec_title("🧪", "端到端核查演示 · 三通道对照", "2026-10-14 实测")
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
            f"<td>P.{c['rule']['pages']}</td></tr>"
        )
    st.markdown(
        """
        <table class="pretty">
          <tr><th>编号</th><th>研报断言</th><th>真实错误类型</th>
              <th>规则引擎</th><th>大模型（带证据）</th><th>大模型（无证据）</th><th>证据页</th></tr>
        """ + "".join(rows) + "</table>",
        unsafe_allow_html=True,
    )

    sec_title("🔑", "三组关键实测证据")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            """
            <div class="card">
              <div class="card-title">📕 小米年报 408 页文字层损坏</div>
              <div class="muted">415 页中 408 页 CID 编码损坏，双解析器均读出乱码 → 必须 OCR。
              四页实测平均可信度 <b>0.86 / 0.67 / 0.65 / 0.71</b>，全部 &lt; 0.9。</div>
              <div class="muted" style="margin-top:7px;">→ 实证「图像处理只发现可疑，不定罪」的证据分级设计</div>
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
              <div class="muted" style="margin-top:7px;">→ 证明有效性来自证据链而非模型本身，
              是「双通道 + 证据锚定」架构最直接的实验支撑</div>
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
              <div class="muted" style="margin-top:7px;">→ 页面分类器用真实信号，不用粗判据</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# Tab 3：技术架构
# ============================================================

def render_arch_tab() -> None:
    sec_title("🏗", "双通道核查架构")
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

    sec_title("⚖️", "证据分级体系")
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

    sec_title("🎯", "竞赛评分项 ↔ 技术机制")
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

    sec_title("🤖", "模型选型", "OpenAI 兼容协议 · 切换零代码改动")
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

    sec_title("📜", "合规声明")
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


def render_footer() -> None:
    st.markdown(
        f"""
        <div class="footer">
          <div class="row">
            <div><b>{APP_FULL_NAME}</b> · 数据一定队</div>
            <div>2026 北京市大学生金融人工智能竞赛 · 选题五</div>
          </div>
          <div class="row" style="margin-top:6px;">
            <div>演示数据为 2026-10-14 实测产物，研报草稿系构造样例，不冒充真实研报</div>
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
    render_sidebar()

    tab1, tab2, tab3 = st.tabs(["🔍 核查工作台", "🧪 演示与实测", "🏗 技术架构"])
    with tab1:
        render_workbench()
    with tab2:
        render_demo_tab()
    with tab3:
        render_arch_tab()

    render_footer()


if __name__ == "__main__":
    main()
