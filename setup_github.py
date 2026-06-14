#!/usr/bin/env python3
"""
نص إعداد GitHub — ينشئ مستودعاً ويرفع الكود تلقائياً.
"""

import os
import sys
import subprocess
import json
import urllib.request
import urllib.error
from pathlib import Path


def run(cmd: list, cwd: str = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  ❌ خطأ: {result.stderr.strip() or result.stdout.strip()}")
        sys.exit(1)
    return result


def github_request(url: str, token: str, method: str = "GET", data: dict = None):
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "TelegramCloner/2.0")
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


def get_github_username(token: str) -> str:
    data, status = github_request("https://api.github.com/user", token)
    if status != 200:
        print(f"❌ فشل التحقق من رمز GitHub: {data.get('message', 'خطأ غير معروف')}")
        sys.exit(1)
    return data["login"]


def create_or_get_repo(token: str, username: str, repo_name: str) -> str:
    print(f"\n📦 التحقق من وجود المستودع '{repo_name}'...")
    data, status = github_request(f"https://api.github.com/repos/{username}/{repo_name}", token)

    if status == 200:
        print(f"  ✅ المستودع موجود مسبقاً: {data['html_url']}")
        return data["clone_url"]

    print(f"  🆕 إنشاء مستودع جديد '{repo_name}'...")
    data, status = github_request(
        "https://api.github.com/user/repos",
        token,
        method="POST",
        data={
            "name": repo_name,
            "description": "🤖 نظام نسخ قنوات تيليجرام الاحترافي — Telegram Channel Cloner",
            "private": False,
            "auto_init": False,
        }
    )

    if status not in (200, 201):
        print(f"❌ فشل إنشاء المستودع: {data.get('message', 'خطأ غير معروف')}")
        sys.exit(1)

    print(f"  ✅ تم إنشاء المستودع: {data['html_url']}")
    return data["clone_url"]


def push_to_github(repo_dir: str, clone_url: str, token: str, username: str):
    print("\n🔧 تهيئة git...")

    git_dir = Path(repo_dir) / ".git"
    if git_dir.exists():
        run(["git", "remote", "remove", "origin"], cwd=repo_dir, check=False)
    else:
        run(["git", "init"], cwd=repo_dir)
        run(["git", "config", "user.email", "bot@telegram-cloner.app"], cwd=repo_dir)
        run(["git", "config", "user.name", "Telegram Cloner Bot"], cwd=repo_dir)

    auth_url = clone_url.replace("https://", f"https://{username}:{token}@")
    run(["git", "remote", "add", "origin", auth_url], cwd=repo_dir)

    print("\n📝 إضافة الملفات...")
    run(["git", "add", "-A"], cwd=repo_dir)

    status = run(["git", "status", "--porcelain"], cwd=repo_dir, check=False)
    if not status.stdout.strip():
        print("  ℹ️  لا توجد تغييرات للحفظ.")
    else:
        run(["git", "commit", "-m", "🤖 إضافة نظام نسخ قنوات تيليجرام الاحترافي"], cwd=repo_dir)
        print("  ✅ تم حفظ التغييرات")

    print("\n🚀 رفع الكود على GitHub...")
    result = run(["git", "push", "-u", "origin", "main", "--force"], cwd=repo_dir, check=False)
    if result.returncode != 0:
        run(["git", "push", "-u", "origin", "master", "--force"], cwd=repo_dir, check=False)
        run(["git", "branch", "-M", "main"], cwd=repo_dir, check=False)
        run(["git", "push", "-u", "origin", "main", "--force"], cwd=repo_dir)

    print("  ✅ تم الرفع بنجاح!")


def main():
    token = os.getenv("GITHUB_TOKEN", "")
    repo_name = os.getenv("REPOSITORY_NAME", "telegram-channel-cloner")

    if not token:
        print("❌ يرجى تعيين GITHUB_TOKEN")
        sys.exit(1)

    print("=" * 60)
    print("🐙  إعداد مستودع GitHub")
    print("=" * 60)

    print("\n👤 جارٍ التحقق من حساب GitHub...")
    username = get_github_username(token)
    print(f"  ✅ مرحباً، {username}!")

    clone_url = create_or_get_repo(token, username, repo_name)

    repo_dir = str(Path(__file__).parent.absolute())
    push_to_github(repo_dir, clone_url, token, username)

    repo_url = f"https://github.com/{username}/{repo_name}"
    print("\n" + "=" * 60)
    print("✅ اكتمل إعداد GitHub بنجاح!")
    print(f"🔗 رابط المستودع: {repo_url}")
    print("=" * 60)

    with open("/tmp/github_info.txt", "w") as f:
        f.write(f"GITHUB_USERNAME={username}\n")
        f.write(f"REPO_NAME={repo_name}\n")
        f.write(f"REPO_URL={repo_url}\n")

    return username, repo_name


if __name__ == "__main__":
    main()
