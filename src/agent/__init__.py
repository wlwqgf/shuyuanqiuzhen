# -*- coding: utf-8 -*-
"""
src.agent —— 编排与语义层（系统的"大脑"）

职责：不确定性的语义判断与全流程编排。
    · 断言抽取：从材料中抽取待核查的事实性表述
    · 语义核验：数值与原文一致性、表述与数据矛盾、引用真实性
    · 双通道合并：与 rules/ 的确定性结论比对，不一致时进人工复核队列
    · 改写建议生成：输出 diff 式建议（原文 → 建议改为 → 依据 → 影响范围）
    · 可追溯：每次模型调用记录厂商与型号

子模块：
    model_provider.py  大模型调用统一入口（已完成）
    orchestrator.py    主流程编排（待建）
    extractor.py       LLM 断言抽取（待建）
    verifier.py        语义核验与证据分级（待建）

硬性约束：
    1. 业务代码不得出现任何厂商接口地址字符串，一律经 ModelProvider 获取。
    2. 每次模型调用必须把 ModelProvider.info() 写入 trace.jsonl。

owner：A
"""

__all__ = ["model_provider"]
