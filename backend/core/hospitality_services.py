

# import os
# import json
# import re
# import asyncio
# from openai import AsyncOpenAI
# from gtts import gTTS
# import io
# import time
# from collections import deque
# from typing import Optional, Dict, AsyncGenerator
# from datetime import datetime, date
# from dotenv import load_dotenv

# from core.database import BookingManager, SessionManager

# load_dotenv()

# # ==================== 🎭 RIYA'S PERSONA ====================
# RIYA_SYSTEM_PROMPT = """
# You are Riya, the warm, efficient, and intelligent AI Hostess at 'The Guru's Kitchen'.
# Your voice is friendly, professional, and slightly energetic.

# YOUR MISSION:
# Help the user book a table efficiently while making them feel welcomed.

# GUIDELINES:
# 1. GREETING: If the user says "Hi", greet them warmly.
# 2. IDENTITY: If you don't know their phone number yet, ask for it politely as the first step.
# 3. EFFICIENCY: Keep questions direct. Don't ask for multiple things at once.
# 4. CONFIRMATION: Once all data is gathered, say "Thank you [Name], your booking is confirmed" clearly.
# 5. TONE: Human-like, concise (max 2 sentences).
# 6. FORMAT: Do not output markdown or emojis.
# """

# BOOKING_FLOW = ["phone", "name", "party_size", "date", "time", "special_requests"]
# SESSION_TIMEOUT_MINUTES = 10

# # ==================== LOGGER HELPER ====================
# def log_debug(stage: str, message: str, data: any = None):
#     print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🛠️  {stage.upper()}")
#     print(f"   └─ {message}")
#     if data:
#         print(f"   └─ DATA: {json.dumps(data, default=str)}")

# # ==================== RATE LIMITER ====================
# class TokenTracker:
#     def __init__(self, max_tokens_per_minute=1000):
#         self.max_tokens_per_minute = max_tokens_per_minute
#         self.requests = deque()
    
#     def estimate_tokens(self, text: str) -> int:
#         clean_text = re.sub(r'\s+', ' ', text.strip())
#         return int(len(clean_text) / 4) + 20
    
#     def can_make_request(self, text: str) -> tuple[bool, int]:
#         current_time = time.time()
#         estimated_tokens = self.estimate_tokens(text)
#         while self.requests and current_time - self.requests[0][0] > 60:
#             self.requests.popleft()
#         tokens_used = sum(tokens for _, tokens in self.requests)
#         if tokens_used + estimated_tokens > self.max_tokens_per_minute:
#             return False, tokens_used
#         return True, tokens_used
    
#     def record_request(self, text: str):
#         current_time = time.time()
#         estimated_tokens = self.estimate_tokens(text)
#         self.requests.append((current_time, estimated_tokens))

# # ==================== INITIALIZATION ====================
# try:
#     log_debug("INIT", "Loading Riya (Hospitality AI Services)...")
    
#     groq_api_keys = [
#         os.environ.get("GROQ_API_KEY_1"),
#         os.environ.get("GROQ_API_KEY_2"),
#         os.environ.get("GROQ_API_KEY_3"),
#         os.environ.get("GROQ_API_KEY_4"),
#         os.environ.get("GROQ_API_KEY_5"),
#     ]
#     valid_keys = [k for k in groq_api_keys if k]
#     if not valid_keys: raise ValueError("No Groq API keys found!")

#     groq_clients = [
#         AsyncOpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
#         for key in valid_keys
#     ]
#     main_client = groq_clients[0]
#     token_tracker = TokenTracker()
#     log_debug("INIT", f"✅ Riya is online. Connected to {len(groq_clients)} Groq Clients.")
    
# except Exception as e:
#     log_debug("INIT_ERROR", str(e))
#     main_client = groq_clients = token_tracker = None

# # ==================== AI BRAIN LAYERS ====================

# async def extract_booking_data(message: str) -> Dict:
#     """Uses Llama-3 to extract structured JSON."""
#     log_debug("EXTRACTOR", "Starting Extraction...", message)
#     today = datetime.now().strftime("%Y-%m-%d")
    
#     # 🔥 FIXED PROMPT: Handles "No special requests" correctly
#     system_prompt = f"""
#     You are a Data Extractor API. Today's date is {today}.
#     GOAL: Extract booking information from the user's message into JSON.
    
#     TARGET FIELDS:
#     - phone: Valid phone numbers.
#     - name: User's name.
#     - party_size: Integer.
#     - date: YYYY-MM-DD format.
#     - time: HH:MM format (24 hour).
#     - special_requests: Dietary restrictions or seating. 
#       IMPORTANT: If user says "no", "nothing", "none", or "no requests", set this to the string "None". Do NOT set to null.
    
#     RULES:
#     1. Return JSON ONLY. No markdown.
#     2. If a field is TRULY missing, set it to null.
#     """
#     try:
#         completion = await main_client.chat.completions.create(
#             model="llama-3.3-70b-versatile",
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": message}
#             ],
#             temperature=0.1,
#             max_tokens=200,
#             response_format={"type": "json_object"}
#         )
#         content = completion.choices[0].message.content
#         data = json.loads(content)
#         log_debug("EXTRACTOR", "Extraction Complete", data)
#         return data
#     except Exception as e:
#         log_debug("EXTRACTOR_ERROR", str(e))
#         return {}

# async def generate_riya_response(intent: str, collected_data: Dict) -> str:
#     """Generates the spoken response using Riya's persona."""
#     log_debug("GENERATOR", f"Generating response for intent: {intent}", collected_data)
    
#     prompt = f"""
#     CONTEXT:
#     - Intent: {intent}
#     - Collected Data: {json.dumps(collected_data)}
    
#     INSTRUCTIONS:
#     Draft a spoken response as Riya.
    
#     SCENARIOS:
#     - If intent='ask_phone' -> Ask for their phone number.
#     - If intent='ask_name' -> Ask for the name.
#     - If intent='ask_party_size' -> Ask how many people.
#     - If intent='ask_date' -> Ask for the date.
#     - If intent='ask_time' -> Ask for the preferred time.
#     - If intent='ask_special_requests' -> Ask about allergies/seating.
#     - If intent='confirm_booking' -> Say EXACTLY: "Thank you [Name], your booking for [Date] at [Time] is confirmed! We look forward to serving you."
#     - If intent='unavailable' -> Apologize that the slot is full.
#     - If intent='welcome_back' -> Welcome the user back.
    
#     Keep it short. No emojis.
#     """
    
#     try:
#         completion = await main_client.chat.completions.create(
#             model="llama-3.3-70b-versatile",
#             messages=[
#                 {"role": "system", "content": RIYA_SYSTEM_PROMPT},
#                 {"role": "user", "content": prompt}
#             ],
#             temperature=0.6,
#             max_tokens=200
#         )
#         response = completion.choices[0].message.content.strip().replace('"', '')
        
#         if not response:
#             if "confirm" in intent: return "Thank you, your booking is confirmed!"
#             if "phone" in intent: return "Could I please have your phone number?"
#             return "I'm sorry, I didn't catch that."
#         return response
#     except Exception as e:
#         log_debug("GENERATOR_ERROR", str(e))
#         return "I'm sorry, I'm having trouble thinking right now."

# # ==================== AUDIO PROCESSING ====================

# async def get_text_from_speech(audio_bytes: bytes) -> str:
#     log_debug("STT", f"Transcribing {len(audio_bytes)} bytes...")
#     try:
#         transcription = await main_client.audio.transcriptions.create(
#             file=("request.wav", audio_bytes, "audio/wav"),
#             model="whisper-large-v3",
#             language="en"
#         )
#         return transcription.text
#     except Exception as e:
#         log_debug("STT_ERROR", str(e))
#         return ""

# async def get_speech_from_text(text: str):
#     log_debug("TTS", f"Requesting Audio for: '{text}'")
    
#     can_request, tokens = token_tracker.can_make_request(text)
#     if not can_request:
#         log_debug("TTS_WARN", f"Rate limit hit! Tokens: {tokens}")
#         return None

#     # Try Groq Clients
#     for i, client in enumerate(groq_clients):
#         try:
#             response = await client.audio.speech.create(
#                 model="canopylabs/orpheus-v1-english",
#                 voice="autumn",
#                 response_format="wav",
#                 input=text
#             )
#             token_tracker.record_request(text)
#             if not response: continue
#             return (chunk for chunk in response.iter_bytes())
#         except Exception as e:
#             log_debug("TTS_FAIL", f"Client {i+1} failed: {e}")
#             continue
    
#     # Fallback to gTTS
#     try:
#         tts = gTTS(text=text, lang='en', slow=False)
#         fp = io.BytesIO()
#         tts.write_to_fp(fp)
#         fp.seek(0)
#         return iter([fp.read()])
#     except: return None

# # ==================== CORE PIPELINE ====================

# async def process_booking_conversation(user_text: str, caller_phone: Optional[str] = None) -> str:
#     """The Logic Engine"""
#     log_debug("PIPELINE_START", f"User: '{user_text}' | Phone: {caller_phone}")
    
#     # 1. Parse
#     extracted_data = await extract_booking_data(user_text)
    
#     # 2. Identity Resolution
#     if not caller_phone and extracted_data.get('phone'):
#         caller_phone = extracted_data['phone']
#         log_debug("IDENTITY", f"Resolved: {caller_phone}")
    
#     # 3. Memory Check
#     if caller_phone:
#         booking = await BookingManager.get_upcoming_booking(caller_phone)
#         reset_keywords = ["new booking", "start over"]
#         is_reset = any(kw in user_text.lower() for kw in reset_keywords)
        
#         if booking and not is_reset:
#             context = {
#                 "name": booking['name'],
#                 "date": booking['booking_date'],
#                 "time": booking['booking_time'],
#                 "party_size": booking['party_size']
#             }
#             return await generate_riya_response("welcome_back", context)

#     # 4. Session Retrieval
#     session = await SessionManager.get_state(caller_phone) if caller_phone else None
#     collected_data = session['collected_data'] if session else {}

#     # 5. Data Merge
#     clean_data = {k: v for k, v in extracted_data.items() if v is not None}
#     collected_data.update(clean_data)
#     log_debug("MERGE", "Updated Data", collected_data)
    
#     # 6. State Machine
#     missing_field = None
#     for field in BOOKING_FLOW:
#         if field == 'phone':
#             if not caller_phone and not collected_data.get('phone'):
#                 missing_field = 'phone'
#                 break
#         else:
#             if not collected_data.get(field):
#                 missing_field = field
#                 break
    
#     log_debug("STATE_MACHINE", f"Next Missing Field: {missing_field}")

#     # 7. Logic Branching
#     if missing_field:
#         if caller_phone:
#             # Check DB constraint issues: pass "name" not "ask_name" if schema requires it?
#             # Actually we fixed schema to accept anything.
#             await SessionManager.update_state(caller_phone, f"ask_{missing_field}", collected_data)
#         return await generate_riya_response(f"ask_{missing_field}", collected_data)

#     else:
#         # Validate & Book
#         log_debug("VALIDATION", "All fields present. Checking slots...")
        
#         is_available = await BookingManager.check_slot_availability(
#             collected_data['date'], collected_data['time'], int(collected_data['party_size'])
#         )
        
#         if is_available:
#             log_debug("BOOKING", "Slot Available. Creating Booking...")
            
#             # 🔥 MANUAL DB MAPPING (Fixes 'date' column error)
#             final_data = {
#                 "phone": caller_phone,
#                 "name": collected_data['name'],
#                 "party_size": int(collected_data['party_size']),
#                 "booking_date": collected_data['date'], # Map JSON date -> DB booking_date
#                 "booking_time": collected_data['time'], # Map JSON time -> DB booking_time
#                 "special_requests": collected_data.get('special_requests', 'None')
#             }
            
#             success = await BookingManager.create_booking(final_data)
#             if success:
#                 if caller_phone: await SessionManager.clear_session(caller_phone)
#                 return await generate_riya_response("confirm_booking", collected_data)
#             else:
#                 log_debug("BOOKING_ERROR", "DB Insert Failed")
#                 return "I'm having trouble connecting to the reservation system."
#         else:
#             log_debug("BOOKING", "Slot Unavailable")
#             collected_data.pop('time')
#             if caller_phone: await SessionManager.update_state(caller_phone, 'ask_time', collected_data)
#             return await generate_riya_response("unavailable", collected_data)

# # ==================== PUBLIC INTERFACES ====================

# async def stream_response_tokens(response_text: str) -> AsyncGenerator[str, None]:
#     """Simulates typing for SSE."""
#     words = response_text.split(" ")
#     for word in words:
#         yield word + " "
#         await asyncio.sleep(0.05)

# async def process_booking_text_stream(text: str, caller_phone: Optional[str] = None) -> AsyncGenerator[str, None]:
#     if not text: yield "I didn't catch that."; return
#     full_response = await process_booking_conversation(text, caller_phone)
#     async for token in stream_response_tokens(full_response): yield token

# async def process_booking_text(text: str, caller_phone: Optional[str] = None) -> str:
#     return await process_booking_conversation(text, caller_phone)

# async def process_booking_audio(audio_bytes: bytes, caller_phone: Optional[str] = None):
#     """Audio -> Audio (Returns Stream + Phone)"""
#     user_text = await get_text_from_speech(audio_bytes)
#     if not user_text: 
#         s = await get_speech_from_text("I couldn't hear you.")
#         return s, caller_phone
    
#     if not caller_phone:
#         temp = await extract_booking_data(user_text)
#         if temp.get('phone'): caller_phone = temp['phone']

#     response_text = await process_booking_conversation(user_text, caller_phone)
#     audio_stream = await get_speech_from_text(response_text)
#     return audio_stream, caller_phone

# async def process_text_to_audio(text: str, caller_phone: Optional[str] = None):
#     """Text -> Audio (Returns Stream + Phone)"""
#     log_debug("PROCESS_START", f"Request: '{text}'")
    
#     if not caller_phone:
#         temp = await extract_booking_data(text)
#         if temp.get('phone'): caller_phone = temp['phone']

#     response_text = await process_booking_conversation(text, caller_phone)
#     log_debug("PROCESS_MID", f"Riya says: '{response_text}'")
    
#     audio_stream = await get_speech_from_text(response_text)
#     return audio_stream, caller_phone
import os
import json
import re
import asyncio
from openai import AsyncOpenAI
from gtts import gTTS
import io
import time
from collections import deque
from typing import Optional, Dict, AsyncGenerator
from datetime import datetime, date
from dotenv import load_dotenv

from core.database import BookingManager, SessionManager

load_dotenv()

# ==================== 🎭 RIYA'S PERSONA ====================
RIYA_SYSTEM_PROMPT = """
You are Riya, the warm, efficient, and intelligent AI Hostess at 'The Guru's Kitchen'.
Your voice is friendly, professional, and slightly energetic.

YOUR MISSION:
Help the user book a table efficiently while making them feel welcomed.

GUIDELINES:
1. GREETING: If the user says "Hi", greet them warmly.
2. IDENTITY: If you don't know their phone number yet, ask for it politely as the first step.
3. EFFICIENCY: Keep questions direct. Don't ask for multiple things at once.
4. CONFIRMATION: Once all data is gathered, say "Thank you [Name], your booking for [Date] at [Time] is confirmed! We look forward to serving you."
5. TONE: Human-like, concise (max 2 sentences).
6. FORMAT: Do not output markdown or emojis.
"""

# 🔥 DEMO CHANGE: Removed 'special_requests' from required flow to prevent loops
BOOKING_FLOW = ["phone", "name", "party_size", "date", "time"] 
SESSION_TIMEOUT_MINUTES = 10

# ==================== LOGGER HELPER ====================
def log_debug(stage: str, message: str, data: any = None):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🛠️  {stage.upper()}")
    print(f"   └─ {message}")
    if data:
        print(f"   └─ DATA: {json.dumps(data, default=str)}")

# ==================== RATE LIMITER ====================
class TokenTracker:
    def __init__(self, max_tokens_per_minute=1000):
        self.max_tokens_per_minute = max_tokens_per_minute
        self.requests = deque()
    
    def estimate_tokens(self, text: str) -> int:
        clean_text = re.sub(r'\s+', ' ', text.strip())
        return int(len(clean_text) / 4) + 20
    
    def can_make_request(self, text: str) -> tuple[bool, int]:
        current_time = time.time()
        estimated_tokens = self.estimate_tokens(text)
        while self.requests and current_time - self.requests[0][0] > 60:
            self.requests.popleft()
        tokens_used = sum(tokens for _, tokens in self.requests)
        if tokens_used + estimated_tokens > self.max_tokens_per_minute:
            return False, tokens_used
        return True, tokens_used
    
    def record_request(self, text: str):
        current_time = time.time()
        estimated_tokens = self.estimate_tokens(text)
        self.requests.append((current_time, estimated_tokens))

# ==================== INITIALIZATION ====================
try:
    log_debug("INIT", "Loading Riya (Hospitality AI Services)...")
    
    groq_api_keys = [
        os.environ.get("GROQ_API_KEY_1"),
        os.environ.get("GROQ_API_KEY_2"),
        os.environ.get("GROQ_API_KEY_3"),
        os.environ.get("GROQ_API_KEY_4"),
        os.environ.get("GROQ_API_KEY_5"),
    ]
    valid_keys = [k for k in groq_api_keys if k]
    if not valid_keys: raise ValueError("No Groq API keys found!")

    groq_clients = [
        AsyncOpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
        for key in valid_keys
    ]
    main_client = groq_clients[0]
    token_tracker = TokenTracker()
    log_debug("INIT", f"✅ Riya is online. Connected to {len(groq_clients)} Groq Clients.")
    
except Exception as e:
    log_debug("INIT_ERROR", str(e))
    main_client = groq_clients = token_tracker = None

# ==================== AI BRAIN LAYERS ====================

async def extract_booking_data(message: str) -> Dict:
    """Uses Llama-3 to extract structured JSON."""
    log_debug("EXTRACTOR", "Starting Extraction...", message)
    today = datetime.now().strftime("%Y-%m-%d")
    
    system_prompt = f"""
    You are a Data Extractor API. Today's date is {today}.
    GOAL: Extract booking information from the user's message into JSON.
    
    TARGET FIELDS:
    - phone: Valid phone numbers.
    - name: User's name.
    - party_size: Integer.
    - date: YYYY-MM-DD format.
    - time: HH:MM format (24 hour).
    - special_requests: Dietary restrictions or seating. 
    
    RULES:
    1. Return JSON ONLY. No markdown.
    2. If a field is TRULY missing, set it to null.
    """
    try:
        completion = await main_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"}
        )
        content = completion.choices[0].message.content
        data = json.loads(content)
        log_debug("EXTRACTOR", "Extraction Complete", data)
        return data
    except Exception as e:
        log_debug("EXTRACTOR_ERROR", str(e))
        return {}

async def generate_riya_response(intent: str, collected_data: Dict) -> str:
    """Generates the spoken response using Riya's persona."""
    log_debug("GENERATOR", f"Generating response for intent: {intent}", collected_data)
    
    prompt = f"""
    CONTEXT:
    - Intent: {intent}
    - Collected Data: {json.dumps(collected_data)}
    
    INSTRUCTIONS:
    Draft a spoken response as Riya.
    
    SCENARIOS:
    - If intent='ask_phone' -> Ask for their phone number.
    - If intent='ask_name' -> Ask for the name.
    - If intent='ask_party_size' -> Ask how many people.
    - If intent='ask_date' -> Ask for the date.
    - If intent='ask_time' -> Ask for the preferred time.
    - If intent='confirm_booking' -> Say: "Thank you [Name], your booking for [Party Size] people on [Date] at [Time] is confirmed!"
    - If intent='unavailable' -> Apologize that the slot is full.
    - If intent='welcome_back' -> Welcome the user back.
    
    Keep it short. No emojis.
    """
    
    try:
        completion = await main_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": RIYA_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=200
        )
        response = completion.choices[0].message.content.strip().replace('"', '')
        
        if not response:
            if "confirm" in intent: return "Thank you, your booking is confirmed!"
            return "I'm sorry, I didn't catch that."
        return response
    except Exception as e:
        log_debug("GENERATOR_ERROR", str(e))
        return "I'm sorry, I'm having trouble thinking right now."

# ==================== AUDIO PROCESSING (ROBUST FALLBACK) ====================

async def get_text_from_speech(audio_bytes: bytes) -> str:
    log_debug("STT", f"Transcribing {len(audio_bytes)} bytes...")
    try:
        transcription = await main_client.audio.transcriptions.create(
            file=("request.wav", audio_bytes, "audio/wav"),
            model="whisper-large-v3",
            language="en"
        )
        return transcription.text
    except Exception as e:
        log_debug("STT_ERROR", str(e))
        return ""

async def get_speech_from_text(text: str):
    log_debug("TTS", f"Requesting Audio for: '{text}'")
    
    # Try Groq Clients (Round Robin)
    for i, client in enumerate(groq_clients):
        try:
            can_request, tokens = token_tracker.can_make_request(text)
            if not can_request:
                log_debug("TTS_WARN", f"Rate limit hit on Client {i+1}")
                continue

            response = await client.audio.speech.create(
                model="canopylabs/orpheus-v1-english",
                voice="autumn",
                response_format="wav",
                input=text
            )
            token_tracker.record_request(text)
            log_debug("TTS", f"✅ TTS Success (Client {i+1})")
            return (chunk for chunk in response.iter_bytes())
        except Exception as e:
            log_debug("TTS_FAIL", f"Client {i+1} failed: {e}")
            continue
    
    # Fallback to gTTS (Bulletproof)
    log_debug("TTS", "⚠️ ALL GROQ CLIENTS FAILED. FALLBACK TO GTTS.")
    try:
        tts = gTTS(text=text, lang='en', slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return iter([fp.read()])
    except: return None

# ==================== CORE PIPELINE ====================

async def process_booking_conversation(user_text: str, caller_phone: Optional[str] = None) -> str:
    """The Logic Engine"""
    log_debug("PIPELINE_START", f"User: '{user_text}' | Phone: {caller_phone}")
    
    # 1. Parse
    extracted_data = await extract_booking_data(user_text)
    
    # 2. Identity Resolution
    if not caller_phone and extracted_data.get('phone'):
        caller_phone = extracted_data['phone']
        log_debug("IDENTITY", f"Resolved: {caller_phone}")
    
    # 3. Memory Check
    if caller_phone:
        booking = await BookingManager.get_upcoming_booking(caller_phone)
        reset_keywords = ["new booking", "start over"]
        is_reset = any(kw in user_text.lower() for kw in reset_keywords)
        
        if booking and not is_reset:
            context = {
                "name": booking['name'],
                "date": booking['booking_date'],
                "time": booking['booking_time'],
                "party_size": booking['party_size']
            }
            return await generate_riya_response("welcome_back", context)

    # 4. Session Retrieval
    session = await SessionManager.get_state(caller_phone) if caller_phone else None
    collected_data = session['collected_data'] if session else {}

    # 5. Data Merge
    clean_data = {k: v for k, v in extracted_data.items() if v is not None}
    collected_data.update(clean_data)
    log_debug("MERGE", "Updated Data", collected_data)
    
    # 6. State Machine
    missing_field = None
    for field in BOOKING_FLOW:
        if field == 'phone':
            if not caller_phone and not collected_data.get('phone'):
                missing_field = 'phone'
                break
        else:
            if not collected_data.get(field):
                missing_field = field
                break
    
    log_debug("STATE_MACHINE", f"Next Missing Field: {missing_field}")

    # 7. Logic Branching
    if missing_field:
        if caller_phone:
            await SessionManager.update_state(caller_phone, f"ask_{missing_field}", collected_data)
        return await generate_riya_response(f"ask_{missing_field}", collected_data)

    else:
        # 🔥 DEMO MODE: AUTO-FILL SPECIAL REQUESTS
        # If we have all required fields, assume requests="None" and finish.
        if not collected_data.get('special_requests'):
            collected_data['special_requests'] = "None"

        # Validate & Book
        log_debug("VALIDATION", "Checking slots...")
        
        is_available = await BookingManager.check_slot_availability(
            collected_data['date'], collected_data['time'], int(collected_data['party_size'])
        )
        
        if is_available:
            log_debug("BOOKING", "Slot Available. Creating Booking...")
            
            # 🔥 MANUAL DB MAPPING
            final_data = {
                "phone": caller_phone,
                "name": collected_data['name'],
                "party_size": int(collected_data['party_size']),
                "booking_date": collected_data['date'], 
                "booking_time": collected_data['time'], 
                "special_requests": collected_data.get('special_requests', 'None')
            }
            
            success = await BookingManager.create_booking(final_data)
            if success:
                if caller_phone: await SessionManager.clear_session(caller_phone)
                return await generate_riya_response("confirm_booking", collected_data)
            else:
                return "I'm having trouble connecting to the reservation system."
        else:
            log_debug("BOOKING", "Slot Unavailable")
            collected_data.pop('time')
            if caller_phone: await SessionManager.update_state(caller_phone, 'ask_time', collected_data)
            return await generate_riya_response("unavailable", collected_data)

# ==================== PUBLIC INTERFACES ====================

async def stream_response_tokens(response_text: str) -> AsyncGenerator[str, None]:
    words = response_text.split(" ")
    for word in words:
        yield word + " "
        await asyncio.sleep(0.05)

async def process_booking_text_stream(text: str, caller_phone: Optional[str] = None) -> AsyncGenerator[str, None]:
    if not text: yield "I didn't catch that."; return
    full_response = await process_booking_conversation(text, caller_phone)
    async for token in stream_response_tokens(full_response): yield token

async def process_booking_text(text: str, caller_phone: Optional[str] = None) -> str:
    return await process_booking_conversation(text, caller_phone)

async def process_booking_audio(audio_bytes: bytes, caller_phone: Optional[str] = None):
    """Audio -> Audio (Returns Stream + Phone)"""
    user_text = await get_text_from_speech(audio_bytes)
    if not user_text: 
        s = await get_speech_from_text("I couldn't hear you.")
        return s, caller_phone
    
    if not caller_phone:
        temp = await extract_booking_data(user_text)
        if temp.get('phone'): caller_phone = temp['phone']

    response_text = await process_booking_conversation(user_text, caller_phone)
    audio_stream = await get_speech_from_text(response_text)
    return audio_stream, caller_phone

async def process_text_to_audio(text: str, caller_phone: Optional[str] = None):
    """Text -> Audio (Returns Stream + Phone)"""
    log_debug("PROCESS_START", f"Request: '{text}'")
    
    if not caller_phone:
        temp = await extract_booking_data(text)
        if temp.get('phone'): caller_phone = temp['phone']

    response_text = await process_booking_conversation(text, caller_phone)
    log_debug("PROCESS_MID", f"Riya says: '{response_text}'")
    
    audio_stream = await get_speech_from_text(response_text)
    return audio_stream, caller_phone