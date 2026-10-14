# -*- coding: utf-8 -*-
"""
src.common —— 公共数据契约与基础设施

本包是全项目的"公共地基"：数据模型、页级溯源索引、统一日志。

依赖方向规则（必须遵守）：
    本包被所有业务模块依赖，自身不依赖任何业务模块。
    反向依赖会造成循环导入，属于架构违规。

owner：A（其中 schema.py 的变更需 A、B 双签）

模块：
    schema.py       数据模型（FinancialFact / Finding / 枚举）—— 已冻结
    trace_index.py  页级溯源索引（每条数据可回溯到原始来源页码）
    logging_util.py 统一日志与 trace.jsonl 写入

字段规范文档：docs/data_spec.md
"""

__all__ = ["schema", "trace_index", "logging_util"]
