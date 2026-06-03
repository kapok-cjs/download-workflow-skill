#!/usr/bin/python3
"""读取 runninghub_workflow.json，通过浏览器登录获取 token，下载工作流到 ../workflow/"""

import requests
import sys
import json
import os
import time
from playwright.sync_api import sync_playwright


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.environ.get("WORKDIR", os.path.abspath(os.path.join(SCRIPT_DIR, "..", "work")))
INPUT_FILE = os.path.join(WORK_DIR, "runninghub_workflow.json")
USER_DATA_DIR = os.path.join(WORK_DIR, ".playwright_runninghub_data")

EXPORT_URL = "https://www.runninghub.cn/api/workflow/export"
HOME_URL = "https://www.runninghub.cn"


def load_workflows():
    if not os.path.exists(INPUT_FILE):
        print(f"文件不存在: {INPUT_FILE}")
        print("请先运行 search_rh_workflow.py 获取工作流列表")
        sys.exit(1)
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("workflows", [])


def get_token_from_browser():
    """打开浏览器让用户登录，从 localStorage 读取 Rh-Accesstoken"""
    print("正在启动浏览器，请登录 RunningHub...\n")

    with sync_playwright() as p:
        # 持久化上下文，保留登录态
        os.makedirs(USER_DATA_DIR, exist_ok=True)
        context = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        page.goto(HOME_URL, wait_until="domcontentloaded")

        print("请在浏览器中完成登录（支持微信/手机号等方式）")
        print("登录成功后脚本将自动检测到 token 并继续...\n")

        # 轮询等待 localStorage 中出现 Rh-Accesstoken
        token = None
        for _ in range(300):  # 最多等 5 分钟
            try:
                token = page.evaluate("() => localStorage.getItem('Rh-Accesstoken')")
            except Exception:
                pass
            if token:
                break
            time.sleep(1)

        if token:
            print(f"\n已获取 token: {token[:20]}...{token[-10:]}")
        else:
            print("\n超时：未在浏览器 localstorage 中检测到 Rh-Accesstoken")
            print("请确保已登录 runninghub.cn")

        context.close()

    if not token:
        sys.exit(1)

    return token


def download_workflow(token, workflow):
    """下载单个工作流"""
    workflow_id = workflow["id"]
    name = workflow["name"]
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": "Mozilla/5.0",
        "Rh-Accesstoken": token,
    }

    try:
        resp = requests.post(
            EXPORT_URL,
            json={"workflowId": workflow_id},
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}")
            return False

        # 保存响应内容（可能是 JSON 或直接是文件二进制）
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type:
            data = resp.json()
            if data.get("code") != 0:
                print(f"  API 错误: {data.get('msg', '未知')}")
                return False
            # 如果 JSON 中包含文件数据，尝试解析
            file_data = data.get("data")
            if isinstance(file_data, str):
                content = file_data.encode("utf-8")
            elif isinstance(file_data, dict) and "workflow" in file_data:
                content = json.dumps(file_data["workflow"], ensure_ascii=False, indent=2).encode("utf-8")
            else:
                content = json.dumps(file_data, ensure_ascii=False, indent=2).encode("utf-8")
        else:
            content = resp.content

        # 保存到文件
        safe_name = "".join(c if c.isalnum() or c in " _-()（）" else "_" for c in name)
        filepath = os.path.join(WORK_DIR, "workflow", f"{workflow_id}_{safe_name}.json")
        with open(filepath, "wb") as f:
            f.write(content)
        return True

    except requests.RequestException as e:
        print(f"  请求失败: {e}")
        return False


def main():
    workflows = load_workflows()
    if not workflows:
        print("工作流列表为空")
        return

    print(f"共 {len(workflows)} 个工作流待下载\n")

    token = get_token_from_browser()

    os.makedirs(WORK_DIR, exist_ok=True)

    success = 0
    fail = 0
    for i, wf in enumerate(workflows, 1):
        print(f"[{i}/{len(workflows)}] {wf['name']} ({wf['id']})")
        if download_workflow(token, wf):
            success += 1
            print(f"  下载成功")
        else:
            fail += 1
            print(f"  下载失败")

    print(f"\n完成: 成功 {success} 个, 失败 {fail} 个")
    print(f"保存目录: {WORK_DIR}")


if __name__ == "__main__":
    main()
