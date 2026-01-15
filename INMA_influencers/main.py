import base64
import json
import os
import re
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from pymongo import MongoClient
from openai import OpenAI

load_dotenv()

# ---------------------------
# ENV
# ---------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
TOKEN_CACHE_FILE = os.getenv("TOKEN_CACHE_FILE", "token_cache.json")
TOKEN_URI = "https://oauth2.googleapis.com/token"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",  # poll + mark read
]

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
oa = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or os.getenv("MONGO_PUBLIC_URL")
MONGODB_DB = os.getenv("MONGODB_DB", "inma")
MONGODB_KB_COLLECTION = os.getenv("MONGODB_KB_COLLECTION", "kb")
MONGODB_VECTOR_INDEX = os.getenv("MONGODB_VECTOR_INDEX", "kb_vector_index")
MONGODB_INFLUENCER_COLLECTION = os.getenv("MONGODB_INFLUENCER_COLLECTION", "influencers")

# 위험 키워드(사람에게 넘김)
RISKY_KWS = [
    "계약", "계약서", "서명", "독점", "위약금", "저작권", "초상권",
    "법률", "합의", "협상", "분쟁", "확정", "세금계산서"
]

# 답장 템플릿(LLM이 이 골격을 절대 벗어나면 안 됨)
BASE_REPLY_TEMPLATE_RULES = """\
- 아래 5단 구조를 반드시 지켜라 (줄바꿈 포함):
1) 인사/감사 1줄
2) 상대 질문 요약 1줄
3) 답변(필요하면 불릿)
4) 부족한 정보 질문 0~2개(짧게)
5) 다음 단계 1줄(확정/계약 확답 금지)

- 이모지 금지.
- ctx + evidence에 없는 숫자/날짜/조건/정책을 만들어내지 마라.
- 확정/계약/협상/법률 느낌이면 handoff=true로 돌려라.
"""

app = FastAPI(title="INMA Gmail + RAG Reply Agent")


# ---------------------------
# Token cache
# ---------------------------
def load_token_cache() -> Dict[str, Any]:
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_token_cache(data: Dict[str, Any]) -> None:
    try:
        with open(TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_credentials() -> Credentials:
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and REFRESH_TOKEN):
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/REFRESH_TOKEN이 .env에 필요합니다.",
        )

    cache = load_token_cache()
    token = cache.get("access_token") or ACCESS_TOKEN
    expiry_iso = cache.get("expiry")

    expiry = None
    if expiry_iso:
        try:
            expiry = datetime.fromisoformat(expiry_iso.replace("Z", "+00:00"))
        except Exception:
            expiry = None

    creds = Credentials(
        token=token,
        refresh_token=REFRESH_TOKEN,
        token_uri=TOKEN_URI,
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )
    if expiry:
        creds.expiry = expiry

    if (not creds.token) or creds.expired:
        try:
            creds.refresh(Request())
            save_token_cache(
                {
                    "access_token": creds.token,
                    "expiry": creds.expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    if creds.expiry else None,
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"토큰 refresh 실패: {e}")

    return creds


def get_gmail_service():
    creds = get_credentials()
    return build("gmail", "v1", credentials=creds)


# ---------------------------
# Gmail utils
# ---------------------------
def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8")


def decode_body(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def extract_headers(msg: Dict[str, Any]) -> Dict[str, str]:
    headers = msg.get("payload", {}).get("headers", [])
    out: Dict[str, str] = {}
    for h in headers:
        k = (h.get("name") or "").lower()
        v = h.get("value") or ""
        if k in ("from", "to", "subject", "date", "message-id", "references", "reply-to"):
            out[k] = v
    return out


def parse_email(addr: str) -> str:
    m = re.search(r"<([^>]+)>", addr)
    return (m.group(1) if m else addr).strip()


def get_message_text(full_msg: Dict[str, Any]) -> str:
    payload = full_msg.get("payload", {})
    parts = payload.get("parts")

    body = payload.get("body", {}).get("data")
    if body:
        return decode_body(body)

    if parts:
        for p in parts:
            if p.get("mimeType") == "text/plain":
                d = p.get("body", {}).get("data")
                if d:
                    return decode_body(d)
        for p in parts:
            if p.get("mimeType") == "text/html":
                d = p.get("body", {}).get("data")
                if d:
                    html = decode_body(d)
                    return re.sub(r"<[^>]+>", " ", html)

    return ""


def mark_as_read(service, msg_id: str):
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()


def send_message(
    service,
    to_email: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> Dict[str, Any]:
    msg = MIMEText(body, _charset="utf-8")
    msg["to"] = to_email
    msg["subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    raw = b64url(msg.as_bytes())
    payload: Dict[str, Any] = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id

    return service.users().messages().send(userId="me", body=payload).execute()


# ---------------------------
# MongoDB RAG
# ---------------------------
def get_kb_collection():
    if not MONGODB_URI:
        raise HTTPException(status_code=500, detail="MONGODB_URI가 .env에 필요합니다.")
    client = MongoClient(MONGODB_URI)
    return client[MONGODB_DB][MONGODB_KB_COLLECTION]


def embed_text(text: str) -> List[float]:
    if not oa:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 .env에 필요합니다.")
    t = (text or "").strip()
    if not t:
        return []
    emb = oa.embeddings.create(model=EMBEDDING_MODEL, input=t)
    return emb.data[0].embedding


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> List[str]:
    text = re.sub(r"\s+\n", "\n", (text or "").strip())
    if len(text) <= chunk_size:
        return [text] if text else []
    out = []
    i = 0
    while i < len(text):
        j = min(len(text), i + chunk_size)
        out.append(text[i:j])
        if j == len(text):
            break
        i = max(0, j - overlap)
    return out


def retrieve_evidence(
    query: str,
    top_k: int = 6,
    brand: Optional[str] = None,
    campaign: Optional[str] = None,
    min_score: float = 0.75,
) -> List[Dict[str, Any]]:
    """
    Atlas Vector Search 기반.
    - 인덱스: MONGODB_VECTOR_INDEX
    - path: embedding
    """
    col = get_kb_collection()
    qvec = embed_text(query)
    if not qvec:
        return []

    flt: Dict[str, Any] = {}
    if brand:
        flt["metadata.brand"] = brand
    if campaign:
        flt["metadata.campaign"] = campaign

    stage: Dict[str, Any] = {
        "$vectorSearch": {
            "index": MONGODB_VECTOR_INDEX,
            "path": "embedding",
            "queryVector": qvec,
            "numCandidates": 200,
            "limit": top_k,
        }
    }
    if flt:
        stage["$vectorSearch"]["filter"] = flt

    pipeline = [
        stage,
        {
            "$project": {
                "_id": 1,
                "title": 1,
                "url": 1,
                "text": 1,
                "source_type": 1,
                "metadata": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    docs = list(col.aggregate(pipeline))
    # 너무 낮은 점수는 버림(근거 약하면 쓰지 않게)
    docs = [d for d in docs if float(d.get("score", 0.0)) >= min_score]
    return docs


def build_evidence_pack(docs: List[Dict[str, Any]], max_chars_each: int = 500) -> Tuple[str, List[Dict[str, Any]]]:
    """
    LLM 입력용 evidence 문자열 + 메타(추적용)
    """
    packed = []
    meta = []
    for i, d in enumerate(docs, start=1):
        eid = f"E{i}"
        txt = (d.get("text") or "").strip()
        snippet = txt[:max_chars_each]
        title = d.get("title") or ""
        url = d.get("url") or ""
        packed.append(f"[{eid}] {title}\nURL: {url}\nSNIPPET: {snippet}")
        meta.append(
            {
                "eid": eid,
                "id": str(d.get("_id")),
                "title": title,
                "url": url,
                "score": float(d.get("score", 0.0)),
                "source_type": d.get("source_type"),
            }
        )
    return "\n\n".join(packed), meta


# ---------------------------
# LLM (template + evidence only)
# ---------------------------
def contains_risky(text: str) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in RISKY_KWS)


def extract_risky_from_reply(reply_body: str) -> bool:
    # 답장 내용에 위험 뉘앙스가 들어오면 즉시 handoff
    return any(k in (reply_body or "") for k in ["계약", "서명", "확정", "위약금", "독점", "합의", "협상"])


def extract_sensitive_numbers(text: str) -> List[str]:
    """
    근거 없는 숫자/조건을 잡기 위한 최소 검증.
    - 3자리 이상 숫자(가격) or %, 원, 만원, 일/월/년 등 단위 포함만 검사
    """
    tokens = re.findall(r"\d[\d,]*(?:\.\d+)?(?:\s*(?:원|만원|%|일|월|년))?", text or "")
    out = []
    for tok in tokens:
        t = tok.strip()
        if not t:
            continue
        digits = re.sub(r"[^\d]", "", t)
        if ("원" in t) or ("만원" in t) or ("%" in t) or ("월" in t) or ("일" in t) or ("년" in t) or (len(digits) >= 3):
            out.append(t)
    return list(dict.fromkeys(out))


def validate_reply_against_sources(reply_body: str, ctx: Dict[str, Any], evidence_text: str) -> Optional[str]:
    """
    reply에 들어간 숫자/기간/퍼센트가 ctx 또는 evidence에 없으면 실패 사유 반환.
    """
    haystack = (evidence_text or "") + "\n" + json.dumps(ctx or {}, ensure_ascii=False)
    for tok in extract_sensitive_numbers(reply_body):
        if tok not in haystack:
            return f"근거 없는 수치/조건 감지: '{tok}'"
    return None


def llm_generate_reply(
    email_text: str,
    ctx: Dict[str, Any],
    meta: Dict[str, str],
    evidence_text: str,
    evidence_meta: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    return dict:
      category, confidence, handoff, handoff_reason,
      reply_subject, reply_body,
      evidence_used (e.g., ["E1","E3"]),
      missing_questions (0~2)
    """
    if not oa:
        return {
            "category": "OTHER",
            "confidence": 0.0,
            "handoff": True,
            "handoff_reason": "OPENAI_API_KEY 미설정",
            "reply_subject": None,
            "reply_body": None,
            "evidence_used": [],
            "missing_questions": [],
        }

    if contains_risky(email_text):
        return {
            "category": "RISKY",
            "confidence": 0.95,
            "handoff": True,
            "handoff_reason": "메일에 계약/협상/확정/법률 키워드 감지",
            "reply_subject": None,
            "reply_body": None,
            "evidence_used": [],
            "missing_questions": [],
        }

    schema = {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": ["PRICE","SCHEDULE","DETAILS","MEDIAKIT","SHIPPING","PAYMENT","DECLINE","OTHER","RISKY"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "handoff": {"type": "boolean"},
            "handoff_reason": {"type": "string"},
            "reply_subject": {"type": ["string", "null"]},
            "reply_body": {"type": ["string", "null"]},
            "evidence_used": {"type": "array", "items": {"type": "string"}},
            "missing_questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "category","confidence","handoff","handoff_reason",
            "reply_subject","reply_body","evidence_used","missing_questions"
        ],
        "additionalProperties": False,
    }

    instructions = (
        "You are an influencer outreach email agent.\n"
        "Write the reply in Korean.\n"
        + BASE_REPLY_TEMPLATE_RULES +
        "\n\nEVIDENCE RULES:\n"
        "- 답변에 들어가는 사실/수치/정책은 ctx 또는 evidence에 존재해야 한다.\n"
        "- ctx/evidence에 없으면 '확인 질문'으로 돌려라.\n"
        "- evidence_used에는 실제로 참고한 EID만 넣어라.\n"
    )

    payload = {
        "email_text": email_text,
        "meta": meta,
        "ctx": ctx,
        "evidence": evidence_text,        # LLM 입력
        "evidence_meta": evidence_meta,  # 추적용(LLM이 봐도 됨)
    }

    resp = oa.responses.create(
        model="gpt-4o-mini",
        instructions=instructions,
        input=json.dumps(payload, ensure_ascii=False),
        text={"format": {"type": "json_schema", "name": "inma_rag_reply", "strict": True, "schema": schema}},
        store=False,
    )
    out = json.loads(resp.output_text)

    # 2차 방어: 위험 뉘앙스면 handoff
    if out.get("reply_body") and extract_risky_from_reply(out["reply_body"]):
        out["category"] = "RISKY"
        out["handoff"] = True
        out["handoff_reason"] = "생성 답장에 계약/확정/협상 뉘앙스 감지"
        out["reply_subject"] = None
        out["reply_body"] = None
        out["evidence_used"] = []
        out["missing_questions"] = []

    # 3차 방어: 근거 없는 수치 감지
    if out.get("reply_body"):
        fail = validate_reply_against_sources(out["reply_body"], ctx, evidence_text)
        if fail:
            out["handoff"] = True
            out["handoff_reason"] = fail
            out["reply_subject"] = None
            out["reply_body"] = None
            out["evidence_used"] = []
            # 질문으로 돌리고 싶으면 여기서 missing_questions 채우도록 바꿔도 됨.

    return out


# ---------------------------
# KB Ingest / Search API (내부정보 넣기)
# ---------------------------
class KBUpsertReq(BaseModel):
    source_type: str = Field(default="internal", description="internal|web")
    title: str
    url: Optional[str] = None
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KBUpsertRes(BaseModel):
    inserted: int


@app.post("/kb/upsert", response_model=KBUpsertRes)
def kb_upsert(req: KBUpsertReq):
    col = get_kb_collection()
    chunks = chunk_text(req.text)
    if not chunks:
        raise HTTPException(status_code=400, detail="text가 비어있음")

    docs = []
    for ch in chunks:
        vec = embed_text(ch)
        docs.append(
            {
                "source_type": req.source_type,
                "title": req.title,
                "url": req.url or "",
                "text": ch,
                "embedding": vec,
                "metadata": req.metadata,
                "created_at": datetime.now(timezone.utc),
            }
        )

    if docs:
        col.insert_many(docs)
    return KBUpsertRes(inserted=len(docs))


class KBSearchReq(BaseModel):
    query: str
    brand: Optional[str] = None
    campaign: Optional[str] = None
    top_k: int = 6


class KBSearchRes(BaseModel):
    results: List[Dict[str, Any]]


@app.post("/kb/search", response_model=KBSearchRes)
def kb_search(req: KBSearchReq):
    docs = retrieve_evidence(req.query, top_k=req.top_k, brand=req.brand, campaign=req.campaign, min_score=0.0)
    out = []
    for d in docs:
        out.append(
            {
                "id": str(d.get("_id")),
                "title": d.get("title"),
                "url": d.get("url"),
                "score": float(d.get("score", 0.0)),
                "snippet": (d.get("text") or "")[:300],
                "metadata": d.get("metadata", {}),
            }
        )
    return KBSearchRes(results=out)


# ---------------------------
# FastAPI schemas (send/poll/poll_and_reply)
# ---------------------------
class SendReq(BaseModel):
    to: str
    subject: str
    body: str
    tag: Optional[str] = None


class SendRes(BaseModel):
    id: str
    threadId: str


class PollReq(BaseModel):
    tag: Optional[str] = Field(default=None, description='subject에 포함된 태그로 필터 (예: "[INMA-001]")')
    query: Optional[str] = Field(default=None, description="Gmail search query 직접 지정")
    newer_than_days: int = 14
    max_results: int = 10
    mark_read: bool = True


class PolledMessage(BaseModel):
    id: str
    threadId: str
    from_email: str
    subject: str
    snippet: str
    body: str


class PollRes(BaseModel):
    messages: List[PolledMessage]


class PollAndReplyReq(BaseModel):
    query: str = Field(
        default='newer_than:14d is:unread in:anywhere subject:"[INMA-" -from:me',
        description="Gmail search query"
    )
    max_results: int = 10
    mark_read: bool = True
    dry_run: bool = True

    brand: str = "브랜드"
    campaign: str = "캠페인"

    # 캠페인 사실(LLM이 쓸 수 있는 사실 저장소)
    ctx: Dict[str, Any] = Field(default_factory=dict)

    subject_prefix: str = "Re: "

    # RAG 옵션
    rag_top_k: int = 6
    rag_min_score: float = 0.75


class PollAndReplyRes(BaseModel):
    processed: int
    replied: int
    handed_off: int
    details: List[Dict[str, Any]]

class SendInfluencersReq(BaseModel):
    subject: str
    body: str

    # 각 메일 제목에 붙일 고유 태그 생성 옵션 (답장 추적용)
    tag_prefix: str = "INMA"
    start_index: int = 1  # INMA-001부터 시작

    # 대상 추출 옵션
    limit: int = 200
    min_inma_score: Optional[float] = None
    sort_by_score_desc: bool = True

    # 운용 옵션
    dry_run: bool = True  # True면 실제 전송 안 하고 대상/태그만 리턴
    delay_ms: int = 250   # 발송 간격(쿼터/스팸 방지용)
    max_fail: int = 20    # 실패가 너무 많으면 중단


class SendInfluencersRes(BaseModel):
    total_targets: int
    attempted: int
    sent: int
    failed: int
    items: List[Dict[str, Any]]  # email, tag, message_id, threadId, status, error(optional)

# ---------------------------
# Email Import
# ---------------------------

import re
from typing import List, Optional
from pymongo import MongoClient
from fastapi import HTTPException

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.I)

def get_influencer_collection():
    if not MONGODB_URI:
        raise HTTPException(status_code=500, detail="MONGODB_URI가 .env에 필요합니다.")
    client = MongoClient(MONGODB_URI)
    return client[MONGODB_DB][MONGODB_INFLUENCER_COLLECTION]

from typing import List, Optional

def fetch_influencer_emails(
    limit: int = 1000,
    min_inma_score: Optional[float] = None,
    sort_by_score_desc: bool = True,
) -> List[str]:
    col = get_influencer_collection()

    q = {}
    if min_inma_score is not None:
        q["inma_score"] = {"$gte": float(min_inma_score)}

    cursor = col.find(q, {"_id": 0, "email": 1, "inma_score": 1})

    if sort_by_score_desc:
        cursor = cursor.sort("inma_score", -1)

    if limit and limit > 0:
        cursor = cursor.limit(int(limit))

    return [doc.get("email") for doc in cursor]

# ---------------------------
# Routes
# ---------------------------
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware import cors
app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="INMA Email Agent")

# ✅ CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8001",
        "http://localhost:8001"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")

@app.get("/")
def ui_root():
    return FileResponse("static/index.html")


@app.get("/")
def ui_root():
    return FileResponse("static/index.html")

@app.get("/health")
def health(limit: int = 10000):
    datas = fetch_influencer_emails(limit = limit)
    return {"status": 'ok', 'emails': datas}

# ---------------------------
# Frontend API Endpoints
# ---------------------------
from matching_engine import MatchingEngine
from bson import ObjectId

# Helper to serialize ObjectId
def serialize_mongo(doc):
    if not doc: return None
    if isinstance(doc, list):
        return [serialize_mongo(d) for d in doc]
    if isinstance(doc, dict):
        return {k: (str(v) if isinstance(v, ObjectId) else serialize_mongo(v)) for k, v in doc.items()}
    return doc

@app.get("/influencers")
def list_influencers(
    page: int = 1, 
    limit: int = 20, 
    min_score: float = 0.0, 
    category: Optional[str] = None,
    sort_by: str = "inma_score",
    search: Optional[str] = None
):
    col = get_influencer_collection()
    query = {}
    
    if min_score > 0:
        query["inma_score"] = {"$gte": min_score}
        
    if category and category != "All":
        # Simply check if keyword exists in keywords list or title/description
        query["$or"] = [
            {"keywords": {"$regex": category, "$options": "i"}},
            {"title": {"$regex": category, "$options": "i"}},
            {"description": {"$regex": category, "$options": "i"}}
        ]
        
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]

    total = col.count_documents(query)
    cursor = col.find(query).sort(sort_by, -1).skip((page - 1) * limit).limit(limit)
    
    items = list(cursor)
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": serialize_mongo(items)
    }

@app.get("/products")
def list_products():
    # Listing all products for dropdown
    if not MONGODB_URI:
        raise HTTPException(500, "MONGODB_URI missing")
    client = MongoClient(MONGODB_URI)
    col = client[MONGODB_DB]["products"]
    
    products = list(col.find({}, {"embedding": 0})) # Exclude large embedding
    return serialize_mongo(products)

class MatchReq(BaseModel):
    product_id: str
    limit: int = 10

@app.post("/match")
def match_influencers(req: MatchReq):
    try:
        engine = MatchingEngine()
        
        # Determine if ID or Name
        if ObjectId.is_valid(req.product_id):
            product = engine.products.find_one({"_id": ObjectId(req.product_id)})
        else:
            product = engine.products.find_one({"_id": req.product_id}) # Fallback
            
        if not product:
             raise HTTPException(404, "Product not found")
             
        recommendations = engine.find_influencers_for_product(product, limit=req.limit)
        
        # Serialize results
        serialized_recs = []
        for rec in recommendations:
            rec["influencer"] = serialize_mongo(rec["influencer"])
            serialized_recs.append(rec)
            
        return serialized_recs
        
    except Exception as e:
        print(f"Match Error: {e}")
        raise HTTPException(500, str(e))


@app.post("/send", response_model=SendRes)
def api_send(req: SendReq):
    service = get_gmail_service()
    subject = req.subject
    if req.tag and req.tag not in subject:
        subject = f"{subject} {req.tag}"

    try:
        sent = send_message(service, req.to, subject, req.body)
        return SendRes(id=sent["id"], threadId=sent["threadId"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"메일 전송 실패: {e}")
    
import time
@app.post("/send/influencers", response_model=SendInfluencersRes)
def send_to_influencers(req: SendInfluencersReq):
    # 1) 이메일 리스트 가져오기
    emails = fetch_influencer_emails(
        limit=req.limit,
        min_inma_score=req.min_inma_score,
        sort_by_score_desc=req.sort_by_score_desc,
    )

    # dry_run이면 서비스 생성 불필요
    service = None if req.dry_run else get_gmail_service()

    items: List[Dict[str, Any]] = []
    sent = 0
    failed = 0
    attempted = 0

    for i, email in enumerate(emails):
        attempted += 1
        tag = f"[{req.tag_prefix}-{req.start_index + i:03d}]"
        subject = f"{req.subject} {tag}"

        if req.dry_run:
            items.append(
                {"email": email, "tag": tag, "status": "dry_run"}
            )
            continue

        try:
            res = send_message(service, to_email=email, subject=subject, body=req.body)
            sent += 1
            items.append(
                {
                    "email": email,
                    "tag": tag,
                    "status": "sent",
                    "message_id": res.get("id"),
                    "threadId": res.get("threadId"),
                }
            )
        except Exception as e:
            failed += 1
            items.append(
                {"email": email, "tag": tag, "status": "failed", "error": str(e)}
            )
            if failed >= req.max_fail:
                break

        if req.delay_ms > 0:
            time.sleep(req.delay_ms / 1000.0)

    return SendInfluencersRes(
        total_targets=len(emails),
        attempted=attempted,
        sent=sent,
        failed=failed,
        items=items,
    )


@app.post("/poll", response_model=PollRes)
def api_poll(req: PollReq):
    service = get_gmail_service()

    if req.query:
        q = req.query
    else:
        q = f"in:inbox is:unread newer_than:{req.newer_than_days}d"
        if req.tag:
            q += f' subject:"{req.tag}" -from:me'

    try:
        res = service.users().messages().list(userId="me", q=q, maxResults=req.max_results).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail list 실패: {e}")

    refs = res.get("messages", [])
    out: List[PolledMessage] = []

    for r in refs:
        msg_id = r["id"]
        try:
            full = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            headers = extract_headers(full)
            body = get_message_text(full).strip()

            from_email = parse_email(headers.get("reply-to") or headers.get("from", ""))
            subject = headers.get("subject", "")
            thread_id = full.get("threadId", "")
            snippet = full.get("snippet", "")

            out.append(
                PolledMessage(
                    id=msg_id,
                    threadId=thread_id,
                    from_email=from_email,
                    subject=subject,
                    snippet=snippet,
                    body=body,
                )
            )

            if req.mark_read:
                mark_as_read(service, msg_id)

        except Exception:
            continue

    return PollRes(messages=out)


@app.post("/poll_and_reply", response_model=PollAndReplyRes)
def poll_and_reply(req: PollAndReplyReq):
    """
    핵심:
    - poll로 답장(수신메일) 가져옴
    - RAG(MongoDB)로 근거 가져옴
    - LLM은 ctx+evidence 밖 정보 금지 + 템플릿 고정
    - dry_run이면 초안만 반환
    """
    service = get_gmail_service()

    try:
        res = service.users().messages().list(userId="me", q=req.query, maxResults=req.max_results).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail list 실패: {e}")

    refs = res.get("messages", [])
    replied = 0
    handed_off = 0
    details: List[Dict[str, Any]] = []

    for r in refs:
        msg_id = r["id"]
        try:
            full = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            headers = extract_headers(full)
            body = get_message_text(full).strip()

            from_email = parse_email(headers.get("reply-to") or headers.get("from", ""))
            subject = headers.get("subject", "")
            thread_id = full.get("threadId", "")
            in_reply_to = headers.get("message-id")
            references = headers.get("references") or in_reply_to

            # ---- RAG: 메일 본문 기반 근거 검색 ----
            rag_query = f"{subject}\n\n{body}"
            docs = retrieve_evidence(
                query=rag_query,
                top_k=req.rag_top_k,
                brand=req.brand,
                campaign=req.campaign,
                min_score=req.rag_min_score,
            )
            evidence_text, evidence_meta = build_evidence_pack(docs)

            meta = {"brand": req.brand, "campaign": req.campaign}
            decision = llm_generate_reply(
                email_text=body,
                ctx=req.ctx,
                meta=meta,
                evidence_text=evidence_text,
                evidence_meta=evidence_meta,
            )

            if decision["handoff"]:
                handed_off += 1
                details.append(
                    {
                        "msg_id": msg_id,
                        "from": from_email,
                        "subject": subject,
                        "status": "handoff",
                        "reason": decision["handoff_reason"],
                        "category": decision["category"],
                        "evidence_meta": evidence_meta,  # 디버깅용(근거 뭐 잡혔는지)
                    }
                )
            else:
                reply_subject = decision.get("reply_subject") or (req.subject_prefix + subject)
                reply_body = decision.get("reply_body")

                if not reply_body:
                    handed_off += 1
                    details.append(
                        {
                            "msg_id": msg_id,
                            "from": from_email,
                            "subject": subject,
                            "status": "handoff",
                            "reason": "reply_body가 비어있음",
                            "category": decision.get("category", "OTHER"),
                            "evidence_meta": evidence_meta,
                        }
                    )
                else:
                    if not req.dry_run:
                        send_message(
                            service=service,
                            to_email=from_email,
                            subject=reply_subject,
                            body=reply_body,
                            thread_id=thread_id,
                            in_reply_to=in_reply_to,
                            references=references,
                        )
                        replied += 1

                    details.append(
                        {
                            "msg_id": msg_id,
                            "from": from_email,
                            "subject": subject,
                            "status": "draft" if req.dry_run else "replied",
                            "category": decision["category"],
                            "confidence": decision["confidence"],
                            "evidence_used": decision.get("evidence_used", []),
                            "missing_questions": decision.get("missing_questions", []),
                            "reply_subject": reply_subject,
                            "reply_body": reply_body if req.dry_run else None,
                            "evidence_meta": evidence_meta,
                        }
                    )

            if req.mark_read:
                mark_as_read(service, msg_id)

        except Exception as e:
            details.append({"msg_id": msg_id, "status": "error", "error": str(e)})

    return PollAndReplyRes(
        processed=len(refs),
        replied=replied,
        handed_off=handed_off,
        details=details,
    )
@app.get("/stats")
def get_stats():
    if not MONGODB_URI:
        raise HTTPException(500, "MONGODB_URI missing")
    
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DB]
    
    inf_col = db[MONGODB_INFLUENCER_COLLECTION]
    prod_col = db["products"]
    
    total_influencers = inf_col.count_documents({})
    total_products = prod_col.count_documents({})
    
    # Top segments (simple aggregation on keywords or category field if exists)
    # Here we simulate segments based on keywords/industries for the dashboard chart
    pipeline = [
        {"$project": {"keywords": 1}},
        {"$unwind": "$keywords"},
        {"$group": {"_id": "$keywords", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5}
    ]
    top_keywords = list(inf_col.aggregate(pipeline))
    
    return {
        "total_influencers": total_influencers,
        "total_products": total_products,
        "active_campaigns": 3, # Mock data for now
        "emails_sent": 128,    # Mock data for now
        "segments": [{"name": k["_id"], "value": k["count"]} for k in top_keywords]
    }
