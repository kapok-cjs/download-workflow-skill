#!/usr/bin/python3
"""读取 mission_node.json，通过 ComfyUI Manager 注册表匹配 GitHub 仓库，SSH 安装到 GPU 服务器"""

import json
import os
import sys
import time

import requests
import paramiko
from paramiko.ssh_exception import AuthenticationException


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.environ.get("WORKDIR", os.path.join(SCRIPT_DIR, "..", "work"))
MISSION_FILE = os.path.join(WORK_DIR, "mission_node.json")

# ComfyUI Manager 社区节点注册表
CN_LIST_URL = "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/custom-node-list.json"

# GitHub 搜索 API（无认证限制 10次/分钟，作为注册表的补漏）
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


def load_mission():
    if not os.path.exists(MISSION_FILE):
        print(f"文件不存在: {MISSION_FILE}")
        return None
    with open(MISSION_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("status") != "missing":
        print("mission_node.json 状态不是 missing，无需安装")
        return None
    return data


def fetch_comfy_registry():
    """拉取 ComfyUI Manager 自定义节点注册表，返回 {node_type: repo_url}"""
    print("正在获取 ComfyUI Manager 节点注册表...")
    try:
        resp = requests.get(CN_LIST_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"  获取失败: {e}")
        return {}

    node_map = {}
    custom_nodes = data.get("custom_nodes", [])
    for entry in custom_nodes:
        reference = entry.get("reference", [])
        if not isinstance(reference, list) or len(reference) < 1:
            continue
        repo_url = reference[0]  # 优先取第一个 git clone URL
        files = entry.get("files", [])
        if not isinstance(files, list):
            continue
        # files 里的每一项是 "https://github.com/.../py/{classname}.py"
        for f in files:
            if not isinstance(f, str):
                continue
            classname = os.path.splitext(os.path.basename(f))[0]
            if classname and not classname.startswith("__"):
                node_map[classname] = repo_url
    print(f"  获取到 {len(node_map)} 条节点映射\n")
    return node_map


def search_github(node_type):
    """GitHub 搜索补漏：搜不到就用注册表没覆盖的节点"""
    params = {
        "q": f"{node_type} comfyui",
        "per_page": 3,
        "sort": "stars",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.github+json",
    }
    try:
        resp = requests.get(GITHUB_SEARCH_URL, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                return items[0]["clone_url"]
    except Exception:
        pass
    return None


def resolve_repos(missing_nodes, registry):
    """将缺失节点映射到 GitHub 仓库 URL"""
    resolved = {}  # repo_url -> [node_types]

    for ntype, info in missing_nodes.items():
        repo = None

        # 1. 先从注册表查找
        if ntype in registry:
            repo = registry[ntype]
            print(f"  [注册表] {ntype} -> {repo}")
        else:
            # 2. GitHub 搜索补漏
            print(f"  [搜索] {ntype} ...", end=" ", flush=True)
            repo = search_github(ntype)
            if repo:
                print(f"found: {repo}")
            else:
                print("未找到")
            time.sleep(2)  # GitHub API 限速

        if repo:
            resolved.setdefault(repo, []).append(ntype)

    return resolved


def ssh_input():
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
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, port=port, username=user, password=pwd, timeout=15)
        print(f"已连接到 {host}\n")
        return client
    except AuthenticationException:
        sys.exit("SSH 认证失败")
    except Exception as e:
        sys.exit(f"SSH 连接失败: {e}")


def install_node_on_server(ssh_client, custom_nodes_dir, repo_url, node_types):
    """在服务器上 git clone 自定义节点仓库"""
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    target_dir = f"{custom_nodes_dir}/{repo_name}"

    # 检查是否已存在
    _, stdout, _ = ssh_client.exec_command(f"test -d '{target_dir}' && echo EXISTS || echo MISSING")
    exists = stdout.read().decode().strip() == "EXISTS"

    node_str = ", ".join(node_types)
    if exists:
        print(f"  [{repo_name}] 已存在，执行 git pull 更新...")
        cmd = f"cd '{target_dir}' && git pull 2>&1"
    else:
        print(f"  [{repo_name}] git clone {repo_url}...")
        cmd = f"cd '{custom_nodes_dir}' && git clone '{repo_url}' 2>&1"

    _, stdout, stderr = ssh_client.exec_command(cmd, timeout=120)
    output = stdout.read().decode()
    err = stderr.read().decode()
    exit_code = stdout.channel.recv_exit_status()

    if exit_code == 0:
        print(f"  完成: {node_str}")
        # 检查是否有 requirements.txt
        req_file = f"{target_dir}/requirements.txt"
        _, so, _ = ssh_client.exec_command(f"test -f '{req_file}' && echo EXISTS || echo MISSING")
        if so.read().decode().strip() == "EXISTS":
            print(f"  检测到 requirements.txt，正在 pip install...")
            _, so2, se2 = ssh_client.exec_command(
                f"pip install -r '{req_file}' 2>&1 | tail -3", timeout=120
            )
            print(f"  {so2.read().decode().strip()}")
        return True
    else:
        print(f"  失败: {err[:200]}")
        return False


def main():
    print("=" * 60)
    print("  ComfyUI 自定义节点安装工具")
    print("=" * 60 + "\n")

    # 1. 加载 mission_node.json
    mission = load_mission()
    if not mission:
        return

    missing = mission.get("missing", {})
    if not missing:
        print("无缺失节点")
        return

    custom_nodes_dir = mission.get("custom_nodes_dir", "/data/partner/laimiaoai/custom_nodes")
    print(f"共 {len(missing)} 个缺失节点")
    print(f"远程安装目录: {custom_nodes_dir}\n")

    # 2. 拉取 ComfyUI Manager 注册表
    registry = fetch_comfy_registry()

    # 3. 解析仓库映射
    print("正在匹配 GitHub 仓库...")
    resolved = resolve_repos(missing, registry)

    if not resolved:
        print("\n未能匹配到任何 GitHub 仓库")
        return

    print(f"\n共匹配到 {len(resolved)} 个仓库，待安装:\n")
    for repo, nodes in resolved.items():
        print(f"  {repo}")
        for n in nodes:
            print(f"    - {n}")
    print()

    answer = input("确认开始安装？(y/n): ").strip().lower()
    if answer != "y":
        return

    # 4. SSH 安装
    host, port, user, pwd = ssh_input()
    print()
    ssh = ssh_connect(host, port, user, pwd)

    ok = fail = 0
    for i, (repo, nodes) in enumerate(resolved.items(), 1):
        print(f"[{i}/{len(resolved)}] {repo}")
        if install_node_on_server(ssh, custom_nodes_dir, repo, nodes):
            ok += 1
        else:
            fail += 1
        print()

    ssh.close()

    print(f"安装完成: 成功 {ok} 个, 失败 {fail} 个\n")
    if ok > 0:
        print("=" * 60)
        print("  请登录 GPU 服务器手动重启 ComfyUI 以加载新节点:")
        print(f"    ssh {user}@{host}")
        print("    # 重启 ComfyUI 服务")
        print("=" * 60)


if __name__ == "__main__":
    main()
