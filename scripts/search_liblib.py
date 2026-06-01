#!/usr/bin/env python3
"""搜索 哩布哩布(liblib.art) 工作流，自动翻页，保存到 liblib_workflow.json"""

import requests
import sys
import json
import os
import time
import uuid


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "..", "workflow", "liblib_workflow.json")

SEARCH_URL = "https://api2.liblib.art/api/www/comfy/search"


def search_workflow(keyword, page=1, page_size=30):
    """搜索 liblib 工作流，返回 data 字段"""
    timestamp_ms = str(int(time.time() * 1000))
    url = f"{SEARCH_URL}?timestamp={timestamp_ms}"

    payload = {
        "time": "",
        "keyword": keyword,
        "tagIds": [],
        "followed": 0,
        "liked": 0,
        "page": page,
        "pageSize": page_size,
        "requestId": str(uuid.uuid4()),
        "cid": f"{timestamp_ms}akipxwfs",
        "imageUrl": ""
    }
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://www.liblib.art",
        "Referer": "https://www.liblib.art/"
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            print(f"API 返回错误: code={data.get('code')}, msg={data.get('msg')}")
            return None
        return data["data"]
    except requests.RequestException as e:
        print(f"请求失败: {e}")
        return None


def fetch_all(keyword, page_size=30):
    """自动翻页获取全部结果"""
    all_records = []
    page = 1
    while True:
        print(f"正在获取第 {page} 页...", end=" ")
        data = search_workflow(keyword, page=page, page_size=page_size)
        if not data:
            print("获取失败，停止翻页")
            break
        records = data.get("data", [])
        all_records.extend(records)
        total = int(data.get("total", 0))
        print(f"获取 {len(records)} 条 (累计 {len(all_records)}/{total})")
        if not data.get("hasMore") or len(records) == 0:
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

    output = []
    for r in records:
        images = r.get("images", [])
        cover_url = r.get("imageUrl", "")
        output.append({
            "id": r["id"],
            "uuid": r.get("uuid", ""),
            "name": r.get("name", ""),
            "description": r.get("description", ""),
            "modelTypeName": r.get("modelTypeName", ""),
            "author": r.get("nickname", ""),
            "authorId": r.get("userId", 0),
            "authorUuid": r.get("userUuid", ""),
            "likeCount": r.get("likeCount", 0),
            "downloadCount": r.get("downloadCount", 0),
            "runCount": r.get("runCount", 0),
            "heat": r.get("heat", 0),
            "imageUrl": cover_url,
            "width": r.get("width", 0),
            "height": r.get("height", 0),
            "publishTime": r.get("auditTime") or r.get("createTime"),
            "versionId": r.get("versionId"),
            "versionUuid": r.get("versionUuid"),
            "isPackaged": r.get("isPackaged", 0),
            "openAccess": r.get("openAccess", 0),
            "tags": _extract_tags(r),
        })

    result = {
        "keyword": keyword,
        "total": len(records),
        "workflows": output
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n共 {len(records)} 条结果，已保存到 {OUTPUT_FILE}")


def _extract_tags(r):
    """从 tagsV2 中提取标签名称"""
    tags = []
    tags_v2 = r.get("tagsV2", {})
    for group in tags_v2.values():
        if isinstance(group, list):
            for t in group:
                label = t.get("tagLabel", "")
                if label:
                    tags.append(label)
    return tags


if __name__ == "__main__":
    main()
