#!/usr/bin/env python3
"""
初回セットアップ用スクリプト（ローカルで1回だけ実行する）
Google OAuth のリフレッシュトークンを取得して GitHub Secrets に登録する情報を出力する
"""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", scopes=SCOPES)
creds = flow.run_local_server(port=0)

print("\n" + "=" * 60)
print("✅ 認証成功！以下の値を GitHub Secrets に登録してください")
print("=" * 60)
print(f"GOOGLE_CLIENT_ID     = {creds.client_id}")
print(f"GOOGLE_CLIENT_SECRET = {creds.client_secret}")
print(f"GOOGLE_REFRESH_TOKEN = {creds.refresh_token}")
print("=" * 60)