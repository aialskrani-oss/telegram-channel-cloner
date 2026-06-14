#!/usr/bin/env python3
"""
نص النشر على Render — ينشئ خدمة ويربطها بـ GitHub تلقائياً.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path


def render_request(path: str, token: str, method: str = "GET", data: dict = None):
    url = f"https://api.render.com/v1{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/json")
    req.method = method

    body = json.dumps(data).encode() if data else None
    try:
        with urllib.request.urlopen(req, body) as resp:
            return json.loads(resp.read().decode()), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body), e.code
        except Exception:
            return {"message": body}, e.code


def get_render_owner(token: str) -> str:
    print("👤 جارٍ التحقق من حساب Render...")
    data, status = render_request("/owners?limit=1", token)
    if status != 200:
        print(f"❌ فشل التحقق من رمز Render: {data}")
        sys.exit(1)
    owner_id = data[0]["owner"]["id"]
    print(f"  ✅ مرحباً! المالك: {data[0]['owner'].get('name', owner_id)}")
    return owner_id


def find_existing_service(token: str, service_name: str) -> dict | None:
    data, status = render_request(f"/services?name={service_name}&limit=20", token)
    if status != 200:
        return None
    for item in data:
        svc = item.get("service", {})
        if svc.get("name") == service_name:
            return svc
    return None


def create_render_service(
    token: str,
    owner_id: str,
    github_username: str,
    repo_name: str,
    service_name: str,
    env_vars: dict,
) -> dict:
    print(f"\n🚀 إنشاء خدمة Render '{service_name}'...")

    existing = find_existing_service(token, service_name)
    if existing:
        print(f"  ℹ️  الخدمة موجودة مسبقاً: {existing.get('serviceDetails', {}).get('url', '')}")
        return existing

    env_vars_list = [{"key": k, "value": v} for k, v in env_vars.items()]

    payload = {
        "type": "background_worker",
        "name": service_name,
        "ownerId": owner_id,
        "repo": f"https://github.com/{github_username}/{repo_name}",
        "branch": "main",
        "autoDeploy": "yes",
        "envVars": env_vars_list,
        "serviceDetails": {
            "env": "docker",
            "dockerfilePath": "./Dockerfile",
            "disk": {
                "name": "cloner-data",
                "mountPath": "/data",
                "sizeGB": 1,
            },
        },
    }

    data, status = render_request("/services", token, method="POST", data=payload)

    if status not in (200, 201):
        print(f"  ⚠️  فشل إنشاء كـ background_worker: {data.get('message', data)}")
        print("  🔄 المحاولة كـ web_service...")

        payload["type"] = "web_service"
        payload["serviceDetails"]["plan"] = "free"
        del payload["serviceDetails"]["disk"]

        data, status = render_request("/services", token, method="POST", data=payload)

        if status not in (200, 201):
            print(f"  ❌ فشل إنشاء الخدمة: {data.get('message', data)}")
            sys.exit(1)

    svc = data.get("service", data)
    print(f"  ✅ تم إنشاء الخدمة! ID: {svc.get('id', 'N/A')}")
    return svc


def wait_for_deploy(token: str, service_id: str, timeout: int = 300):
    print("\n⏳ انتظار اكتمال النشر...")
    start = time.time()
    last_status = None

    while time.time() - start < timeout:
        data, status = render_request(f"/services/{service_id}/deploys?limit=1", token)
        if status == 200 and data:
            deploy = data[0].get("deploy", {})
            deploy_status = deploy.get("status", "unknown")

            if deploy_status != last_status:
                print(f"  📊 حالة النشر: {deploy_status}")
                last_status = deploy_status

            if deploy_status in ("live", "succeeded"):
                print("  ✅ تم النشر بنجاح!")
                return True
            elif deploy_status in ("failed", "canceled", "deactivated"):
                print(f"  ❌ فشل النشر بحالة: {deploy_status}")
                return False

        time.sleep(10)

    print(f"  ⚠️  انتهت مهلة الانتظار ({timeout}ث). تحقق من لوحة Render.")
    return False


def main():
    render_token = os.getenv("RENDER_API_KEY", "")

    try:
        with open("/tmp/github_info.txt") as f:
            info = dict(line.strip().split("=", 1) for line in f if "=" in line)
        github_username = info.get("GITHUB_USERNAME", "")
        repo_name = info.get("REPO_NAME", "telegram-channel-cloner")
        github_url = info.get("REPO_URL", "")
    except FileNotFoundError:
        github_username = os.getenv("GITHUB_USERNAME", "")
        repo_name = os.getenv("REPOSITORY_NAME", "telegram-channel-cloner")
        github_url = f"https://github.com/{github_username}/{repo_name}"

    if not render_token:
        print("❌ يرجى تعيين RENDER_API_KEY")
        sys.exit(1)

    if not github_username:
        print("❌ لم يتم العثور على GITHUB_USERNAME")
        sys.exit(1)

    env_vars = {
        "API_ID": os.getenv("API_ID", ""),
        "API_HASH": os.getenv("API_HASH", ""),
        "SESSION_STRING": os.getenv("SESSION_STRING", ""),
        "SOURCE_CHANNEL": os.getenv("SOURCE_CHANNEL", ""),
        "DESTINATION_CHANNEL": os.getenv("DESTINATION_CHANNEL", ""),
        "BATCH_SIZE": os.getenv("BATCH_SIZE", "50"),
        "DELAY_BETWEEN_MESSAGES": os.getenv("DELAY_BETWEEN_MESSAGES", "0.5"),
        "DELAY_BETWEEN_BATCHES": os.getenv("DELAY_BETWEEN_BATCHES", "2.0"),
        "MAX_RETRIES": os.getenv("MAX_RETRIES", "5"),
        "RETRY_DELAY": os.getenv("RETRY_DELAY", "10.0"),
        "DB_PATH": "/data/cloner.db",
    }

    service_name = os.getenv("RENDER_SERVICE_NAME", "telegram-channel-cloner")

    print("=" * 60)
    print("🚀  نشر تطبيق Telegram Channel Cloner على Render")
    print("=" * 60)

    owner_id = get_render_owner(render_token)
    svc = create_render_service(
        render_token, owner_id, github_username, repo_name, service_name, env_vars
    )

    service_id = svc.get("id", "")
    service_url = svc.get("serviceDetails", {}).get("url", "")
    if not service_url:
        service_url = f"https://{service_name}.onrender.com"

    if service_id:
        wait_for_deploy(render_token, service_id, timeout=300)

    dashboard_url = f"https://dashboard.render.com/worker/{service_id}" if service_id else "https://dashboard.render.com"

    print("\n" + "=" * 60)
    print("🎉 اكتمل النشر!")
    print(f"🐙 مستودع GitHub: {github_url}")
    print(f"☁️  خدمة Render:   {service_url}")
    print(f"📊 لوحة التحكم:    {dashboard_url}")
    print("\n⚙️  لا تنسَ إضافة متغيرات البيئة في لوحة Render:")
    print("   API_ID, API_HASH, SESSION_STRING, SOURCE_CHANNEL, DESTINATION_CHANNEL")
    print("=" * 60)


if __name__ == "__main__":
    main()
