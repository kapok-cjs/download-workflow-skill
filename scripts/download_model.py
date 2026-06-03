#!/usr/bin/python3
"""读取 mission_model.json，在 GPU 服务器上 wget 下载缺失模型"""

import json
import os
import sys
import time
from urllib.parse import urlparse

import paramiko
from paramiko.ssh_exception import AuthenticationException


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.environ.get("WORKDIR", os.path.abspath(os.path.join(SCRIPT_DIR, "..", "work")))
WORKFLOW_DIR = os.path.join(WORK_DIR, "workflow")
MISSION_FILE = os.path.join(WORK_DIR, "mission_model.json")

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

# ComfyUI 节点类型 -> (模型类别, 索引)
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

# 跳过下载的平台内置域名
SKIP_DOMAINS = {"liblib.art", "runninghub.cn", "liblib.cloud", "liblibai-online.liblib.cloud"}


def parse_workflow_files(workflow_dir=None):
    """扫描 workflow 目录下所有 JSON，提取模型引用"""
    if workflow_dir is None:
        workflow_dir = WORKFLOW_DIR
    models = {}

    if not os.path.isdir(workflow_dir):
        print(f"工作流目录不存在: {workflow_dir}")
        return models

    json_files = [f for f in os.listdir(workflow_dir) if f.endswith(".json")]
    if not json_files:
        print(f"工作流目录下无 JSON 文件: {workflow_dir}")
        return models

    print(f"扫描 {len(json_files)} 个工作流文件...\n")

    for fname in json_files:
        filepath = os.path.join(workflow_dir, fname)
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
    result = {}
    nodes = data.get("nodes", [])
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            _extract_from_node(node, result)

    for key in ("checkpoint", "ckpt", "vae", "lora"):
        if key in data:
            val = data[key]
            if isinstance(val, str) and val:
                cat = "checkpoints" if key in ("checkpoint", "ckpt") else key
                result.setdefault(cat, set()).add(val)

    return result


def _extract_from_node(node, result):
    ntype = node.get("type", "")
    wvals = node.get("widgets_values", [])

    if ntype in NODE_MODEL_MAP:
        cat, idx = NODE_MODEL_MAP[ntype]
        if isinstance(wvals, list) and len(wvals) > idx:
            name = wvals[idx]
            if name and isinstance(name, str):
                result.setdefault(cat, set()).add(name)
        return

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


def load_mission():
    """读取 mission_model.json"""
    if not os.path.exists(MISSION_FILE):
        print(f"文件不存在: {MISSION_FILE}")
        print("请先运行 missing_model_gpuserver.py 和 analysis_mission_model.py")
        return None
    with open(MISSION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_download_list(mission):
    """从 mission_model.json 提取待下载列表（有url且非平台域名）"""
    missing = mission.get("missing", {})
    download_list = []

    for cat, entries in missing.items():
        remote_dir = MODEL_DIR_MAP.get(cat)
        if not remote_dir:
            print(f"  [跳过] 未知类别 {cat}")
            continue

        for entry in entries:
            name = entry.get("name", "")
            url = entry.get("url", "")
            source = entry.get("source", "")

            if not url:
                continue

            # 跳过平台内置来源
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if any(skip in domain for skip in SKIP_DOMAINS):
                print(f"  [跳过-平台源] {name} -> {source}")
                continue

            download_list.append({
                "name": name,
                "url": url,
                "category": cat,
                "remote_dir": remote_dir,
                "source": source,
            })

    return download_list


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


def wget_download(ssh_client, name, url, remote_dir):
    """在 GPU 服务器上执行 wget -c 断点续传下载"""
    filepath = f"{remote_dir}/{name}"
    cmd = f"wget -c -O '{filepath}' '{url}'"
    print(f"  wget -c -O '{filepath}'")
    stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=3600)
    exit_code = stdout.channel.recv_exit_status()
    if exit_code == 0:
        print(f"  下载完成")
        return True
    else:
        err = stderr.read().decode()[:300]
        print(f"  下载失败 (exit={exit_code}): {err}")
        return False


def main():
    print("=" * 60)
    print("  模型下载工具 (基于 mission_model.json)")
    print("=" * 60 + "\n")

    # 1. 加载 mission_model.json
    mission = load_mission()
    if not mission:
        return

    if mission.get("status") != "missing":
        print("mission_model.json 状态不是 missing，无需下载")
        return

    # 2. 构建下载列表
    download_list = build_download_list(mission)

    if not download_list:
        print("没有可下载的模型（所有 URL 为空或来自平台内置源）")
        return

    # 3. 打印待下载清单
    print(f"待下载 {len(download_list)} 个模型:\n")
    for item in download_list:
        print(f"  [{item['category']}] {item['name']}")
        print(f"    url: {item['url'][:100]}...")
        print(f"    source: {item['source']}")
        print(f"    dir: {item['remote_dir']}")
        print()

    answer = input("确认开始下载？(y/n): ").strip().lower()
    if answer != "y":
        return

    # 4. 连接 GPU 服务器
    host, port, user, pwd = ssh_input()
    print()
    ssh = ssh_connect(host, port, user, pwd)

    # 5. 下载
    ok = fail = 0
    for i, item in enumerate(download_list, 1):
        name = item["name"]
        url = item["url"]
        remote_dir = item["remote_dir"]
        cat = item["category"]

        print(f"[{i}/{len(download_list)}] [{cat}] {name}")

        # 确保目录存在
        ssh.exec_command(f"mkdir -p '{remote_dir}'")

        # 检查是否已存在
        _, stdout, _ = ssh.exec_command(f"test -f '{remote_dir}/{name}' && echo EXISTS || echo MISSING")
        if stdout.read().decode().strip() == "EXISTS":
            print(f"  已存在，跳过")
            continue

        if wget_download(ssh, name, url, remote_dir):
            ok += 1
        else:
            fail += 1
        time.sleep(0.5)

    print(f"\n完成: 成功 {ok} 个, 失败 {fail} 个")
    ssh.close()


if __name__ == "__main__":
    main()
