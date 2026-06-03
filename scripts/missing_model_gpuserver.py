#!/usr/bin/python3
"""对比 GPU 服务器找出缺失模型，记录到 mission_model.json"""

import json
import os
import sys

import paramiko
from paramiko.ssh_exception import AuthenticationException

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# 复用 download_model 中的共享函数
from download_model import (
    parse_workflow_files,
    MODEL_DIR_MAP,
)

WORK_DIR = os.environ.get("WORKDIR", os.path.join(SCRIPT_DIR, "..", "work"))
WORKFLOW_DIR = os.path.join(WORK_DIR, "workflow")
OUTPUT_FILE = os.path.join(WORK_DIR, "mission_model.json")


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
    existing = {}

    # 对于每个类别的目录，一次性列出已有文件再比对（比逐个 test -f 快得多）
    for cat, names in models.items():
        remote_dir = MODEL_DIR_MAP.get(cat)
        if not remote_dir:
            continue

        existing.setdefault(cat, set())
        _, stdout, _ = ssh_client.exec_command(f"ls -1 '{remote_dir}' 2>/dev/null")
        remote_files = set(stdout.read().decode().splitlines())

        for name in names:
            if name in remote_files:
                existing[cat].add(name)

    return existing


def main():
    print("=" * 60)
    print("  ComfyUI 模型缺失检测")
    print("=" * 60 + "\n")

    # 1. 解析工作流文件
    models = parse_workflow_files()
    if not models:
        print("未找到任何模型引用")
        return

    total_models = sum(len(v) for v in models.values())
    print(f"从工作流中提取到 {total_models} 个模型引用：")
    for cat in sorted(models.keys()):
        names = sorted(models[cat])
        print(f"  [{cat}] {len(names)} 个")
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
    ssh.close()

    # 4. 计算缺失
    missing = {}
    for cat, names in models.items():
        exist_set = existing.get(cat, set())
        miss = [n for n in names if n not in exist_set]
        if miss:
            missing[cat] = sorted(miss)

    # 5. 输出结果并保存
    if not missing:
        print("所有模型已存在于 GPU 服务器上。")
        result = {"status": "complete", "missing": {}}
    else:
        miss_total = sum(len(v) for v in missing.values())
        print(f"缺失 {miss_total} 个模型:\n")
        for cat in sorted(missing.keys()):
            remote_dir = MODEL_DIR_MAP.get(cat, "???")
            print(f"  [{cat}] -> {remote_dir}")
            for n in missing[cat]:
                print(f"    - {n}")
        print()

        result = {
            "status": "missing",
            "server": host,
            "missing": {
                cat: [
                    {"name": n, "dir": MODEL_DIR_MAP.get(cat, ""), "url": ""}
                    for n in names
                ]
                for cat, names in missing.items()
            }
        }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"已保存到 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
