# -*- coding: utf-8 -*-
"""
脚本 02：图像识别（OCR）——把图片里的文字读出来。

作用：
  年报扫描件、研报里的图表截图、图片型表格，都没有文字层，
  必须用 OCR 才能变成电脑能检索的文本。
  这个脚本会告诉你每个字在图片上的哪个位置（坐标），
  后面做「来源定位」和「图表数值还原」都要靠这个坐标。

用法：
  python 02_ocr.py output/xxx_images/page_0001.png       # 识别一张图
  python 02_ocr.py output/xxx_images                      # 识别整个文件夹

产出：
  output/ocr_result.json  识别结果：文字 + 坐标 + 可信度
"""

import json
import sys
from pathlib import Path


def load_ocr():
    """加载 OCR 引擎，没装就给人话提示。"""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        print("=" * 60)
        print("还没装 OCR 引擎，请先执行这条命令：")
        print()
        print("  pip install rapidocr-onnxruntime -i https://mirrors.tencent.com/pypi/simple")
        print()
        print("说明：这个包约 15MB，会自动带中文识别模型，CPU 就能跑，")
        print("      不需要显卡，装完即可用（比 PaddleOCR 省心很多）。")
        print("=" * 60)
        sys.exit(1)
    return RapidOCR()


def ocr_image(engine, img_path: Path):
    result, _ = engine(str(img_path))
    items = []
    if result:
        for box, text, score in result:
            # box 是四个角的坐标，取左上角和右下角算出一个矩形范围
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            items.append({
                "文字": text,
                "可信度": round(float(score), 3),
                "左": round(min(xs), 1),
                "上": round(min(ys), 1),
                "右": round(max(xs), 1),
                "下": round(max(ys), 1),
            })
    return items


def main(target: str):
    path = Path(target)
    if not path.exists():
        print(f"找不到：{target}")
        sys.exit(1)

    files = [path] if path.is_file() else sorted(path.glob("*.png")) + sorted(path.glob("*.jpg"))
    if not files:
        print(f"目录里没有 png/jpg 图片：{target}")
        sys.exit(1)

    print(f"共 {len(files)} 张图片，正在加载 OCR 引擎（首次加载约 5-10 秒）...")
    engine = load_ocr()

    out = {}
    for i, f in enumerate(files, 1):
        items = ocr_image(engine, f)
        out[f.name] = items
        low = [x for x in items if x["可信度"] < 0.8]
        flag = f"  ⚠ 其中 {len(low)} 条可信度低于 0.8，需要人工校对" if low else ""
        print(f"  [{i}/{len(files)}] {f.name}：识别到 {len(items)} 段文字{flag}")

    out_file = Path("output") / "ocr_result.json"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(v) for v in out.values())
    weak = sum(1 for v in out.values() for x in v if x["可信度"] < 0.8)
    print()
    print("=" * 60)
    print(f"识别完成：{len(files)} 张图，共 {total} 段文字")
    print(f"结果已存到：{out_file}")
    if weak:
        print(f"⚠ 有 {weak} 段文字可信度偏低（<0.8），这些不能直接拿来做判定，")
        print("   只能当「可疑线索」，必须人工核对原文后再用。")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python 02_ocr.py <图片路径或目录>")
        print("示例：python 02_ocr.py output/某公司年报/images")
        sys.exit(1)
    main(sys.argv[1])
