#!/usr/bin/env python3
"""通过 GitHub Git Database API 推送 git 历史（github.com 被网络阻断时的备用通道）。

适用场景：api.github.com 可达、但 github.com:443 被网络封死（git push 报
"Empty reply from server" / "CONNECT tunnel failed 502" / 连接超时）时。

原理：用 GitHub 官方 Git Data API 按 commit 顺序重建历史——
  blob（文件内容）→ tree（目录结构）→ commit（含原作者/时间/消息）→ 更新 ref
与 git 协议推送结果一致；若 author/committer/message 逐字节复刻成功，
远端 commit SHA 与本地完全相同（输出 SAME 即表示一致）。

用法（在 fincheck 仓库根目录执行）：
    python tools/push_via_api.py            # 推送 main 全部历史
    python tools/push_via_api.py --reset    # 先删远端 main 再推（中途失败重适用）
    python tools/push_via_api.py --dry-run  # 只本地演练，不调 API

token 从仓库根目录 .ghtoken 文件读取（该文件已在 .gitignore，用完即删）。
"""
import base64
import datetime
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
OWNER, REPO, BRANCH = "wlwqgf", "shuyuanqiuzhen", "main"
REPO_ROOT = Path(__file__).resolve().parents[1]
TOKEN_FILE = REPO_ROOT / ".ghtoken"


def sh(args: list, binary: bool = False):
    """在仓库根目录执行 git 命令，返回 stdout。"""
    r = subprocess.run(args, cwd=str(REPO_ROOT), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {r.stderr.decode('utf-8', 'replace')}")
    return r.stdout if binary else r.stdout.decode("utf-8")


def api(method: str, path: str, token: str, payload: dict = None, retry: int = 3):
    """调用 GitHub API，返回 (status, body_dict)。网络抖动与限流自动重试。"""
    url = f"{API}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    for attempt in range(retry):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"token {token}")
        req.add_header("Accept", "application/vnd.github+json")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
                return resp.status, (json.loads(body.decode("utf-8")) if body else {})
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                parsed = json.loads(body.decode("utf-8")) if body else {}
            except json.JSONDecodeError:
                parsed = {"raw": body[:200].decode("utf-8", "replace")}
            if e.code in (403, 429, 500, 502, 503) and attempt < retry - 1:
                time.sleep(4 * (attempt + 1))
                continue
            return e.code, parsed
        except (urllib.error.URLError, TimeoutError):
            if attempt < retry - 1:
                time.sleep(3)
                continue
            raise
    return 0, {}


def parse_ident(line: str) -> dict:
    """解析 'Name <email> 1699999999 +0800' 为 GitHub API 的 author/committer 对象。"""
    m = re.match(r"^(.*) <(.*)> (\d+) ([+-]\d{4})$", line)
    if not m:
        raise ValueError(f"无法解析身份行: {line!r}")
    name, email, ts, tz = m.groups()
    sign = 1 if tz[0] == "+" else -1
    offset = sign * (int(tz[1:3]) * 3600 + int(tz[3:5]) * 60)
    dt = datetime.datetime.fromtimestamp(
        int(ts), tz=datetime.timezone(datetime.timedelta(seconds=offset))
    )
    return {"name": name, "email": email, "date": dt.isoformat()}


def parse_commit(raw: bytes) -> dict:
    """解析 git commit 对象，逐字节保留 message。"""
    text = raw.decode("utf-8")
    head, _, message = text.partition("\n\n")
    info = {"parents": [], "tree": None, "author": None, "committer": None, "message": message}
    for line in head.split("\n"):
        if line.startswith("tree "):
            info["tree"] = line[5:].strip()
        elif line.startswith("parent "):
            info["parents"].append(line[7:].strip())
        elif line.startswith("author "):
            info["author"] = parse_ident(line[7:])
        elif line.startswith("committer "):
            info["committer"] = parse_ident(line[10:])
    return info


def ls_tree(commit: str) -> list:
    """-z 输出按 NUL 切分，避免中文/特殊路径被 git 转义。"""
    out = sh(["git", "ls-tree", "-r", "-z", commit])
    entries = []
    for chunk in out.split("\0"):
        if not chunk:
            continue
        meta, path = chunk.split("\t", 1)
        mode, typ, sha = meta.split()
        entries.append({"mode": mode, "type": typ, "sha": sha, "path": path})
    return entries


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    reset = "--reset" in sys.argv

    if not TOKEN_FILE.exists():
        print(f"错误：未找到 {TOKEN_FILE}（token 文件，gitignore 中，用完即删）")
        return 1
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token.startswith("ghp_"):
        print("错误：token 格式不正确")
        return 1

    commits = sh(["git", "rev-list", "--reverse", "--topo-order", BRANCH]).split()
    print(f"本地 {BRANCH} 分支共 {len(commits)} 个 commit（从旧到新）")
    if dry_run:
        for c in commits:
            info = parse_commit(sh(["git", "cat-file", "commit", c], binary=True))
            files = ls_tree(c)
            print(f"  {c[:8]}  {len(files):3d} 文件  {info['message'].splitlines()[0][:50]}")
        print("dry-run 完成，未调用 API")
        return 0

    # ---- 空仓库处理 ----
    # GitHub 不允许在空仓库直接创建 git 对象（409 Git Repository is empty），
    # 先用 Contents API 建一个初始提交解锁，首个 commit 挂到它下面。
    st, refs = api("GET", f"/repos/{OWNER}/{REPO}/git/refs", token)
    refs_list = refs if isinstance(refs, list) else []
    repo_empty = (st != 200) or (len(refs_list) == 0)
    main_exists = any(r.get("ref") == f"refs/heads/{BRANCH}" for r in refs_list)

    if main_exists and not reset:
        print(f"远端 {BRANCH} 已存在历史，且未指定 --reset；为防止覆盖远端历史，中止。")
        print("确认要重推请执行：python tools/push_via_api.py --reset")
        return 1

    init_sha = None
    if reset and main_exists:
        st, _ = api("DELETE", f"/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}", token)
        print(f"--reset: 删除远端 {BRANCH} -> HTTP {st}（404=原本就不存在，正常）")
        repo_empty = True

    if repo_empty:
        readme_b64 = base64.b64encode(
            "# FinCheck\n\n初始化提交（技术性）：GitHub 不允许在空仓库直接创建 git 对象，\n"
            "此提交用于解锁该限制，随后由 push_via_api.py 经 Git Data API 重建完整历史。\n"
            .encode("utf-8")
        ).decode("ascii")
        st, r = api("PUT", f"/repos/{OWNER}/{REPO}/contents/README.md", token,
                    {"message": "chore: 初始化仓库（API 备用通道解锁空仓库限制）",
                     "content": readme_b64})
        if st != 201:
            print(f"  初始提交失败 -> HTTP {st} {r}")
            return 1
        init_sha = r["commit"]["sha"]
        print(f"空仓库已解锁：初始提交 {init_sha[:8]}（临时 README，随后被正式历史覆盖）")

    blob_cache = {}   # 本地 blob sha -> 远端 blob sha（同内容不重复上传）
    sha_map = {}      # 本地 commit sha -> 远端 commit sha

    for c in commits:
        info = parse_commit(sh(["git", "cat-file", "commit", c], binary=True))
        tree_entries = []
        for e in ls_tree(c):
            if e["type"] == "blob":
                if e["sha"] not in blob_cache:
                    content = sh(["git", "cat-file", "blob", e["sha"]], binary=True)
                    try:
                        text = content.decode("utf-8")
                        payload = {"content": text, "encoding": "utf-8"}
                    except UnicodeDecodeError:
                        payload = {"content": base64.b64encode(content).decode("ascii"),
                                   "encoding": "base64"}
                    st, r = api("POST", f"/repos/{OWNER}/{REPO}/git/blobs", token, payload)
                    if st != 201:
                        print(f"  blob 失败 {e['path']} -> HTTP {st} {r}")
                        return 1
                    blob_cache[e["sha"]] = r["sha"]
                tree_entries.append({"path": e["path"], "mode": e["mode"],
                                     "type": "blob", "sha": blob_cache[e["sha"]]})
            else:
                tree_entries.append({"path": e["path"], "mode": e["mode"],
                                     "type": e["type"], "sha": e["sha"]})

        st, tree = api("POST", f"/repos/{OWNER}/{REPO}/git/trees", token, {"tree": tree_entries})
        if st != 201:
            print(f"  tree 失败 {c[:8]} -> HTTP {st} {tree}")
            return 1

        parents = [sha_map[p] for p in info["parents"]]
        if not parents and init_sha:
            parents = [init_sha]  # 本地首个 commit 无父，挂到初始提交下
        payload = {
            "message": info["message"],
            "tree": tree["sha"],
            "parents": parents,
            "author": info["author"],
            "committer": info["committer"],
        }
        st, commit = api("POST", f"/repos/{OWNER}/{REPO}/git/commits", token, payload)
        if st != 201:
            print(f"  commit 失败 {c[:8]} -> HTTP {st} {commit}")
            return 1
        sha_map[c] = commit["sha"]

        st, _ = api("PATCH", f"/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}", token,
                    {"sha": commit["sha"], "force": True})
        if st != 200:
            st2, r2 = api("POST", f"/repos/{OWNER}/{REPO}/git/refs", token,
                          {"ref": f"refs/heads/{BRANCH}", "sha": commit["sha"]})
            if st2 != 201:
                print(f"  ref 更新失败 {c[:8]} -> PATCH:{st} POST:{st2} {r2}")
                return 1

        match = "SAME" if commit["sha"] == c else f"DIFF(本地 {c[:8]})"
        print(f"  {c[:8]} -> {commit['sha'][:8]}  {match}  {info['message'].splitlines()[0][:44]}")

    print(f"\n完成。远端 {BRANCH} HEAD = {sha_map[commits[-1]]}")
    print(f"上传 blob 缓存 {len(blob_cache)} 个文件内容（跨 commit 去重）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
