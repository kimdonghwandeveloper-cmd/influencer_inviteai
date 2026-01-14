import base64
import os
from dotenv import load_dotenv
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# 🔑 네가 발급받은 access_token
# 🔑 .env에서 access_token 로드
load_dotenv()
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

creds = Credentials(token=ACCESS_TOKEN)

service = build("gmail", "v1", credentials=creds)

# 메일 내용 생성
message = MIMEText("안녕하세요.\nGmail API 테스트 메일입니다.")
message["to"] = "ektks06782@gmail.com"
message["from"] = "me"
message["subject"] = "Gmail API 테스트"

# 인코딩
raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

# 메일 전송
send_message = (
    service.users()
    .messages()
    .send(userId="me", body={"raw": raw})
    .execute()
)

print("메일 전송 성공:", send_message["id"])