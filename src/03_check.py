# -*- coding: utf-8 -*-
"""
脚本 03：最小核查闭环（先跑通逻辑，不依赖大模型）

作用：
  演示选题五最核心的一件事——
  研报里写的数字，跟原始年报里的数字，到底对不对得上。

  思路很简单：
  1. 你手工列出研报里的几条「断言」（哪句话、什么指标、什么数字、什么单位）
  2. 脚本去原始年报的文本里找这个指标的数字
  3. 两边比对，给出结论

  这个版本只用「文字匹配 + 数字比对」，不需要大模型、不需要联网，
  目的是让你先把流程跑通、看懂原理，后面再逐步升级。

用法：
  python 03_check.py

你需要改的地方：
  文件最下面的 CLAIMS 列表 —— 把里面换成你自己研报里的真实句子。
"""

import re
from pathlib import Path

# ============ 工具函数 ============

def norm_num(s: str):
    """把 '1,234.56'、'1234.56万元'、'约1234' 这样的文字变成数字。"""
    s = s.replace(",", "").replace("，", "").replace(" ", "")
    m = re.search(r"-?\d+\.?\d*", s)
    return float(m.group()) if m else None


def find_near(text: str, keyword: str, window: int = 120):
    """
    在原文里找关键词，返回关键词后面 window 个字符（数字一般就在附近）。
    返回 (片段, 片段里第一个数字)
    """
    positions = [m.start() for m in re.finditer(re.escape(keyword), text)]
    if not positions:
        return None, None
    pos = positions[0]
    snippet = text[pos:pos + window].replace("\n", " ")
    return snippet, norm_num(snippet)


def compare(claim_value, source_value, tol=0.01):
    """
    比对两个数。tol 是允许的误差比例（默认 1%，因为单位换算、四舍五入会有出入）。
    """
    if claim_value is None or source_value is None:
        return "无法判定", "有一边没找到数字"
    if source_value == 0:
        return "无法判定", "原始值为 0，无法算比例"
    diff = abs(claim_value - source_value) / abs(source_value)
    if diff <= tol:
        return "一致", f"差异 {diff*100:.2f}%，在容差内"
    return "不一致", f"研报 {claim_value} vs 原文 {source_value}，差异 {diff*100:.2f}%"


# ============ 主流程 ============

def run(claims, source_texts: dict):
    """
    claims: 断言列表，每条是一个字典
    source_texts: {"材料名": "文本"}
    """
    results = []

    for c in claims:
        kw = c["关键词"]
        row = {
            "研报原句": c["原句"],
            "指标": kw,
            "研报数值": c["数值"],
            "研报单位": c.get("单位", ""),
            "证据": None,
            "判定": "未找到",
            "说明": "所有原始材料里都没找到这个指标",
        }

        for name, text in source_texts.items():
            snippet, num = find_near(text, kw)
            if snippet is None:
                continue
            verdict, reason = compare(c["数值"], num)
            row["证据"] = f"{name}：{snippet[:100]}"
            row["判定"] = verdict
            row["说明"] = reason
            if verdict == "一致":
                break  # 找到一致的就停，不再继续找

        results.append(row)

    return results


def report(results):
    print()
    print("=" * 70)
    print("核查结果")
    print("=" * 70)
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] 指标：{r['指标']}")
        print(f"    研报原句：{r['研报原句']}")
        print(f"    研报数值：{r['研报数值']} {r['研报单位']}")
        print(f"    判定：{r['判定']}")
        print(f"    说明：{r['说明']}")
        if r["证据"]:
            print(f"    证据：{r['证据']}")
    print()
    print("=" * 70)
    n_bad = sum(1 for r in results if r["判定"] == "不一致")
    n_ok = sum(1 for r in results if r["判定"] == "一致")
    n_na = sum(1 for r in results if r["判定"] in ("未找到", "无法判定"))
    print(f"共 {len(results)} 条断言：一致 {n_ok}，不一致 {n_bad}，无法判定 {n_na}")
    print("注意：'无法判定'不等于没错，只说明证据不足 —— 这正是误报控制的核心。")
    print("=" * 70)


if __name__ == "__main__":
    # ===== 第一步：把你处理好的原始年报文本读进来 =====
    # 先用脚本 01 生成 output/xxx/text/ 目录，然后把目录名填在这里
    TEXT_DIR = Path("output")  # ← 改成你的目录

    source_texts = {}
    if TEXT_DIR.exists():
        for f in sorted(TEXT_DIR.rglob("page_*.txt")):
            source_texts[f.parent.parent.name] = source_texts.get(f.parent.parent.name, "") + f.read_text(encoding="utf-8")

    if not source_texts:
        print("=" * 70)
        print("还没读到任何原始材料。请按这个顺序来：")
        print()
        print("  1. 把年报 PDF 放进 data/raw/")
        print("  2. 运行 python src/01_extract.py data/raw/你的文件.pdf")
        print("  3. 再运行 python src/03_check.py")
        print("=" * 70)

    # ===== 第二步：把研报里的断言填进来（⚠ 这里要你手工改）=====
    CLAIMS = [
        # {"原句": "公司2024年营业收入为125.6亿元", "关键词": "营业收入", "数值": 125.6, "单位": "亿元"},
        # {"原句": "归母净利润同比增长32.5%",         "关键词": "归母净利润", "数值": 32.5,  "单位": "%"},
    ]

    if CLAIMS:
        report(run(CLAIMS, source_texts))
    else:
        print()
        print("CLAIMS 列表是空的。请用记事本打开这个文件，")
        print("把最下面 CLAIMS 里两行开头的 # 删掉，换成你自己研报里的真实句子，再运行。")
