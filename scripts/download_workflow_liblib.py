#!/usr/bin/python3
"""读取 liblib_workflow.json，通过浏览器登录获取 usertoken cookie，下载工作流到 ../workflow/"""

import requests
import sys
import json
import os
import time
from playwright.sync_api import sync_playwright


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.environ.get("WORKDIR", os.path.abspath(os.path.join(SCRIPT_DIR, "..", "work")))
INPUT_FILE = os.path.join(WORK_DIR, "liblib_workflow.json")
USER_DATA_DIR = os.path.join(WORK_DIR, ".playwright_liblib_data")

HOME_URL = "https://www.liblib.art"


def load_workflows():
    if not os.path.exists(INPUT_FILE):
        print(f"文件不存在: {INPUT_FILE}")
        print("请先运行 search_liblib_workflow.py 获取工作流列表")
        sys.exit(1)
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("workflows", [])


def get_token_from_cookie():
    """打开浏览器让用户登录，从 cookie 读取 usertoken"""
    print("正在启动浏览器，请登录 哩布哩布...\n")

    with sync_playwright() as p:
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
        print("登录成功后脚本将自动检测到 usertoken 并继续...\n")

        token = None
        for _ in range(300):
            cookies = context.cookies()
            for c in cookies:
                if c["name"] == "usertoken":
                    token = c["value"]
                    break
            if token:
                break
            time.sleep(1)

        if token:
            print(f"\n已获取 usertoken: {token[:20]}...{token[-10:]}")
        else:
            print("\n超时：未在浏览器 cookie 中检测到 usertoken")
            print("请确保已登录 liblib.art")

        context.close()

    if not token:
        sys.exit(1)

    return token


def get_download_url(token, version_id):
    """获取工作流 JSON 文件下载 URL"""
    url = f"https://api2.liblib.art/api/www/comfy/version/attachment/{version_id}"
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://www.liblib.art",
        "Referer": "https://www.liblib.art/",
        "Cookie": f"usertoken={token}"
    }

    try:
        resp = requests.post(url, json={}, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}")
            return None
        data = resp.json()
        if data.get("code") != 0:
            print(f"  API 错误: code={data.get('code')}, msg={data.get('msg')}")
            return None
        return data.get("data")
    except requests.RequestException as e:
        print(f"  请求失败: {e}")
        return None


def download_file(download_url, filepath):
    """下载 JSON 文件到指定路径"""
    try:
        resp = requests.get(download_url, timeout=60)
        if resp.status_code != 200:
            print(f"  下载 HTTP {resp.status_code}")
            return False
        with open(filepath, "wb") as f:
            f.write(resp.content)
        return True
    except requests.RequestException as e:
        print(f"  下载失败: {e}")
        return False


def main():
    workflows = load_workflows()
    if not workflows:
        print("工作流列表为空")
        return

    # 过滤出有 versionId 的工作流
    valid = [w for w in workflows if w.get("versionId")]
    if not valid:
        print("没有可下载的工作流（缺少 versionId）")
        return

    skipped = len(workflows) - len(valid)
    print(f"共 {len(workflows)} 个工作流，{len(valid)} 个待下载")
    if skipped:
        print(f"跳过 {skipped} 个（无 versionId）")
    print()

    token = get_token_from_cookie()

    os.makedirs(WORK_DIR, exist_ok=True)

    success = 0
    fail = 0
    for i, wf in enumerate(valid, 1):
        name = wf.get("name", "unnamed")
        uid = wf.get("uuid", wf["id"])
        version_id = wf["versionId"]

        print(f"[{i}/{len(valid)}] {name} (id={wf['id']}, version={version_id})")

        download_url = get_download_url(token, version_id)
        if not download_url:
            print(f"  获取下载链接失败")
            fail += 1
            continue

        safe_name = "".join(c if c.isalnum() or c in " _-()（）" else "_" for c in name).strip()
        filepath = os.path.join(WORK_DIR, "workflow", f"{uid}_{safe_name}.json")
        print(f"  下载中... {download_url[:80]}...")
        if download_file(download_url, filepath):
            print(f"  保存成功: {os.path.basename(filepath)}")
            success += 1
        else:
            fail += 1

    print(f"\n完成: 成功 {success} 个, 失败 {fail} 个")
    print(f"保存目录: {WORK_DIR}")


if __name__ == "__main__":
    main()
