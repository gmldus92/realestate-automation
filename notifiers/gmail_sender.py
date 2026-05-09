"""Gmail API를 통한 이메일 발송"""
import os
import base64
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
TOKEN_FILE = Path(__file__).parent.parent / "data" / "gmail_token.json"
CREDENTIALS_JSON = os.environ.get("GMAIL_CREDENTIALS", "")  # JSON 문자열
REPORT_EMAIL = os.environ.get("REPORT_EMAIL", "")


def _get_service():
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # GitHub Actions: 환경변수에서 credentials 로드
            if CREDENTIALS_JSON:
                cred_data = json.loads(CREDENTIALS_JSON)
                TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
                TOKEN_FILE.write_text(json.dumps(cred_data))
                creds = Credentials.from_authorized_user_info(cred_data, SCOPES)
            else:
                raise RuntimeError("GMAIL_CREDENTIALS 환경변수가 설정되지 않았습니다.")

        TOKEN_FILE.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send(to: str, subject: str, html_body: str) -> None:
    service = _get_service()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = "me"
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"[gmail] 발송 완료 → {to} / {subject}")


def send_report(html_body: str, date: str) -> None:
    to = REPORT_EMAIL
    if not to:
        print("[gmail] REPORT_EMAIL 환경변수가 설정되지 않았습니다.")
        return
    send(to, f"[부동산 리포트] {date}", html_body)


def send_alert(html_body: str, date: str) -> None:
    to = REPORT_EMAIL
    if not to:
        return
    send(to, f"🚨 [가격 알림] {date}", html_body)
