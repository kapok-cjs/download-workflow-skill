#!/usr/bin/env python3
"""读取 mission_model.json，在 runninghub.cn 搜索模型，保存到 WORK_DIR/modelsearch/"""

import requests
import sys
import json
import os
import time


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.environ.get("WORKDIR", os.path.join(SCRIPT_DIR, "..", "work"))
MISSION_FILE = os.path.join(WORK_DIR, "mission_model.json")
SEARCH_DIR = os.path.join(WORK_DIR, "modelsearch")

SEARCH_URL = "https://www.runninghub.cn/api/search/model"
PAGE_SIZE = 30
MAX_PAGES = 3


def search_model(keyword, page=1):
    """搜索 runninghub 模型，返回 data 字段"""
    payload = {
        "size": PAGE_SIZE,
        "current": page,
        "tags": None,
        "resourceType": "",
        "baseModels": [],
        "search": keyword,
        "systemResource": None,
    }
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": "Mozilla/5.0",
    }

    try:
        resp = requests.post(SEARCH_URL, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            msg = data.get("msg", "unknown")
            print(f"  API 错误: code={data.get('code')}, msg={msg}")
            return None
        return data["data"]
    except requests.RequestException as e:
        print(f"  请求失败: {e}")
        return None


def fetch_model_pages(keyword):
    """搜索模型，最多取 MAX_PAGES 页"""
    all_items = []
    for page in range(1, MAX_PAGES + 1):
        data = search_model(keyword, page=page)
        if not data:
            break
        items = data.get("records", [])
        all_items.extend(items)
        total = int(data.get("total", 0))
        print(f"    第 {page} 页: {len(items)} 条 (累计 {len(all_items)}/{total})")
        if not data.get("hasNext") or len(items) == 0:
            break
        time.sleep(0.3)
    return all_items


def load_mission():
    """从 mission_model.json 读取缺失模型列表"""
    if not os.path.exists(MISSION_FILE):
        print(f"文件不存在: {MISSION_FILE}")
        print("请先运行 missing_model_gpuserver.py 生成缺失模型列表")
        return []
    with open(MISSION_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("status") != "missing":
        print("mission_model.json 中无缺失模型")
        return []
    models = []
    for cat, entries in data.get("missing", {}).items():
        for entry in entries:
            models.append({"name": entry["name"], "category": cat, "dir": entry.get("dir", "")})
    return models


def simplify(item):
    """精简搜索结果，只保留关键字段"""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "desc": item.get("desc", ""),
        "modelTypeName": item.get("modelTypeName"),
        "labels": item.get("labels", ""),
        "author": item.get("owner", {}).get("name") if item.get("owner") else None,
        "useCount": item.get("statisticsInfo", {}).get("useCount", 0) if item.get("statisticsInfo") else 0,
        "likeCount": item.get("statisticsInfo", {}).get("likeCount", 0) if item.get("statisticsInfo") else 0,
        "downloadCount": item.get("statisticsInfo", {}).get("downloadCount", 0) if item.get("statisticsInfo") else 0,
        "publishTime": item.get("publishTime"),
        "covers": [{"url": c["thumbnailUri"]} for c in item.get("covers", [])] if item.get("covers") else [],
        "tags": [t["name"] for t in item.get("tags", [])] if item.get("tags") else [],
    }


def main():
    models = load_mission()
    if not models:
        return

    print(f"共 {len(models)} 个缺失模型待搜索 (每个最多 {MAX_PAGES} 页)\n")

    os.makedirs(SEARCH_DIR, exist_ok=True)

    for i, m in enumerate(models, 1):
        name = m["name"]
        cat = m.get("category", "")

        keyword = os.path.splitext(name)[0]
        if not keyword:
            continue

        print(f"[{i}/{len(models)}] [{cat}] {name}")
        print(f"    搜索关键词: {keyword}")

        items = fetch_model_pages(keyword)

        result = {
            "model_name": name,
            "category": cat,
            "keyword": keyword,
            "total": len(items),
            "results": [simplify(it) for it in items]
        }

        safe_name = "".join(c if c.isalnum() or c in " _-." else "_" for c in name)
        outfile = os.path.join(SEARCH_DIR, f"{safe_name}-runninghub.json")
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"    保存 {len(items)} 条结果 -> {outfile}\n")
        time.sleep(0.5)

    print(f"搜索完成，结果保存在 {SEARCH_DIR}")


if __name__ == "__main__":
    main()
