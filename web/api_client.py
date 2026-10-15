# -*- coding: utf-8 -*-
"""
web/api_client.py —— 后端 API 客户端（预留接口，当前为桩实现）

背景：
    按 10/14 调整后的分工，10/18 前只完成网站前端；智能体核心功能
    （PDF 解析、断言抽取、双通道核查）在 10/18 后接入。本模块把
    "前端需要调用的全部后端能力"以函数签名形式固定下来——

    **后端接入 = 只改本文件内的实现 + 翻转 DATA_SOURCE 开关，
    前端 app.py 零改动。**

接口约定（与 src/common/schema.py 数据契约对齐）：
    submit_check()  提交一份待核查研报，返回任务 ID
    poll_task()     轮询任务状态与进度
    get_findings()  拉取结构化核查结论（Finding 列表）
    get_docs()      拉取材料库列表

部署形态（后端接入时的目标架构，二选一）：
    A. FastAPI/Flask 独立服务：本客户端走 HTTP；
    B. Streamlit 同进程直连：把桩实现替换为 src/agent/pipeline.py 的
       直接调用（开发期最简路径）。

合规约束：
    · API 密钥只允许出现在服务端环境变量 / Streamlit secrets，
      严禁写入本文件或任何前端代码；
    · 所有函数必须能对"后端未接入"状态给出明确信号
      （返回 NOT_IMPLEMENTED 或抛出 BackendNotReady），
      不允许静默返回空数据——空数据会被误读成"研报没有错误"。

归属：A（队长 · 语义与编排层）
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

# 数据源开关：builtin = 前端内置核查结论；api = 真实后端（接入后启用）
DATA_SOURCE = "builtin"

# 任务状态机（与后端约定一致）
TASK_STATUS = {
    "PENDING": "排队中",
    "PARSING": "解析材料",
    "EXTRACTING": "抽取断言",
    "CHECKING": "双通道核查",
    "DONE": "完成",
    "FAILED": "失败",
    "NOT_IMPLEMENTED": "后端未接入",
}


class BackendNotReady(RuntimeError):
    """后端核心功能尚未接入。前端据此展示明确提示，不静默降级。"""


def _not_ready(api: str) -> None:
    raise BackendNotReady(
        f"{api} 尚未接入：后端核心功能排期在 10/18 之后。"
        f"当前 DATA_SOURCE='builtin'，网站展示内置核查结论。"
    )


# ============ 预留接口（桩实现） ============

def submit_check(pdf_bytes: bytes, filename: str,
                 target_doc_id: str, profile: str = "glm") -> Dict[str, Any]:
    """提交待核查研报。

    参数：
        pdf_bytes     ：研报 PDF 二进制内容
        filename      ：原始文件名（留痕，写入任务记录）
        target_doc_id ：比对的年报标识（见 docs/data_spec.md 命名规则）
        profile       ：模型档案（glm / deepseek / mock）

    返回（接入后）：
        {"task_id": "...", "status": "PENDING", "submitted_at": "ISO8601"}

    当前：抛出 BackendNotReady。
    """
    _not_ready("submit_check")


def poll_task(task_id: str) -> Dict[str, Any]:
    """轮询任务进度。

    返回（接入后）：
        {"task_id": "...", "status": "CHECKING", "progress": 0.6,
         "message": "正在核查第 12/20 条断言…"}

    当前：抛出 BackendNotReady。
    """
    _not_ready("poll_task")


def get_findings(task_id: str) -> List[Dict[str, Any]]:
    """拉取结构化核查结论。

    返回（接入后）：
        Finding 对象列表的 dict 形式（schema.py 的 to_dict() 输出），
        字段含 error_type / status / evidence_level / evidences 等。

    当前：抛出 BackendNotReady。
    """
    _not_ready("get_findings")


def get_docs() -> List[Dict[str, str]]:
    """拉取材料库列表（doc_id / 名称 / 页数 / 备注）。

    当前：抛出 BackendNotReady；前端改用 web/demo_data.py
    的 DOC_LIBRARY 常量。
    """
    _not_ready("get_docs")


# ============ 接入检查（供界面显示后端状态） ============

def backend_status() -> Dict[str, Any]:
    """返回后端就绪状态，前端据此渲染状态徽标。"""
    return {
        "data_source": DATA_SOURCE,
        "ready": DATA_SOURCE == "api",
        "message": (
            "内置核查结论（2026-10-14 实测）"
            if DATA_SOURCE == "builtin"
            else "实时后端核查"
        ),
    }


def simulated_progress(steps: List[str], on_step=None) -> List[str]:
    """内置结论模式下的流程进度（不产生新结论，仅呈现核查阶段）。

    steps：阶段名列表；on_step：回调 (index, step_name)。
    返回steps 原样。真实接入后由 poll_task 替代。
    """
    logs: List[str] = []
    for i, s in enumerate(steps):
        if on_step:
            on_step(i, s)
        logs.append(s)
        time.sleep(0.4)  # 仅流程节奏，无实际计算
    return logs
