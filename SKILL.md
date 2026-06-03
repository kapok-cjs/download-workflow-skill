---
name: download-workflow-skill
description: 从runninghub.cn、liblib.art下载comfyui工作流。在用户提到下载工作流时使用。
author: cjs@kapokcloud.com
version: 0.0.1
platforms: [linux, macos, windows]
metadata:
    hermes:
        tags: [comfyui, workflow, runninghub, liblib]
        related_skills: []
---

# 下载工作流

从runninghub.cn、liblib.art下载comfyui工作流，上传到来秒AI团队空间协作，自动下载缺失model模型，并解决缺少的节点。

## 工作流程

1.  **用户提供关键词**
2.  **智能体询问**: "成果工作目录指向？"
3.  **智能体询问**："使用liblib.art搜索还是running.cn搜索？"
4.  **liblib.art** -> `python3 scripts/search_workflow_liblib.py`、`python3 scripts/download_workflow_liblib.py` 、`python3 scripts/missing_model_gpuserver.py`、`python3 scripts/search_model_liblib.py`、`python3 scripts/search_model_google.py`、`python3 scripts/analysis_mission_model.py`、`python3 scripts/download_model_liblib.py`、`python3 scripts/download_model.py`、`python3 scripts/mission_node_gpuserver.py`、`python3 scripts/download_node.py`
5.  **runninghub.cn** -> `python3 scripts/search_workflow_runninghub.py`、`python3 scripts/download_workflow_runninghub.py`、`python3 scripts/missing_model_gpuserver.py`、`python3 scripts/search_model_runninghub.py`、`python3 scripts/search_model_google.py`、`python3 scripts/analysis_mission_model.py`、`python3 scripts/download_model_runninghub.py`、`python3 scripts/download_model.py`、`python3 scripts/mission_node_gpuserver.py`、`python3 scripts/download_node.py`

## scripts

* `scripts/search_workflow_liblib.py` - 搜索工作流liblib.art
* `scripts/search_workflow_runninghub.py` - 搜索工作流runninghub.cn
* `scripts/download_workflow_liblib.py` - 下载liblib工作流
* `scripts/download_workflow_runninghub.py` - 下载runninghub工作流
* `scripts/missing_model_gpuserver.py` - 对比服务器找出缺失模型，需要提供gpu server服务器ssh ip、用户名、密码
* `scripts/search_model_liblib.py` - 搜索模型liblib.art
* `scripts/search_model_runninghub.py` - 搜索模型runninghub.cn
* `scripts/search_model_google.py` - 搜索模型google.com
* `scripts/analysis_mission_model.py` - 分析搜索结果，找出最优下载连接
* `scripts/download_model_liblib.py` - 下载模型liblib.art
* `scripts/download_model_runninghub.py` - 下载模型runninghub.cn
* `scripts/download_model.py` - 下载模型到gpu server
* `scripts/mission_node_gpuserver.py` - 对比服务器找出缺失节点
* `scripts/download_node.py` - 下载安装节点

## 使用说明

```bash
# 搜索runninghub.cn
python3 scripts/search_workflow_runninghub.py "longcat"

# 搜索liblib.art
python3 scripts/search_workflow_liblib.py "longcat"

# 下载runninghub.cn工作流
python3 scripts/download_workflow_runninghub.py

# 下载liblib.art工作流
python3 scripts/download_workflow_liblib.py

# 对比服务器找出缺失模型
python3 scripts/missing_model_gpuserver.py

# 搜索模型liblib.art
python3 scripts/search_model_liblib.py

# 搜索模型runninghub.cn
python3 scripts/search_model_runninghub.py

# 搜索模型google.com
python3 scripts/search_model_google.py

# 分析搜索结果，找出最优下载连接
python3 scripts/analysis_mission_model.py

# 下载模型liblib.art
python3 scripts/download_model_liblib.py

# 下载模型runninghub.cn
python3 scripts/download_model_runninghub.py

# 在远程gpu server上使用wget下载模型
python3 scripts/download_model.py

# 对比服务器找出缺失节点
python3 scripts/mission_node_gpuserver.py

# 下载安装节点
python3 scripts/download_node.py

```

