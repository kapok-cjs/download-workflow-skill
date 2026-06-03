#!/usr/bin/python3
"""检查 GPU 服务器上缺失的 ComfyUI 自定义节点，记录到 mission_node.json"""

import json
import os
import sys

import paramiko
from paramiko.ssh_exception import AuthenticationException


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.environ.get("WORKDIR", os.path.join(SCRIPT_DIR, "..", "work"))
WORKFLOW_DIR = os.path.join(WORK_DIR, "workflow")
OUTPUT_FILE = os.path.join(WORK_DIR, "mission_node.json")

# GPU 服务器自定义节点默认目录
CUSTOM_NODES_DIR = "/data/partner/laimiaoai/custom_nodes"

# ComfyUI 内置节点类型（不需要作为自定义节点安装）
BUILTIN_NODES = {
    "CheckpointLoader", "CheckpointLoaderSimple",
    "VAELoader", "VAEDecode", "VAEDecodeTiled", "VAEEncode", "VAEEncodeTiled",
    "VAEEncodeForInpaint",
    "CLIPLoader", "DualCLIPLoader", "CLIPVisionLoader", "CLIPVisionEncode",
    "CLIPTextEncode", "CLIPSetLastLayer",
    "UNETLoader", "UNETCrossAttnDownscale",
    "DiffusionLoader",
    "ControlNetLoader", "ControlNetApply", "ControlNetApplyAdvanced",
    "ControlNetInpaintingAliMamaApply",
    "LoraLoader", "LoraLoaderModelOnly",
    "GLIGENLoader", "GLIGENTextBoxApply",
    "StyleModelLoader", "StyleModelApply",
    "UpscaleModelLoader", "ImageUpscaleWithModel",
    "KSampler", "KSamplerAdvanced", "KSamplerSelect",
    "SamplerCustom", "SamplerCustomAdvanced",
    "LoadImage", "SaveImage", "PreviewImage",
    "LoadVideo", "SaveAnimatedWEBP", "SaveAnimatedPNG",
    "EmptyLatentImage", "LatentFromBatch", "RepeatLatentBatch",
    "LatentComposite", "LatentCompositeMasked", "LatentBlend",
    "LatentUpscale", "LatentUpscaleBy",
    "ImageScale", "ImageScaleBy", "ImageScaleToTotalPixels",
    "ImageInvert", "ImageBlend", "ImageCompositeMasked",
    "ImageBatch", "ImageFromBatch",
    "CropMask", "InvertMask", "GrowMask", "MaskComposite",
    "SolidMask", "ThresholdMask", "FeatherMask",
    "ImageToMask", "MaskToImage",
    "Canny", "HEDPreprocessor", "M-LSDPreprocessor", "LineArtPreprocessor",
    "OpenposePreprocessor", "DepthAnythingPreprocessor", "Zoe-DepthMapPreprocessor",
    "MiDaS-DepthMapPreprocessor", "DWPreprocessor",
    "TilePreprocessor", "BAE-NormalMapPreprocessor",
    "ConditioningCombine", "ConditioningConcat", "ConditioningAverage",
    "ConditioningSetArea", "ConditioningSetMask",
    "ConditioningZeroOut", "ConditioningSetTimestepRange",
    "CLIPTextEncodeSDXL", "CLIPTextEncodeSDXLRefiner",
    "FreeU", "FreeU_V2",
    "ModelMergeSimple", "ModelMergeBlocks",
    "HypernetworkLoader", "HypernetworkLoader|pysssss",
    "PatchModelAddDownscale", "Reroute", "PrimitiveNode",
    "Note", "SetNode", "GetNode",
    "String", "StringMultiline", "Int", "Float", "Bool",
    "VHS_LoadVideo", "VHS_VideoCombine", "VHS_LoadVideoPath",
}


def parse_workflow_nodes():
    """扫描 workflow 目录下所有 JSON，提取所有自定义节点类型"""
    if not os.path.isdir(WORKFLOW_DIR):
        print(f"目录不存在: {WORKFLOW_DIR}")
        return {}

    json_files = [f for f in os.listdir(WORKFLOW_DIR) if f.endswith(".json")]
    if not json_files:
        print(f"目录下无 JSON 文件: {WORKFLOW_DIR}")
        return {}

    node_files = {}   # node_type -> set of workflow filenames
    builtin_count = 0

    for fname in json_files:
        filepath = os.path.join(WORKFLOW_DIR, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  跳过 {fname}: {e}")
            continue

        nodes = data.get("nodes", [])
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                ntype = node.get("type", "")
                if not ntype:
                    continue
                if ntype in BUILTIN_NODES:
                    builtin_count += 1
                    continue
                node_files.setdefault(ntype, set()).add(fname)

    print(f"扫描 {len(json_files)} 个工作流，发现 {len(node_files)} 个自定义节点类型 (内置 {builtin_count} 个已过滤)\n")

    return node_files


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
        sys.exit("SSH 认证失败")
    except Exception as e:
        sys.exit(f"SSH 连接失败: {e}")


def check_remote_nodes(ssh_client, node_types):
    """在 GPU 服务器上检查哪些自定义节点类型已存在（一次批量提取所有类名）"""
    node_set = set(node_types)
    existing = set()
    remote_classes = set()

    print("  正在提取服务器上所有自定义节点类名...")
    cmd = (
        f"find {CUSTOM_NODES_DIR} -name '*.py' "
        f"-exec grep -oP '(?<=^class )\\w+' {{}} \\; 2>/dev/null | sort -u"
    )
    _, stdout, stderr = ssh_client.exec_command(cmd, timeout=60)
    remote_classes = set(stdout.read().decode().splitlines())

    print(f"  已从服务器提取 {len(remote_classes)} 个类名")
    print(f"  交叉比对 {len(node_set)} 个目标节点...\n")

    for ntype in node_set:
        if ntype in remote_classes:
            existing.add(ntype)

    return existing


def main():
    print("=" * 60)
    print("  ComfyUI 自定义节点缺失检测")
    print("=" * 60 + "\n")

    # 1. 解析工作流获取自定义节点
    node_files = parse_workflow_nodes()
    if not node_files:
        print("未发现自定义节点")
        return

    print("自定义节点列表:")
    for ntype in sorted(node_files.keys()):
        wfs = node_files[ntype]
        print(f"  {ntype}  (引用自: {', '.join(sorted(wfs)[:3])}{'...' if len(wfs) > 3 else ''})")
    print()

    # 2. 连接 GPU 服务器
    host, port, user, pwd = ssh_input()
    print()
    ssh = ssh_connect(host, port, user, pwd)

    # 3. 检查远程节点
    print(f"正在检查 GPU 服务器上已有节点 (目录: {CUSTOM_NODES_DIR})...\n")
    existing = check_remote_nodes(ssh, node_files.keys())
    ssh.close()

    # 4. 计算缺失
    missing_nodes = {}
    for ntype, wfs in node_files.items():
        if ntype not in existing:
            missing_nodes[ntype] = list(wfs)

    if not missing_nodes:
        print("所有自定义节点已存在于 GPU 服务器上。")
        result = {"status": "complete", "missing": {}}
    else:
        print(f"\n缺失 {len(missing_nodes)} 个自定义节点:\n")
        for ntype in sorted(missing_nodes.keys()):
            wfs = missing_nodes[ntype]
            print(f"  {ntype}")
            print(f"    → 引用工作流: {', '.join(wfs[:3])}{'...' if len(wfs) > 3 else ''}")
        print()

        result = {
            "status": "missing",
            "server": host,
            "custom_nodes_dir": CUSTOM_NODES_DIR,
            "missing": {
                ntype: {
                    "workflows": wfs,
                    "install_dir": CUSTOM_NODES_DIR,
                }
                for ntype, wfs in missing_nodes.items()
            }
        }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"已保存到 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
