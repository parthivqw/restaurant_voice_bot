
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
    process_text_to_audio,
    get_speech_from_text,
    start_new_call,  # Ensure this is in your core services
    process_booking_conversation
)
from core.database import db_client, BookingManager, SessionManager

load_dotenv()

app = FastAPI(title="Riya: Restaurant Voice AI", version="3.0 (WebSocket Edition)")

# ==================== CORS ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== MODELS ====================
class TextBookingRequest(BaseModel):
    text: str
    caller_phone: Optional[str] = None

# ==================== DEBUG LOGGER ====================
def log_flow(stage, details):
    print(f"\n{'='*40}")
    print(f"🚦 FLOW: {stage}")
    print(f"📄 DATA: {details}")
    print(f"{'='*40}\n")

# ==================== ⚡ FIXED WEBSOCKET ENDPOINT ====================
# @app.websocket("/ws/call")
# async def websocket_endpoint(websocket: WebSocket):
#     """
#     Real-Time Duplex Connection with PROPER Session Tracking
#     """
#     await websocket.accept()
#     print(f"🔌 Socket Connected: {websocket.client}")
    
#     # 🔥 FIX: Generate a temporary session ID for anonymous users
#     import uuid
#     session_id = str(uuid.uuid4())[:8]  # Short session ID
#     session_phone = None
    
#     try:
#         while True:
#             message = await websocket.receive()
            
#             # --- 1. HANDLE TEXT EVENTS (JSON) ---
#             if "text" in message:
#                 try:
#                     data = json.loads(message["text"])
#                     event_type = data.get("event")
                    
#                     if event_type == "start":
#                         # Handshake
#                         session_phone = data.get("phone")
                        
#                         # 🔥 If no phone provided, use temp session_id
#                         effective_id = session_phone or session_id
                        
#                         log_flow("WS_START", f"Call Started. ID: {effective_id}")
                        
#                         # Generate welcome with session tracking
#                         welcome_text = "Hi! Thanks for calling The Guru's Kitchen. This is Riya. Who am I speaking with?"
#                         audio_gen = await get_speech_from_text(welcome_text)
                        
#                         # 🔥 Initialize empty session in DB
#                         if effective_id:
#                             await SessionManager.update_state(
#                                 effective_id, 
#                                 "welcome", 
#                                 {"history": [f"Riya: {welcome_text}"]}
#                             )
                        
#                         if audio_gen:
#                             for chunk in audio_gen:
#                                 await websocket.send_bytes(chunk)
#                             await websocket.send_text(json.dumps({"event": "response_complete"}))

#                     elif event_type == "interrupt":
#                         print(f"🛑 Interruption Signal received for {session_phone or session_id}")
#                         pass

#                     elif event_type == "text_input":
#                         user_text = data.get("text")
#                         effective_id = session_phone or session_id
                        
#                         # Process with session tracking
#                         audio_gen, detected_phone = await process_text_to_audio(user_text, effective_id)
                        
#                         # 🔥 Identity upgrade: temp session → real phone
#                         if detected_phone and detected_phone != session_phone:
#                             if not session_phone:
#                                 # Migrate temp session to real phone
#                                 log_flow("WS_IDENTITY_UPGRADE", f"{session_id} → {detected_phone}")
#                                 old_session = await SessionManager.get_state(session_id)
#                                 if old_session:
#                                     await SessionManager.update_state(
#                                         detected_phone,
#                                         old_session.get('intent', 'active'),
#                                         old_session.get('collected_data', {})
#                                     )
#                                     await SessionManager.clear_session(session_id)
                            
#                             session_phone = detected_phone
#                             await websocket.send_text(json.dumps({
#                                 "event": "identity_verified", 
#                                 "phone": session_phone
#                             }))
                        
#                         if audio_gen:
#                             for chunk in audio_gen:
#                                 await websocket.send_bytes(chunk)
#                             await websocket.send_text(json.dumps({"event": "response_complete"}))

#                 except json.JSONDecodeError:
#                     print("⚠️ Invalid JSON received on socket")

#             # --- 2. HANDLE AUDIO (BINARY) ---
#             elif "bytes" in message:
#                 audio_bytes = message["bytes"]
                
#                 # 🔥 Use temp session_id if no phone yet
#                 effective_id = session_phone or session_id
                
#                 # Process with session context
#                 audio_gen, detected_phone = await process_booking_audio(audio_bytes, effective_id)
                
#                 # 🔥 Identity upgrade logic
#                 if detected_phone and detected_phone != session_phone:
#                     if not session_phone:
#                         # Migrate session
#                         log_flow("WS_IDENTITY_UPGRADE", f"{session_id} → {detected_phone}")
#                         old_session = await SessionManager.get_state(session_id)
#                         if old_session:
#                             await SessionManager.update_state(
#                                 detected_phone,
#                                 old_session.get('intent', 'active'),
#                                 old_session.get('collected_data', {})
#                             )
#                             await SessionManager.clear_session(session_id)
                    
#                     session_phone = detected_phone
#                     log_flow("WS_IDENTITY", f"Locked: {session_phone}")
#                     await websocket.send_text(json.dumps({
#                         "event": "identity_verified",
#                         "phone": session_phone
#                     }))
                
#                 # Stream response
#                 if audio_gen:
#                     for chunk in audio_gen:
#                         try:
#                             await websocket.send_bytes(chunk)
#                         except RuntimeError:
#                             break
#                     await websocket.send_text(json.dumps({"event": "response_complete"}))

#     except WebSocketDisconnect:
#         print(f"🔌 Socket Disconnected: {session_phone or session_id}")
#     except Exception as e:
#         print(f"❌ Socket Error: {e}")
#         import traceback
#         traceback.print_exc()
#         try:
#             await websocket.close()
#         except:
#             pass
# In main.py - Update the WebSocket handler

@app.websocket("/ws/call")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"🔌 Socket Connected: {websocket.client}")
    
    import uuid
    session_id = str(uuid.uuid4())[:8]  # Temp tracking ID
    real_phone = None  # Actual verified phone
    
    try:
        while True:
            message = await websocket.receive()
            
            if "text" in message:
                try:
                    data = json.loads(message["text"])
                    event_type = data.get("event")
                    
                    if event_type == "start":
                        # 🔥 Pass session_id, not as phone
                        welcome_text = "Hi! Thanks for calling The Guru's Kitchen. This is Riya. Who am I speaking with?"
                        audio_gen = await get_speech_from_text(welcome_text)
                        
                        if audio_gen:
                            for chunk in audio_gen:
                                await websocket.send_bytes(chunk)
                            await websocket.send_text(json.dumps({"event": "response_complete"}))

                    elif event_type == "text_input":
                        user_text = data.get("text")
                        
                        # 🔥 NEW: Pass both session_id AND real_phone
                        audio_gen, detected_phone = await process_text_to_audio(
                            user_text, 
                            session_id=session_id, 
                            real_phone=real_phone
                        )
                        
                        # If phone was detected/verified, lock it in
                        if detected_phone and detected_phone != real_phone:
                            log_flow("WS_PHONE_VERIFIED", f"Locked phone: {detected_phone}")
                            real_phone = detected_phone
                            await websocket.send_text(json.dumps({
                                "event": "identity_verified", 
                                "phone": real_phone
                            }))
                        
                        if audio_gen:
                            for chunk in audio_gen:
                                await websocket.send_bytes(chunk)
                            await websocket.send_text(json.dumps({"event": "response_complete"}))

                except json.JSONDecodeError:
                    print("⚠️ Invalid JSON")

            elif "bytes" in message:
                audio_bytes = message["bytes"]
                
                # 🔥 NEW: Pass session_id and real_phone separately
                audio_gen, detected_phone = await process_booking_audio(
                    audio_bytes, 
                    session_id=session_id, 
                    real_phone=real_phone
                )
                
                if detected_phone and detected_phone != real_phone:
                    log_flow("WS_PHONE_VERIFIED", f"Locked phone: {detected_phone}")
                    real_phone = detected_phone
                    await websocket.send_text(json.dumps({
                        "event": "identity_verified",
                        "phone": real_phone
                    }))
                
                if audio_gen:
                    for chunk in audio_gen:
                        await websocket.send_bytes(chunk)
                    await websocket.send_text(json.dumps({"event": "response_complete"}))

    except WebSocketDisconnect:
        print(f"🔌 Socket Disconnected: {session_id}")

# ==================== HTTP ENDPOINTS (LEGACY / FALLBACK) ====================

@app.post("/api/call/start")
async def start_call_endpoint(request: TextBookingRequest): 
    """
    Triggers the initial greeting audio via HTTP (Fallback).
    """
    log_flow("API_HIT: /api/call/start", f"Starting call for {request.caller_phone}")
    try:
        # Generate the welcome audio
        audio_generator = await start_new_call(request.caller_phone)
        
        if not audio_generator:
             raise HTTPException(status_code=500, detail="Failed to generate welcome audio")

        return StreamingResponse(
            audio_generator, 
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=welcome.wav"}
        )
    except Exception as e:
        log_flow("CALL_START_FAIL", str(e))
        raise HTTPException(status_code=500, detail=str(e))

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

@app.post("/api/chat/stream")
async def stream_chat_response(request: TextBookingRequest):
    log_flow("API_HIT: /api/chat/stream", request.text)
    async def generate():
        async for word in process_booking_text_stream(request.text, request.caller_phone):
            yield {"event": "token", "data": json.dumps({"token": word})}
        yield {"event": "done", "data": json.dumps({"complete": True})}
    return EventSourceResponse(generate())

@app.get("/health")
async def health_check():
    return {"status": "online", "mode": "websocket_enabled"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)