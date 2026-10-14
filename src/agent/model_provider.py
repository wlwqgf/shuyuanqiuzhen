# -*- coding: utf-8 -*-
"""
src/agent/model_provider.py —— 大模型调用统一入口

职责：
  把"调哪个厂商、哪个模型、密钥在哪"全部收进这一个模块，
  业务代码只调用 provider.chat() / provider.chat_json()，
  不出现任何厂商地址字符串。

设计要点：
  1. 只依赖 Python 标准库 urllib，不引入第三方 HTTP 客户端，
     降低评审方的复现门槛（无需额外安装任何包即可调通模型）。
  2. 采用 OpenAI 兼容协议，所有备选厂商共用同一套请求/响应格式，
     因此主备切换只需改配置，零代码改动。
  3. 统一 temperature=0，保证核查结论可复现。
  4. 内置超时与指数退避重试；失败抛出明确异常，绝不静默返回空值。
  5. 每次调用可通过 info() 取回"厂商/型号/base_url"，
     写入 trace.jsonl，满足"哪条结论由哪个模型得出"的可追溯要求。

用法：
    # 查看所有可用模型档案（不联网）
    python src/agent/model_provider.py --list

    # 配置自检（无密钥也能跑，只打印将要调用的地址）
    python src/agent/model_provider.py

    # 实网连通性自检（需先配置密钥）
    python src/agent/model_provider.py --live

在代码中使用：
    from src.agent.model_provider import ModelProvider
    provider = ModelProvider.from_env()
    reply = provider.chat([{"role": "user", "content": "你好"}])

归属：A（队长 · 语义与编排层）
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Windows 控制台中文输出保护
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass


# ============================================================
# 一、预置模型档案
# ============================================================
# 说明：新增厂商只需在此追加一条，业务代码无需改动。
#      base_url 末尾不带斜杠，统一拼接 /chat/completions。

PROFILES: Dict[str, Dict[str, Any]] = {
    "deepseek": {
        "vendor": "深度求索 DeepSeek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "need_key": True,
        "note": "首选。国产、128K 上下文、OpenAI 协议兼容。需要长链推理的子任务可改用 deepseek-reasoner。",
        "doc": "https://platform.deepseek.com/api-docs",
    },
    "qwen": {
        "vendor": "阿里云百炼（通义千问）",
        "model": "qwen-long",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "need_key": True,
        "note": "备用 1。超长材料且要求低成本时使用。",
        "doc": "https://help.aliyun.com/zh/model-studio/",
    },
    "glm": {
        "vendor": "智谱 AI",
        "model": "glm-4-flash",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "ZHIPUAI_API_KEY",
        "need_key": True,
        "note": "备用 2。有免费额度，适合早期联调。",
        "doc": "https://open.bigmodel.cn/dev/api",
    },
    "kimi": {
        "vendor": "月之暗面 Kimi",
        "model": "moonshot-v1-128k",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "need_key": True,
        "note": "备用 3。长文档检索定位能力强。",
        "doc": "https://platform.moonshot.cn/docs",
    },
    "ollama": {
        "vendor": "本地 Ollama",
        "model": "qwen2.5:7b",
        "base_url": "http://localhost:11434/v1",
        "api_key_env": "",
        "need_key": False,
        "note": "离线兜底。现场演示断网时降级使用，准确率会下降。",
        "doc": "https://ollama.com/",
    },
}

DEFAULT_PROFILE = "deepseek"


# ============================================================
# 二、极简 .env 读取（不引入 python-dotenv 依赖）
# ============================================================

def load_dotenv(start_dir: Optional[Path] = None) -> Optional[Path]:
    """从项目根目录向上查找 .env 并载入环境变量。

    规则：已存在的环境变量优先级更高，不会被 .env 覆盖。
    返回实际载入的 .env 路径；未找到返回 None。
    """
    here = (start_dir or Path(__file__).resolve()).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            for raw in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key and value and key not in os.environ:
                    os.environ[key] = value
            return candidate
    return None


# ============================================================
# 三、模型配置
# ============================================================

@dataclass
class ModelConfig:
    """单次运行所使用的模型配置。"""

    profile: str = DEFAULT_PROFILE
    vendor: str = ""
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    need_key: bool = True
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout: int = 120
    max_retries: int = 2

    @property
    def endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "").strip() if self.api_key_env else ""

    def has_key(self) -> bool:
        return bool(self.api_key) or not self.need_key

    def describe(self) -> Dict[str, Any]:
        """返回可写入 trace.jsonl 的模型身份信息（不含密钥）。"""
        return {
            "profile": self.profile,
            "vendor": self.vendor,
            "model": self.model,
            "endpoint": self.endpoint,
            "temperature": self.temperature,
        }

    def display(self) -> str:
        key_state = "已配置" if self.api_key else ("不需要" if not self.need_key else "未配置")
        return (
            f"档案     : {self.profile}\n"
            f"厂商     : {self.vendor}\n"
            f"型号     : {self.model}\n"
            f"接口地址 : {self.endpoint}\n"
            f"密钥变量 : {self.api_key_env or '（不需要）'}  状态：{key_state}\n"
            f"温度/上限: temperature={self.temperature}, max_tokens={self.max_tokens}\n"
            f"超时/重试: timeout={self.timeout}s, max_retries={self.max_retries}"
        )


# ============================================================
# 四、统一调用入口
# ============================================================

class ModelProvider:
    """大模型调用的唯一入口。业务代码只依赖本类。"""

    def __init__(self, config: Optional[ModelConfig] = None):
        self.cfg = config or self._config_from_profile(DEFAULT_PROFILE)

    # ---------- 构造 ----------

    @staticmethod
    def _config_from_profile(name: str) -> ModelConfig:
        if name not in PROFILES:
            raise ValueError(f"未知的模型档案：{name}；可选：{', '.join(PROFILES)}")
        p = PROFILES[name]
        return ModelConfig(
            profile=name,
            vendor=p["vendor"],
            model=os.environ.get("FINCHECK_LLM_MODEL") or p["model"],
            base_url=os.environ.get("FINCHECK_LLM_BASE_URL") or p["base_url"],
            api_key_env=p["api_key_env"],
            need_key=p["need_key"],
            temperature=float(os.environ.get("FINCHECK_LLM_TEMPERATURE", 0) or 0),
            max_tokens=int(os.environ.get("FINCHECK_LLM_MAX_TOKENS", 4096) or 4096),
            timeout=int(os.environ.get("FINCHECK_LLM_TIMEOUT", 120) or 120),
        )

    @classmethod
    def from_env(cls, profile: Optional[str] = None) -> "ModelProvider":
        """按环境变量构造：FINCHECK_LLM_PROFILE 指定档案，默认 deepseek。"""
        load_dotenv()
        name = profile or os.environ.get("FINCHECK_LLM_PROFILE") or DEFAULT_PROFILE
        return cls(cls._config_from_profile(name.strip()))

    # ---------- 基础能力 ----------

    def info(self) -> Dict[str, Any]:
        """模型身份信息，供写日志与溯源使用。"""
        return self.cfg.describe()

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """发起一次对话补全，返回助手回复的纯文本。"""
        payload: Dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature if temperature is None else temperature,
            "max_tokens": self.cfg.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        data = self._post_with_retry(payload)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"响应结构异常，无法取出内容：{json.dumps(data, ensure_ascii=False)[:400]}") from exc

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """要求模型输出 JSON 并解析为 dict；解析失败时做一次容错剥离。"""
        text = self.chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=True)
        return parse_json_loose(text)

    # ---------- 内部：HTTP ----------

    def _post_with_retry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.cfg.has_key():
            raise RuntimeError(
                f"未检测到模型密钥：环境变量 {self.cfg.api_key_env} 为空。\n"
                f"  处理办法：复制 .env.example 为 .env，填入密钥后重试；\n"
                f"  或在命令行临时设置：set {self.cfg.api_key_env}=你的密钥（Windows）"
            )

        last_error: Optional[Exception] = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                return self._post(payload)
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", "replace")[:400]
                except Exception:
                    pass
                last_error = RuntimeError(f"接口返回 HTTP {exc.code}：{body}")
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.cfg.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise last_error from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = RuntimeError(f"网络请求失败：{exc}")
                if attempt < self.cfg.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise last_error from exc

        raise last_error or RuntimeError("未知错误")

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        key = self.cfg.api_key
        if key:
            headers["Authorization"] = f"Bearer {key}"

        request = urllib.request.Request(
            self.cfg.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.cfg.timeout) as response:
            raw = response.read().decode("utf-8", "replace")
        return json.loads(raw)


# ============================================================
# 五、工具函数
# ============================================================

def parse_json_loose(text: str) -> Dict[str, Any]:
    """尽力从模型回复中解析出 JSON 对象。

    依次尝试：直接解析 → 剥离 ``` 围栏 → 截取第一个 { 到最后一个 }。
    """
    if text is None:
        raise ValueError("模型返回为空")
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            obj = json.loads(t[i : j + 1])
        else:
            raise ValueError(f"无法解析为 JSON：{text[:300]}")
    if not isinstance(obj, dict):
        raise ValueError(f"期望 JSON 对象，实际得到 {type(obj).__name__}")
    return obj


# ============================================================
# 六、命令行自检
# ============================================================

def _print_profiles() -> None:
    print("=" * 70)
    print("可用模型档案")
    print("=" * 70)
    for name, p in PROFILES.items():
        mark = " ← 默认" if name == DEFAULT_PROFILE else ""
        print(f"\n[{name}]{mark}")
        print(f"  厂商     : {p['vendor']}")
        print(f"  型号     : {p['model']}")
        print(f"  接口     : {p['base_url'].rstrip('/') + '/chat/completions'}")
        print(f"  密钥变量 : {p['api_key_env'] or '（不需要）'}")
        print(f"  说明     : {p['note']}")
    print()


def _selftest(live: bool) -> int:
    provider = ModelProvider.from_env()
    print("=" * 70)
    print("FinCheck 模型接入自检")
    print("=" * 70)
    print(provider.cfg.display())
    print("-" * 70)

    if not provider.cfg.has_key():
        print("结果：配置结构正确，但未配置密钥，已跳过实网调用。")
        print("     这不影响开发——所有不需要模型的模块都可正常运行。")
        print("     配置密钥后执行：python src/agent/model_provider.py --live")
        print("=" * 70)
        return 0

    if not live:
        print("结果：配置结构正确，密钥已就位。")
        print("     如需实网连通性测试，请加参数 --live")
        print("=" * 70)
        return 0

    print("正在发起实网测试请求 ...")
    started = time.time()
    try:
        reply = provider.chat(
            [{"role": "user", "content": "只回复两个字：正常"}],
            max_tokens=16,
        )
    except Exception as exc:
        print(f"结果：实网调用失败 —— {exc}")
        print("=" * 70)
        return 1
    elapsed = time.time() - started
    print(f"结果：实网调用成功，耗时 {elapsed:.1f} 秒")
    print(f"模型回复：{reply.strip()}")
    print(f"溯源信息：{json.dumps(provider.info(), ensure_ascii=False)}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--list" in args:
        _print_profiles()
        sys.exit(0)
    sys.exit(_selftest(live="--live" in args))
