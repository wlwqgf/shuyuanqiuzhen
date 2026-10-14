# -*- coding: utf-8 -*-
"""
src.eval —— 独立评测框架（系统的"标尺"）

职责：
    · 读取标准答案 bench/gold.json（由 B 独立标注）
    · 读取系统输出 findings.json
    · 计算指标：Precision / Recall / F1 / 误报率 / 来源定位准确率
    · 错例分析：逐条列出误报与漏报，供 B 次日修正规则
    · 消融实验：同一批材料在不同模型（ModelProvider 切换）上的表现对比

⚠ 隔离纪律（防自证循环）：
    标准答案由 B 标注，本框架由 A 实现，**两人独立完成、互不查看对方细节**，
    直到评测跑完。否则会出现"规则写错了、标注也跟着错、评测还给满分"的
    自我循环，评测就失去了意义。

    这条纪律会写进项目计划书，作为方法论严谨性的证据。

owner：A

接口契约（与 B 对齐）：
    bench/gold.json 结构见 docs/data_spec.md 第四节；
    findings.json 的每一条须为 common/schema.py 中的 Finding 对象。
"""

__all__: list[str] = []
