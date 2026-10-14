# -*- coding: utf-8 -*-
"""
tools/probe_llm_task.py —— 大模型核查能力对照实验

目的：用同一道题、三种提示策略，实测"把确定性计算交给大模型"会发生什么。
      实验结论直接支撑《计划书》中的架构主张（双通道核查：代码算、模型判）。

设计原则：**不联网也能跑（用 mock），有密钥才跑实测**。
          实测结果如实输出，不美化、不筛选。

题目（真值已知）：
    待核查句：公司2024年营业收入125.6亿元，同比增长32.5%
    原始材料：2024年营业收入 1,240,358,902.13 元；2023年营业收入 1,102,450,633.21 元
    真值   ：营收应为 12.40 亿元（夸大 10 倍量级）；同比应为 12.51%（非 32.5%）
              两项声明**均错误**。

用法：
    python tools/probe_llm_task.py              # 用 .env 中的档案
    python tools/probe_llm_task.py --profile mock
    python tools/probe_llm_task.py --profile glm

归属：A（队长 · 语义与编排层）
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from agent.model_provider import ModelProvider  # noqa: E402

# ============================================================
# 一、题目常量（真值）
# ============================================================

REV_2024 = 1_240_358_902.13   # 元
REV_2023 = 1_102_450_633.21   # 元
CLAIM_REV_YI = 125.6          # 亿元（研报声明）
CLAIM_YOY = 32.5              # %（研报声明）

TRUTH_REV_YI = REV_2024 / 1e8                    # 12.4036 亿元
TRUTH_YOY = (REV_2024 / REV_2023 - 1) * 100      # 12.51 %

SYSTEM = "你是财务事实核查助手，只输出 JSON，不要任何解释文字，不要使用 markdown 代码块。"

JSON_SPEC = (
    '{"rev_claim_correct": bool, "rev_actual_yi": number, '
    '"yoy_claim_correct": bool, "yoy_actual_pct": number, '
    '"error_type": string, "reason": string}'
)

FACT_BLOCK = (
    f"【待核查句】研报草稿称：公司2024年营业收入{CLAIM_REV_YI}亿元，"
    f"同比增长{CLAIM_YOY}%。\n"
    f"【原始材料】2024年营业收入 {REV_2024:,.2f} 元；"
    f"2023年营业收入 {REV_2023:,.2f} 元。"
)


# ============================================================
# 二、三种提示策略
# ============================================================

def case_1_pure_llm(provider: ModelProvider) -> dict:
    """策略一：纯大模型——让它既做计算又做判断（当前多数队伍的默认做法）。"""
    user = (
        FACT_BLOCK
        + f"\n请逐项核对，注意单位换算（1 亿元 = 100,000,000 元）。\n"
        + f"输出 JSON：{JSON_SPEC}"
    )
    return provider.chat_json(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    )


def case_2_cot(provider: ModelProvider) -> dict:
    """策略二：提示工程补救——要求模型先列计算步骤再判定（思维链）。"""
    user = (
        FACT_BLOCK
        + "\n请严格按以下顺序处理：\n"
        "  第1步：把 2024 年营收由「元」换算为「亿元」，写出换算式；\n"
        "  第2步：计算营收同比增速 = (2024营收 / 2023营收 - 1) * 100；\n"
        "  第3步：把第1、2步的结果与研报声明逐项对比；\n"
        "  第4步：给出判定。\n"
        + f"输出 JSON：{JSON_SPEC}"
    )
    return provider.chat_json(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    )


def case_3_code_first(provider: ModelProvider) -> dict:
    """策略三（本项目主张）：代码先算好确定性数值，模型只做语义一致性判断。"""
    computed = (
        f"\n【已由程序精确计算的参考值，可直接采信，无需你自行计算】\n"
        f"  2024年营业收入 = {TRUTH_REV_YI:.4f} 亿元\n"
        f"  营业收入同比增速 = {TRUTH_YOY:.2f} %\n"
    )
    user = (
        FACT_BLOCK
        + computed
        + "\n请仅将研报声明与上述参考值逐项比对，判断是否一致。\n"
        + f"输出 JSON：{JSON_SPEC}"
    )
    return provider.chat_json(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    )


# ============================================================
# 三、判分（真值已知，客观判定，不依赖模型自评）
# ============================================================

def grade(obj: dict) -> dict:
    """按真值判定模型是否抓住了两处错误。"""
    rev_ok = obj.get("rev_claim_correct") is False
    yoy_ok = obj.get("yoy_claim_correct") is False
    try:
        got_yi = abs(float(obj.get("rev_actual_yi", -1)) - TRUTH_REV_YI) <= 0.05
    except (TypeError, ValueError):
        got_yi = False
    try:
        got_yoy = abs(float(obj.get("yoy_actual_pct", -999)) - TRUTH_YOY) <= 0.5
    except (TypeError, ValueError):
        got_yoy = False
    return {
        "识别营收错误": rev_ok,
        "识别同比错误": yoy_ok,
        "营收数值正确": got_yi,
        "同比数值正确": got_yoy,
        "得分": sum([rev_ok, yoy_ok, got_yi, got_yoy]),
    }


CASES = [
    ("策略一 纯大模型（既算又判）", case_1_pure_llm),
    ("策略二 提示词思维链（仍由模型算）", case_2_cot),
    ("策略三 代码先算 + 模型只判 ★本项目", case_3_code_first),
]


# ============================================================
# 四、主流程
# ============================================================

def main() -> int:
    argv = sys.argv[1:]
    profile = None
    if "--profile" in argv:
        i = argv.index("--profile")
        if i + 1 < len(argv):
            profile = argv[i + 1]

    provider = ModelProvider.from_env(profile)
    print("=" * 78)
    print("大模型核查能力对照实验 —— 同一道题、三种策略")
    print("=" * 78)
    print(f"模型档案 : {provider.cfg.profile} / {provider.cfg.model}")
    print(f"厂商     : {provider.cfg.vendor}")
    print(f"温度     : {provider.cfg.temperature}（固定为 0，保证可复现）")
    print("-" * 78)
    print(f"真值     : 营收应为 {TRUTH_REV_YI:.4f} 亿元，同比应为 {TRUTH_YOY:.2f}%")
    print(f"研报声明 : 营收 {CLAIM_REV_YI} 亿元，同比 {CLAIM_YOY}%  → 两项均错误")
    print("=" * 78)

    if not provider.cfg.has_key():
        print("未检测到密钥，无法运行实测。请在 .env 中配置后重试。")
        print("=" * 78)
        return 1

    results = []
    for name, fn in CASES:
        print(f"\n########## {name} ##########")
        t0 = time.time()
        try:
            obj = fn(provider)
        except Exception as exc:
            print(f"  调用失败：{exc}")
            results.append((name, None, time.time() - t0))
            continue
        elapsed = time.time() - t0
        g = grade(obj)
        print(f"  耗时 {elapsed:.1f}s ｜ 得分 {g['得分']}/4")
        print("  模型返回：" + json.dumps(obj, ensure_ascii=False))
        print(
            "  判分：" + "，".join(f"{k}={'✅' if v else '❌'}" for k, v in g.items() if k != "得分")
        )
        results.append((name, g, elapsed))

    # 汇总
    print("\n" + "=" * 78)
    print("汇总（满分 4）")
    print("=" * 78)
    print(f"{'策略':<40}{'得分':>6}{'耗时':>10}")
    print("-" * 78)
    for name, g, el in results:
        score = g["得分"] if g else "调用失败"
        print(f"{name:<40}{str(score):>6}{f'{el:.1f}s':>10}")

    print("-" * 78)
    print("判分口径（按真值客观判定，不采信模型自评）：")
    print("  营收判定为错误 / 同比判定为错误 / 营收数值误差≤0.05亿 / 同比数值误差≤0.5%")
    print("=" * 78)
    print(f"溯源信息：{json.dumps(provider.info(), ensure_ascii=False)}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
