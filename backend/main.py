
import os
import json
from typing import Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from dotenv import load_dotenv

# --- Import Logic ---
from core.hospitality_services import (
    process_booking_audio,
    process_booking_text,
    process_booking_text_stream,
    process_text_to_audio,  # <--- WE NEED THIS ONE
    get_text_from_speech,
    process_booking_conversation
)
from core.database import db_client,BookingManager,SessionManager
load_dotenv()

app = FastAPI(title="Riya: Restaurant Voice AI", version="2.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TextBookingRequest(BaseModel):
    text: str
    caller_phone: Optional[str] = None

# ==================== DEBUG LOGGER ====================
def log_flow(stage, details):
    print(f"\n{'='*40}")
    print(f"🚦 FLOW: {stage}")
    print(f"📄 DATA: {details}")
    print(f"{'='*40}\n")

# ==================== 1. TEXT-TO-AUDIO (The Missing Link) ====================
# @app.post("/api/chat/text-to-audio")
# async def chat_text_to_audio(request: TextBookingRequest):
#     """
#     Input: Text (JSON)
#     Output: Audio Stream (WAV)
#     """
#     log_flow("API_HIT: /api/chat/text-to-audio", f"User: '{request.text}' | Phone: {request.caller_phone}")
    
#     try:
#         # 1. Pass to Service Layer
#         audio_generator = await process_text_to_audio(request.text, request.caller_phone)
        
#         if not audio_generator:
#             log_flow("ERROR", "TTS Generator returned None")
#             raise HTTPException(status_code=500, detail="Riya failed to speak.")
            
#         log_flow("SUCCESS", "Streaming Audio bytes back to client...")
        
#         return StreamingResponse(
#             audio_generator,
#             media_type="audio/wav",
#             headers={"Content-Disposition": "inline; filename=response.wav"}
#         )
        
#     except Exception as e:
#         log_flow("CRITICAL_FAIL", str(e))
#         raise HTTPException(status_code=500, detail=str(e))
# ==================== 1. TEXT-TO-AUDIO (OFFICE MODE) ====================
@app.post("/api/chat/text-to-audio")
async def chat_text_to_audio(request: TextBookingRequest):
    """
    Input: Text (JSON) -> Output: Audio Stream (WAV) + Header (Identity)
    """
    log_flow("API_HIT: /api/chat/text-to-audio", f"User: '{request.text}' | Phone: {request.caller_phone}")
    
    try:
        # 1. Pass to Service Layer (Returns Tuple: Stream, Phone)
        audio_generator, resolved_phone = await process_text_to_audio(request.text, request.caller_phone)
        
        if not audio_generator:
            log_flow("ERROR", "TTS Generator returned None")
            raise HTTPException(status_code=500, detail="Riya failed to speak.")
            
        log_flow("SUCCESS", f"Streaming Audio... (Locked Identity: {resolved_phone})")
        
        # 2. Prepare Headers
        headers = {
            "Content-Disposition": "inline; filename=response.wav",
            "Access-Control-Expose-Headers": "X-Detected-Phone" # Allow JS to read this
        }
        
        # 3. Inject Phone into header if found
        if resolved_phone:
            headers["X-Detected-Phone"] = str(resolved_phone)
        
        return StreamingResponse(
            audio_generator,
            media_type="audio/wav",
            headers=headers
        )
        
    except Exception as e:
        log_flow("CRITICAL_FAIL", str(e))
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 2. VOICE-TO-AUDIO (Standard Call) ====================
# @app.post("/api/book/voice")
# async def book_via_voice(
#     audio: UploadFile = File(...),
#     caller_phone: Optional[str] = Query(None)
# ):
#     log_flow("API_HIT: /api/book/voice", f"Received Audio File | Phone: {caller_phone}")
#     try:
#         audio_bytes = await audio.read()
#         log_flow("AUDIO_READ", f"{len(audio_bytes)} bytes")
        
#         audio_generator = await process_booking_audio(audio_bytes, caller_phone)
        
#         if not audio_generator:
#             raise HTTPException(status_code=500, detail="TTS generation failed")
        
#         return StreamingResponse(audio_generator, media_type="audio/wav")
        
#     except Exception as e:
#         log_flow("VOICE_FAIL", str(e))
#         raise HTTPException(status_code=500, detail=str(e))
# ==================== 2. VOICE-TO-AUDIO (REAL MODE) ====================
@app.post("/api/book/voice")
async def book_via_voice(
    audio: UploadFile = File(...),
    caller_phone: Optional[str] = Query(None)
):
    log_flow("API_HIT: /api/book/voice", f"Received Audio | Phone: {caller_phone}")
    try:
        audio_bytes = await audio.read()
        
        # 1. CALL SERVICE (Now returns Tuple)
        audio_generator, resolved_phone = await process_booking_audio(audio_bytes, caller_phone)
        
        if not audio_generator:
            raise HTTPException(status_code=500, detail="TTS generation failed")
        
        # 2. PREPARE HEADERS (The Handshake)
        headers = {
            "Access-Control-Expose-Headers": "X-Detected-Phone"
        }
        if resolved_phone:
            headers["X-Detected-Phone"] = str(resolved_phone)
            log_flow("SUCCESS", f"Voice Identity Locked: {resolved_phone}")

        # 3. STREAM BACK
        return StreamingResponse(
            audio_generator, 
            media_type="audio/wav",
            headers=headers
        )
        
    except Exception as e:
        log_flow("VOICE_FAIL", str(e))
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 3. TEXT STREAM (For Debugging Text Logic) ====================
@app.post("/api/chat/stream")
async def stream_chat_response(request: TextBookingRequest):
    log_flow("API_HIT: /api/chat/stream", request.text)
    async def generate():
        async for word in process_booking_text_stream(request.text, request.caller_phone):
            yield {"event": "token", "data": json.dumps({"token": word})}
        yield {"event": "done", "data": json.dumps({"complete": True})}
    return EventSourceResponse(generate())

# ==================== HEALTH & UTILS ====================
@app.get("/health")
async def health_check():
    return {"status": "online", "mode": "debug"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)