#!/usr/bin/env python3
"""分析 modelsearch 搜索结果，通过 DeepSeek 大模型推理最优下载链接，更新 mission_model.json"""

import json
import os
import sys
import time

import requests


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.environ.get("WORKDIR", os.path.join(SCRIPT_DIR, "..", "work"))
SEARCH_DIR = os.path.join(WORK_DIR, "modelsearch")
MISSION_FILE = os.path.join(WORK_DIR, "mission_model.json")

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"

SYSTEM_PROMPT = (
    "You are an AI model download specialist. "
    "Given search results for a missing ComfyUI model file, "
    "find the most reliable direct download URL (.safetensors, .ckpt, .pt, .pth). "
    "Prioritize: HuggingFace > CivitAI > other sources. "
    "Return ONLY a valid JSON object with the format below, no extra text."
)

RESPONSE_SCHEMA = """
{
  "found": true,
  "url": "https://huggingface.co/.../resolve/main/model.safetensors",
  "source": "huggingface",
  "confidence": "high",
  "reason": "official HuggingFace repo with direct download link"
}
If no valid download link found, return: {"found": false, "reason": "..."}
"""


def load_mission():
    if not os.path.exists(MISSION_FILE):
        print(f"文件不存在: {MISSION_FILE}")
        return None
    with open(MISSION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_search_results(name):
    """读取三个搜索源的结果"""
    safe_name = "".join(c if c.isalnum() or c in " _-." else "_" for c in name)
    sources = {}

    for src in ("liblib", "runninghub", "google"):
        filepath = os.path.join(SEARCH_DIR, f"{safe_name}-{src}.json")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data.get("results", [])
                if items:
                    sources[src] = items

    return sources


def build_user_prompt(model_name, category, sources):
    """构建发给大模型的提示"""
    parts = [
        f"Missing model: {model_name}",
        f"Category: {category}",
        "",
        "Search results from multiple sources:",
        "",
    ]

    for src, items in sources.items():
        parts.append(f"--- {src} ({len(items)} results) ---")
        for j, item in enumerate(items, 1):
            if src == "google":
                parts.append(f"  [{j}] {item.get('title')}")
                parts.append(f"      link: {item.get('link')}")
                snippet = item.get('snippet') or ''
                parts.append(f"      snippet: {snippet[:200]}")
            else:
                parts.append(f"  [{j}] {item.get('name')} (id={item.get('id')})")
                desc = item.get("desc") or item.get("description", "")
                if desc:
                    parts.append(f"      desc: {desc[:200]}")
                covers = item.get("covers", [])
                for c in covers[:1]:
                    parts.append(f"      cover: {c.get('url', '')}")
                link = item.get("link", "")
                if link:
                    parts.append(f"      link: {link}")
            parts.append("")

    parts.append("Find the best direct download URL for this model file.")
    parts.append(RESPONSE_SCHEMA)
    return "\n".join(parts)


def ask_deepseek(api_key, model_name, category, sources, model=DEEPSEEK_MODEL):
    """调用 DeepSeek API 分析"""
    user_prompt = build_user_prompt(model_name, category, sources)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=60)
        if resp.status_code != 200:
            print(f"  API HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # 移除 markdown 代码块包裹
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content.rsplit("\n", 1)[0]

        return json.loads(content)
    except json.JSONDecodeError:
        print(f"  JSON 解析失败, 原始响应: {content[:300]}")
        return {"found": False, "reason": "JSON parse error", "raw": content[:500]}
    except requests.RequestException as e:
        print(f"  API 请求失败: {e}")
        return None
    except Exception as e:
        print(f"  异常: {e}")
        return None


def main():
    mission = load_mission()
    if not mission or mission.get("status") != "missing":
        print("mission_model.json 中无缺失模型或文件不存在")
        return

    print("--- DeepSeek API 配置 ---")
    api_key = input("  API Key: ").strip()
    if not api_key:
        sys.exit("API Key 不能为空")

    model_choice = input(f"  模型名称 [{DEEPSEEK_MODEL}]: ").strip()
    use_model = model_choice or DEEPSEEK_MODEL

    missing = mission.get("missing", {})
    flat_models = []
    for cat, entries in missing.items():
        for e in entries:
            flat_models.append((cat, e))

    if not flat_models:
        print("无缺失模型")
        return

    print(f"\n共 {len(flat_models)} 个缺失模型待分析\n")

    updated = 0
    for i, (cat, entry) in enumerate(flat_models, 1):
        name = entry["name"]
        print(f"[{i}/{len(flat_models)}] [{cat}] {name}")

        sources = load_search_results(name)
        if not sources:
            print(f"  无搜索结果，跳过\n")
            continue

        src_names = ", ".join(f"{k}({len(v)})" for k, v in sources.items())
        print(f"  已加载搜索数据: {src_names}")
        print(f"  正在分析...")

        result = ask_deepseek(api_key, name, cat, sources, model=use_model)

        if result and result.get("found"):
            url = result.get("url", "")
            entry["url"] = url
            entry["source"] = result.get("source", "unknown")
            entry["confidence"] = result.get("confidence", "")
            print(f"  找到: {url[:80]}...")
            print(f"  来源: {result.get('source')}, 可信度: {result.get('confidence')}")
            print(f"  理由: {result.get('reason', '')[:100]}")
            updated += 1
        elif result:
            print(f"  未找到: {result.get('reason', '')[:100]}")
        else:
            print(f"  分析失败")

        print()
        time.sleep(1)

    # 保存更新后的 mission_model.json
    with open(MISSION_FILE, "w", encoding="utf-8") as f:
        json.dump(mission, f, ensure_ascii=False, indent=2)

    print(f"分析完成: {updated}/{len(flat_models)} 个模型找到下载链接")
    print(f"已更新 {MISSION_FILE}")


if __name__ == "__main__":
    main()
