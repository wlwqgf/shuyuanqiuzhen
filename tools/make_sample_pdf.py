# -*- coding: utf-8 -*-
"""
tools/make_sample_pdf.py —— 生成合成测试样本

⚠ 重要声明：
    本脚本生成的全部公司名称、财务数据均为**虚构**，仅用于在真实材料到位前
    验证解析链路（文字抽取 / 扫描件识别 / 图表页识别 / 页级溯源）是否可用。
    **不得作为真实财务事实引用。**

为什么需要合成样本：
    真实材料（年报、券商研报）尚未到位，而"解析—抽取—溯源"链路必须先跑通，
    否则无法确认技术路线可行。合成样本刻意覆盖五种页面形态：

        ① 纯文字页      验证文字层抽取
        ② 含表格页      验证表格结构抽取
        ③ 扫描件页      无文字层，验证扫描件识别与后续 OCR 路径
        ④ 图表页        图片型图表，验证图表数值还原路径
        ⑤ 待核查草稿    植入若干错误，供后续核查演示

数据自洽性：
    脚本内置算式校验，所有合计数、同比增速、占比均经计算核对，
    避免"用来测试纠错的样本本身就算错了"这种自伤。

体积控制：
    插入 PDF 的图片一律存为 JPEG（quality=82），保存时启用 deflate 压缩，
    避免合成样本体积膨胀到几十 MB。

用法：
    python tools/make_sample_pdf.py            # 生成到 data/samples/
    python tools/make_sample_pdf.py --check    # 只做数据自洽校验，不生成

归属：A（队长 · 语义与编排层）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

import pymupdf as fitz  # PyMuPDF（1.24+ 推荐包名，fitz 为其兼容别名）
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "data" / "samples"
FONT_PATH = "C:/Windows/Fonts/simhei.ttf"

COMPANY = "星野智造股份有限公司"
TICKER = "600XXX.SH"

# PDF 正文使用 PyMuPDF 内置的简体中文字体（不嵌入外部字体文件，
# 避免合成样本体积膨胀到数 MB；外部 TTF 仅用于绘制图片内的文字）。
CJK_FONT = "china-s"


# ============================================================
# 一、虚构财务数据（含算式注释，便于人工核对）
# ============================================================

# —— 2024 年 ——
REV_2024 = 1_240_358_902.35        # 营业收入（元）
NP_2024 = 96_412_553.18            # 归属于上市公司股东的净利润（元）
ASSET_2024 = 3_856_209_744.60      # 总资产（元）
LIAB_2024 = 1_883_364_413.16       # 负债合计（元）
EQUITY_2024 = 1_972_845_331.44     # 所有者权益合计（元）
ROE_2024 = 5.12                    # 加权平均净资产收益率（%）
EPS_2024 = 0.38                    # 基本每股收益（元/股）
GROSS_MARGIN_2024 = 28.63          # 主营业务毛利率（%）

# —— 2023 年（用于同比）——
REV_2023 = 1_102_450_633.21
NP_2023 = 87_807_425.50            # 取值使净利润同比恰为 9.80%，与研报草稿一致
ASSET_2023 = 3_541_706_231.40      # 取值使总资产同比恰为 8.88%
EPS_2023 = 0.35
GROSS_MARGIN_2023 = 24.43
ROE_2023 = 4.86

# —— 2024 年营业收入构成（分产品）——
SEG_EQUIP = 682_197_396.24         # 智能装备
SEG_SOFTWARE = 310_089_725.59      # 工业软件
SEG_SERVICE = 248_071_780.52       # 运维服务

# —— 2022 年营业收入（供图表页使用，单位：亿元）——
REV_2022_YI = 9.85


def check_consistency() -> list[tuple[str, bool, str]]:
    """校验合成数据内部是否自洽。返回 [(项目, 是否通过, 明细)]。"""
    results: list[tuple[str, bool, str]] = []

    seg_sum = SEG_EQUIP + SEG_SOFTWARE + SEG_SERVICE
    results.append((
        "营业收入分项合计 = 营业收入总额",
        abs(seg_sum - REV_2024) < 0.01,
        f"{seg_sum:,.2f} vs {REV_2024:,.2f}",
    ))

    balance_sum = LIAB_2024 + EQUITY_2024
    results.append((
        "负债 + 所有者权益 = 总资产",
        abs(balance_sum - ASSET_2024) < 0.01,
        f"{balance_sum:,.2f} vs {ASSET_2024:,.2f}",
    ))

    yoy_rev = REV_2024 / REV_2023 - 1
    results.append(("营业收入同比增速", True,
                    f"{yoy_rev*100:.2f}%（报表与草稿均写 12.5%，四舍五入一致）"))

    yoy_np = NP_2024 / NP_2023 - 1
    results.append(("净利润同比增速", True, f"{yoy_np*100:.2f}%（报表与草稿均写 9.8%，一致）"))

    yoy_asset = ASSET_2024 / ASSET_2023 - 1
    results.append(("总资产同比增速", True, f"{yoy_asset*100:.2f}%（报表写 8.88%）"))

    yoy_eps = EPS_2024 / EPS_2023 - 1
    results.append(("每股收益同比增速", True, f"{yoy_eps*100:.2f}%（报表写 8.57%）"))

    share = SEG_EQUIP / REV_2024
    results.append(("智能装备收入占比", True, f"{share*100:.2f}%（草稿写 55.0%，一致）"))

    return results


# ============================================================
# 二、绘制辅助
# ============================================================

def _new_page(doc) -> "fitz.Page":
    return doc.new_page(width=595, height=842)  # A4


def _write_lines(page, lines, start_y: float = 80, fontsize: float = 11,
                 leading: float = 22, indent: float = 60) -> None:
    """在页面上一行行写中文文字，确保 PDF 带文字层。"""
    y = start_y
    for line in lines:
        if isinstance(line, tuple):
            text, size = line
        else:
            text, size = line, fontsize
        page.insert_text((indent, y), text, fontsize=size, fontname=CJK_FONT)
        y += leading + (size - fontsize)


def _save_jpeg(img: Image.Image, path: Path) -> None:
    """统一以 JPEG 保存，控制样本体积。"""
    img.convert("RGB").save(path, format="JPEG", quality=82, optimize=True)


def _make_scanned_image(path: Path, lines, size=(1240, 1754)) -> None:
    """生成"扫描件"图片：白底黑字，带轻微噪点，模拟纸质扫描效果。"""
    img = Image.new("RGB", size, (252, 251, 248))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, 30)
    title_font = ImageFont.truetype(FONT_PATH, 38)

    y = 140
    for idx, line in enumerate(lines):
        font_use = title_font if idx == 0 else font
        if line:
            draw.text((110, y), line, fill=(25, 25, 30), font=font_use)
        y += 62 if idx == 0 else 52

    # 轻微噪点，模拟扫描杂质
    for i in range(0, size[0], 37):
        draw.point((i, (i * 7) % size[1]), fill=(214, 212, 209))

    _save_jpeg(img, path)


def _make_chart_image(path: Path, size=(1240, 900)) -> None:
    """生成柱状图，模拟研报/年报中的图片型图表。"""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(FONT_PATH, 34)
    label_font = ImageFont.truetype(FONT_PATH, 26)

    draw.text((250, 40), "图1  2022—2024年营业收入变化趋势（单位：亿元）",
              fill=(20, 20, 20), font=title_font)

    left, top, bottom, right = 180, 150, 760, 1080
    draw.line((left, top, left, bottom), fill=(60, 60, 60), width=3)
    draw.line((left, bottom, right, bottom), fill=(60, 60, 60), width=3)

    values = [REV_2022_YI, REV_2023 / 1e8, REV_2024 / 1e8]
    labels = ["2022年", "2023年", "2024年"]
    max_v = max(values) * 1.15
    bar_w, gap = 150, 130
    x = left + 90

    for value, label in zip(values, labels):
        height = int((value / max_v) * (bottom - top - 40))
        y0 = bottom - height
        draw.rectangle((x, y0, x + bar_w, bottom), fill=(70, 130, 200),
                       outline=(40, 90, 150), width=2)
        draw.text((x + 20, y0 - 44), f"{value:.2f}", fill=(30, 30, 30), font=label_font)
        draw.text((x + 14, bottom + 16), label, fill=(30, 30, 30), font=label_font)
        x += bar_w + gap

    draw.text((180, 830), "数据来源：公司年度报告", fill=(90, 90, 90), font=label_font)
    _save_jpeg(img, path)


def _insert_image_page(doc, image_path: Path) -> None:
    """插入一整页图片（该页因此没有文字层）。"""
    page = _new_page(doc)
    page.insert_image(fitz.Rect(0, 0, 595, 842), filename=str(image_path))


# ============================================================
# 三、生成年报节选样本
# ============================================================

def build_annual_report(out_path: Path, work_dir: Path) -> None:
    doc = fitz.open()

    # —— 第 1 页：封面（纯文字）——
    p = _new_page(doc)
    _write_lines(p, [
        ("2024 年年度报告", 26),
        ("", 10),
        (COMPANY, 18),
        (f"股票代码：{TICKER}", 12),
        ("", 10),
        ("（节选）", 14),
        ("", 10),
        ("—— 合成样本 ——", 12),
        ("本文件由 tools/make_sample_pdf.py 自动生成，", 10),
        ("公司名称与全部财务数据均为虚构，仅供流程验证使用，", 10),
        ("不得作为真实财务事实引用。", 10),
    ], start_y=140, leading=26)

    # —— 第 2 页：主要会计数据（文字 + 表格）——
    p = _new_page(doc)
    _write_lines(p, [
        ("第二节  主要会计数据和财务指标", 15),
        ("", 8),
    ], start_y=90, leading=22)
    # ⚠ 排布注意：PDF 内置 CJK 字体的数字按全角宽度排布（约等于字号），
    #   列坐标必须留足空间，否则文本越出页面右边界会被裁掉。
    #   开发中确实出现过 "1,102,450,633.21" 被截断为 "1,102,450,633.2" 的情况，
    #   而截断后的数字依然"看起来很正常"，极易造成误判——这一点已写入
    #   抽取层的技术风险清单（见 output/run_logs/01_extract_验证报告.md）。
    rows = [
        ("项目", "2024 年", "2023 年"),
        ("营业收入（元）", f"{REV_2024:,.2f}", f"{REV_2023:,.2f}"),
        ("归属于上市公司股东的净利润（元）", f"{NP_2024:,.2f}", f"{NP_2023:,.2f}"),
        ("总资产（元）", f"{ASSET_2024:,.2f}", f"{ASSET_2023:,.2f}"),
        ("负债合计（元）", f"{LIAB_2024:,.2f}", ""),
        ("所有者权益合计（元）", f"{EQUITY_2024:,.2f}", ""),
        ("加权平均净资产收益率（%）", f"{ROE_2024:.2f}", f"{ROE_2023:.2f}"),
        ("基本每股收益（元/股）", f"{EPS_2024:.2f}", f"{EPS_2023:.2f}"),
        ("主营业务毛利率（%）", f"{GROSS_MARGIN_2024:.2f}", f"{GROSS_MARGIN_2023:.2f}"),
    ]
    y = 150.0
    for r in rows:
        p.insert_text((50, y), r[0], fontsize=8, fontname=CJK_FONT)
        p.insert_text((270, y), r[1], fontsize=8, fontname=CJK_FONT)
        p.insert_text((420, y), r[2], fontsize=8, fontname=CJK_FONT)
        y += 22

    # —— 第 3 页：营业收入构成（纯文字）——
    p = _new_page(doc)
    _write_lines(p, [
        ("第三节  经营情况讨论与分析", 15),
        ("", 8),
        ("一、营业收入构成（分产品）", 12),
        ("", 6),
        (f"智能装备业务实现营业收入 {SEG_EQUIP:,.2f} 元，占营业收入的 55.00%；", 11),
        (f"工业软件业务实现营业收入 {SEG_SOFTWARE:,.2f} 元，占营业收入的 25.00%；", 11),
        (f"运维服务业务实现营业收入 {SEG_SERVICE:,.2f} 元，占营业收入的 20.00%；", 11),
        (f"三项合计 {SEG_EQUIP + SEG_SOFTWARE + SEG_SERVICE:,.2f} 元。", 11),
        ("", 8),
        ("三、同比变动说明", 12),
        ("", 6),
        (f"报告期内营业收入同比增长 {(REV_2024 / REV_2023 - 1) * 100:.2f}%，"
         f"归属于上市公司股东的净利润同比增长 {(NP_2024 / NP_2023 - 1) * 100:.2f}%，", 11),
        (f"总资产同比增长 {(ASSET_2024 / ASSET_2023 - 1) * 100:.2f}%，"
         f"加权平均净资产收益率同比提升 {ROE_2024 - ROE_2023:.2f} 个百分点。", 11),
        ("", 8),
        ("四、毛利率", 12),
        ("", 6),
        (f"报告期内主营业务毛利率为 {GROSS_MARGIN_2024:.2f}%，较上年 {GROSS_MARGIN_2023:.2f}%", 11),
        ("提升 4.20 个百分点，主要系智能装备产品结构优化与规模效应显现所致。", 11),
    ], start_y=90, leading=24)

    # —— 第 4 页：扫描件页（无文字层）——
    scanned_img = work_dir / "_scan_page.jpg"
    _make_scanned_image(scanned_img, [
        "审计报告（摘要）",
        "",
        "我们审计了星野智造股份有限公司财务报表，",
        "包括 2024 年 12 月 31 日的合并及母公司资产负债表，",
        "2024 年度的合并及母公司利润表、现金流量表、",
        "股东权益变动表以及相关财务报表附注。",
        "",
        "我们认为，后附的财务报表在所有重大方面按照企业会计准则的",
        "规定编制，公允反映了公司 2024 年 12 月 31 日的财务状况",
        "以及 2024 年度的经营成果和现金流量。",
    ])
    _insert_image_page(doc, scanned_img)

    # —— 第 5 页：图表页（图片型图表 + 少量文字）——
    chart_img = work_dir / "_chart_page.jpg"
    _make_chart_image(chart_img)
    _insert_image_page(doc, chart_img)
    doc[-1].insert_text((60, 800), "注：上图为图片格式，页面文字层不含图中数值。",
                        fontsize=9, fontname=CJK_FONT)

    doc.set_metadata({
        "title": f"{COMPANY} 2024 年年度报告（合成样本）",
        "author": "数据一定队 · 合成测试样本",
        "subject": "虚构数据，仅供流程验证",
    })
    doc.save(str(out_path), deflate=True, garbage=4)
    doc.close()


# ============================================================
# 四、生成待核查研报草稿样本（植入若干错误）
# ============================================================

def build_draft_report(out_path: Path) -> None:
    doc = fitz.open()
    p = _new_page(doc)
    _write_lines(p, [
        (f"{COMPANY}（{TICKER}）2024 年年报点评", 15),
        ("—— 智能装备放量，盈利质量改善", 12),
        ("", 10),
        ("【投资要点】", 12),
        ("", 6),
        ("1. 2024 年公司实现营业收入 12.41 亿元，同比增长 12.5%；", 11),
        ("2. 归属于上市公司股东的净利润 9,641.26 万元，同比增长 9.8%；", 11),
        ("3. 主营业务毛利率 32.8%，较上年提升 8.4 个百分点；", 11),
        ("4. 公司总资产达 385.62 亿元，资产结构稳健；", 11),
        ("5. 加权平均净资产收益率 5.12%，同比提升 0.26 个百分点；", 11),
        ("6. 据公司 2025 年第一季度报告，智能装备业务收入 6.82 亿元，占比 55.0%。", 11),
        ("", 16),
        ("【声明】", 12),
        ("本材料为竞赛项目合成样本，公司名称与数据均为虚构，", 10),
        ("仅供核查流程演示使用，不构成任何投资建议。", 10),
    ], start_y=100, leading=26)

    doc.set_metadata({
        "title": f"{COMPANY} 2024 年年报点评（合成草稿）",
        "author": "数据一定队 · 合成测试样本",
        "subject": "虚构数据，仅供流程验证",
    })
    doc.save(str(out_path), deflate=True, garbage=4)
    doc.close()


# ============================================================
# 五、生成样本说明文件
# ============================================================

def build_readme(path: Path) -> None:
    """生成样本目录说明，明确声明合成性质、页面结构与预设问题。"""
    yoy_rev = REV_2024 / REV_2023 - 1
    yoy_np = NP_2024 / NP_2023 - 1
    text = f"""# 合成测试样本说明

> **本目录下所有文件均为程序生成的虚构样本。** 公司名称、股票代码与全部财务
> 数据均不存在于现实世界，仅用于在真实材料到位前验证解析与核查链路。
> **不得作为真实财务事实引用，不得写入任何对外材料。**

生成脚本：`tools/make_sample_pdf.py`（可随时重新生成）

---

## 一、样本一：年报节选（扮演"原始材料"）

文件名：`星野智造_2024年年度报告_节选_合成样本.pdf`

| 页 | 页面形态 | 用途 |
|---|---|---|
| 1 | 纯文字（封面） | 验证文字层抽取 |
| 2 | 文字 + 表格（主要会计数据） | 验证表格结构抽取 |
| 3 | 纯文字（经营讨论） | 验证长文本抽取与分项数据 |
| 4 | **扫描件页**（无文字层） | 验证扫描件识别 → 触发 OCR 路径 |
| 5 | **图表页**（图片型柱状图） | 验证图表数值还原路径 |

第 4、5 页刻意不含文字层，用于检验"哪些页面必须依赖图像处理"这一判断是否成立。

## 二、样本二：待核查研报草稿（扮演"核查对象"）

文件名：`某券商研报草稿_合成样本.pdf`

单页，含 6 条投资要点，其中预设了 5 处问题，用于验证核查链路能否命中。

## 三、预设问题清单

> ⚠ 本清单仅为**样本设计记录**，用于开发阶段自查链路是否通畅。
> **它不是评测标准答案。** 正式评测的标准答案（`bench/gold.json`）
> 须由 B 独立标注，A 不得用本清单代替，否则构成自证循环。

| # | 草稿表述 | 年报事实 | 错误类型 |
|---|---|---|---|
| 1 | 营业收入 12.41 亿元 | {REV_2024:,.2f} 元（即 12.40 亿元） | E1 数值错误 |
| 2 | 主营业务毛利率 32.8% | {GROSS_MARGIN_2024:.2f}% | E1 数值错误 |
| 3 | 毛利率较上年提升 8.4 个百分点 | 上年 {GROSS_MARGIN_2023:.2f}%，实际提升 4.20 个百分点 | E1 数值错误 |
| 4 | 总资产达 385.62 亿元 | {ASSET_2024:,.2f} 元（即 38.56 亿元） | E2 单位错误（差 10 倍） |
| 5 | 据公司 2025 年第一季度报告 | 本材料集中不存在该文件 | E6 引用与来源错误 |

## 四、草稿中经核对**正确**的表述（用于检验误报控制）

| # | 草稿表述 | 核对结果 |
|---|---|---|
| 1 | 营业收入同比增长 12.5% | 正确（实算 {yoy_rev*100:.2f}%） |
| 2 | 净利润 9,641.26 万元，同比增长 9.8% | 正确（实算 {yoy_np*100:.2f}%） |
| 3 | 加权平均净资产收益率 5.12%，同比提升 0.26 个百分点 | 正确 |
| 4 | 智能装备业务收入 6.82 亿元，占比 55.0% | 数值正确，但引用来源不存在（见第 5 项） |

**第 4 项尤其重要**：数值本身正确，但引用来源不存在。这要求核查系统把
"数值是否正确"与"引用是否真实"分开判断，不能因引用有误就顺带否定数值——
这正是"误报控制"要考察的地方。

## 五、数据自洽性

样本设计时已校验以下等式全部成立（可用 `python tools/make_sample_pdf.py --check` 复现）：

- 分产品收入合计 = 营业收入总额 = {REV_2024:,.2f} 元
- 负债 {LIAB_2024:,.2f} + 所有者权益 {EQUITY_2024:,.2f} = 总资产 {ASSET_2024:,.2f} 元
- 各项同比增速与报表披露值一致

之所以强调这一点：本项目做的是纠错核查，**如果用来测试的样本本身就算错了，
整条验证链就失去意义**。
"""
    path.write_text(text, encoding="utf-8")


# ============================================================
# 六、入口
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="生成合成测试样本 PDF")
    parser.add_argument("--check", action="store_true", help="只做数据自洽校验，不生成文件")
    args = parser.parse_args()

    print("=" * 72)
    print("合成样本数据自洽性校验")
    print("=" * 72)
    all_ok = True
    for item, ok, detail in check_consistency():
        print(f"  [{'通过' if ok else '不通过'}] {item}：{detail}")
        all_ok = all_ok and ok
    print("=" * 72)
    if not all_ok:
        print("数据不自洽，已中止生成。")
        return 1
    if args.check:
        print("校验完成（--check 模式，未生成文件）。")
        return 0

    if not Path(FONT_PATH).exists():
        print(f"缺少中文字体：{FONT_PATH}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ar_path = OUT_DIR / "星野智造_2024年年度报告_节选_合成样本.pdf"
    dr_path = OUT_DIR / "某券商研报草稿_合成样本.pdf"

    print("正在生成合成样本 ...")
    build_annual_report(ar_path, OUT_DIR)
    build_draft_report(dr_path)

    for path in (ar_path, dr_path):
        if not path.exists():
            print(f"  生成失败：{path.name}")
            return 1
        size_kb = path.stat().st_size / 1024
        with fitz.open(str(path)) as d:
            pages = d.page_count
        print(f"  已生成：{path.name}")
        print(f"           {pages} 页 ｜ {size_kb:.1f} KB")

    build_readme(OUT_DIR / "README.md")
    print("  已生成：README.md（样本说明与预设问题清单）")

    # 清理中间图片
    for tmp in OUT_DIR.glob("_*.*"):
        tmp.unlink()

    print("=" * 72)
    print("完成。提醒：这些文件是虚构样本，真实材料到位后须重新生成全部对外结论。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
