#!/usr/bin/env python3
"""
デイリーモーニングブリーフィング
毎朝05:00 JSTにGitHub Actionsで実行し、Gmail通知として送信する
"""

import os
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

import anthropic
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

JST = ZoneInfo("Asia/Tokyo")

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def get_google_credentials() -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=GOOGLE_SCOPES,
    )
    creds.refresh(Request())
    return creds


def get_calendar_events(creds: Credentials) -> str:
    service = build("calendar", "v3", credentials=creds)
    now = datetime.datetime.now(JST)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

    result = service.events().list(
        calendarId="primary",
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    if not events:
        return "今日の予定はありません。"

    lines = []
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date", ""))
        if "T" in start:
            dt = datetime.datetime.fromisoformat(start).astimezone(JST)
            time_str = dt.strftime("%H:%M")
        else:
            time_str = "終日"
        summary = event.get("summary", "（無題）")
        location = event.get("location", "")
        loc_str = f" 📍{location}" if location else ""
        lines.append(f"- {time_str} {summary}{loc_str}")

    return "\n".join(lines)


def get_emails(creds: Credentials) -> tuple[list[dict], list[dict]]:
    service = build("gmail", "v1", credentials=creds)

    def fetch_summaries(query: str, max_results: int) -> list[dict]:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        messages = []
        for m in resp.get("messages", []):
            detail = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
            messages.append({
                "subject": headers.get("Subject", "（件名なし）"),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
            })
        return messages

    important = fetch_summaries("is:important is:unread", max_results=5)
    unread = fetch_summaries("is:unread in:inbox", max_results=10)
    return important, unread


def get_chatwork_messages() -> list[dict]:
    token = os.environ.get("CHATWORK_API_TOKEN", "")
    if not token:
        return []

    headers = {"X-ChatWorkToken": token}
    base_url = "https://api.chatwork.com/v2"

    rooms_resp = requests.get(f"{base_url}/rooms", headers=headers, timeout=10)
    rooms_resp.raise_for_status()
    rooms = rooms_resp.json()

    unread_messages = []
    for room in rooms:
        if room.get("unread_num", 0) == 0:
            continue

        room_id = room["room_id"]
        room_name = room.get("name", f"Room {room_id}")
        msgs_resp = requests.get(
            f"{base_url}/rooms/{room_id}/messages",
            headers=headers,
            params={"force": 1},
            timeout=10,
        )
        if msgs_resp.status_code != 200:
            continue

        for msg in msgs_resp.json()[-5:]:
            unread_messages.append({
                "room": room_name,
                "account": msg.get("account", {}).get("name", ""),
                "body": msg.get("body", "")[:100],
                "send_time": datetime.datetime.fromtimestamp(
                    msg.get("send_time", 0), tz=JST
                ).strftime("%H:%M"),
            })

    return unread_messages


def format_chatwork_list(messages: list[dict]) -> str:
    if not messages:
        return "未読メッセージなし"
    lines = []
    for m in messages:
        lines.append(f"- [{m['send_time']}] {m['room']} / {m['account']}\n  {m['body']}")
    return "\n".join(lines)


def format_email_list(emails: list[dict]) -> str:
    if not emails:
        return "なし"
    return "\n".join(f"- {e['from']}\n  件名: {e['subject']}" for e in emails)


def generate_briefing(calendar_text: str, important_emails: list, unread_emails: list, chatwork_messages: list) -> str:
    today = datetime.datetime.now(JST).strftime("%Y年%m月%d日（%A）")

    prompt = f"""今日は{today}（日本時間）です。

以下のデータをもとに、デイリーモーニングブリーフィングを日本語で作成してください。

【今日のGoogleカレンダー】
{calendar_text}

【Chatwork未読メッセージ】
{format_chatwork_list(chatwork_messages)}

【重要メール（IMPORTANTフラグ・未読）】
{format_email_list(important_emails)}

【未読メール（受信トレイ）】
{format_email_list(unread_emails)}

加えて、以下をWeb検索で調べてください：
1. 岐阜市の今日の天気予報（気温・降水確率・風速など）
2. 世界経済から日本経済への影響を含む本日の経済ニュース1件

以下の形式で、絵文字を使ったわかりやすいレポートをまとめてください。
各セクションに出典（URLまたは情報源名）を明記すること。

---
# 🌅 モーニングブリーフィング {today}

## 📅 今日のスケジュール
（カレンダーの内容）

## 🌤️ 岐阜市の天気
（天気予報・気温・降水確率）
👔 服装アドバイス: ...
🎒 持ち物アドバイス: ...
出典: ...

## 📊 経済ニュース
（世界経済から日本経済への影響を含む1件）
出典: ...

## 💬 Chatworkチェック
（未読メッセージの要約・件数と一覧）

## ✉️ メールチェック
### 🔴 重要メール（IMPORTANT）
（件数と一覧）

### 📬 未読メール
（件数と一覧）
---
"""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    text_blocks = [block.text for block in response.content if hasattr(block, "text")]
    return "\n".join(text_blocks)


def send_email(body: str) -> None:
    sender = os.environ["GMAIL_SENDER"]
    receiver = os.environ.get("GMAIL_RECEIVER", sender)
    app_password = os.environ["GMAIL_APP_PASSWORD"]

    today_str = datetime.datetime.now(JST).strftime("%Y/%m/%d")
    subject = f"🌅 モーニングブリーフィング {today_str}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, app_password)
        server.sendmail(sender, receiver, msg.as_string())

    print(f"✅ 送信完了 → {receiver}")


def main() -> None:
    print("🌅 デイリーモーニングブリーフィング開始...")

    creds = get_google_credentials()
    print("✅ Google認証完了")

    calendar_text = get_calendar_events(creds)
    print(f"📅 カレンダー取得完了")

    important_emails, unread_emails = get_emails(creds)
    print(f"✉️ メール取得完了 (重要: {len(important_emails)}件 / 未読: {len(unread_emails)}件)")

    chatwork_messages = get_chatwork_messages()
    print(f"💬 Chatwork取得完了 (未読: {len(chatwork_messages)}件)")

    briefing = generate_briefing(calendar_text, important_emails, unread_emails, chatwork_messages)
    print("\n" + briefing)

    send_email(briefing)


if __name__ == "__main__":
    main()