import asyncio
import os
from dotenv import load_dotenv
from supabase import create_client

# Import the brain we just built
from core.hospitality_services import (
    process_booking_conversation,
    process_booking_text_stream,
    SessionManager,
    BookingManager
)

load_dotenv()

# Test Configuration
TEST_PHONE = "+919999999999"  # A fake number for testing
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
db = create_client(supabase_url, supabase_key)

async def cleanup_test_data():
    """Wipes test data so we start fresh every time"""
    print(f"\n🧹 CLEANUP: Removing test data for {TEST_PHONE}...")
    try:
        # Delete from conversation state
        db.table('conversation_state').delete().eq('phone', TEST_PHONE).execute()
        # Delete from bookings
        db.table('bookings').delete().eq('phone', TEST_PHONE).execute()
        print("✅ DB Cleaned.")
    except Exception as e:
        print(f"⚠️ Cleanup warning: {e}")

async def run_test_scenario_1_anonymous():
    """
    SCENARIO: User on website (No phone passed in API).
    Expectation: Riya asks for phone, then proceeds.
    """
    print(f"\n{'='*60}")
    print("🧪 TEST SCENARIO 1: Anonymous Web User (Identity Resolution)")
    print(f"{'='*60}")

    # Track the "Client Side" session
    current_caller_id = None 

    # 1. User says Hi (No Phone)
    print("👤 User: 'Hi, I want to book a table.'")
    response = await process_booking_conversation("Hi, I want to book a table.", caller_phone=current_caller_id)
    print(f"🤖 Riya: {response}")
    
    # 2. User gives phone -> WE MUST UPDATE OUR TEST STATE
    # In a real app, the frontend sends the phone info, or the backend returns a session token.
    # Here, we simulate the user providing it.
    user_input = f"Sure, it is {TEST_PHONE}"
    print(f"\n👤 User: '{user_input}'")
    
    # Send the input. Riya will resolve identity internally.
    # CRITICAL: We pass None first, let Riya find it.
    response = await process_booking_conversation(user_input, caller_phone=current_caller_id)
    print(f"🤖 Riya: {response}")

    # *** SIMULATING SESSION HANDOFF ***
    # Now that the user has provided the phone, the "Frontend" or "Twilio" 
    # would identify this caller by that number from now on.
    current_caller_id = TEST_PHONE 
    print(f"ℹ️ [SYSTEM]: Identity Established. Next request will use Caller ID: {current_caller_id}")

    # 3. User gives details (Now sending the ID)
    input_3 = "Parthiv, party of 2 for tomorrow at 7 PM"
    print(f"\n👤 User: '{input_3}'")
    response = await process_booking_conversation(input_3, caller_phone=current_caller_id)
    print(f"🤖 Riya: {response}")
async def run_test_scenario_2_streaming():
    """
    SCENARIO: Testing the SSE Stream generator.
    """
    print(f"\n{'='*60}")
    print("🧪 TEST SCENARIO 2: Streaming Response (SSE)")
    print(f"{'='*60}")
    
    prompt = "Do you have any vegan options?"
    print(f"👤 User: '{prompt}' (Stream Requested)")
    print("🤖 Riya (Streaming): ", end="", flush=True)
    
    async for token in process_booking_text_stream(prompt, caller_phone=TEST_PHONE):
        print(token, end="", flush=True)
    print("\n✅ Stream complete.")

async def run_test_scenario_3_memory():
    """
    SCENARIO: User calls back (Phone known).
    Expectation: Riya remembers the booking from Scenario 1.
    """
    print(f"\n{'='*60}")
    print("🧪 TEST SCENARIO 3: Returning Caller (Memory Check)")
    print(f"{'='*60}")

    # Simulate a call coming from the test phone
    print(f"📞 Incoming Call: {TEST_PHONE}")
    print("👤 User: 'Hey Riya, just checking in.'")
    
    # Note: We pass the phone number explicitly here
    response = await process_booking_conversation("Hey Riya, just checking in.", caller_phone=TEST_PHONE)
    print(f"🤖 Riya: {response}")

async def main():
    print("🚀 STARTING HOSPITALITY ENGINE DIAGNOSTICS...")
    
    # 1. Reset DB
    await cleanup_test_data()
    
    # 2. Run Anonymous Flow (Booking Creation)
    await run_test_scenario_1_anonymous()
    
    # 3. Run Streaming Test
    await run_test_scenario_2_streaming()
    
    # 4. Run Memory Test (Confirming the booking from Step 2 exists)
    await run_test_scenario_3_memory()
    
    # 5. Cleanup (Optional - comment out if you want to see data in Supabase)
    # await cleanup_test_data()
    
    print(f"\n{'='*60}")
    print("✅ DIAGNOSTICS COMPLETE")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())