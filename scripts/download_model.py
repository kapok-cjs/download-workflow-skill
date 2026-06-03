#!/usr/bin/python3
"""分析 ComfyUI workflow JSON，找出缺失模型，通过 SSH 在 GPU 服务器上 wget 下载"""

import json
import os
import sys

import paramiko
from paramiko.ssh_exception import AuthenticationException


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.environ.get("WORKDIR", os.path.abspath(os.path.join(SCRIPT_DIR, "..", "work")))
WORKFLOW_DIR = os.path.join(WORK_DIR, "workflow")
MODEL_URLS_FILE = os.path.join(WORK_DIR, "model_urls.json")

# 模型类型 -> GPU 服务器存放目录
MODEL_DIR_MAP = {
    "checkpoints":     "/data/models/checkpoints",
    "model":           "/data/models/diffusion_models",
    "vae":             "/data/models/vae",
    "loras":           "/data/models/loras",
    "controlnet":      "/data/models/controlnet",
    "upscale_models":  "/data/models/upscale_models",
    "clip":            "/data/models/clip",
    "clip_vision":     "/data/models/clip_vision",
    "gligen":          "/data/models/gligen",
    "style_models":    "/data/models/style_models",
    "embeddings":      "/data/models/embeddings",
}

# ComfyUI 节点类型 -> (模型类别, 模型文件名在 widget_values 中的索引)
NODE_MODEL_MAP = {
    "CheckpointLoaderSimple":       ("checkpoints", 0),
    "CheckpointLoader":             ("checkpoints", 0),
    "VAELoader":                    ("vae", 0),
    "LoraLoader":                   ("loras", 0),
    "LoraLoaderModelOnly":          ("loras", 0),
    "ControlNetLoader":             ("controlnet", 0),
    "UNETLoader":                   ("model", 0),
    "DiffusionLoader":              ("model", 0),
    "CLIPLoader":                   ("clip", 0),
    "DualCLIPLoader":               ("clip", 0),
    "UpscaleModelLoader":           ("upscale_models", 0),
    "GLIGENLoader":                 ("gligen", 0),
    "StyleModelLoader":             ("style_models", 0),
    "CLIPVisionLoader":             ("clip_vision", 0),
}


def load_model_urls():
    """加载 model_urls.json 映射表 {filename: download_url}"""
    if os.path.exists(MODEL_URLS_FILE):
        with open(MODEL_URLS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def parse_workflow_files():
    """扫描 workflow 目录下所有 JSON，提取模型引用"""
    models = {}  # category -> set of filenames

    if not os.path.isdir(WORKFLOW_DIR):
        print(f"工作流目录不存在: {WORKFLOW_DIR}")
        return models

    json_files = [f for f in os.listdir(WORKFLOW_DIR) if f.endswith(".json")]
    if not json_files:
        print(f"工作流目录下无 JSON 文件: {WORKFLOW_DIR}")
        return models

    print(f"扫描 {len(json_files)} 个工作流文件...\n")

    for fname in json_files:
        filepath = os.path.join(WORKFLOW_DIR, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  跳过 {fname}: {e}")
            continue

        file_models = _extract_models(data)
        for cat, names in file_models.items():
            models.setdefault(cat, set()).update(names)

    return models


def _extract_models(data):
    """从单个 workflow JSON 中提取模型引用"""
    result = {}

    # 从 nodes 数组提取
    nodes = data.get("nodes", [])
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            _extract_from_node(node, result)

    # 也从顶层直接获取 (某些导出格式)
    for key in ("checkpoint", "ckpt", "vae", "lora"):
        if key in data:
            val = data[key]
            if isinstance(val, str) and val:
                cat = "checkpoints" if key in ("checkpoint", "ckpt") else key
                result.setdefault(cat, set()).add(val)

    return result


def _extract_from_node(node, result):
    """从单个节点提取模型名"""
    ntype = node.get("type", "")
    wvals = node.get("widgets_values", [])

    # 精确匹配
    if ntype in NODE_MODEL_MAP:
        cat, idx = NODE_MODEL_MAP[ntype]
        if isinstance(wvals, list) and len(wvals) > idx:
            name = wvals[idx]
            if name and isinstance(name, str):
                result.setdefault(cat, set()).add(name)
        return

    # 模糊匹配：节点类型包含关键词
    ntype_lower = ntype.lower()
    if "lora" in ntype_lower:
        if isinstance(wvals, list) and len(wvals) > 0 and isinstance(wvals[0], str):
            result.setdefault("loras", set()).add(wvals[0])
    elif "controlnet" in ntype_lower and "apply" not in ntype_lower:
        if isinstance(wvals, list) and len(wvals) > 0 and isinstance(wvals[0], str):
            result.setdefault("controlnet", set()).add(wvals[0])
    elif "vae" in ntype_lower:
        if isinstance(wvals, list) and len(wvals) > 0 and isinstance(wvals[0], str):
            result.setdefault("vae", set()).add(wvals[0])
    elif "checkpoint" in ntype_lower or "ckpt" in ntype_lower:
        if isinstance(wvals, list) and len(wvals) > 0 and isinstance(wvals[0], str):
            result.setdefault("checkpoints", set()).add(wvals[0])


def ssh_input():
    """交互获取 GPU 服务器 SSH 信息"""
    print("--- GPU 服务器 SSH 信息 ---")
    host = input("  IP 地址: ").strip()
    if not host:
        sys.exit("IP 地址不能为空")

    port_str = input("  端口号 [22]: ").strip()
    port = int(port_str) if port_str else 22

    user = input("  用户名: ").strip()
    if not user:
        sys.exit("用户名不能为空")

    pwd = input("  密码: ").strip()
    if not pwd:
        sys.exit("密码不能为空")

    return host, port, user, pwd


def ssh_connect(host, port, user, pwd):
    """建立 SSH 连接"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, port=port, username=user, password=pwd, timeout=15)
        print(f"已连接到 {host}\n")
        return client
    except AuthenticationException:
        sys.exit("SSH 认证失败，请检查用户名和密码")
    except Exception as e:
        sys.exit(f"SSH 连接失败: {e}")


def check_remote_models(ssh_client, models):
    """检查 GPU 服务器上已存在的模型文件"""
    existing = {}  # category -> set of existing filenames

    for cat, names in models.items():
        remote_dir = MODEL_DIR_MAP.get(cat)
        if not remote_dir:
            print(f"  [跳过] 未知类别 {cat} -> 无对应目录")
            continue

        existing.setdefault(cat, set())

        for name in names:
            path = f"{remote_dir}/{name}"
            _, stdout, _ = ssh_client.exec_command(f"test -f '{path}' && echo EXISTS || echo MISSING")
            output = stdout.read().decode().strip()
            if output == "EXISTS":
                existing[cat].add(name)

    return existing


def wget_download(ssh_client, cat, name, url, remote_dir):
    """在 GPU 服务器上执行 wget -c 断点续传下载"""
    filepath = f"{remote_dir}/{name}"
    cmd = f"wget -c -O '{filepath}' '{url}'"
    print(f"    执行: wget -c -O '{filepath}' ...")
    stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=1200)
    exit_code = stdout.channel.recv_exit_status()
    if exit_code == 0:
        print(f"    下载完成")
        return True
    else:
        err = stderr.read().decode()[:200]
        print(f"    下载失败 (exit={exit_code}): {err}")
        return False


def main():
    print("=" * 60)
    print("ComfyUI 模型缺失检测 & GPU 服务器下载工具")
    print("=" * 60 + "\n")

    # 1. 解析工作流文件
    models = parse_workflow_files()
    if not models:
        print("未找到任何模型引用")
        return

    total_models = sum(len(v) for v in models.values())
    print(f"共提取到 {total_models} 个模型引用：")
    for cat in sorted(models.keys()):
        names = sorted(models[cat])
        print(f"  [{cat}] ({len(names)} 个)")
        for n in names:
            print(f"    - {n}")
    print()

    # 2. 连接 GPU 服务器
    host, port, user, pwd = ssh_input()
    print()
    ssh = ssh_connect(host, port, user, pwd)

    # 3. 检查远程已有模型
    print("正在检查 GPU 服务器上已有模型...\n")
    existing = check_remote_models(ssh, models)

    # 4. 计算缺失
    missing = {}
    for cat, names in models.items():
        exist_set = existing.get(cat, set())
        miss = [n for n in names if n not in exist_set]
        if miss:
            missing[cat] = sorted(miss)

    if not missing:
        print("所有模型已存在于 GPU 服务器上，无需下载。")
        ssh.close()
        return

    miss_total = sum(len(v) for v in missing.values())
    print("缺失模型列表:")
    for cat in sorted(missing.keys()):
        remote_dir = MODEL_DIR_MAP.get(cat, "???")
        print(f"  [{cat}] -> {remote_dir}")
        for n in missing[cat]:
            print(f"    - {n}")
    print(f"\n共缺失 {miss_total} 个模型\n")

    # 5. 尝试匹配 model_urls.json 中的下载链接
    url_map = load_model_urls()
    matched = {}
    unmatched = {}
    for cat, names in missing.items():
        for n in names:
            if n in url_map:
                matched.setdefault(cat, []).append((n, url_map[n]))
            else:
                unmatched.setdefault(cat, []).append(n)

    if unmatched:
        print("以下模型无下载链接，请在 model_urls.json 中补充：")
        print(f"  文件位置: {MODEL_URLS_FILE}\n")
        for cat, names in unmatched.items():
            for n in names:
                print(f'  "{n}": "",  [{cat}]')
        print()

    if not matched:
        print("没有可下载的模型，请先配置 model_urls.json")
        ssh.close()
        return

    # 6. 下载
    print("开始下载缺失模型（wget 断点续传）...\n")
    ok = fail = 0
    for cat, items in matched.items():
        remote_dir = MODEL_DIR_MAP.get(cat)
        if not remote_dir:
            print(f"跳过未知类别 {cat}")
            continue
        # 确保目录存在
        ssh.exec_command(f"mkdir -p '{remote_dir}'")
        for name, url in items:
            print(f"  [{cat}] {name}")
            if wget_download(ssh, cat, name, url, remote_dir):
                ok += 1
            else:
                fail += 1

    print(f"\n完成: 成功 {ok} 个, 失败 {fail} 个")
    ssh.close()


if __name__ == "__main__":
    main()
