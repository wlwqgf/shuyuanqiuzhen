# 数鉴——投研报告纠错核查智能体 · 网站前端（web/）

> 归属：A（队长 · 语义与编排层）｜ 更新：2026-10-15
>
> **当前状态**：单页产品形态（正式对外发布版）。界面仅保留「核查工作台」，
> 无侧边栏、无额外页签，全部输出为最终产品口径。
> 后端核心功能（PDF 解析 / 断言抽取 / 双通道核查）经 `api_client.py` 接入——
> 接入时只改那一个文件与数据源开关，`app.py` 界面零改动。

## 文件说明

| 文件 | 作用 |
|---|---|
| `app.py` | Streamlit 主界面：单页核查工作台（上传 / 选材料 / 核查流程 / 结论卡片 / JSON 导出） |
| `api_client.py` | **后端 API 预留接口**（当前为桩实现，抛出 BackendNotReady，不静默返空） |
| `demo_data.py` | 内置核查结论数据（2026-10-14 实测，自包含，不依赖 output/ 目录） |

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

## 界面结构（单页）

- **品牌区**：深蓝渐变 Hero + 五项核心指标（1,067 页真实年报材料 / 8 类错误识别体系 / 2 通道 / 实测覆盖 / A-B-C 证据分级）
- **左栏**：提交待核查研报（PDF 上传）+ 选择比对年报（平安 / 腾讯 / 小米，均已登记 SHA256）
- **右栏**：核查流程时间线 → 结论卡片（判定徽章 + 原文引用 + 证据页 + 计算过程）→ JSON 导出 / 重新核查

## 后端接入路径

1. 实现 `api_client.py` 中四个函数：`submit_check` / `poll_task` / `get_findings` / `get_docs`；
2. 把 `DATA_SOURCE` 从 `"builtin"` 改为 `"api"`；
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
