---
name: download-workflow-skill
description: 从runninghub.cn、liblib.art下载comfyui工作流。在用户提到下载工作流时使用。
author: cjs@kapokcloud.com
version: 0.0.1
tags: [comfyui, workflow, runninghub, liblib]
---

# 下载工作流

从runninghub.cn、liblib.art下载comfyui工作流，上传到来秒AI团队空间协作，自动下载缺失model模型，并解决缺少的节点。

## 工作流程

1.  **用户提供关键词**
2. **智能体咨询**："使用liblib.art搜索还是running.cn搜索？"
3. **liblib.art** -> `python3 scripts/search_liblib.py`、`python3 scripts/download_liblib.py`
4. **runninghub.cn** -> `python3 scripts/search_runninghub.py`、`python3 scripts/download_runninghub.py`

## scripts

* `scripts/search_liblib.py` - 搜索liblib.art
* `scripts/search_runninghub.py` - 搜索runninghub.cn
* `scripts/download_liblib.py` - 下载liblib工作流
* `scripts/download_runninghub.py` - 下载runninghub工作流

## 使用说明

```bash
# 搜索runninghub.cn
python3 scripts/search_runninghub.py "longcat"

# 搜索liblib.art
python3 scripts/search_liblib.py "longcat"

# 下载runninghub.cn工作流
python3 scripts/download_runninghub.py

# 下载liblib.art工作流
python3 scripts/download_liblib.py

```

