"""
pip install openai google-api-python-client google-auth-httplib2 google-auth-oauthlib python-dotenv

환경변수:
  OPENAI_API_KEY=...

파일:
  credentials.json  (Google OAuth Client)
  campaign_ctx.json (캠페인 사실정보)

사용:
  python inma_email_agent.py send --to someone@example.com --tag "[INMA-001]" --subject "INMA 제안" --body "..."
  python inma_email_agent.py poll --tag "[INMA-001]"
"""

import os
import json
import base64
import argparse
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


# ----------------------------
# Config
# ----------------------------
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",  # read + mark read
]
TOKEN_FILE = "token.json"
CREDS_FILE = "credentials.json"

CTX_FILE = "campaign_ctx.json"
HANDOFF_FILE = "handoff_queue.jsonl"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key = OPENAI_API_KEY)


# ----------------------------
# Gmail OAuth / Service
# ----------------------------
def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_FILE):
                raise FileNotFoundError("credentials.json 없음 (Google OAuth Client 파일)")
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8")


def send_email(service, to_email: str, subject: str, body: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
    msg = MIMEText(body, _charset="utf-8")
    msg["to"] = to_email
    msg["subject"] = subject

    raw = _b64url(msg.as_bytes())
    payload: Dict[str, Any] = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id  # 같은 스레드에 붙이기

    return service.users().messages().send(userId="me", body=payload).execute()


def search_unread_by_subject_tag(service, tag: str, newer_than_days: int = 14, max_results: int = 10) -> List[Dict[str, str]]:
    # tag를 subject에 심어두면 이 쿼리로 스레드 추적이 제일 쉬움
    q = f'in:inbox is:unread newer_than:{newer_than_days}d subject:"{tag}"'
    res = service.users().messages().list(userId="me", q=q, maxResults=max_results).execute()
    return res.get("messages", [])  # [{"id": "...", "threadId": "..."}] 형태로 옴


def _decode_body(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def get_message_full(service, msg_id: str) -> Dict[str, Any]:
    return service.users().messages().get(userId="me", id=msg_id, format="full").execute()


def extract_headers(msg: Dict[str, Any]) -> Dict[str, str]:
    headers = msg.get("payload", {}).get("headers", [])
    out = {}
    for h in headers:
        name = h.get("name", "").lower()
        val = h.get("value", "")
        if name in ("from", "to", "subject", "date", "message-id"):
            out[name] = val
    return out


def get_message_text(msg: Dict[str, Any]) -> str:
    payload = msg.get("payload", {})
    parts = payload.get("parts")

    # 1) 단일 본문
    body = payload.get("body", {}).get("data")
    if body:
        return _decode_body(body)

    # 2) multipart -> text/plain 우선
    if parts:
        for p in parts:
            if p.get("mimeType") == "text/plain":
                data = p.get("body", {}).get("data")
                if data:
                    return _decode_body(data)

        # fallback: text/html
        for p in parts:
            if p.get("mimeType") == "text/html":
                data = p.get("body", {}).get("data")
                if data:
                    html = _decode_body(data)
                    # html 태그 제거(최소)
                    import re
                    return re.sub(r"<[^>]+>", " ", html)

    return ""


def mark_as_read(service, msg_id: str):
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()


def parse_email_from_header(from_header: str) -> str:
    # "Name <email@x.com>" -> email@x.com
    import re
    m = re.search(r"<([^>]+)>", from_header)
    if m:
        return m.group(1).strip()
    return from_header.strip()


# ----------------------------
# Campaign ctx load
# ----------------------------
def load_ctx_by_tag(tag: str) -> Dict[str, Any]:
    """
    campaign_ctx.json 예시:
    {
      "[INMA-001]": {
        "campaign_window": "2/1~2/15",
        "budget_range": "50~80만원",
        "deliverables": "쇼츠 1 + 스토리 2",
        "usage_rights_scope": "브랜드 채널 2차 활용(광고집행 X)",
        "deadline": "2/18",
        "candidate_dates": "2/7, 2/9, 2/12",
        "product_summary": "OOO 기능성 의류",
        "key_messages": "착용감/내구성/디자인",
        "dos_donts": "의학적 효능 단정 금지",
        "cta": "링크 클릭 + 쿠폰코드 언급",
        "what_we_need": "- 최근 30일 지표(조회/도달/저장)\n- 국가/연령대",
        "ship_date": "ASAP",
        "options_needed": "사이즈/색상",
        "payment_method_options": "계좌이체",
        "settlement_timing_options": "게시 후 7일 이내"
      }
    }
    """
    if not os.path.exists(CTX_FILE):
        return {}
    with open(CTX_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get(tag, {})


# ----------------------------
# OpenAI: one-call classify + reply (base template only)
# ----------------------------
RISKY_KWS = ["계약", "계약서", "서명", "독점", "위약금", "저작권", "법률", "합의", "협상", "분쟁", "최종확정", "확정"]
NEGOTIATION_KWS = ["깎", "할인", "네고", "조정", "최저", "성과형"]


def classify_and_generate_reply(email_text: str, ctx: Dict[str, Any], meta: Dict[str, str]) -> Dict[str, Any]:
    """
    meta: {"name": "...", "brand": "...", "campaign": "..."}
    """
    lowered = email_text.lower()
    if any(k.lower() in lowered for k in RISKY_KWS):
        return {
            "category": "RISKY",
            "confidence": 0.95,
            "handoff": True,
            "handoff_reason": "법률/계약/확정 관련",
            "reply_body": None,
            "used_ctx_keys": [],
        }

    schema = {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": ["PRICE","SCHEDULE","DETAILS","MEDIAKIT","SHIPPING","PAYMENT","DECLINE","OTHER","RISKY"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "handoff": {"type": "boolean"},
            "handoff_reason": {"type": "string"},
            "reply_body": {"type": ["string", "null"]},
            "used_ctx_keys": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["category","confidence","handoff","handoff_reason","reply_body","used_ctx_keys"],
        "additionalProperties": False,
    }

    instructions = (
        "You are an outreach email agent.\n"
        "Write the reply in Korean.\n"
        "CRITICAL: Use ONLY facts present in ctx. Never invent numbers, dates, policies.\n"
        "If info is missing, ask at most 2 short questions.\n"
        "Use this fixed structure:\n"
        "1) Greeting/thanks (1 line)\n"
        "2) One-line summary of what they asked\n"
        "3) Answer using ctx facts (bullets ok)\n"
        "4) If missing: ask up to 2 questions\n"
        "5) Next step line (DO NOT confirm contract)\n"
        "If the email involves contract/negotiation/confirmation, set category=RISKY, handoff=true, reply_body=null.\n"
        "No emojis. Keep it concise.\n"
    )

    payload = {
        "email_text": email_text,
        "ctx": ctx,
        "meta": meta,
    }

    resp = client.responses.create(
        model="gpt-5",
        instructions=instructions,
        input=json.dumps(payload, ensure_ascii=False),
        text={"format": {"type": "json_schema", "name": "classify_and_reply", "strict": True, "schema": schema}},
        store=False,
    )

    out = json.loads(resp.output_text)

    # 추가 안전장치: 네고 단어 있으면 사람 넘김
    if any(k.lower() in lowered for k in NEGOTIATION_KWS):
        out["category"] = "RISKY"
        out["handoff"] = True
        out["handoff_reason"] = "가격 협상(네고) 감지"
        out["reply_body"] = None

    # 답장 안에 위험 단어 있으면 컷
    if isinstance(out.get("reply_body"), str):
        for t in ["계약", "서명", "확정", "독점", "위약금", "합의", "협상"]:
            if t in out["reply_body"]:
                out["category"] = "RISKY"
                out["handoff"] = True
                out["handoff_reason"] = "답장 내용에서 확정/계약 뉘앙스 감지"
                out["reply_body"] = None
                break

    return out


# ----------------------------
# Handoff queue
# ----------------------------
def enqueue_handoff(item: Dict[str, Any]):
    line = json.dumps(item, ensure_ascii=False)
    with open(HANDOFF_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ----------------------------
# CLI actions
# ----------------------------
def cmd_send(args):
    service = get_gmail_service()
    subject = f"{args.subject} {args.tag}"
    sent = send_email(service, args.to, subject, args.body)
    print("SENT:", sent.get("id"), "thread:", sent.get("threadId"))


def cmd_poll(args):
    service = get_gmail_service()
    ctx = load_ctx_by_tag(args.tag)

    msgs = search_unread_by_subject_tag(service, args.tag, newer_than_days=args.days, max_results=args.max)
    if not msgs:
        print("NO UNREAD")
        return

    for m in msgs:
        msg_id = m["id"]
        full = get_message_full(service, msg_id)
        headers = extract_headers(full)
        text = get_message_text(full).strip()

        from_email = parse_email_from_header(headers.get("from", ""))
        subject = headers.get("subject", "")
        thread_id = full.get("threadId")

        # 최소 메타(실전은 DB에서 influencer_name 가져오는 게 맞음)
        meta = {"name": args.name or "담당자", "brand": args.brand, "campaign": args.campaign}

        result = classify_and_generate_reply(text, ctx, meta)

        if result["handoff"]:
            enqueue_handoff({
                "time": datetime.utcnow().isoformat(),
                "from": from_email,
                "subject": subject,
                "threadId": thread_id,
                "category": result["category"],
                "reason": result["handoff_reason"],
                "email_text": text[:2000],
            })
            mark_as_read(service, msg_id)
            print("HANDOFF:", from_email, result["handoff_reason"])
            continue

        reply_body = result["reply_body"]
        if not reply_body:
            # 방어적으로 사람 큐
            enqueue_handoff({
                "time": datetime.utcnow().isoformat(),
                "from": from_email,
                "subject": subject,
                "threadId": thread_id,
                "category": result["category"],
                "reason": "reply_body가 비어있음",
                "email_text": text[:2000],
            })
            mark_as_read(service, msg_id)
            print("HANDOFF(empty reply):", from_email)
            continue

        # 같은 스레드에 붙여 보내기(간단히 subject 그대로)
        send_email(service, from_email, subject, reply_body, thread_id=thread_id)
        mark_as_read(service, msg_id)
        print("REPLIED:", from_email, "cat:", result["category"], "conf:", round(result["confidence"], 2))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("send")
    ps.add_argument("--to", required=True)
    ps.add_argument("--tag", required=True)
    ps.add_argument("--subject", default="캠페인 제안드립니다")
    ps.add_argument("--body", required=True)
    ps.set_defaults(func=cmd_send)

    pp = sub.add_parser("poll")
    pp.add_argument("--tag", required=True)
    pp.add_argument("--days", type=int, default=14)
    pp.add_argument("--max", type=int, default=10)
    pp.add_argument("--brand", default="브랜드")
    pp.add_argument("--campaign", default="캠페인")
    pp.add_argument("--name", default=None)  # 인플루언서 이름 DB에서 넣는 게 맞음
    pp.set_defaults(func=cmd_poll)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
