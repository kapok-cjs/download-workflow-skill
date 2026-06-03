#!/usr/bin/env python3
"""读取 mission_model.json，通过 Google Custom Search API 搜索模型，保存到 WORK_DIR/modelsearch/"""

import json
import os
import sys
import time

import requests


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.environ.get("WORKDIR", os.path.join(SCRIPT_DIR, "..", "work"))
MISSION_FILE = os.path.join(WORK_DIR, "mission_model.json")
SEARCH_DIR = os.path.join(WORK_DIR, "modelsearch")

GOOGLE_API_URL = "https://www.googleapis.com/customsearch/v1"
MAX_RESULTS = 30


def search_google(query, api_key, cx, start=1):
    """调用 Google Custom Search API，返回 items 列表"""
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "start": start,
        "num": min(10, MAX_RESULTS),
    }

    try:
        resp = requests.get(GOOGLE_API_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            print(f"  API 错误: {data['error'].get('message', 'unknown')}")
            return None
        return data.get("items", [])
    except requests.RequestException as e:
        print(f"  请求失败: {e}")
        return None


def fetch_google_pages(query, api_key, cx):
    """搜索 Google，最多取 MAX_RESULTS 条"""
    all_items = []
    start = 1
    page = 1
    while len(all_items) < MAX_RESULTS:
        items = search_google(query, api_key, cx, start=start)
        if not items:
            break
        all_items.extend(items)
        print(f"    第 {page} 页: {len(items)} 条 (累计 {len(all_items)})")
        if len(items) < 10 or len(all_items) >= MAX_RESULTS:
            break
        start += 10
        page += 1
        time.sleep(1)
    return all_items[:MAX_RESULTS]


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
    """精简搜索结果"""
    return {
        "title": item.get("title"),
        "link": item.get("link"),
        "snippet": item.get("snippet"),
        "displayLink": item.get("displayLink"),
    }


def main():
    models = load_mission()
    if not models:
        return

    print("--- Google Custom Search API 配置 ---")
    api_key = input("  API Key: ").strip()
    if not api_key:
        sys.exit("API Key 不能为空")

    cx = input("  Search Engine ID (cx): ").strip()
    if not cx:
        sys.exit("Search Engine ID 不能为空")

    print(f"\n共 {len(models)} 个缺失模型待搜索 (每个最多 {MAX_RESULTS} 条)\n")

    os.makedirs(SEARCH_DIR, exist_ok=True)

    for i, m in enumerate(models, 1):
        name = m["name"]
        cat = m.get("category", "")

        keyword = os.path.splitext(name)[0]
        if not keyword:
            continue

        # 添加 "safetensors download" 后缀提高精度
        query = f"{keyword} safetensors download"

        print(f"[{i}/{len(models)}] [{cat}] {name}")
        print(f"    搜索关键词: {query}")

        items = fetch_google_pages(query, api_key, cx)

        result = {
            "model_name": name,
            "category": cat,
            "query": query,
            "total": len(items),
            "results": [simplify(it) for it in items]
        }

        safe_name = "".join(c if c.isalnum() or c in " _-." else "_" for c in name)
        outfile = os.path.join(SEARCH_DIR, f"{safe_name}-google.json")
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"    保存 {len(items)} 条结果 -> {outfile}\n")
        time.sleep(1)

    print(f"搜索完成，结果保存在 {SEARCH_DIR}")


if __name__ == "__main__":
    main()
