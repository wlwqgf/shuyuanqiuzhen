# 数据字段规范

> 归属：A（队长 · 语义与编排层）｜ 建档：2026-10-13 ｜ 冻结状态：**已冻结**（2026-10-13 12:00 起）
> 实现文件：`src/common/schema.py`（本规范的可执行版本）
>
> **变更纪律**：本规范冻结后，任何字段的增删改须由 A、B 双方确认（双签），
> 并同步更新本文件与 `schema.py`。变更前须在 `git log` 中留下记录。

---

## 一、文档标识（doc_id）命名规则

`doc_id` 是全系统引用一份材料的唯一标识，出现在每一条事实与证据中。命名必须稳定、唯一、可读。

| 材料类型 | 命名格式 | 示例 |
|---|---|---|
| 上市公司年报 | `{主体代码}-AR-{年份}` | `XYZZ-AR-2024` |
| 上市公司季报 | `{主体代码}-Q{N}-{年份}` | `XYZZ-Q3-2024` |
| 上市公司公告 | `{主体代码}-ANN-{日期}` | `XYZZ-ANN-20241220` |
| 券商研报草稿 | `RPT-{序号:03d}` | `RPT-001` |
| 合成测试样本 | `SAMPLE-{类型}-{年份}` | `SAMPLE-AR-2024` |

**规则**：
1. `主体代码` 使用公司中文简称的拼音首字母，不超过 6 位。
2. 每份材料在 `data/raw/SOURCES.md` 登记后，`doc_id` 即固定，不得事后更改。
3. **合成样本的 `doc_id` 必须以 `SAMPLE-` 开头**，确保在日志与报告中一眼可辨，杜绝合成数据与真实数据混淆。

---

## 二、指标名称受控词表（metric_name）

`metric_name` 必须取自下表，不得自由命名。自由命名会导致同义指标无法比对（"净利润"与"归母净利润"是两个不同指标）。

| 类别 | 受控名称 | 单位 | 期间类型 |
|---|---|---|---|
| 损益 | 营业收入 | 元 | 期间数 |
| 损益 | 营业成本 | 元 | 期间数 |
| 损益 | 毛利 | 元 | 期间数 |
| 损益 | 毛利率 | % | 期间数 |
| 损益 | 归属于上市公司股东的净利润 | 元 | 期间数 |
| 损益 | 扣除非经常性损益后的净利润 | 元 | 期间数 |
| 损益 | 研发费用 | 元 | 期间数 |
| 损益 | 销售费用 | 元 | 期间数 |
| 损益 | 管理费用 | 元 | 期间数 |
| 资产负债 | 总资产 | 元 | 时点数 |
| 资产负债 | 总负债 | 元 | 时点数 |
| 资产负债 | 归属于上市公司股东的净资产 | 元 | 时点数 |
| 现金流 | 经营活动产生的现金流量净额 | 元 | 期间数 |
| 每股 | 基本每股收益 | 元/股 | 期间数 |
| 每股 | 稀释每股收益 | 元/股 | 期间数 |
| 回报 | 加权平均净资产收益率 | % | 期间数 |
| 回报 | 总资产报酬率 | % | 期间数 |
| 估值 | 市盈率 | 倍 | 时点数 |
| 估值 | 市净率 | 倍 | 时点数 |
| 估值 | 市销率 | 倍 | 时点数 |
| 估值 | 企业价值倍数 | 倍 | 时点数 |
| 分项 | 分产品营业收入 | 元 | 期间数 |
| 增长率 | 营业收入同比增长率 | % | 期间数 |
| 增长率 | 净利润同比增长率 | % | 期间数 |

**扩展流程**：需要新指标时，先在本表登记，再在代码中引用。词表本身也是评测集的标注依据——B 在标注 `gold.json` 时同样使用这些名称。

---

## 三、FinancialFact 字段规范（解析层产出：一条财务事实）

| 字段名 | 类型 | 含义 | 必填 | 取值域 / 示例 |
|---|---|---|---|---|
| `fact_id` | str | 事实唯一标识 | **是** | `SAMPLE-AR-2024-p2-001` |
| `doc_id` | str | 来源文件标识 | **是** | `SAMPLE-AR-2024` |
| `page_no` | int | 来源页码（从 1 开始） | **是** | `2` |
| `metric_name` | str | 指标名称 | **是** | 取自第二节受控词表 |
| `value_raw` | str | 原文形态数值 | **是** | `1,240,358,902.35` |
| `entity` | str | 主体名称 | 否 | `星野智造股份有限公司` |
| `value_num` | float \| null | 数值化结果 | 否（强烈建议） | `1240358902.35` |
| `unit` | str | 单位 | 否（默认 `元`） | `元` / `万元` / `亿元` / `%` / `元/股` / `倍` |
| `currency` | str | 币种 | 否（默认 `CNY`） | `CNY` / `HKD` / `USD` |
| `period` | str | 期间 | 否 | `2024` / `2024Q3` / `2024-12-31` |
| `period_type` | 枚举 | 期间类型 | 否（默认 `point_in_time`） | `annual` / `quarterly` / `half_year` / `ttm` / `point_in_time` |
| `basis` | 枚举 | 报表口径 | 否（默认 `未标注`） | `合并` / `母公司` / `未标注` |
| `accounting_standard` | 枚举 | 会计准则 | 否（默认 `未标注`） | `中国企业会计准则` / `国际财务报告准则` / `美国公认会计原则` / `未标注` |
| `statement` | str | 所属报表 | 否 | `合并利润表` |
| `section` | str | 所属章节 | 否 | `第三节 经营情况讨论与分析` |
| `char_start` | int | 全文中的字符起始偏移 | 否（-1 表示未记录） | `1024` |
| `char_end` | int | 字符结束偏移（不含） | 否 | `1054` |
| `evidence_text` | str | 该事实所在原文句段 | 否 | `营业收入（元） 1,240,358,902.35` |
| `evidence_level` | 枚举 | 证据等级 | 否（默认 `A`） | `A` / `B` / `C` |
| `extract_method` | 枚举 | 抽取方式 | 否（默认 `text_layer`） | `text_layer` / `table_parser` / `ocr` / `chart_reverse` / `manual` |
| `confidence` | float | 抽取置信度 | 否（默认 `1.0`） | 0.0 ~ 1.0 |
| `table_ref` | str | 表格位置 | 否 | `page2/table1/row1` |
| `truncated` | bool | **疑似截断标记** | 否（默认 `false`） | 见第六节 |
| `created_at` | str | 生成时间（ISO 8601） | 否（自动填充） | `2026-10-14T08:55:02+08:00` |

### 关键字段说明

**`value_raw` 与 `value_num` 为什么都要保留**：`value_raw` 保留原文写法（千分位、单位后缀），用于向用户展示"原文是怎么写的"；`value_num` 用于计算比对。两者不一致本身就是一个信号。

**`basis`（报表口径）为什么必须显式声明**：同一公司在同一时点，合并报表与母公司报表的总资产、净资产数值不同。若不声明口径就做比对，会把"口径差异"误判为"数值错误"——这是 E3 类错误的主要来源，也是误报的高发区。

---

## 四、Finding 字段规范（核查结论：系统对外交付的核心单元）

| 字段名 | 类型 | 含义 | 必填 | 取值域 / 示例 |
|---|---|---|---|---|
| `finding_id` | str | 结论唯一标识 | **是** | `F-0001` |
| `target_doc_id` | str | 被核查草稿的文件标识 | **是** | `RPT-001` |
| `target_page` | int | 草稿中出现问题的页码 | **是** | `1` |
| `error_type` | 枚举 | 错误类型 | **是** | `E1`~`E7` |
| `status` | 枚举 | 结论状态 | **是** | `confirmed` / `suspect` / `pending` / `rejected` |
| `evidence_level` | 枚举 | 支撑本结论的最高证据等级 | **是** | `A` / `B` / `C` |
| `target_quote` | str | 草稿中的原文片段 | 否（强烈建议） | `公司总资产达 385.62 亿元` |
| `target_char_start` | int | 草稿中的字符起始偏移 | 否 | `-1` |
| `target_char_end` | int | 草稿中的字符结束偏移 | 否 | `-1` |
| `severity` | 枚举 | 严重程度 | 否（默认 `medium`） | `high` / `medium` / `low` |
| `claim_value` | str | 草稿中的值（原文形态） | 否 | `385.62 亿元` |
| `correct_value` | str | 正确值 | 否 | `38.56 亿元` |
| `unit` | str | 相关单位 | 否 | `亿元` |
| `delta` | str | 差异描述 | 否 | `单位错误，虚增 10 倍` |
| `reason` | str | 判定理由（面向评审的可读说明） | 否（强烈建议） | 见示例 |
| `evidences` | list[Evidence] | 证据列表 | **是（至少 1 条）** | 见第五节 |
| `rule_id` | str | 命中的规则编号 | 否 | `R-UNIT-001` |
| `channel` | 枚举 | 判定通道 | 否（默认 `rule`） | `rule` / `llm` / `hybrid` |
| `model_info` | dict | 模型身份（经 LLM 判定时必填） | 条件必填 | `{"vendor": "深度求索 DeepSeek", "model": "deepseek-chat"}` |
| `suggestion_original` | str | 改写建议·原文 | 否 | 同上 |
| `suggestion_revised` | str | 改写建议·建议改为 | 条件必填（confirmed 时） | `公司总资产达 38.56 亿元，资产结构稳健` |
| `suggestion_basis` | str | 改写建议·依据 | 条件必填（confirmed 时） | `年报合并资产负债表：总资产 3,856,209,744.60 元` |
| `suggestion_impact` | str | 改写建议·影响范围 | 否 | `影响资产规模表述，不影响结论方向` |
| `review_status` | 枚举 | 人工复核状态 | 否（默认 `not_reviewed`） | `not_reviewed` / `approved` / `rejected` / `escalated` |
| `reviewer` | str | 复核人 | 否 | `B` |
| `review_note` | str | 复核备注 | 否 | |
| `run_id` | str | 本次运行标识 | 否 | `20261014-0853` |
| `created_at` | str | 生成时间 | 否（自动填充） | |

### 条件必填规则（由 `Finding.validate()` 强制）

| 条件 | 要求 |
|---|---|
| 任何结论 | `evidences` 至少一条，且每条含非空 `quote` |
| `status = confirmed` | `evidence_level` 不得为 `C`；`suggestion_revised` 与 `suggestion_basis` 不得为空 |
| `channel` 为 `llm` 或 `hybrid` | `model_info` 不得为空 |
| 任何结论 | `claim_value` 与 `correct_value` 不能同时为空 |

---

## 五、Evidence 字段规范（证据四元组）

| 字段名 | 类型 | 含义 | 必填 | 取值域 / 示例 |
|---|---|---|---|---|
| `doc_id` | str | 源文件标识 | **是** | `SAMPLE-AR-2024` |
| `page_no` | int | 页码（≥1） | **是** | `2` |
| `quote` | str | 原文片段（逐字摘录，不得改写） | **是** | `总资产（元） 3,856,209,744.60` |
| `char_start` | int | 全文字符起始偏移 | 否 | `1024` |
| `char_end` | int | 全文字符结束偏移（不含） | 否 | `1054` |
| `calculation` | str | 计算过程 | 否 | `3,856,209,744.60 元 / 1e8 = 38.56 亿元` |
| `page_type` | 枚举 | 证据所在页面形态 | 否（默认 `text`） | `text` / `table` / `chart` / `scanned` / `mixed` |
| `evidence_level` | 枚举 | 本条证据的等级 | 否（默认 `A`） | `A` / `B` / `C` |
| `image_path` | str | 页面图片路径（图片页证据） | 否 | `output/.../images/page_0005.png` |

**为什么 `quote` 要求逐字摘录**：来源定位评分项考察的是"能不能回到原文"。如果允许改写，就无法证明该片段真实存在于原文中，定位也就不可验证。

---

## 六、证据等级判定规则

| 等级 | 判定条件 | 能否自动判定 |
|---|---|---|
| **A** | 文字层直接命中；或表格结构解析所得 | ✅ 可 |
| **B** | OCR 识别，可信度 ≥ 0.9，且经人工抽检通过 | ✅ 可 |
| **C** | 图表像素反推；或 OCR 可信度 < 0.9 | ❌ **只能报"疑似"，进人工复核队列** |

**这条红线由 `Finding.validate()` 强制**：若 `evidence_level = C` 而 `status = confirmed`，校验直接报错。把规则写进代码，而不是写在文档里靠人自觉——这是本项目控制误报率的核心机制，也是计划书中可展示的方法论亮点。

### 特别约定：`truncated` 标记

抽取环节可能发生"数字被页面边界截断"（如 `1,102,450,633.21` 变成 `1,102,450,633.2`）。截断后的数字**看起来完全正常**，极易被当作真实值参与比对，从而凭空制造误报。因此：

- 抽取层一旦发现数值位数异常或文本触及页面边界，须置 `truncated = True`；
- 校验层拒绝使用 `truncated = True` 的事实做判定；
- 此类条目进入人工复核队列，而非直接报错。

---

## 七、执行日志（TraceRecord）字段规范

竞赛要求完整记录文件访问、工具调用、计算过程与结果生成。

| 字段名 | 类型 | 含义 | 必填 | 示例 |
|---|---|---|---|---|
| `run_id` | str | 本次运行标识 | **是** | `20261014-0853` |
| `step` | str | 步骤名 | **是** | `ingest.extract` / `agent.verify` |
| `action` | str | 动作描述 | **是** | `解析第 2 页表格` |
| `status` | str | 执行状态 | 否（默认 `ok`） | `ok` / `error` / `skip` |
| `doc_id` | str | 相关文档 | 否 | `SAMPLE-AR-2024` |
| `page_no` | int | 相关页码 | 否 | `2` |
| `detail` | dict | 详细信息 | 否 | 任意可 JSON 序列化结构 |
| `model_info` | dict | 模型身份 | 否 | `{"model": "deepseek-chat"}` |
| `elapsed_ms` | int | 耗时（毫秒） | 否 | `128` |
| `created_at` | str | 时间戳 | 否（自动填充） | |

落盘格式为 JSON Lines（每行一条），文件名 `output/trace.jsonl`。选用 JSONL 而非单个 JSON 数组的原因：便于增量追加、便于用 `diff` 逐行比对两次运行的差异。

---

## 八、评测标准答案（bench/gold.json）结构

由 B 独立标注，A 的评测框架读取。**A 不得参与标注，标注期间 B 不得参考系统输出。**

```json
{
  "bench_version": "1.0",
  "annotator": "B",
  "annotated_at": "2026-10-15",
  "target_doc_id": "RPT-001",
  "items": [
    {
      "item_id": "G-001",
      "page_no": 1,
      "error_type": "E2",
      "is_true_error": true,
      "quote": "公司总资产达 385.62 亿元",
      "char_start": 210,
      "char_end": 232,
      "correct_value": "38.56 亿元",
      "reference_doc_id": "SAMPLE-AR-2024",
      "reference_page_no": 2,
      "note": "单位错误，应为 38.56 亿元"
    },
    {
      "item_id": "G-002",
      "page_no": 1,
      "error_type": null,
      "is_true_error": false,
      "quote": "营业收入同比增长 12.5%",
      "note": "正确表述，用于检验误报（系统若报错即为误报）"
    }
  ]
}
```

**关键设计**：不仅标注"真错误"，也标注**"正确的表述"**（`is_true_error: false`）。后者用于计算**误报率**——系统若把正确表述判为错误，即为误报。没有这部分标注，就无法评测误报控制这一评分项。

---

## 九、必填项汇总（速查）

| 数据单元 | 必填字段 |
|---|---|
| `FinancialFact` | `fact_id`、`doc_id`、`page_no`、`metric_name`、`value_raw` |
| `Finding` | `finding_id`、`target_doc_id`、`target_page`、`error_type`、`status`、`evidence_level`、`evidences`（≥1） |
| `Evidence` | `doc_id`、`page_no`、`quote` |
| `TraceRecord` | `run_id`、`step`、`action` |

必填项在 `__post_init__` 中即被校验，构造阶段就会失败——**不允许构造出半成品对象流入下游**。

---

## 十、关联文件

| 文件 | 关系 |
|---|---|
| `src/common/schema.py` | 本规范的可执行实现，含红线校验与自检 |
| `src/common/trace_index.py` | 页级溯源索引，为 `char_start/char_end` 提供定位能力 |
| `output/run_logs/01_extract_验证报告.md` | `truncated` 标记的来源（发现三） |
| `bench/gold.json` | 评测标准答案，由 B 标注，结构见第八节 |
