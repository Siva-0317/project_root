# app/main.py
import os, json, httpx, logging
from typing import List
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from faster_whisper import WhisperModel
from app.settings import settings

# --------- JUNE system prompt (server-side canonical) ---------
PROMPT_JUNE = """You are JUNE (full form: Journey to understand, navigate and enlighten), a helpful library assistant for Easwari Engineering College Central Library.

General Library Info:
- Incharge: Dr. Joseph Anburaj
- Timings: 7.45 AM to 6 PM, Monday to Saturday
- Borrowing Limit: 2 books per student
- Loan Duration: 14 days
- Fine: ₹5 per day if not returned on time
- Location: First Floor, South Wing, Civil Block
- Contact: centralibrary@eec.srmrmp.edu.in

Collections:
1  Total no. of Volumes                80294
2  Total no. of Titles                 21671
3  Total no of National Journals       117
4  IEEE (ASPP)                         222
5  ELSEVIER (SCIENCE DIRECT)           275
6  BUSNESS SOURCE ELITE(Management)    1056
7  Delnet Online                       10000+

Membership:
Institutional Membership Libraries:
1  British Council Library, Chennai
2  CSIR- SERC – Knowledge Resource Center, Chennai*
3  DELNET (Developing Library Network), New Delhi

Other Resources:
1  Open Access No of NPTEL (Web & Video) Course
2  NDL (National Digital Library) and NDLI Club

Faculties:
1  Dr. A.JOSEPH ANBURAJ   LIBRARIAN      M.LIS,M.PHIL,PH.D
2  Mr.K.KADHIRAVAN        LIB.ASSISTANT  B.A.,M.LIS
3  Mrs.S.LEELAVATHI       LIB.ASSISTANT  B.COM,M.LIS

Digital Access:
- Delnet Portal: https://delnet.in/
- E-books Portal: https://ndl.iitkgp.ac.in/
- Research Archives: https://www.sciencedirect.com/
- IEEE Access: https://ieeexplore.ieee.org/Xplore/home.jsp
- NPTEL Portal: https://nptel.ac.in/

Remote Access:
- Use your college email to access digital resources from home.
- Link: https://srmeaswari.knimbus.com/user#/home

Policy:
- Respond to user questions only using the above info as JUNE.
- Do not perform book searches.
- Even if the question is repeated, always respond.
- Be concise, friendly, and clear; include links from Digital Access only when helpful.
"""

DB_URL: str = settings.DB_URL
LM_BASE: str = settings.LM_BASE
LM_CHAT: str = f"{LM_BASE}/v1/chat/completions"

def _parse_origins(origins: str) -> List[str]:
    if not origins or origins.strip() == "*": return ["*"]
    return [o.strip() for o in origins.split(",") if o.strip()]

CORS_ORIGINS = _parse_origins(settings.CORS_ORIGIN)

engine = create_engine(DB_URL, pool_size=10, max_overflow=20, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

app = FastAPI(title="JUNE Library Assistant API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
def login_page():
    return FileResponse(str(static_dir / "login.html"))

@app.get("/chat")
def chat_page():
    return FileResponse(str(static_dir / "chat.html"))

log = logging.getLogger("uvicorn.error")

# STT model (Windows-safe compute default; override with WH_* in .env)
stt = WhisperModel(settings.WHISPER_SIZE, device=settings.WH_DEVICE, compute_type=os.getenv("WH_COMPUTE_TYPE", "int8"))

@app.get("/health/db")
def health_db(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True}

@app.get("/health/lm")
def health_lm():
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{LM_BASE}/v1/models")
            r.raise_for_status()
            return {"ok": True, "models": r.json().get("data", [])}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LM server check failed: {e}")

@app.post("/api/login")
def login(body: dict, db=Depends(get_db)):
    reg = str(body.get("reg_no","")).strip()
    row = db.execute(text("SELECT name, dept FROM students WHERE reg_no=:r"), {"r": reg}).fetchone()
    if not row:
        return {"ok": False, "msg": "Invalid register number"}
    return {"ok": True, "reg_no": reg, "name": row[0], "dept": row[1]}

@app.post("/api/logout")
def logout():
    return {"ok": True}

@app.get("/api/history")
def history(reg_no: str, db=Depends(get_db)):
    rows = db.execute(text("SELECT message, timestamp FROM history WHERE reg_no=:r ORDER BY timestamp DESC LIMIT 20"), {"r": reg_no}).fetchall()
    return {"items": [{"message": r[0], "timestamp": r[1].isoformat()} for r in rows]}

# Windows-safe temp file handling for WebM uploads
@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    data = await file.read()
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".webm")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        segments, _ = stt.transcribe(path, vad_filter=True, beam_size=1)
        text = "".join(s.text for s in segments).strip()
        return {"text": text}
    finally:
        try: os.remove(path)
        except OSError: pass

@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            while True:
                msg = await ws.receive_json()
                reg_no = str(msg.get("reg_no","")).strip()
                user_msg = str(msg.get("content",""))
                model_id = msg.get("model","llama-3.2-3b-instruct")

                if not reg_no or not user_msg:
                    await ws.send_json({"event":"error","text":"Missing reg_no or content"})
                    continue

                # Always inject the canonical JUNE prompt server-side
                messages = [
                    {"role": "system", "content": PROMPT_JUNE},
                    {"role": "user",   "content": user_msg},
                ]
                payload = {"model": model_id, "messages": messages, "stream": True}

                # Save user message
                try:
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO history (reg_no, message, timestamp) VALUES (:r,:m,NOW())"),
                                     {"r": reg_no, "m": f"User: {user_msg}"})
                except Exception as e:
                    log.error(f"DB insert (user) failed: {e}")

                buffer: List[str] = []
                try:
                    async with client.stream("POST", LM_CHAT, json=payload) as r:
                        if r.status_code != 200:
                            body = await r.aread()
                            await ws.send_json({"event":"error","text":f"LM error {r.status_code}: {body.decode('utf-8','ignore')}"})
                            continue
                        async for line in r.aiter_lines():
                            if not line or line.startswith(":"): continue
                            if not line.startswith("data:"): continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                await ws.send_json({"event":"done"})
                                break
                            try:
                                obj = json.loads(data)
                                delta = obj["choices"][0]["delta"].get("content","")
                                if delta:
                                    buffer.append(delta)
                                    await ws.send_json({"event":"token","text":delta})
                            except Exception:
                                pass
                except Exception as e:
                    await ws.send_json({"event":"error","text":f"Stream failed: {e}"})
                    continue

                final = "".join(buffer).strip()
                if final:
                    try:
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO history (reg_no, message, timestamp) VALUES (:r,:m,NOW())"),
                                         {"r": reg_no, "m": f"Assistant: {final}"})
                    except Exception as e:
                        log.error(f"DB insert (assistant) failed: {e}")
    except WebSocketDisconnect:
        return
