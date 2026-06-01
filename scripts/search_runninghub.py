#!/usr/bin/env python3
"""搜索 RunningHub 工作流，自动翻页，保存到 runninghub_workflow.json"""

import requests
import sys
import json
import os


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "..", "workflow", "runninghub_workflow.json")


def search_workflow(keyword, size=30, page=1):
    url = "https://www.runninghub.cn/api/search/workflow"
    payload = {
        "size": size,
        "current": page,
        "search": keyword,
        "tags": [],
        "sort": ""
    }
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            print(f"API 返回错误: {data.get('msg', '未知错误')}")
            return None
        return data["data"]
    except requests.RequestException as e:
        print(f"请求失败: {e}")
        return None


def fetch_all(keyword, size=30):
    """自动翻页获取全部结果"""
    all_records = []
    page = 1
    while True:
        print(f"正在获取第 {page} 页...", end=" ")
        data = search_workflow(keyword, size=size, page=page)
        if not data:
            print("获取失败，停止翻页")
            break
        records = data.get("records", [])
        all_records.extend(records)
        total = int(data.get("total", 0))
        print(f"获取 {len(records)} 条 (累计 {len(all_records)}/{total})")
        if not data.get("hasNext") or len(records) == 0:
            break
        page += 1
    return all_records


def main():
    if len(sys.argv) > 1:
        keyword = " ".join(sys.argv[1:])
    else:
        keyword = input("请输入搜索关键词: ").strip()

    if not keyword:
        print("关键词不能为空")
        sys.exit(1)

    print(f"\n搜索关键词: {keyword}\n")

    records = fetch_all(keyword)

    if not records:
        print("无搜索结果")
        return

    # 构建精简的输出数据
    output = []
    for r in records:
        covers = r.get("covers", [])
        preview = r.get("preview")
        tags = r.get('tags', [])
        tags = [t['name'] for t in tags] if tags else []
        output.append({
            "id": r["id"],
            "name": r["name"],
            "desc": r.get("desc", ""),
            "author": r["owner"]["name"],
            "authorId": r["owner"]["id"],
            "labels": r.get("labels", ""),
            "useCount": r["statisticsInfo"]["useCount"],
            "likeCount": r["statisticsInfo"]["likeCount"],
            "downloadCount": r["statisticsInfo"]["downloadCount"],
            "publishTime": r.get("publishTime"),
            "covers": [{"url": c["thumbnailUri"]} for c in covers] if covers else [],
            "preview": preview["thumbnailUri"] if preview else None,
            "tags": tags,
        })

    result = {
        "keyword": keyword,
        "total": len(records),
        "workflows": output
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n共 {len(records)} 条结果，已保存到 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
