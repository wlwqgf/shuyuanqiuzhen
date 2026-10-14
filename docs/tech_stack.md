# 技术栈与模型选型说明

> 归属：A（队长 · 语义与编排层）｜ 建档日期：2026-10-12 ｜ 最近更新：2026-10-14
>
> 本文档记录本项目的技术选型结论与理由，是竞赛要求的"第三方模型/软件须说明名称、版本、调用方式及使用范围"的正式依据。**任何新增依赖或更换模型，必须先更新本文档，再改代码。**

---

## 一、选型速查（一页结论）

| 层面 | 选型 | 一句话理由 |
|---|---|---|
| 语言 | Python 3.13 | 已在本机验证可用，金融数据处理生态最完整 |
| 核心推理引擎 | 开发期 **智谱 GLM-4-Flash**（永久免费）／决赛 **DeepSeek `deepseek-chat`**（国产） | 二者均国产、均走 OpenAI 兼容协议，切换零代码改动；开发期零成本，决赛用长上下文主力 |
| 接入方式 | **OpenAI 兼容 HTTP 协议**（`POST /chat/completions`） | 行业标准协议，任何厂商都支持，便于主备切换与消融实验 |
| 调用抽象 | 自建 `ModelProvider`（`src/agent/model_provider.py`） | 业务代码不得出现具体厂商接口，选型变更不影响业务逻辑 |
| PDF 解析 | pdfplumber + PyMuPDF | pdfplumber 抽文字与表格更准，PyMuPDF 渲染页面图片更快 |
| 中文 OCR | rapidocr-onnxruntime | CPU 可跑、自带中文模型、Apache-2.0 许可，无需申请 Key |
| HTTP 客户端 | **Python 标准库 urllib**（零新增依赖） | 降低评审方复现门槛：不需要额外装任何包即可调通模型 |
| 数据校验 | 标准库 dataclasses + 自写校验 | 字段规范需要强约束但不需要重型框架 |

---

## 二、运行环境

| 项 | 值 |
|---|---|
| Python | 3.13.14（managed） |
| 虚拟环境 | `C:\Users\ao wen wen\.workbuddy\binaries\python\envs\fincheck` |
| 项目根目录 | `C:\Users\ao wen wen\WorkBuddy\2026-10-12-15-01-58\fincheck` |
| 包索引源 | `https://mirrors.tencent.com/pypi/simple`（**本机清华源不通，勿用**） |
| 操作系统 | Windows（开发）／ Linux（评审复现均可，代码未使用平台专有 API） |

### 环境重建命令（评审方复现用）

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt -i https://mirrors.tencent.com/pypi/simple
```

> `requirements.txt` 只列直接依赖并锁定版本；传递依赖由 pip 自动解析。

---

## 三、直接依赖清单

| 包 | 版本 | 许可证 | 用途 | 使用范围 |
|---|---|---|---|---|
| pdfplumber | 0.11.10 | MIT | PDF 文字层抽取、表格结构抽取 | 全流程 |
| PyMuPDF（import 名 `fitz`） | 1.28.2 | **AGPL-3.0** | 页面渲染为图片 | 全流程（见下方风险提示） |
| pypdfium2 | 5.14.0 | Apache-2.0 / BSD-3-Clause | PyMuPDF 的宽松许可替代品 | 备用 |
| Pillow | 12.3.0 | MIT-CMU（HPND） | 图像读写、合成样本生成、图表绘制 | 开发与预处理 |
| rapidocr-onnxruntime | 1.2.3 | Apache-2.0 | 中文 OCR（扫描件与图表文字） | 视觉层 |
| onnxruntime | 1.31.0 | MIT | OCR 模型推理引擎 | 视觉层 |
| NumPy | 2.5.4 | BSD-3-Clause | 数值计算（图表数值还原） | 视觉层 |
| PyYAML | 6.0.3 | MIT | 读取规则库 YAML 文件 | 规则层 |

完整传递依赖与许可证核对结果见 `docs/license.md`（由 `tools/collect_licenses.py` 自动生成，非人工誊抄）。

### ⚠ 许可证风险提示（必须在计划书如实说明）

**PyMuPDF 采用 AGPL-3.0 许可证，属强传染性开源协议。** 本项目对其的使用范围**仅限页面渲染**（把 PDF 页画成 PNG 图片），不修改其源代码、不再分发其衍生物。计划书中须如实列明。

若评审方或指导老师认为 AGPL 不可接受，替换方案已就绪：改用 `pypdfium2`（Apache-2.0 / BSD-3-Clause），接口差异极小，替换工作量约半小时。**替换开关位置**：`src/ingest/extract.py` 中的 `_render_page()` 函数。

---

## 四、大模型选型

### 4.1 首要澄清：作品运行时不得依赖桌面客户端

竞赛要求"提交与展示版本一致的完整源代码""说明模型名称、版本、调用方式"，且"运行结果可复现"。因此：

- **WorkBuddy 等 AI 客户端仅用于开发辅助**（写代码、整理文档、审阅材料），**不得作为作品运行时的推理引擎**——评审方无法复现，该项直接失分。
- 作品内部的推理必须通过**标准 API 协议**调用，模型名称、接口地址、密钥全部走配置，代码可审计。

> 结论：**本项目的推理引擎 = 通过 HTTP API 调用的国产大模型**，桌面客户端不参与运行时。

### 4.2 分阶段选型（当前执行口径）

本项目采用"开发期零成本、决赛用主力"的分阶段策略，两者接口协议完全一致，切换仅需改一行配置。

| 阶段 | 启用模型 | 厂商 | 密钥环境变量 | 理由 |
|---|---|---|---|---|
| **开发期（当前）** | `glm-4-flash` | 智谱 AI（BigModel） | `ZHIPUAI_API_KEY` | 官方承诺**永久免费**；128K 上下文；OpenAI 协议兼容；用于跑通链路、积累评测数据，**零成本** |
| **决赛交付** | `deepseek-chat` | 深度求索 | `DEEPSEEK_API_KEY` | 中文金融语料表现稳定、长上下文成本可控；作为最终演示与消融实验主力 |
| 离线自检 | `mock-echo` | 无（本地） | 不需要 | **不联网、零成本**，输出带 `_mock` 标记，仅用于验证代码链路是否连通 |

**切换方式**：修改 `.env` 中的 `FINCHECK_LLM_PROFILE`（可选值 `glm` / `deepseek` / `qwen` / `kimi` / `ollama` / `mock`），业务代码不做任何改动。

> ⚠ **mock 档案的合规约束**：mock 输出是固定结构、并非真实判定，**严禁**用于评测计分、计划书效果展示或写入正式核查结论。所有正式结论必须由真实模型产生，并在 `trace.jsonl` 中记录模型身份（`is_mock` 字段用于自动区分）。

### 4.3 决赛首选模型（DeepSeek）

| 项 | 值 |
|---|---|
| 厂商 | 深度求索（DeepSeek） |
| 模型型号 | `deepseek-chat`（通用对话与文本理解） |
| 备用型号 | `deepseek-reasoner`（需要长链推理的复杂勾稽判断，成本较高，仅在特定子任务启用） |
| 调用协议 | **OpenAI 兼容协议** |
| 接口地址 | `POST https://api.deepseek.com/chat/completions` |
| 认证方式 | 请求头 `Authorization: Bearer <API_KEY>` |
| 密钥环境变量 | `DEEPSEEK_API_KEY` |
| 上下文长度 | 128K tokens |
| 使用范围 | 语义层全部判定：断言抽取、数值与原文一致性比对、表述与数据矛盾识别、引用真实性核验、改写建议生成 |
| 官方文档 | https://platform.deepseek.com/api-docs （参数以官方文档为准） |

**选择理由**：① 国产模型，符合竞赛鼓励方向；② 128K 上下文足以容纳单篇研报正文加相关年报片段，避免过度分块导致上下文断裂；③ 中文金融语料表现稳定；④ 接口与 OpenAI 协议完全兼容，切换其他厂商只需改 base_url 与模型名；⑤ 价格低，全流程成本可控。

**请求示例**（真实可用，可直接复制调试）：

```bash
curl https://api.deepseek.com/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  -d '{
    "model": "deepseek-chat",
    "messages": [
      {"role": "system", "content": "你是财务事实核查助手，只输出 JSON。"},
      {"role": "user", "content": "核对：原文称营业收入 12.4 亿元，年报为 1,240,358,902 元。是否一致？"}
    ],
    "temperature": 0,
    "response_format": {"type": "json_object"}
  }'
```

### 4.4 备选模型（主备切换用）

| 优先级 | 厂商 | 型号 | Base URL | 密钥环境变量 | 适用场景 |
|---|---|---|---|---|---|
| **开发期启用** | 智谱 AI | `glm-4-flash` | `https://open.bigmodel.cn/api/paas/v4` | `ZHIPUAI_API_KEY` | **永久免费**，当前开发与联调默认档案 |
| 备用 1 | 阿里云百炼 | `qwen-long` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` | 超长材料（整份年报）且要求低成本 |
| 备用 2 | 月之暗面 | `moonshot-v1-128k` | `https://api.moonshot.cn/v1` | `MOONSHOT_API_KEY` | 长文档检索定位 |
| 离线兜底 | 本地 Ollama | `qwen2.5:7b` | `http://localhost:11434/v1` | 无需密钥 | 现场演示断网时降级，牺牲部分准确率 |
| 链路自检 | 本地 mock | `mock-echo` | 无（不联网） | 无需密钥 | 零成本验证代码链路，**不得用于评测与展示** |

所有备选均使用**同一套 OpenAI 兼容协议**，因此切换零代码改动，只需修改配置文件。

### 4.5 调用抽象设计

`src/agent/model_provider.py` 提供统一入口，业务代码只依赖这一个接口：

```python
provider = ModelProvider.from_env()          # 读环境变量，默认 profile=deepseek
text = provider.chat(messages)               # 返回纯文本
data = provider.chat_json(messages)          # 强制 JSON 输出并解析为 dict
meta = provider.info()                       # 返回厂商/型号/base_url，写入 trace.jsonl
```

**设计约束（硬性）**：
1. 业务代码中**不得**出现 `api.deepseek.com`、`dashscope` 等厂商地址字符串，一律从 provider 取。
2. 每次调用必须把 `provider.info()` 写入 `trace.jsonl`，使"哪条结论由哪个模型、哪个版本得出"可追溯。
3. 统一 `temperature=0`，保证核查结论可复现；确需多样性的任务另行显式覆盖。
4. 内置超时与重试（默认超时 120 秒、重试 2 次、指数退避），失败后抛出明确异常而非静默返回空值。

### 4.6 密钥管理

- 密钥**只存环境变量**，绝不写入代码或提交进仓库。
- 仓库提供 `.env.example` 模板（不含真实密钥），本地复制为 `.env` 使用。
- `.gitignore` 已排除 `.env`、`.env.*`、`*.key`、`secrets.json`。
- 若密钥曾意外提交，须立即到厂商控制台吊销并重新签发。

### 4.7 成本估算

按 15 篇研报 + 配套年报的规模估算：单篇材料平均触发约 20 次模型调用，每次输入约 8K tokens、输出约 1K tokens，全流程输入约 240 万 tokens、输出约 30 万 tokens。按国产模型当前价格水平，**全部消耗在人民币数十元量级**，自充 50 元即可覆盖从开发到决赛的用量，无需等待任何额度审批。

**开发期实际成本为 0**：GLM-4-Flash 官方承诺永久免费（有并发限制，单用户约 2 并发，对本项目的批处理节奏足够）。因此从今天到决赛前的全部联调、评测、消融实验均不产生费用，仅在决赛前切换到 DeepSeek 时才需要充值。

### 4.8 模型消融实验（计划书亮点）

由于调用层已抽象，同一批材料可在不同模型上重复跑评测框架，得到"模型选择对核查准确率与误报率的影响"这一组实测数据。这组数据直接支撑计划书中的选型论证，比定性描述更有说服力。实验设计见 `src/eval/README.md`。

---

## 五、变更流程

1. 新增依赖或更换模型 → 先提交本文档更新（说明理由与许可证）。
2. 涉及 `src/common/schema.py` 数据契约的变更 → 需 A、B 双签确认（见项目指令书 I1）。
3. 涉及界面/接口的变更 → 需同步更新 `src/README.md` 模块地图。

---

## 六、关联文件

- `requirements.txt` —— 依赖锁定清单
- `docs/license.md` —— 第三方许可证完整核对表（脚本生成）
- `.env.example` —— 密钥配置模板
- `src/agent/model_provider.py` —— 模型调用统一入口
- `tools/collect_licenses.py` —— 许可证自动采集脚本
