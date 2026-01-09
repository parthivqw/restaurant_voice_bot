
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
You are Riya, the voice of The Guru's Kitchen—a warm, professional hostess who makes every caller feel like a regular, even if it's their first time.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 YOUR MISSION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Secure a reservation while making the caller feel heard, valued, and excited about their visit.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🗣️ HOW YOU SPEAK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **ACKNOWLEDGE → THEN ASK**
   Never jump straight to the next question. React to what they just said.
   
   ❌ Bad: "What time?"
   ✅ Good: "Perfect, a table for 4! What time works best for you?"

2. **CONVERSATIONAL, NOT TRANSACTIONAL**
   You're a human, not a form. Use natural fillers:
   - "Got it!"
   - "Sure thing."
   - "Let me just grab that real quick."
   - "No problem at all."

3. **SHORT & SWEET**
   Keep responses to 1-2 sentences max. Let the caller speak.

4. **NO ROBOTIC LISTS**
   Never say: "I need your name, phone number, date, and time."
   Ask one thing at a time, naturally.

5. **PHONE NUMBER FORMATTING** ⚠️ CRITICAL
   When saying phone numbers out loud, ALWAYS format them naturally with spaces/dashes for TTS clarity:
   
   ❌ Bad: "7994335235" (sounds like "seven billion...")
   ✅ Good: "799-433-5235" or "799 433 5235"
   
   Examples:
   - "Got it, 799-433-5235."
   - "We'll text confirmation to 799 433 5235."
   - "Your number is 799-433-5235, correct?"

6. **TONE CALIBRATION**
   - **New caller**: Friendly, upbeat.
   - **Returning caller**: Pleasantly surprised.
   - **Confirmation**: Confident and enthusiastic.

Remember: You're not filling out a form. You're helping a guest feel excited about their meal.
"""

# 🔥 FIXED: Phone MUST come before booking finalizes
BOOKING_FLOW = ["name", "phone", "party_size", "date", "time"]
MAX_RETRIES_PER_FIELD = 3

# ==================== LOGGER ====================
def log_debug(stage: str, message: str, data: any = None):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🛠️  {stage.upper()}")
    print(f"   └─ {message}")
    if data:
        print(f"   └─ DATA: {json.dumps(data, default=str, indent=2)}")

# ==================== PHONE VALIDATOR ====================
def is_valid_phone(phone_str: str) -> bool:
    """Check if string looks like a real phone number (not a session ID)"""
    if not phone_str or not isinstance(phone_str, str):
        return False
    
    # Remove common formatting
    clean = re.sub(r'[\s\-\(\)\+]', '', phone_str)
    
    # Must be 10-15 digits (typical phone range)
    if not clean.isdigit():
        return False
    
    if len(clean) < 10 or len(clean) > 15:
        return False
    
    # Session IDs are 8 hex chars - reject those
    if len(clean) == 8 and all(c in '0123456789abcdef' for c in phone_str.lower()):
        return False
    
    return True

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
    
    groq_api_keys = [os.environ.get(f"GROQ_API_KEY_{i}") for i in range(1, 6)]
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

# ==================== AI EXTRACTION ====================
async def extract_booking_data(message: str) -> Dict:
    """Uses Llama-3 to extract structured JSON from user message."""
    log_debug("EXTRACTOR", "Starting Extraction...", message)
    today = datetime.now().strftime("%Y-%m-%d")
    
    system_prompt = f"""
You are a Data Extractor API for a restaurant booking system. Today's date is {today}.

GOAL: Extract booking information from the user's message into JSON.

TARGET FIELDS:
- phone: Valid phone numbers (10+ digits, with or without country code). Must look like a real phone number.
- name: User's full name or first name
- party_size: Integer (number of guests)
- date: YYYY-MM-DD format (convert relative dates like "tomorrow", "next Friday")
- time: HH:MM format (24-hour, e.g., 19:00 for 7 PM)
- special_requests: Any dietary restrictions, seating preferences, or special occasions

EXTRACTION RULES:
1. Return ONLY valid JSON. No markdown, no explanations.
2. If a field is TRULY missing from the input, set it to null.
3. For dates: "tomorrow" = {today} + 1 day
4. For times: Convert "7 PM" → "19:00", "noon" → "12:00", "1 PM" → "13:00"
5. Extract partial info: If user says "table for 4", extract party_size=4 even if other fields are missing.
6. If user REPEATS information (e.g., "I already told you my name is John"), extract it again to confirm.
7. CRITICAL: Only extract phone if it looks like a REAL phone number (10+ digits). Ignore random IDs or short codes.

EXAMPLES:
Input: "Hi, I'm John. I need a table for 4 tomorrow at 7 PM"
Output: {{"phone": null, "name": "John", "party_size": 4, "date": "2025-01-09", "time": "19:00", "special_requests": null}}

Input: "My number is 555-123-4567"
Output: {{"phone": "5551234567", "name": null, "party_size": null, "date": null, "time": null, "special_requests": null}}

Input: "Call me at +91 98765 43210"
Output: {{"phone": "919876543210", "name": null, "party_size": null, "date": null, "time": null, "special_requests": null}}

Now extract from the user's message.
"""
    try:
        completion = await main_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            temperature=0.1,
            max_tokens=250,
            response_format={"type": "json_object"}
        )
        content = completion.choices[0].message.content
        data = json.loads(content)
        
        # 🔥 CRITICAL: Validate phone before accepting
        if data.get('phone') and not is_valid_phone(data['phone']):
            log_debug("EXTRACTOR_PHONE_REJECTED", f"Invalid phone: {data['phone']}")
            data['phone'] = None
        
        log_debug("EXTRACTOR", "Extraction Complete", data)
        return data
    except Exception as e:
        log_debug("EXTRACTOR_ERROR", str(e))
        return {}

# ==================== AI RESPONSE GENERATION ====================
async def generate_riya_response(intent: str, collected_data: Dict, last_user_text: str = '') -> str:
    """Generates natural spoken response using Riya's persona."""
    log_debug("GENERATOR", f"Generating response for intent: {intent}", collected_data)
    
    history_list = collected_data.get('history', [])
    recent_history = history_list[-6:]
    history_str = "\n".join(recent_history) if recent_history else "No previous context."

    prompt = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📞 CONVERSATION STATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**Recent Conversation:**
{history_str}

**What the caller just said:**
"{last_user_text}"

**Current Goal (Intent):**
{intent}

**Information Collected So Far:**
{json.dumps(collected_data, indent=2)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 YOUR TASK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generate a natural, spoken response based on the current intent.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 INTENT-SPECIFIC BEHAVIORS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**welcome**
→ "Hi! Thanks for calling The Guru's Kitchen. This is Riya. Who am I speaking with?"

**ask_name**
→ "Perfect! And who should I put this reservation under?"

**ask_phone**
→ "Great! And what's the best number to reach you at?"

**ask_party_size**
→ "Got it! How many people will be joining you?"

**ask_date**
→ "Awesome! What date were you thinking?"

**ask_time**
→ "Perfect! What time works best for you?"

**confirm_booking**
→ "Amazing! You're all set—table for [party_size] on [date] at [time] under [name]. We can't wait to see you!"

**unavailable**
→ "Oh, that time's fully booked. Would another time work for you?"

**force_complete**
→ "Perfect! Let me finalize your reservation with the details we have. You're booked for [party_size] people on [date] at [time] under [name]. We'll see you then!"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ CRITICAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **ALWAYS acknowledge what they just said** before asking the next question.
2. **Keep it SHORT**: 1-2 sentences max.
3. **NO EMOJIS** in your response.
4. **Don't repeat yourself**. If they already gave you info, don't ask for it again.

Now generate your response:
"""
    
    try:
        completion = await main_client.chat.completions.create(
            model="moonshotai/kimi-k2-instruct-0905",
            messages=[
                {"role": "system", "content": RIYA_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150
        )
        response = completion.choices[0].message.content.strip()
        response = response.replace('"', '').replace('*', '').strip()
        
        if not response:
            if "confirm" in intent: return "Thank you! Your booking is confirmed."
            if "welcome" in intent: return "Hi! Thanks for calling The Guru's Kitchen. This is Riya."
            return "I'm sorry, I didn't catch that."
        
        log_debug("GENERATOR_SUCCESS", f"Generated: {response}")
        return response
        
    except Exception as e:
        log_debug("GENERATOR_ERROR", str(e))
        return "I'm sorry, I'm having trouble thinking right now."

# ==================== AUDIO PROCESSING ====================
async def get_text_from_speech(audio_bytes: bytes) -> str:
    log_debug("STT", f"Transcribing {len(audio_bytes)} bytes...")
    try:
        transcription = await main_client.audio.transcriptions.create(
            file=("request.wav", audio_bytes, "audio/wav"),
            model="whisper-large-v3",
            language="en"
        )
        text = transcription.text.strip()
        log_debug("STT_SUCCESS", f"Transcribed: '{text}'")
        return text
    except Exception as e:
        log_debug("STT_ERROR", str(e))
        return ""

async def get_speech_from_text(text: str):
    log_debug("TTS", f"Requesting Audio for: '{text}'")
    
    for i, client in enumerate(groq_clients):
        try:
            can_request, tokens = token_tracker.can_make_request(text)
            if not can_request: continue

            response = await client.audio.speech.create(
                model="canopylabs/orpheus-v1-english",
                voice="autumn",
                response_format="wav",
                input=text
            )
            token_tracker.record_request(text)
            log_debug("TTS_SUCCESS", f"✅ TTS Success (Client {i+1})")
            return (chunk for chunk in response.iter_bytes())
        except Exception as e:
            log_debug("TTS_FAIL", f"Client {i+1}: {e}")
            continue
    
    log_debug("TTS_FALLBACK", "⚠️ FALLBACK TO GTTS.")
    try:
        tts = gTTS(text=text, lang='en', slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return iter([fp.read()])
    except: return None

# ==================== 🔥 FIXED CORE PIPELINE ====================
async def process_booking_conversation(
    user_text: str, 
    session_id: Optional[str] = None,  # 🔥 NEW: Separate session tracking
    real_phone: Optional[str] = None    # 🔥 NEW: Actual phone (when verified)
) -> tuple[str, Optional[str]]:
    """
    Returns: (response_text, verified_phone_number)
    """
    log_debug("PIPELINE_START", f"User: '{user_text}' | Session: {session_id} | Phone: {real_phone}")
    
    # 1. Parse Input
    extracted_data = await extract_booking_data(user_text)
    
    # 2. Identity Resolution (only if phone looks valid)
    detected_phone = extracted_data.get('phone')
    phone_just_verified = False
    
    if detected_phone and is_valid_phone(detected_phone):
        if not real_phone:
            real_phone = detected_phone
            phone_just_verified = True
            log_debug("IDENTITY_VERIFIED", f"Phone confirmed: {real_phone}")
    
    # 3. 🔥 CRITICAL FIX: Load session from CURRENT tracking key FIRST
    current_key = real_phone or session_id
    session = await SessionManager.get_state(current_key) if current_key else None
    
    # 4. 🔥 MIGRATE SESSION DATA when phone is verified
    if phone_just_verified and session_id and session_id != real_phone:
        # Load old session from temp session_id
        old_session = await SessionManager.get_state(session_id)
        
        if old_session and old_session.get('collected_data'):
            log_debug("SESSION_MIGRATION", f"Migrating data from {session_id} → {real_phone}")
            # Copy old session data to new phone-based session
            collected_data = old_session['collected_data'].copy()
            # Save under new phone number
            await SessionManager.update_state(real_phone, old_session.get('current_step', 'active'), collected_data)
            # Clear old temp session
            await SessionManager.clear_session(session_id)
            log_debug("SESSION_MIGRATED", "Data successfully migrated", collected_data)
        elif session and session.get('collected_data'):
            # Phone session already exists
            collected_data = session['collected_data'].copy()
            log_debug("SESSION_LOADED", "Restored previous data", collected_data)
        else:
            collected_data = {'retry_count': {}}
            log_debug("SESSION_NEW", "Starting fresh conversation")
    elif session and session.get('collected_data'):
        collected_data = session['collected_data'].copy()
        log_debug("SESSION_LOADED", "Restored previous data", collected_data)
    else:
        collected_data = {'retry_count': {}}
        log_debug("SESSION_NEW", "Starting fresh conversation")
    
    # 5. Update History
    history = collected_data.get('history', [])
    history.append(f"Caller: {user_text}")
    collected_data['history'] = history
    
    # 6. Merge extracted data
    for key, value in extracted_data.items():
        if value is not None and value != "":
            # Special handling for phone - must be validated
            if key == 'phone':
                if is_valid_phone(value):
                    collected_data[key] = value
                    retry_counts = collected_data.get('retry_count', {})
                    retry_counts[key] = 0
                    collected_data['retry_count'] = retry_counts
                    log_debug("DATA_UPDATED", f"Phone validated: {value}")
            else:
                collected_data[key] = value
                retry_counts = collected_data.get('retry_count', {})
                retry_counts[key] = 0
                collected_data['retry_count'] = retry_counts
                log_debug("DATA_UPDATED", f"Field updated: {key} = {value}")
    
    log_debug("MERGE", "Current State", collected_data)
    
    # 7. 🔥 ALWAYS use real_phone for saving if available
    tracking_key = real_phone or session_id
    
    # 8. Welcome Logic
    greeting_keywords = ["hi", "hello", "hey", "good morning"]
    is_greeting = any(kw in user_text.lower() for kw in greeting_keywords)
    if not session and is_greeting:
        response = await _generate_and_save_response(
            "welcome", collected_data, user_text, tracking_key
        )
        return response, real_phone

    # 9. State Machine - Find next missing field
    missing_field = None
    retry_counts = collected_data.get('retry_count', {})
    
    for field in BOOKING_FLOW:
        # 🔥 CRITICAL: Phone must be REAL and VALIDATED
        if field == 'phone':
            current_phone = collected_data.get('phone')
            if not current_phone or not is_valid_phone(current_phone):
                field_retries = retry_counts.get(field, 0)
                
                if field_retries >= MAX_RETRIES_PER_FIELD:
                    # Cannot proceed without valid phone
                    log_debug("PHONE_REQUIRED", "Cannot complete booking without valid phone")
                    response = "I'm sorry, I need a valid phone number to complete your reservation. What's the best number to reach you?"
                    return response, real_phone
                
                missing_field = field
                retry_counts[field] = field_retries + 1
                collected_data['retry_count'] = retry_counts
                break
        elif not collected_data.get(field):
            field_retries = retry_counts.get(field, 0)
            
            if field_retries >= MAX_RETRIES_PER_FIELD:
                log_debug("THRESHOLD_HIT", f"Auto-filling {field}")
                
                # Auto-fill with defaults
                if field == 'name':
                    collected_data['name'] = 'Guest'
                elif field == 'party_size':
                    collected_data['party_size'] = 2
                elif field == 'date':
                    collected_data['date'] = datetime.now().strftime("%Y-%m-%d")
                elif field == 'time':
                    collected_data['time'] = "19:00"
                
                log_debug("AUTO_FILLED", f"{field} = {collected_data.get(field)}")
                continue
            
            missing_field = field
            retry_counts[field] = field_retries + 1
            collected_data['retry_count'] = retry_counts
            break
    
    log_debug("STATE", f"Next missing: {missing_field} | Retries: {retry_counts}")

    # 10. Response Logic
    if missing_field:
        response = await _generate_and_save_response(
            f"ask_{missing_field}", collected_data, user_text, tracking_key
        )
        return response, real_phone
    else:
        # All data collected - Final validation before booking
        final_phone = collected_data.get('phone')
        
        if not final_phone or not is_valid_phone(final_phone):
            log_debug("BOOKING_BLOCKED", "Invalid phone number")
            response = "I need a valid phone number to complete your reservation. What's your contact number?"
            return response, real_phone
        
        if not collected_data.get('special_requests'): 
            collected_data['special_requests'] = "None"

        # Validate slot
        is_available = await BookingManager.check_slot_availability(
            collected_data['date'], 
            collected_data['time'], 
            int(collected_data['party_size'])
        )
        
        if is_available:
            # Create booking with validated phone
            final_data = {
                "phone": final_phone,  # 🔥 GUARANTEED VALID NOW
                "name": collected_data['name'],
                "party_size": int(collected_data['party_size']),
                "booking_date": collected_data['date'],
                "booking_time": collected_data['time'],
                "special_requests": collected_data.get('special_requests', 'None')
            }
            
            success = await BookingManager.create_booking(final_data)
            
            if success:
                if tracking_key: 
                    await SessionManager.clear_session(tracking_key)
                log_debug("BOOKING_SUCCESS", "Reservation confirmed!", final_data)
                
                auto_filled = any(retry_counts.get(f, 0) >= MAX_RETRIES_PER_FIELD for f in BOOKING_FLOW)
                intent = "force_complete" if auto_filled else "confirm_booking"
                
                response = await generate_riya_response(intent, collected_data, user_text)
                return response, final_phone
            else:
                return "I'm having trouble connecting to the system.", real_phone
        else:
            collected_data.pop('time', None)
            retry_counts['time'] = 0
            collected_data['retry_count'] = retry_counts
            response = await _generate_and_save_response(
                "unavailable", collected_data, user_text, tracking_key
            )
            return response, real_phone

async def _generate_and_save_response(intent, data, user_text, tracking_key):
    """Helper to generate response and save it to history/DB"""
    response = await generate_riya_response(intent, data, user_text)
    
    history = data.get('history', [])
    history.append(f"Riya: {response}")
    data['history'] = history
    
    if tracking_key: 
        await SessionManager.update_state(tracking_key, intent, data)
        log_debug("SESSION_SAVED", f"Saved to DB for {tracking_key}", data)
    
    return response

# ==================== PUBLIC INTERFACES ====================
async def stream_response_tokens(response_text: str) -> AsyncGenerator[str, None]:
    words = response_text.split(" ")
    for word in words:
        yield word + " "
        await asyncio.sleep(0.05)

async def process_booking_text_stream(text: str, session_id: str = None, real_phone: str = None):
    if not text: yield "I didn't catch that."; return
    response, phone = await process_booking_conversation(text, session_id, real_phone)
    async for token in stream_response_tokens(response): 
        yield token

async def process_booking_text(text: str, session_id: str = None, real_phone: str = None):
    response, phone = await process_booking_conversation(text, session_id, real_phone)
    return response

async def process_booking_audio(audio_bytes: bytes, session_id: str = None, real_phone: str = None):
    user_text = await get_text_from_speech(audio_bytes)
    if not user_text: 
        s = await get_speech_from_text("I couldn't hear you.")
        return s, real_phone

    response_text, detected_phone = await process_booking_conversation(user_text, session_id, real_phone)
    audio_stream = await get_speech_from_text(response_text)
    return audio_stream, detected_phone

async def process_text_to_audio(text: str, session_id: str = None, real_phone: str = None):
    log_debug("PROCESS_START", f"Request: '{text}'")
    
    response_text, detected_phone = await process_booking_conversation(text, session_id, real_phone)
    log_debug("PROCESS_MID", f"Riya says: '{response_text}'")
    
    audio_stream = await get_speech_from_text(response_text)
    return audio_stream, detected_phone

async def start_new_call(session_id: str = None):
    """Initiates the call from Riya's side"""
    log_debug("CALL_START", f"New call initiated for session: {session_id}")
    
    if session_id:
        await SessionManager.clear_session(session_id)
    
    greeting_text = "Hi! Thanks for calling The Guru's Kitchen. This is Riya. Who am I speaking with?"
    return await get_speech_from_text(greeting_text)