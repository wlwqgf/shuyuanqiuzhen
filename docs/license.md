# 第三方组件许可证清单

> **本文件由 `tools/collect_licenses.py` 自动生成，请勿手工编辑。**
> 生成日期：2026-10-14 ｜ 来源：当前 Python 环境实际安装的包元数据
>
> 竞赛要求：使用第三方开源项目、模型、数据或代码的，须列明名称、版本、来源、许可证及具体使用范围。
> 使用范围一栏为人工补充，脚本每次重跑都会保留 `docs/license_scope.md` 中的内容，请在那里维护。

## 一、⚠ 需要重点说明的传染性许可证

以下组件采用 AGPL / GPL 系列许可证，属强传染性开源协议，**必须在计划书中如实说明使用范围**。

| 包名 | 版本 | 许可证 |
|---|---|---|
| pymupdf | 1.28.2 | Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License |

本项目对上述组件的使用均限于**调用其公开接口**，不修改其源代码、不再分发其衍生物。
若指导老师或评审方认为该协议不可接受，替换方案见 `docs/tech_stack.md` 第三节。

## 二、完整依赖清单

共采集到 21 个已安装包，其中标注「项目直接依赖」的 8 个。

| 包名 | 版本 | 许可证 | 项目直接依赖 |
|---|---|---|---|
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | 是 |
| onnxruntime | 1.31.0 | MIT License | 是 |
| pdfplumber | 0.11.10 | MIT License | 是 |
| pillow | 12.3.0 | MIT-CMU | 是 |
| pymupdf | 1.28.2 | Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License | 是 |
| pypdfium2 | 5.14.0 | BSD-3-Clause, Apache-2.0, dependency licenses | 是 |
| PyYAML | 6.0.3 | MIT License | 是 |
| rapidocr-onnxruntime | 1.2.3 | Apache-2.0 | 是 |
| cffi | 2.1.1 | MIT-0 |  |
| charset-normalizer | 3.5.2 | MIT |  |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |  |
| flatbuffers | 25.12.19 | Apache Software License |  |
| opencv-python | 5.0.0.93 | Apache Software License |  |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |  |
| pdfminer.six | 20260107 | MIT |  |
| pip | 26.1.2 | MIT |  |
| protobuf | 7.36.2 | 3-Clause BSD License |  |
| pyclipper | 1.4.0 | MIT License |  |
| pycparser | 3.11 | BSD-3-Clause |  |
| shapely | 2.2.0 | BSD-3-Clause |  |
| six | 1.17.0 | MIT License |  |

## 三、说明

1. 许可证标识取自各包自身的元数据。**提交前须抽查关键包的实际 LICENSE 文件**，
   因为部分包的元数据声明与实际许可证文件存在不一致。
2. 未在表中出现的库（如标准库 `urllib`、`json`、`dataclasses`）属 Python 官方发布，
   适用 PSF License，无需单独登记。
3. 大模型 API 属商业服务而非软件分发，其名称、型号、调用方式见 `docs/tech_stack.md`。
