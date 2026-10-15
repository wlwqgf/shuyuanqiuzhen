# 数鉴——投研报告纠错核查智能体 · 网站前端（web/）

> 归属：A（队长 · 语义与编排层）｜ 更新：2026-10-15
>
> **当前状态（分工调整后）**：10/18 前只交付外观界面与基础交互。
> 后端核心功能（PDF 解析 / 断言抽取 / 双通道核查）排期 10/18 后接入，
> 接口已在 `api_client.py` 预留——接入时只改那一个文件，`app.py` 零改动。

## 文件说明

| 文件 | 作用 |
|---|---|
| `app.py` | Streamlit 主界面：核查工作台 / 演示与实测 / 技术架构 三个页签 |
| `api_client.py` | **后端 API 预留接口**（当前为桩实现，抛出 BackendNotReady） |
| `demo_data.py` | 演示数据（2026-10-14 实测结论，自包含，不依赖 output/ 目录） |

## 本地运行

```bash
# 1. 进入项目根目录（fincheck/）
cd fincheck

# 2. 激活虚拟环境（Windows）
.venv\Scripts\activate
# 或直接把 Scripts 目录加进 PATH

# 3. 安装依赖（只需第一次）
pip install -r requirements.txt -i https://mirrors.tencent.com/pypi/simple

# 4. 启动
streamlit run web/app.py
```

浏览器打开 http://localhost:8501 即可看到界面。

## 界面结构

- **核查工作台**：上传研报 → 选择比对年报 → 开始核查（演示模式回放实测结论）
- **演示与实测**：三通道对照表 + 三组关键实测证据
- **技术架构**：双通道架构图 + 证据分级 + 评分项对照 + 模型选型 + 合规声明

## 后端接入路径（10/18 后）

1. 实现 `api_client.py` 中四个函数：`submit_check` / `poll_task` / `get_findings` / `get_docs`；
2. 把 `DATA_SOURCE` 从 `"demo"` 改为 `"api"`；
3. `app.py` 不需要任何改动。

实现可直接调用已写好的 `src/agent/claim_extractor.py`（断言抽取）与
`src/agent/pipeline.py`（双通道核查）。

## 部署（Streamlit Cloud）

1. 代码推送到 GitHub 仓库；
2. 登录 share.streamlit.io → New app → 选择仓库；
3. **Main file path 填 `web/app.py`**（不是根目录的 app.py）；
4. Advanced settings → Secrets 按需配置模型密钥（密钥只进 secrets，不进代码）；
5. Deploy。此后每次 `git push` 真实改动会自动触发重新部署。

## 红线（写入代码，非文档约定）

- 密钥只允许出现在服务端环境变量 / Streamlit secrets，严禁进入前端代码；
- 后端未就绪时必须给出明确信号，不允许静默返回空数据——
  空数据会被误读成"研报没有错误"；
- mock 档案输出带 `_mock` 标记，严禁用于评测计分或正式核查结论。
