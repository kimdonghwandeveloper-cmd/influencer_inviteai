import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# 🔑 네가 발급받은 access_token
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN_HERE" # .env 파일이나 환경변수에서 관리하는 것을 추천합니다.

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