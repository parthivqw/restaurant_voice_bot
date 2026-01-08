import os
from supabase import create_client, Client
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Singleton DB Client
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") # Use Service Role for backend ops
db_client: Client = create_client(url, key)

class BookingManager:
    @staticmethod
    async def get_upcoming_booking(phone: str):
        """Check if this user has a future confirmed/pending booking (Memory)"""
        if not phone: return None
        try:
            response = db_client.table('bookings').select('*')\
                .eq('phone', phone)\
                .in_('status', ['confirmed', 'pending'])\
                .gte('booking_date', datetime.now().date().isoformat())\
                .execute()
            
            if response.data:
                return response.data[0] # Return the first active booking
            return None
        except Exception as e:
            print(f"❌ DB Error (get_booking): {e}")
            return None

    @staticmethod
    async def create_booking(data: dict):
        """Insert a new booking"""
        try:
            return db_client.table('bookings').insert(data).execute()
        except Exception as e:
            print(f"❌ DB Error (create_booking): {e}")
            return None

    @staticmethod
    async def check_slot_availability(date_str: str, time_str: str, party_size: int):
        """Check time_slots table for capacity"""
        try:
            # First, check if slot exists
            response = db_client.table('time_slots').select('*')\
                .eq('booking_date', date_str)\
                .eq('booking_time', time_str)\
                .execute()
            
            if not response.data:
                return False # Slot doesn't exist (e.g., closed)

            slot = response.data[0]
            if (slot['table_capacity'] - slot['booked_capacity']) >= party_size:
                return True
            return False
        except Exception as e:
            print(f"❌ DB Error (check_availability): {e}")
            return False

class SessionManager:
    @staticmethod
    async def get_state(phone: str):
        """Get where the user is in the conversation flow"""
        if not phone: return None
        try:
            response = db_client.table('conversation_state').select('*').eq('phone', phone).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ DB Error (get_state): {e}")
            return None

    @staticmethod
    async def update_state(phone: str, step: str, data: dict = None):
        """Update the conversation step and collected data"""
        if not phone: return
        
        try:
            existing = await SessionManager.get_state(phone)
            
            payload = {
                "phone": phone,
                "current_step": step,
                "last_interaction": datetime.now().isoformat()
            }
            
            if data:
                # Merge new data with existing JSONB data
                current_data = existing['collected_data'] if existing else {}
                current_data.update(data)
                payload['collected_data'] = current_data
            elif not existing:
                 # Initialize empty if creating new and no data passed
                 payload['collected_data'] = {}

            if existing:
                db_client.table('conversation_state').update(payload).eq('phone', phone).execute()
            else:
                db_client.table('conversation_state').insert(payload).execute()
                
        except Exception as e:
            print(f"❌ DB Error (update_state): {e}")

    @staticmethod
    async def clear_session(phone: str):
        """Wipe session after successful booking"""
        if not phone: return
        try:
            db_client.table('conversation_state').delete().eq('phone', phone).execute()
        except Exception as e:
            print(f"❌ DB Error (clear_session): {e}")