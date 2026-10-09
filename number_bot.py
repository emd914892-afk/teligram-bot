import sqlite3
import re
from datetime import datetime, date, timedelta
import time
import logging
import io 
import random 
import asyncio 
import os 
import requests 
import signal
import warnings
from logging import INFO 

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, 
    Bot, error, CallbackQuery 
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes,
    ConversationHandler
)

warnings.filterwarnings('ignore', category=UserWarning) 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=INFO)

BOT_TOKEN = "8249342286:AAHfDDsSThMVfk8pkeHJXV_EHr6ad2AB70k" 
DB_NAME = 'bot_users.db' 
ADMIN_USERNAME = "@Creator_GlobalSMSCommunity_Owner" 
ADMIN_ID = 7895816348 
MIN_WITHDRAWAL_AMOUNT = 1.00 
REFERRAL_EARNING_RATE = 0.002

REQUIRED_CHANNELS = [
    ('Update Channel', 'https://t.me/Global_SMS_Update'),
    ('Method Channel', 'https://t.me/Global_SMS_Method'),
    ('Support Group', 'https://t.me/Global_SMS_Support'),
    ('Otp Group', 'https://t.me/Global_SMS_OTP')
]
OTP_CHANNEL_LINK = "https://t.me/Global_SMS_OTP"

WITHDRAW_START, WAITING_FOR_BINANCE_ID, WAITING_FOR_WITHDRAW_AMOUNT = range(1, 4) 
ADMIN_PANEL_MENU = 4 
ADMIN_INVENTORY_MENU = 5 
ADMIN_CONFIRM_DELETE = 7 
ADMIN_BROADCAST_START = 8
ADMIN_BROADCAST_CONFIRM = 9
ADMIN_VIEW_WITHDRAW = 10
COUNTRY_SELECT = 11 
ADMIN_USER_MANAGE = 12 
ADMIN_WAITING_FOR_FILE = 13 
ADMIN_NUMBER_CHECK_START = 14
ADMIN_WAITING_FOR_NUMBER = 15
ADMIN_COUNTRY_MANAGE = 16 
USERS_PER_PAGE = 20

def get_db_connection():
    """১০ হাজার ইউজার হ্যান্ডেল করার জন্য অপ্টিমাইজড কানেকশন"""
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30.0) # টাইমআউট ৩০ সেকেন্ড
        conn.execute("PRAGMA journal_mode = WAL")      # রাইট অপারেশন ফাস্ট করবে
        conn.execute("PRAGMA synchronous = NORMAL")   # ডিস্ক রাইটিং অপ্টিমাইজ করবে
        conn.execute("PRAGMA cache_size = -2000")     # ২ মেগাবাইট ক্যাশ
        conn.execute("PRAGMA mmap_size = 300000000")  # মেমোরি ম্যাপিং স্পিড বাড়াবে
        return conn
    except sqlite3.Error as e:
        logging.error(f"Database connection failed: {e}")
        return None

def setup_database():
    """১০ হাজার ইউজার এবং হাই ট্রাফিকের জন্য উন্নত ডাটাবেস সেটআপ"""
    conn = get_db_connection()
    if not conn: return 
    cursor = conn.cursor()
    
    # ১. ইউজার টেবিল (পারফরম্যান্স ইনডেক্স সহ)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            phone_number TEXT, 
            binance_id TEXT,
            balance REAL DEFAULT 0.00,
            otp_received_count INTEGER DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            referred_by_id INTEGER,
            last_received_otp TEXT,
            last_assigned_country TEXT,
            is_banned INTEGER DEFAULT 0 
        )
    """)
    
    # ২. ইনভেন্টরি ও নম্বর টেবিল
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            country_name TEXT PRIMARY KEY,
            available_count INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS all_numbers (
            number TEXT PRIMARY KEY,
            country_full_name TEXT NOT NULL,
            service TEXT,
            country_code TEXT,
            status TEXT DEFAULT 'Available'
        )
    """)

    # ৩. উইথড্র ও ওটিপি লগ টেবিল
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            binance_id TEXT,
            status TEXT DEFAULT 'Pending',
            request_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS otp_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            country_name TEXT,
            earning_amount REAL,
            log_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            phone_number TEXT,
            otp_code TEXT,
            UNIQUE(phone_number, otp_code)
        )
    """)

    # --- কলাম চেক ও অটো-আপডেট (Alter Table) ---
    columns_to_add = {
        "users": [
            ("is_banned", "INTEGER DEFAULT 0"),
            ("last_assigned_country", "TEXT"),
            ("last_received_otp", "TEXT")
        ],
        "otp_logs": [
            ("earning_amount", "REAL"),
            ("phone_number", "TEXT"),
            ("otp_code", "TEXT")
        ]
    }

    for table, cols in columns_to_add.items():
        for col_name, col_type in cols:
            try:
                cursor.execute(f"SELECT {col_name} FROM {table} LIMIT 1")
            except sqlite3.OperationalError:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")

    # --- ৪. ইনডেক্সিং (১০ হাজার ইউজারের জন্য এটিই আসল জাদু) ---
    # এগুলো সার্চ স্পিড ১০০ গুণ বাড়িয়ে দেয়
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON users (phone_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_numbers_lookup ON all_numbers (status, country_full_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_otp_logs_chat ON otp_logs (chat_id)")
    
    conn.commit()
    conn.close()
    logging.info("Database setup and optimization complete.")


def get_chat_id(phone_number: str) -> int | None:
    """
    Finds the Telegram chat_id of the user who was assigned this phone_number.
    """
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        
        normalized_number = phone_number.lstrip('+').replace(' ', '')
        
        cursor.execute("SELECT chat_id FROM users WHERE phone_number = ?", (normalized_number,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except sqlite3.Error as e:
        logging.error(f"DB Error getting chat_id: {e}")
        return None

def get_country_by_chat_id(chat_id: int) -> str | None:
    """Retrieves the last assigned country name for a given chat_id."""
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT last_assigned_country FROM users WHERE chat_id = ?", (chat_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except sqlite3.Error as e:
        logging.error(f"DB Error getting country: {e}")
        return None
        
def add_or_update_user(chat_id: int, referrer_id: int = None):
    """Adds a new user or handles referral for existing users."""
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    
    cursor.execute("SELECT chat_id FROM users WHERE chat_id = ?", (chat_id,))
    if cursor.fetchone():
        conn.close()
        return 
    
    if referrer_id == chat_id:
         referrer_id = None
         
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        cursor.execute("""
            INSERT INTO users (chat_id, referred_by_id) 
            VALUES (?, ?)
        """, (chat_id, referrer_id))

        if referrer_id:
            
            cursor.execute("SELECT is_banned FROM users WHERE chat_id = ?", (referrer_id,))
            referrer_status = cursor.fetchone()
            
            if referrer_status and referrer_status[0] == 0:
                cursor.execute("""
                    UPDATE users 
                    SET referral_count = referral_count + 1, 
                        balance = ROUND(balance + ?, 3) 
                    WHERE chat_id = ?
                """, (REFERRAL_EARNING_RATE, referrer_id))
            else:
                 logging.warning(f"Referrer {referrer_id} not found or is banned. Skipping referral bonus.")
            
        conn.commit()
    except sqlite3.Error as e:
         logging.error(f"DB Error adding or updating user {chat_id}: {e}")
         conn.rollback()
    finally:
        conn.close()

def get_user_data(chat_id: int) -> dict:
    """Retrieves user data (Balance, Wallet ID, and Counts, is_banned)."""
    conn = get_db_connection()
    if not conn: return {'balance': 0.00, 'binance_id': None, 'otp_count': 0, 'referral_count': 0, 'is_banned': 0}
    cursor = conn.cursor()
    cursor.execute("""
        SELECT balance, binance_id, otp_received_count, referral_count, is_banned
        FROM users WHERE chat_id = ?
    """, (chat_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'balance': round(row[0], 3), 
            'binance_id': row[1],
            'otp_count': row[2],
            'referral_count': row[3],
            'is_banned': row[4] 
        }
    return {'balance': 0.00, 'binance_id': None, 'otp_count': 0, 'referral_count': 0, 'is_banned': 0}

def get_status_data(chat_id: int) -> dict:
    """Retrieves status data (last number and last OTP, last country)."""
    conn = get_db_connection()
    if not conn: return {'number': None, 'otp': None, 'country': None}
    cursor = conn.cursor()
    
    cursor.execute("SELECT phone_number, last_received_otp, last_assigned_country FROM users WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'number': row[0], 'otp': row[1], 'country': row[2]}
    return {'number': None, 'otp': None, 'country': None} 

def get_user_by_last_assigned_number(number: str) -> dict | None:
    """
    Finds a user based on their phone_number (which holds the last assigned number).
    """
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor()
    
    normalized_number = number.lstrip('+').replace(' ', '')
    
    cursor.execute("""
        SELECT chat_id, last_assigned_country, phone_number, last_received_otp
        FROM users 
        WHERE phone_number = ?
    """, (normalized_number,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'chat_id': row[0],
            'country': row[1],
            'number': row[2], 
            'otp': row[3]
        }
    return None

def get_top_traffic_30min() -> str:
    """গত ৩০ মিনিটের টপ ৩টি দেশের ট্রাফিক ডাটা বের করবে"""
    conn = get_db_connection()
    if not conn: return "Database Error"
    cursor = conn.cursor()
    
    try:
        # বর্তমান সময় থেকে ৩০ মিনিট আগের সময় বের করা
        # sqlite এর datetime('now', '-30 minutes') ব্যবহার করা হয়েছে
        cursor.execute("""
            SELECT country_name, COUNT(log_id) AS usage_count
            FROM otp_logs
            WHERE log_time >= datetime('now', '-30 minutes')
            GROUP BY country_name
            ORDER BY usage_count DESC
            LIMIT 3
        """)
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            return "No traffic in the last 30 minutes."
        
        message = ""
        for i, (country, count) in enumerate(results, 1):
            message += f"<b>Top{i} Country:</b> {country} ({count} OTPs)\n"
        return message
    except Exception as e:
        logging.error(f"Traffic Error: {e}")
        return "Error fetching traffic."


def get_inventory_counts() -> dict[str, int]:
    """Retrieves all country names and their current available counts (> 0)."""
    try:
        conn = get_db_connection()
        if not conn: return {}
        cursor = conn.cursor()
        cursor.execute("SELECT country_name, available_count FROM inventory WHERE available_count > 0 ORDER BY available_count DESC")
        results = cursor.fetchall()
        conn.close()
        return {country: count for country, count in results}
    except sqlite3.Error as e:
        logging.error(f"DB Error getting inventory counts: {e}")
        return {}

def get_inventory_all_countries() -> list[tuple[str, int]]:
    """Retrieves all country names and their current available counts (including 0)."""
    try:
        conn = get_db_connection()
        if not conn: return []
        cursor = conn.cursor()
        cursor.execute("SELECT country_name, available_count FROM inventory ORDER BY country_name ASC")
        results = cursor.fetchall()
        conn.close()
        return results
    except sqlite3.Error as e:
        logging.error(f"DB Error getting all inventory counts: {e}")
        return []

def get_inventory_count_by_country(country_name: str) -> int:
    """Retrieves the available count for a specific country."""
    conn = get_db_connection()
    if not conn: return 0
    cursor = conn.cursor()
    cursor.execute("SELECT available_count FROM inventory WHERE country_name = ?", (country_name,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def get_available_number(country_full_name: str) -> str | None:
    """Finds and returns the first available number for a given country."""
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT number 
        FROM all_numbers 
        WHERE country_full_name = ? AND status = 'Available'
        LIMIT 1
    """, (country_full_name,))
    
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def update_number_and_inventory(number: str, country_full_name: str, chat_id: int):
    """
    Updates the number status to 'Used' immediately upon assignment, 
    updates the user's last number, and decrements inventory.
    """
    conn = get_db_connection()
    if not conn: return False
    cursor = conn.cursor()
    
    NEW_STATUS = 'Used' 
    
    try:
        cursor.execute("BEGIN TRANSACTION")

        cursor.execute("UPDATE all_numbers SET status = ? WHERE number = ?", (NEW_STATUS, number,))

        cursor.execute("""
            UPDATE users 
            SET phone_number = ?, 
                last_assigned_country = ?, 
                last_received_otp = NULL
            WHERE chat_id = ?
        """, (number, country_full_name, chat_id))
        
        cursor.execute("""
            UPDATE inventory 
            SET available_count = available_count - 1
            WHERE country_name = ? AND available_count > 0
        """, (country_full_name,))
        
        conn.commit()
        return True
    
    except sqlite3.Error as e:
        logging.error(f"Database update failed for number assignment: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()
        
def set_number_status_used(number: str, chat_id: int):
    """Marks a number as 'Used' but keeps it in user history for status display."""
    conn = get_db_connection()
    if not conn: return False
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN TRANSACTION")
        # শুধু নম্বরটিকে ইনভেন্টরিতে 'Used' মার্ক করুন
        cursor.execute("UPDATE all_numbers SET status = 'Used' WHERE number = ?", (number,))
        
        # ইউজারের কলামগুলো NULL করবেন না, যাতে Status বাটনে দেখা যায়। 
        # শুধুমাত্র নতুন নম্বর নিলে বা ওটিপি আসলে এগুলো আপডেট হবে।
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        logging.error(f"Failed to set number status to 'Used': {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
        
def insert_bulk_numbers(numbers_list: list[tuple[str, str, str]]) -> dict:
    """
    Inserts a list of numbers into all_numbers and updates the inventory count.
    Used for general bulk upload.
    """
    conn = get_db_connection()
    if not conn: return {'total_numbers': 0, 'inserted_count': 0, 'skipped_count': 0, 'affected_countries': []}
    cursor = conn.cursor()
    inserted_count = 0
    skipped_count = 0
    
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        inventory_changes = {}
        insert_data = []

        for number, country_full_name, service in numbers_list:
            cursor.execute("SELECT number FROM all_numbers WHERE number = ?", (number,))
            if cursor.fetchone():
                skipped_count += 1
                continue 
            
            insert_data.append((number, country_full_name, service, 'Available'))
            inventory_changes[country_full_name] = inventory_changes.get(country_full_name, 0) + 1
            inserted_count += 1

        if insert_data:
            cursor.executemany("""
                INSERT INTO all_numbers (number, country_full_name, service, status) 
                VALUES (?, ?, ?, ?)
            """, insert_data)

        for country, count in inventory_changes.items():
            cursor.execute("""
                INSERT INTO inventory (country_name, available_count) 
                VALUES (?, ?)
                ON CONFLICT(country_name) DO UPDATE SET available_count = available_count + excluded.available_count
            """, (country, count))
            
        conn.commit()
        return {
            'total_numbers': len(numbers_list),
            'inserted_count': inserted_count,
            'skipped_count': skipped_count,
            'affected_countries': list(inventory_changes.keys())
        }
        
    except sqlite3.Error as e:
        logging.error(f"Bulk insert failed: {e}")
        conn.rollback()
        return {
            'total_numbers': len(numbers_list),
            'inserted_count': 0,
            'skipped_count': len(numbers_list),
            'affected_countries': []
        }
    finally:
        conn.close()

def insert_bulk_numbers_for_country(numbers_list: list[tuple[str, str, str]], country_name: str) -> dict:
    """একটি নির্দিষ্ট দেশের জন্য বাল্ক নম্বর ইনসার্ট করে।"""
    conn = get_db_connection()
    if not conn: return {'total_number_in_file': len(numbers_list), 'inserted_count': 0, 'skipped_count': len(numbers_list), 'old_stock': 0, 'total_stock': 0}
    cursor = conn.cursor()
    inserted_count = 0
    skipped_count = 0
    
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        old_stock = get_inventory_count_by_country(country_name)
        
        insert_data = []
     
        for number, _, service in numbers_list:
            cursor.execute("SELECT number FROM all_numbers WHERE number = ?", (number,))
            if cursor.fetchone():
                skipped_count += 1
                continue 
            
            insert_data.append((number, country_name, service, 'Available'))

        if insert_data:
            cursor.executemany("""
                INSERT INTO all_numbers (number, country_full_name, service, status) 
                VALUES (?, ?, ?, ?)
            """, insert_data)
            inserted_count = len(insert_data) 

        if inserted_count > 0:
            cursor.execute("""
                INSERT INTO inventory (country_name, available_count) 
                VALUES (?, ?)
                ON CONFLICT(country_name) DO UPDATE SET available_count = available_count + ?
            """, (country_name, inserted_count, inserted_count))
            
        conn.commit()
        
        new_total_stock = old_stock + inserted_count
        
        return {
            'total_number_in_file': len(numbers_list),
            'inserted_count': inserted_count,
            'skipped_count': skipped_count,
            'old_stock': old_stock,
            'total_stock': new_total_stock
        }
        
    except sqlite3.Error as e:
        logging.error(f"Bulk insert for country {country_name} failed: {e}")
        conn.rollback()
      
        current_stock = get_inventory_count_by_country(country_name)
        return {
             'total_number_in_file': len(numbers_list),
             'inserted_count': 0,
             'skipped_count': len(numbers_list),
             'old_stock': current_stock,
             'total_stock': current_stock
        }
    finally:
        conn.close()

def delete_all_numbers():
    """Deletes all entries from all_numbers and resets inventory counts."""
    conn = get_db_connection()
    if not conn: return False
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("DELETE FROM all_numbers")
        cursor.execute("UPDATE inventory SET available_count = 0")
        
        cursor.execute("""
            UPDATE users 
            SET phone_number = NULL, 
                last_assigned_country = NULL, 
                last_received_otp = NULL
        """)
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        logging.error(f"Error during all numbers deletion: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
        
def delete_country_inventory(country_name: str) -> bool:
    """একটি নির্দিষ্ট দেশের জন্য all_numbers থেকে ডেটা এবং inventory এন্ট্রি মুছে ফেলে।"""
    conn = get_db_connection()
    if not conn: return False
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        cursor.execute("DELETE FROM all_numbers WHERE country_full_name = ?", (country_name,))
        
        cursor.execute("DELETE FROM inventory WHERE country_name = ?", (country_name,))
        
        cursor.execute("""
            UPDATE users 
            SET phone_number = NULL, 
                last_assigned_country = NULL, 
                last_received_otp = NULL
            WHERE last_assigned_country = ?
        """, (country_name,))
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        logging.error(f"Error during country inventory deletion for {country_name}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_all_user_chat_ids() -> list[int]:
    """Retrieves all chat IDs for broadcasting."""
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor()

    cursor.execute("SELECT chat_id FROM users WHERE is_banned = 0")
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results

def get_pending_withdraw_requests() -> list[tuple]:
    """Retrieves all pending withdrawal requests."""
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor()
    cursor.execute("""
        SELECT request_id, chat_id, amount, binance_id, request_time 
        FROM withdraw_requests 
        WHERE status = 'Pending' 
        ORDER BY request_time ASC
    """)
    results = cursor.fetchall()
    conn.close()
    return results

def update_withdraw_status(request_id: int, status: str):
    """Updates the status of a specific withdrawal request."""
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    cursor.execute("UPDATE withdraw_requests SET status = ? WHERE request_id = ?", (status, request_id))
    conn.commit()
    conn.close()

def refund_user_balance(chat_id: int, amount: float):
    """Refunds the specified amount to the user's balance."""
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
    
        cursor.execute("""
            UPDATE users 
            SET balance = ROUND(balance + ?, 3) 
            WHERE chat_id = ?
        """, (amount, chat_id))
        conn.commit()
        logging.info(f"Refunded ${amount:.3f} to user {chat_id}.")
    except sqlite3.Error as e:
        logging.error(f"Error refunding balance for user {chat_id}: {e}")
        conn.rollback()
    finally:
        conn.close()

def update_binance_id(chat_id: int, binance_id: str):
    """Updates the user's binance ID."""
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET binance_id = ? WHERE chat_id = ?", (binance_id, chat_id))
    conn.commit()
    conn.close()
    
def insert_withdraw_request(chat_id: int, amount: float, binance_id: str):
    """Inserts a withdrawal request and deducts balance."""
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        cursor.execute("""
            INSERT INTO withdraw_requests (chat_id, amount, binance_id)
            VALUES (?, ?, ?)
        """, (chat_id, amount, binance_id))
        
        cursor.execute("UPDATE users SET balance = ROUND(balance - ?, 3) WHERE chat_id = ?", (amount, chat_id))
        
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Error submitting withdraw request: {e}")
        conn.rollback()
    finally:
        conn.close()
        
def update_user_ban_status(chat_id: int, is_banned: int) -> bool:
    """Updates the ban status of a specific user."""
    conn = get_db_connection()
    if not conn: return False
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET is_banned = ? WHERE chat_id = ?", (is_banned, chat_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logging.error(f"Error updating ban status for user {chat_id}: {e}")
        return False
    finally:
        conn.close()
        
def find_user_by_username_or_id(identifier: str) -> int | None:
    """Finds chat_id by a direct chat_id."""
    
    if identifier.isdigit():
        return int(identifier)
        
    if identifier.startswith('@'):
      
        plain_id = identifier[1:]
        if plain_id.isdigit():
             return int(plain_id)
        
    return None

async def check_subscription(bot: Bot, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """১০ মিনিটের ক্যাশ সিস্টেমসহ সাবস্ক্রিপশন চেক"""
    
    # ১. ক্যাশ চেক: গত ১০ মিনিটের মধ্যে চেক করা হয়েছে কি না
    now = datetime.now()
    last_check = context.user_data.get('last_sub_check_time')
    
    if last_check and (now - last_check) < timedelta(minutes=10):
        # যদি ১০ মিনিট পার না হয়, তবে মেমোরি থেকে আগের রেজাল্ট দিবে
        return context.user_data.get('is_subscribed_cached', False)

    # ২. ব্যান চেক
    user_data = await asyncio.to_thread(get_user_data, user_id)
    if user_data.get('is_banned', 0) == 1:
        return False 
        
    is_subscribed = True
    for channel_name, channel_link in REQUIRED_CHANNELS:
        match = re.search(r't\.me/([a-zA-Z0-9_]+)', channel_link)
        if not match:
             is_subscribed = False 
             break
        
        channel_identifier = f"@{match.group(1)}"
        try:
            member = await bot.get_chat_member(chat_id=channel_identifier, user_id=user_id)
            if member.status in ['left', 'kicked', 'restricted']:
                is_subscribed = False
                break 
        except error.TelegramError:
            is_subscribed = False
            break
            
    # ৩. রেজাল্ট এবং বর্তমান সময় ক্যাশ করে রাখা
    context.user_data['last_sub_check_time'] = now
    context.user_data['is_subscribed_cached'] = is_subscribed
    
    return is_subscribed


def get_join_markup():
    """Generates the inline keyboard for joining channels."""
    keyboard = []
    for name, link in REQUIRED_CHANNELS:
        
        keyboard.append([InlineKeyboardButton(f"🔗 Join {name}", url=link)])
        
    keyboard.append([InlineKeyboardButton("✅ I Have Joined", callback_data="check_join_status")])
    return InlineKeyboardMarkup(keyboard)

def get_main_menu_markup(chat_id):
    """Generates the Reply Keyboard Menu, conditionally showing Admin Panel."""
    
    keyboard = [
        [KeyboardButton("📱 Get Number"), KeyboardButton("💰 Balance")],
        [KeyboardButton("💸 Withdraw"), KeyboardButton("🇮🇹 Status")],
        [KeyboardButton("🚦 Live Traffic"), KeyboardButton("👥 Refer/Link")], 
        [KeyboardButton("📞 Support")]
    ]
    
    if chat_id == ADMIN_ID:
        keyboard.append([KeyboardButton("🔑 Admin Panel")])
        
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_panel_markup():
    """Admin Panel Inline Keyboard."""
    keyboard = [
        [InlineKeyboardButton("💵 View Withdraw Requests", callback_data="admin_view_withdraw")],
        [InlineKeyboardButton("➕ Manage Inventory & Numbers", callback_data="admin_manage_inventory")],
        [InlineKeyboardButton("📣 Message All User", callback_data="admin_broadcast_start")],
        [InlineKeyboardButton("🔎 Number Check User", callback_data="admin_number_check_start")],
        [InlineKeyboardButton("👥 Manage Users (Ban/Unban)", callback_data="admin_user_manage")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="admin_back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_country_manage_markup(country_name: str):
    """নির্দিষ্ট দেশের জন্য ম্যানেজমেন্ট অপশন।"""
    keyboard = [
        [InlineKeyboardButton(f"➕ Add More Number To {country_name}", callback_data=f"admin_add_bulk_country_{country_name}")],
        [InlineKeyboardButton(f"🗑️ Delete {country_name} Inventory", callback_data=f"admin_delete_country_confirm_{country_name}")],
        [InlineKeyboardButton("⬅️ Back to Inventory List", callback_data="admin_manage_inventory")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_withdraw_action_markup(request_id: int):
    """Markup for approving/rejecting a withdrawal request."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"withdraw_action_approve_{request_id}"),
            InlineKeyboardButton("❌ Reject (Refund)", callback_data=f"withdraw_action_reject_{request_id}") 
        ],
        [InlineKeyboardButton("➡️ Next Request", callback_data="admin_view_withdraw")] 
    ]
    return InlineKeyboardMarkup(keyboard)

def get_number_control_markup():
    """Generates the inline keyboard for number control."""
    keyboard = [
        [InlineKeyboardButton("View Otp Group", url=OTP_CHANNEL_LINK)],
        [
            InlineKeyboardButton("🔄 Change Number", callback_data="change_number"), 
            InlineKeyboardButton("🌍 Change Country", callback_data="get_number_start_callback") 
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_number_assigned_message(country_full_name: str, number: str):
    """Creates the formatted message for number assignment."""
    
    return (
        f"**{country_full_name} Number Assigned:**\n\n"
        f"📱 **Your Number:**\n"
        f"┗━━ `+{number}` ━━┛\n\n"
        f"╭─────────────────────╮\n"
        f"│   ⏳ **Waiting for OTP...** │\n"
        f"╰─────────────────────╯\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📢  এই নম্বর এ Otp পাঠানোর সাথে সাথে আমাদের এই বট এ আসবেই + তার সাথে সাথে Otp Group এও পাবেন এবং কোন দেশে ট্র্যাফিক আছে দেখার জন্য Otp Group Visit করতে পারেন, ধন্যবাদ।"
    )
    
def get_withdraw_confirm_markup():
    """Generates the inline keyboard for withdrawal confirmation."""
    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Submit", callback_data="withdraw_execute")],
        [InlineKeyboardButton("❌ Cancel Withdrawal", callback_data="cancel_withdrawal")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    
    referrer_id = None
    if context.args and context.args[0].isdigit():
        referrer_id = int(context.args[0])
        if referrer_id == chat_id: referrer_id = None
             
    await asyncio.to_thread(add_or_update_user, chat_id, referrer_id)
    
    user_data = await asyncio.to_thread(get_user_data, chat_id)
    if user_data.get('is_banned', 0) == 1:
         await context.bot.send_message(chat_id=chat_id, text="🚫 **Access Denied!** Your account has been banned by the admin.", parse_mode='HTML')
         return
         
       # context যোগ করে আপডেট করা কোড:
    if await check_subscription(context.bot, chat_id, context): # এখানে context যোগ করা হয়েছে
        await context.bot.send_message(
            chat_id=chat_id,
            text="Welcome! Use the menu below.",
            reply_markup=get_main_menu_markup(chat_id)
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ <b>To use this bot, you must join all the channels below.</b>",
            reply_markup=get_join_markup(),
            parse_mode='HTML'
        )


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
   
    # ১. বাটন চাপলে ক্যাশ ক্লিয়ার করা হবে, যাতে ১০ মিনিট অপেক্ষা না করে সাথে সাথে চেক করে
    context.user_data.pop('last_sub_check_time', None)
    context.user_data.pop('is_subscribed_cached', None)

    user_data = await asyncio.to_thread(get_user_data, chat_id)
    if user_data.get('is_banned', 0) == 1:
        await query.edit_message_text("🚫 **Access Denied!** Your account has been banned by the admin.", parse_mode='HTML')
        return
    
    # ২. এখানে context পাস করা হয়েছে যাতে নতুন করে চেক করে রেজাল্ট ক্যাশ হয়
    if await check_subscription(context.bot, chat_id, context):
        try:
            await query.edit_message_text(
                "✅ Thank you! Your subscription is confirmed. Use the menu below.",
                parse_mode='HTML'
            )
        except error.TelegramBadRequest:
             pass 
            
        await context.bot.send_message(
            chat_id=chat_id,
            text="Welcome to the Main Menu!",
            reply_markup=get_main_menu_markup(chat_id)
        )
    else:
        await query.edit_message_text(
            "❌ <b>Sorry!</b> Subscription failed or not yet confirmed. Please ensure you have joined **all** channels and that the bot is an **Admin** in those channels.",
            reply_markup=get_join_markup(),
            parse_mode='HTML'
        )


async def cancel_conversation(update: Update | None, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    if update:
        chat_id = update.effective_chat.id
        
        is_callback = isinstance(update, Update) and update.callback_query is not None
        
        context.user_data.pop('withdraw_amount', None)
        context.user_data.pop('binance_id', None)
        context.user_data.pop('temp_selected_country', None)
        context.user_data.pop('broadcast_message', None)
        context.user_data.pop('user_manage_page', None) 
        context.user_data.pop('number_to_check', None) 
        context.user_data.pop('temp_country_name', None) 
        
        if update.message and update.message.text and update.message.text.lower() == "/cancel":
             await update.message.reply_text("Conversation cancelled. Returning to main menu.", reply_markup=get_main_menu_markup(chat_id))
        
        if is_callback:
             try:
                 await update.callback_query.answer("Conversation cancelled.")
                 try:
                     await update.callback_query.edit_message_text("❌ Conversation cancelled. Returning to main menu.", reply_markup=get_main_menu_markup(chat_id))
                 except error.TelegramBadRequest:
                      pass 
             except Exception:
                 pass
    
    return ConversationHandler.END

# ... (আগের ইম্পোর্ট এবং ভেরিয়েবল ঠিক আছে)

async def handle_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
   
    user_data = await asyncio.to_thread(get_user_data, chat_id)
    if user_data.get('is_banned', 0) == 1:
         await update.message.reply_text("🚫 **Access Denied!** Your account has been banned.", parse_mode='HTML')
         return 
         
       # context যোগ করে আপডেট করা লাইন:
    if not await check_subscription(context.bot, chat_id, context):
        await update.message.reply_text("⚠️ Please complete the joining check.", reply_markup=get_join_markup())
        return

        
    if text == "📱 Get Number":
        return await get_number_start(update, context) 
    elif text == "💸 Withdraw":
        return await withdraw_start(update, context) 
    elif text == "🔑 Admin Panel" and chat_id == ADMIN_ID:
        return await start_admin_panel(update, context) 
    elif text == "💰 Balance":
        balance = user_data['balance']
        await update.message.reply_text(f"💰 Your current balance is: <b>${balance:.3f}</b>", parse_mode='HTML')
        return
    elif text == "👥 Refer/Link":
        referral_link = f"https://t.me/{context.bot.username}?start={chat_id}"
        message = (
            f"👥 <b>Your Referral Information</b>\n\n"
            f"🔗 <b>Your Link:</b> <a href='{referral_link}'>{referral_link}</a>\n\n"
            f"👤 <b>Total Referrals:</b> <b>{user_data.get('referral_count', 0)}</b>\n"
            f"💸 <b>Earning Per Referral:</b> <b>${REFERRAL_EARNING_RATE:.3f}</b>"
        )
        await update.message.reply_text(message, parse_mode='HTML', disable_web_page_preview=True)
        return
        
    # এখানে Indentation ঠিক করা হয়েছে
    elif text == "🇮🇹 Status":
        status_data = await asyncio.to_thread(get_status_data, chat_id)
        username = update.effective_user.username
        user_display = f"@{username}" if username else f"ID: {chat_id}"
        
        num = f"+{status_data['number']}" if status_data['number'] else "No Number Assigned"
        country = status_data['country'] if status_data['country'] else "N/A"
        otp = status_data['otp'] if status_data['otp'] else "Waiting for OTP..."

        message = (
            f"🇮🇹 <b>Account Status</b>\n\n"
            f"👤 User: <b>{user_display}</b>\n"
            f"🌍 Country: <b>{country}</b>\n"
            f"📱 Number: <code>{num}</code>\n"
            f"🔑 Last OTP: <code>{otp}</code>"
        )
        await update.message.reply_text(message, parse_mode='HTML')
        return
        
    elif text == "🚦 Live Traffic":  # এটি এখন সঠিক লাইনে আছে
        traffic_text = await asyncio.to_thread(get_top_traffic_30min)
        message = (
            f"📊 <b>Last 30 Minutes Live Traffic</b>\n\n"
            f"{traffic_text}\n"
            f"🕒 <i>Last Updated: {datetime.now().strftime('%H:%M:%S')}</i>"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="refresh_traffic")]])
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='HTML')
        return

        
    elif text == "📞 Support":
        await update.message.reply_text(f"📞 <b>Bot Owner:</b> {ADMIN_USERNAME}", parse_mode='HTML')
        return

    if not text.startswith('/'): 
        await update.message.reply_text("I didn't understand that command. Please use the menu buttons.")


async def get_number_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    is_callback = update.callback_query is not None
    chat_id = update.effective_chat.id 
    
    user_data = await asyncio.to_thread(get_user_data, chat_id)
    if user_data.get('is_banned', 0) == 1:
         message = "🚫 **Access Denied!** Your account has been banned by the admin, you cannot get a number."
         if is_callback:
             await update.callback_query.answer(message, show_alert=True)
             try:
                 await update.callback_query.edit_message_text(message, reply_markup=InlineKeyboardMarkup([[]]), parse_mode='HTML')
             except error.TelegramBadRequest:
                 pass
         else:
             await update.message.reply_text(message, parse_mode='HTML')
         return ConversationHandler.END
    
    if is_callback:
        await update.callback_query.answer()

    status_data = await asyncio.to_thread(get_status_data, chat_id)
    if status_data['number']:
        await asyncio.to_thread(set_number_status_used, status_data['number'], chat_id) 
        
    inventory_data = await asyncio.to_thread(get_inventory_counts)
    available_countries_markup = []
    
    sorted_inventory = sorted(inventory_data.items(), key=lambda item: item[1], reverse=True)
    
    for full_name, count in sorted_inventory:
        if count > 0:
            display_text = f"{full_name} (Left {count})"
            callback_data = f"assign_{full_name}" 
            available_countries_markup.append([InlineKeyboardButton(display_text, callback_data=callback_data)])

    if not available_countries_markup:
        message_text = "❌ Sorry! No numbers are available at the moment."
        if is_callback:
             try:
                 await update.callback_query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup([[]]), parse_mode='HTML') 
             except error.TelegramBadRequest:
                 pass
        else:
             await update.message.reply_text(message_text, reply_markup=get_main_menu_markup(chat_id), parse_mode='HTML')
        return ConversationHandler.END

    country_markup = InlineKeyboardMarkup(available_countries_markup)
    message_text = "🌍 Select your country:"
    
    if is_callback:
        await update.callback_query.edit_message_text(message_text, reply_markup=country_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(message_text, reply_markup=country_markup, parse_mode='HTML')
        
    return COUNTRY_SELECT 

async def handle_country_assignment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    chat_id = query.from_user.id
    
    # --- ১০ সেকেন্ডের রেট লিমিট চেক (যদি ইউজার খুব দ্রুত কান্ট্রি চেঞ্জ করতে চায়) ---
    now = time.time()
    last_change_time = context.user_data.get('last_number_change_time', 0)
    wait_time = 10 
    
    if now - last_change_time < wait_time:
        remaining = int(wait_time - (now - last_change_time))
        await query.answer(f"⏳ Please wait {remaining}s before getting another number!", show_alert=True)
        return COUNTRY_SELECT 
    # ----------------------------------------------------------------------

    await query.answer("Assigning number...")
    
    user_data = await asyncio.to_thread(get_user_data, chat_id)
    if user_data.get('is_banned', 0) == 1:
         await query.edit_message_text("🚫 **Access Denied!** Your account has been banned by the admin.", parse_mode='HTML')
         return ConversationHandler.END

    country_full_name = query.data.split('assign_', 1)[-1]
    
    assigned_number = await asyncio.to_thread(get_available_number, country_full_name)
    
    if not assigned_number:
        await query.edit_message_text(f"❌ No available numbers found for **{country_full_name}**.", 
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌍 Try Again", callback_data="get_number_start_callback")]]), parse_mode='Markdown')
        return COUNTRY_SELECT 

    if await asyncio.to_thread(update_number_and_inventory, assigned_number, country_full_name, chat_id):
        
        # সফলভাবে নম্বর অ্যাসাইন হলে বর্তমান সময় সেভ করে রাখুন
        context.user_data['last_number_change_time'] = time.time()
        
        message = get_number_assigned_message(country_full_name, assigned_number)
        
        await query.edit_message_text(
            message,
            reply_markup=get_number_control_markup(),
            parse_mode='Markdown'
        )
        
    else:
        await query.edit_message_text("❌ An error occurred during number assignment.", 
                                      reply_markup=get_main_menu_markup(chat_id))
                                      
    return ConversationHandler.END

async def call_change_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    chat_id = query.from_user.id
    
    # --- ১০ সেকেন্ডের রেট লিমিট চেক শুরু ---
    now = time.time()
    last_change_time = context.user_data.get('last_number_change_time', 0)
    wait_time = 10  # ১০ সেকেন্ড বিরতি
    
    if now - last_change_time < wait_time:
        remaining = int(wait_time - (now - last_change_time))
        await query.answer(f"⏳ Please wait {remaining}s before changing again!", show_alert=True)
        return ConversationHandler.END
    # --- রেট লিমিট চেক শেষ ---

    await query.answer("Getting new number for same country...")
    
    user_data = await asyncio.to_thread(get_user_data, chat_id)
    if user_data.get('is_banned', 0) == 1:
         await query.edit_message_text("🚫 **Access Denied!** Your account has been banned.", parse_mode='HTML')
         return ConversationHandler.END
         
    status_data = await asyncio.to_thread(get_status_data, chat_id)
    current_number = status_data.get('number')
    country_full_name = status_data.get('country')
    
    if current_number:
        await asyncio.to_thread(set_number_status_used, current_number, chat_id) 
    
    if not country_full_name:
         await query.edit_message_text("❌ No country previously selected.", 
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌍 Select Country", callback_data="get_number_start_callback")]]))
         return ConversationHandler.END

    assigned_number = await asyncio.to_thread(get_available_number, country_full_name)
    
    if not assigned_number:
        await query.edit_message_text(f"❌ No more available numbers found for **{country_full_name}**.", 
                                      reply_markup=get_number_control_markup(),
                                      parse_mode='Markdown')
        return ConversationHandler.END

    if await asyncio.to_thread(update_number_and_inventory, assigned_number, country_full_name, chat_id):
        # সফলভাবে নম্বর চেঞ্জ হলে সময় আপডেট করে দিন
        context.user_data['last_number_change_time'] = now 
        
        message = get_number_assigned_message(country_full_name, assigned_number)
        await query.edit_message_text(
            f"✅ **Number Changed.**\n\n{message}",
            reply_markup=get_number_control_markup(),
            parse_mode='Markdown'
        )
    else:
         await query.edit_message_text("❌ An error occurred during assignment.", 
                                      reply_markup=get_main_menu_markup(chat_id))
                                      
    return ConversationHandler.END


async def refresh_traffic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # বাটন চাপলে ছোট একটা পপআপ দেখাবে
    await query.answer("Refreshing Traffic Data...")
    
    traffic_text = await asyncio.to_thread(get_top_traffic_30min)
    message = (
        f"📊 <b>Last 30 Minutes Live Traffic</b>\n\n"
        f"{traffic_text}\n"
        f"🕒 <i>Last Updated: {datetime.now().strftime('%H:%M:%S')}</i>"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="refresh_traffic")]])
    
    try:
        await query.edit_message_text(message, reply_markup=keyboard, parse_mode='HTML')
    except error.TelegramBadRequest:
        # যদি ডাটা একই থাকে তবে এরর এড়াতে এটা ব্যবহার করা হয়
        pass
      
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
 
    user_data = await asyncio.to_thread(get_user_data, chat_id)
    
    if user_data.get('is_banned', 0) == 1:
         await update.message.reply_text("🚫 **Access Denied!** Your account has been banned.", parse_mode='HTML')
         return ConversationHandler.END
    
    user_balance = user_data['balance']
    
    if user_balance < MIN_WITHDRAWAL_AMOUNT:
        await update.message.reply_text(
            f"❌ Minimum balance of <b>${MIN_WITHDRAWAL_AMOUNT:.2f}</b> required to withdraw. Your current balance is <b>${user_balance:.3f}</b>", 
            parse_mode='HTML'
        )
        return ConversationHandler.END
        
    await update.message.reply_text("💸 <b>Withdrawal Process</b>\n\nPlease enter your <b>Binance Pay ID (Payer ID)</b>.", parse_mode='HTML')
    return WAITING_FOR_BINANCE_ID 

async def receive_binance_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    binance_id = update.message.text.strip()
    chat_id = update.effective_chat.id
    
    await asyncio.to_thread(update_binance_id, chat_id, binance_id) 
    context.user_data['binance_id'] = binance_id
    
    user_balance = (await asyncio.to_thread(get_user_data, chat_id))['balance']
    
    await update.message.reply_text(
        f"✅ Binance ID stored. Now, please enter the amount you wish to withdraw.\n"
        f"Available Balance: **${user_balance:.3f}** (Min: ${MIN_WITHDRAWAL_AMOUNT:.2f})",
        parse_mode='Markdown'
    )
    return WAITING_FOR_WITHDRAW_AMOUNT 

async def receive_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount_text = update.message.text.strip()
    chat_id = update.effective_chat.id
  
    user_data = await asyncio.to_thread(get_user_data, chat_id)
    user_balance = user_data.get('balance', 0.00)
    
    try:
        amount = float(amount_text)
        amount = round(amount, 3) 
    except ValueError:
        await update.message.reply_text("❌ **Invalid Amount!** Please enter a valid number.", parse_mode='Markdown')
        return WAITING_FOR_WITHDRAW_AMOUNT

    if amount < MIN_WITHDRAWAL_AMOUNT or amount > user_balance:
        await update.message.reply_text(
            f"❌ **Invalid Amount!** Must be between `${MIN_WITHDRAWAL_AMOUNT:.2f}` and `${user_balance:.2f}`.\n"
            f"Please try again.",
            parse_mode='Markdown'
        )
        return WAITING_FOR_WITHDRAW_AMOUNT

    context.user_data['withdraw_amount'] = amount
    
    binance_id = context.user_data.get('binance_id') or user_data.get('binance_id', 'N/A')
    
    message = (
        "⚠️ **Withdrawal Confirmation**\n\n"
        f"💸 **Amount:** **${amount:.3f}**\n"
        f"🆔 **Binance Pay ID:** <code>{binance_id}</code>\n\n"
        "Confirm that the details are correct to submit the request."
    )
    
    await update.message.reply_text(message, reply_markup=get_withdraw_confirm_markup(), parse_mode='HTML')
    return WAITING_FOR_WITHDRAW_AMOUNT 

async def execute_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Submitting request...")
    chat_id = query.from_user.id
    
    amount = context.user_data.pop('withdraw_amount', None)
    
    binance_id = context.user_data.pop('binance_id', (await asyncio.to_thread(get_user_data, chat_id)).get('binance_id')) 
    
    if amount is None or binance_id is None:
        await query.edit_message_text("❌ Withdrawal data missing. Please start the process again.", parse_mode='HTML')
        return ConversationHandler.END
        
    user_balance = (await asyncio.to_thread(get_user_data, chat_id)).get('balance', 0.00)
    if amount > user_balance:
        await query.edit_message_text("❌ Insufficient balance. Please check your balance and try again.", parse_mode='HTML')
        return ConversationHandler.END
        
    await asyncio.to_thread(insert_withdraw_request, chat_id, amount, binance_id)
    
    await query.edit_message_text(
        "✅ **Withdrawal Request Submitted!**\n\n"
        f"Amount: **${amount:.3f}**\n"
        "Your request has been sent to the admin for manual processing. Thank you.", 
        parse_mode='Markdown'
    )
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    username = query.from_user.username if query.from_user.username else "N/A"
    
    admin_notification = (
        f"🔔 **🚨 NEW WITHDRAWAL REQUEST 🚨**\n\n"
        f"👤 **User:** @{username} (ID: <code>{chat_id}</code>)\n"
        f"💸 **Amount:** **${amount:.3f}**\n"
        f"🆔 **Binance Pay ID:** <code>{binance_id}</code>\n"
        f"⏱️ **Time (UTC):** `{current_time}`\n\n"
        f"[Check Pending Requests](t.me/{context.bot.username}?start=admin_panel)"
    )
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_notification,
            parse_mode='HTML'
        )
    except Exception as e:
         logging.error(f"Failed to send admin withdraw notification: {e}")
         
    return ConversationHandler.END

async def cancel_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Withdrawal cancelled.")
    # Call the main cancel function to clean up
    return await cancel_conversation(update, context)


async def start_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    is_callback = update.callback_query is not None
    chat_id = update.effective_chat.id
    
    if is_callback:
        query = update.callback_query
        await query.answer()
        
        if query.data == "admin_back_to_main":
        
            try:
                await query.edit_message_text("Returning to main menu.", reply_markup=get_main_menu_markup(chat_id))
            except error.TelegramBadRequest:
                await context.bot.send_message(chat_id=chat_id, text="Returning to main menu.", reply_markup=get_main_menu_markup(chat_id))
            return ConversationHandler.END

        await query.edit_message_text(
            "🔑 <b>Admin Panel</b>\n\nWelcome, Admin! Select an action:",
            reply_markup=get_admin_panel_markup(),
            parse_mode='HTML'
        )
    
    elif update.message:
        await update.message.reply_text(
            "🔑 <b>Admin Panel</b>\n\nWelcome, Admin! Select an action:",
            reply_markup=get_admin_panel_markup(),
            parse_mode='HTML'
        )
    
    return ADMIN_PANEL_MENU

async def handle_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "admin_manage_inventory":
        return await admin_manage_inventory(update, context)
    elif data == "admin_view_withdraw":
        return await admin_view_withdraw_start(update, context)
    elif data == "admin_broadcast_start":
        return await admin_broadcast_start(update, context)
    elif data == "admin_user_manage":
        return await admin_user_manage_start(update, context)
    elif data == "admin_number_check_start":
        return await admin_number_check_start(update, context)
        
    await query.edit_message_text("Invalid action. Returning to admin menu.", reply_markup=get_admin_panel_markup())
    return ADMIN_PANEL_MENU
    
async def admin_manage_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    inventory_data = await asyncio.to_thread(get_inventory_all_countries)
    
    keyboard = []
    
    keyboard.append([
        InlineKeyboardButton("➕ Add Bulk Numbers (CSV/TXT)", callback_data="admin_add_bulk"),
        InlineKeyboardButton("⚠️ Delete All Numbers", callback_data="admin_delete_all_confirm")
    ])
    
    message = "➕ <b>Inventory Status: Select a Country to Manage</b>\n\n"
    
    sorted_inventory = sorted(inventory_data, key=lambda item: item[0])
    
    if sorted_inventory:
        for country_name, count in sorted_inventory:
            message += f"🌍 <b>{country_name}</b>: Stock: **{count}**\n"
            keyboard.append([InlineKeyboardButton(f"{country_name} ({count})", callback_data=f"manage_country_{country_name}")])
    else:
        message += "No countries found in inventory."
        
    keyboard.append([InlineKeyboardButton("🔄 Refresh List", callback_data="admin_manage_inventory")])
    keyboard.append([InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_start_callback")])

    await query.edit_message_text(
        message, 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    return ADMIN_INVENTORY_MENU

async def admin_handle_inventory_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "admin_add_bulk":
        return await admin_bulk_add_file_start(update, context) 
    elif data == "admin_delete_all_confirm":
        return await admin_bulk_delete_confirm(update, context)
    elif data == "admin_manage_inventory":
        return await admin_manage_inventory(update, context)
    elif data == "admin_panel_start_callback":
        return await start_admin_panel(update, context)
    
    elif data.startswith("manage_country_"):
        country_name = data.split('manage_country_', 1)[-1]
        return await admin_country_manage_start(update, context, country_name)
        
    return ADMIN_INVENTORY_MENU

async def admin_country_manage_start(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str) -> int:
    query = update.callback_query
    await query.answer()
    
    stock = await asyncio.to_thread(get_inventory_count_by_country, country_name)
    
    message = (
        f"🌍 <b>Manage Inventory for {country_name}</b>\n\n"
        f"Current Stock: **{stock}**"
    )
    
    await query.edit_message_text(
        message,
        reply_markup=get_country_manage_markup(country_name),
        parse_mode='HTML'
    )
    
    context.user_data['temp_country_name'] = country_name
    return ADMIN_COUNTRY_MANAGE

async def admin_handle_country_manage_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    
    country_name = context.user_data.get('temp_country_name')
    if not country_name:
        await query.edit_message_text("❌ Country context lost. Returning to inventory list.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Inventory List", callback_data="admin_manage_inventory")]], parse_mode='HTML'))
        return ADMIN_INVENTORY_MENU

    if data.startswith("admin_add_bulk_country_"):
    
        return await admin_bulk_add_file_start_country(update, context, country_name)
        
    elif data.startswith("admin_delete_country_confirm_"):
 
        return await admin_bulk_delete_confirm_country(update, context, country_name)
        
    elif data == "admin_manage_inventory":
        context.user_data.pop('temp_country_name', None) # Clear temp country on back
        return await admin_manage_inventory(update, context)

    return ADMIN_COUNTRY_MANAGE
    
async def admin_bulk_add_file_start_country(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str) -> int:
    query = update.callback_query
    await query.answer()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ বাতিল করুন", callback_data="admin_manage_inventory")]
    ])
    
    await query.edit_message_text(
        f"📄 <b>Upload Bulk Numbers for {country_name}</b>\n\n"
        "Please upload a **TXT** or **CSV** file :\n\n"
        "Click Cancel to return.",
        reply_markup=keyboard,
        parse_mode='HTML' 
    )
    context.user_data['temp_country_name'] = country_name 
    return ADMIN_WAITING_FOR_FILE 

async def receive_bulk_number_file_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """নির্দিষ্ট দেশের জন্য বাল্ক ইনসার্ট হ্যান্ডলার (হেডার থেকে দেশের নাম নিয়ে সব সারিতে বসাবে)"""
   
    selected_country_context = context.user_data.get('temp_country_name')
    
    if not update.message.document:
        return ADMIN_WAITING_FOR_FILE
        
    doc = update.message.document
    new_file = await context.bot.get_file(doc.file_id)
    file_bytes = io.BytesIO()
    await new_file.download_to_memory(file_bytes)
    file_bytes.seek(0)
    
    lines = file_bytes.read().decode('utf-8').splitlines()
    numbers_to_insert = []
    final_country_name = None
    
    for index, line in enumerate(lines):
        line = line.strip()
        if not line: continue

        if index == 0:
            raw_header_parts = line.split(',')
            if len(raw_header_parts) > 0:
                final_country_name = raw_header_parts[-1].replace('"', '').strip()
            
            if not final_country_name:
                final_country_name = selected_country_context
            continue 
          
        if final_country_name:
            parts = re.findall(r'"([^"]*)"', line)
         
            if len(parts) >= 3:
                number = parts[2].strip().lstrip('+').replace(' ', '')
                service = "TG+WP"
                
                if number.isdigit():
                    numbers_to_insert.append((number, final_country_name, service))
    
    if not numbers_to_insert:
        await update.message.reply_text(f"❌ ফাইলে কোনো সঠিক নম্বর পাওয়া যায়নি।")
        return ADMIN_COUNTRY_MANAGE

    results = await asyncio.to_thread(insert_bulk_numbers_for_country, numbers_to_insert, final_country_name)
    
    message = (
        f"**Bulk Add Successful ({final_country_name})** 🎉\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📦 **Old Stock:** {results['old_stock']}\n"
        f"➕ **New Added:** {results['inserted_count']}\n"
        f"📊 **Current Total:** {results['total_stock']}\n"
        f"🚫 **Skipped (Duplicate):** {results['skipped_count']}\n"
    )
    
    context.user_data.pop('temp_country_name', None) # কনটেক্সট ক্লিয়ার করা
    await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="admin_manage_inventory")]]), parse_mode='Markdown')
    return ADMIN_INVENTORY_MENU

async def admin_bulk_delete_confirm_country(update: Update, context: ContextTypes.DEFAULT_TYPE, country_name: str) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data['temp_country_name'] = country_name 
    
    await query.edit_message_text(
        f"⚠️ <b>WARNING: DELETE ALL NUMBERS for {country_name}</b>\n\n"
        f"This action will **permanently delete** all <b>{country_name}</b> numbers from the database and remove the country from inventory. This is irreversible.\n\n"
        "<b>Are you sure you want to proceed?</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ Yes, Delete {country_name}", callback_data=f"admin_delete_country_execute_{country_name}")],
            [InlineKeyboardButton("❌ No, Go Back", callback_data=f"manage_country_{country_name}")]
        ]),
        parse_mode='HTML'
    )
    return ADMIN_CONFIRM_DELETE 

async def admin_bulk_delete_execute_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Deleting country inventory...")
    
    country_name = query.data.split('admin_delete_country_execute_', 1)[-1]
    context.user_data.pop('temp_country_name', None)
    
    if not country_name:
         await query.edit_message_text("❌ Country context lost. Cannot proceed with deletion.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_start_callback")]], parse_mode='HTML'))
         return ADMIN_PANEL_MENU
    
    if await asyncio.to_thread(delete_country_inventory, country_name):
        message = f"✅ **All numbers for {country_name} have been successfully deleted.** Inventory entry removed."
    else:
        message = f"❌ **Error** occurred while deleting {country_name} inventory."
        
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Inventory List", callback_data="admin_manage_inventory")]])
        
    await query.edit_message_text(
        message, 
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    return ADMIN_INVENTORY_MENU

async def admin_bulk_add_file_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop('temp_country_name', None) 
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ বাতিল করুন", callback_data="admin_manage_inventory")]
    ])
    
    await query.edit_message_text(
        "📄 <b>Upload Bulk Numbers (General)</b>\n\n"
        "Please upload a **TXT** or **CSV** file :\n\n"
        "Click Cancel to return.",
        reply_markup=keyboard,
        parse_mode='HTML' 
    )
    return ADMIN_WAITING_FOR_FILE

async def receive_bulk_number_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """সাধারণ বাল্ক ইনসার্ট হ্যান্ডলার (হেডার থেকে একবার দেশের নাম নিয়ে সব সারিতে বসাবে)"""
    if not update.message.document:
        return ADMIN_WAITING_FOR_FILE
        
    doc = update.message.document
    if not (doc.file_name.lower().endswith('.txt') or doc.file_name.lower().endswith('.csv')):
        await update.message.reply_text("❌ শুধুমাত্র TXT বা CSV ফাইল আপলোড করুন।")
        return ADMIN_INVENTORY_MENU

    file_id = doc.file_id
    new_file = await context.bot.get_file(file_id)
    file_bytes = io.BytesIO()
    await new_file.download_to_memory(file_bytes)
    file_bytes.seek(0)
    
    lines = file_bytes.read().decode('utf-8').splitlines()
    numbers_to_insert = []
    detected_country = None
    
    for index, line in enumerate(lines):
        line = line.strip()
        if not line: continue

        if index == 0:
            raw_header_parts = line.split(',')
            if len(raw_header_parts) > 0:
                detected_country = raw_header_parts[-1].replace('"', '').strip()
            continue 
        if detected_country:
            parts = re.findall(r'"([^"]*)"', line)
            if len(parts) >= 3:
                number = parts[2].strip().lstrip('+').replace(' ', '')
                service = "TG+WP"
                
                if number.isdigit():
                    numbers_to_insert.append((number, detected_country, service))
    
    if not numbers_to_insert:
        await update.message.reply_text("❌ ফাইলে সঠিক ফরম্যাটে কোনো নম্বর বা দেশের নাম পাওয়া যায়নি।")
        return ADMIN_INVENTORY_MENU

    # ডেটাবেসে সেভ করা
    results = await asyncio.to_thread(insert_bulk_numbers, numbers_to_insert)
    
    country_list = ", ".join(results['affected_countries'])
    message = (
        f"**Bulk Number Added Successful** 🎉\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🌍 **Detected Country:** {detected_country}\n"
        f"✅ **Inserted:** {results['inserted_count']} \n"
        f"🚫 **Skipped:** {results['skipped_count']} \n"
    )
    await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="admin_manage_inventory")]]), parse_mode='Markdown')
    return ADMIN_INVENTORY_MENU

async def admin_bulk_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop('temp_country_name', None) 
    
    await query.edit_message_text(
        "⚠️ <b>WARNING: DELETE ALL NUMBERS (GLOBAL)</b>\n\n"
        "This action will **permanently delete** all numbers from the database and reset the inventory counts. This is irreversible.\n\n"
        "<b>Are you sure you want to proceed?</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Delete All", callback_data="admin_delete_all_execute")],
            [InlineKeyboardButton("❌ No, Go Back", callback_data="admin_manage_inventory")]
        ]),
        parse_mode='HTML'
    )
    return ADMIN_CONFIRM_DELETE

async def admin_bulk_delete_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Deleting all numbers...")
    
    if await asyncio.to_thread(delete_all_numbers):
        message = "✅ **All numbers have been successfully deleted (Global).** Inventory counts reset."
    else:
        message = "❌ **Error** occurred while deleting numbers."
        
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Inventory", callback_data="admin_manage_inventory")]])
        
    await query.edit_message_text(
        message, 
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    return ADMIN_INVENTORY_MENU

async def admin_view_withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    requests = await asyncio.to_thread(get_pending_withdraw_requests)
    
    if not requests:
        await query.edit_message_text(
            "✅ No pending withdrawal requests at the moment.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_start_callback")]])
        )
        return ADMIN_PANEL_MENU
        
    request_id, chat_id, amount, binance_id, request_time = requests[0]
    
    username = "N/A"
    try:
         user_tg_info = await context.bot.get_chat(chat_id)
         username = f"@{user_tg_info.username}" if user_tg_info.username else "N/A"
    except error.TelegramError:
         pass
         
    message = (
        f"💵 <b>Pending Withdrawal Request (1 of {len(requests)})</b>\n\n"
        f"<b>Request ID:</b> <code>{request_id}</code>\n"
        f"<b>User:</b> {username} (ID: <code>{chat_id}</code>)\n"
        f"<b>Amount:</b> <b>${amount:.3f}</b>\n"
        f"<b>Binance Pay ID:</b> <code>{binance_id}</code>\n"
        f"<b>Requested At:</b> {request_time}"
    )
    
    await query.edit_message_text(
        message,
        reply_markup=get_withdraw_action_markup(request_id),
        parse_mode='HTML'
    )
    return ADMIN_VIEW_WITHDRAW

async def handle_withdraw_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    action = parts[2] 
    request_id = int(parts[3])
    
    new_status = 'Approved' if action == 'approve' else 'Rejected'
    
    user_id_from_db = 0 
    amount = 0.0
    
    def fetch_request_details(req_id):
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id, amount FROM withdraw_requests WHERE request_id = ?", (req_id,))
            result = cursor.fetchone()
            conn.close()
            return result
        return None
        
    result = await asyncio.to_thread(fetch_request_details, request_id)
    if result:
        user_id_from_db = result[0]
        amount = result[1]
            
    await asyncio.to_thread(update_withdraw_status, request_id, new_status)
    
    if user_id_from_db:
         notification_message = ""
         if new_status == 'Approved':
             notification_message = f"✅ Good News! Your withdrawal request of **${amount:.3f}** has been **APPROVED** and is being processed/paid now."
         else: 
             await asyncio.to_thread(refund_user_balance, user_id_from_db, amount) 
             notification_message = f"❌ Bad News! Your withdrawal request of **${amount:.3f}** has been **REJECTED** by the admin. The amount has been **REFUNDED** to your account balance."
             
         try:
             await context.bot.send_message(
                 chat_id=user_id_from_db, 
                 text=notification_message, 
                 parse_mode='Markdown'
             )
         except error.TelegramError:
             logging.warning(f"Could not notify user {user_id_from_db} about withdrawal status.")
        
    await query.edit_message_text(f"✅ Request <code>{request_id}</code> marked as <b>{new_status}</b>. Loading next...", parse_mode='HTML')
    
    return await admin_view_withdraw_start(update, context)
    
async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ বাতিল করুন", callback_data="admin_panel_start_callback")]])
    
    await query.edit_message_text(
        "📣 <b>Broadcast Message</b>\n\n"
        "Please send the message you want to broadcast to all active users. HTML formatting is supported.",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    return ADMIN_BROADCAST_START

async def admin_broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_text = update.message.text
    context.user_data['broadcast_message'] = message_text
    
    await update.message.reply_text(
        "⚠️ <b>Confirm Broadcast</b>\n\n"
        "Do you want to send this message to <b>all</b> active users?\n\n"
        "<b>Message Preview:</b>\n"
        f"{message_text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Send Broadcast", callback_data="admin_broadcast_execute")],
            [InlineKeyboardButton("❌ বাতিল করুন", callback_data="admin_panel_start_callback")]
        ]),
        parse_mode='HTML'
    )
    return ADMIN_BROADCAST_CONFIRM

async def admin_broadcast_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Sending broadcast...")
    
    message_text = context.user_data.pop('broadcast_message', "No message found.")
    
    user_ids = await asyncio.to_thread(get_all_user_chat_ids)
    sent_count = 0
    
    await query.edit_message_text("⏳ Broadcast in progress...", parse_mode='HTML')
    
    for user_id in user_ids:
        try:
            await context.bot.send_message(user_id, message_text, parse_mode='HTML')
            sent_count += 1
        except error.TelegramError as e:
            if 'bot was blocked by the user' in str(e):
                
                 continue
            logging.error(f"Failed to send broadcast to {user_id}: {e}")
            
        await asyncio.sleep(0.1) 
        
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_start_callback")]])
    
    await context.bot.send_message(
        query.from_user.id,
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"Total users: {len(user_ids)}\n"
        f"Messages sent successfully: <b>{sent_count}</b>",
        reply_markup=keyboard, 
        parse_mode='HTML'
    )
    return ADMIN_PANEL_MENU
    
async def admin_user_manage_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    message = (
        "👥 <b>User Management (Command Mode)</b>\n\n"
        "ইউজারকে ব্যান বা আনব্যান করতে নিচের কমান্ডগুলো ব্যবহার করুন। আপনাকে অবশ্যই ইউজারের <b>Telegram Chat ID</b> ব্যবহার করতে হবে।\n\n"
        "❌ ব্যান করার জন্য:\n"
        "<code>/ban [Chat ID]</code>\n"
        "যেমন: <code>/ban 1234567890</code>\n\n"
        "✅ আনব্যান করার জন্য:\n"
        "<code>/unban [Chat ID]</code>\n"
        "যেমন: <code>/unban 1234567890</code>\n\n"
        "<b>NOTE:</b> Admin commands <code>/ban</code> and <code>/unban</code> only work for the <b>Bot Admin</b>."
    )
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_start_callback")]])
        
    await query.edit_message_text(message, reply_markup=keyboard, parse_mode='HTML')
    return ADMIN_PANEL_MENU

async def ban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        await update.message.reply_text("🚫 আপনি এই কমান্ড ব্যবহার করার জন্য অনুমোদিত নন।")
        return

    if not context.args:
        await update.message.reply_text("❌ ব্যবহার: <code>/ban [Chat ID]</code>", parse_mode='HTML')
        return

    target_identifier = context.args[0]
  
    target_chat_id = await asyncio.to_thread(find_user_by_username_or_id, target_identifier)
    
    if target_chat_id is None:
        await update.message.reply_text(f"❌ '{target_identifier}' এর জন্য কোনো ইউজার খুঁজে পাওয়া যায়নি। সঠিক Chat ID দিন।")
        return
    
    if await asyncio.to_thread(update_user_ban_status, target_chat_id, 1):
        try:
         
            await context.bot.send_message(
                chat_id=target_chat_id,
                text="🚨 আপনার অ্যাকাউন্ট অ্যাডমিন দ্বারা **BAN** করা হয়েছে। আপনি আর বটটি ব্যবহার করতে পারবেন না।",
                parse_mode='Markdown'
            )
            await update.message.reply_text(f"✅ ইউজার <code>{target_chat_id}</code> সফলভাবে **BAN** করা হয়েছে।", parse_mode='HTML')
        except error.TelegramError:
            await update.message.reply_text(f"✅ ইউজার <code>{target_chat_id}</code> সফলভাবে **BAN** করা হয়েছে, কিন্তু তাকে নোটিফাই করা যায়নি (সম্ভবত সে বটকে ব্লক করেছে)।", parse_mode='HTML')
    else:
        await update.message.reply_text(f"❌ ইউজার <code>{target_chat_id}</code> ব্যান করার সময় ডেটাবেসে ত্রুটি দেখা দিয়েছে।", parse_mode='HTML')
        
async def unban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id != ADMIN_ID:
        await update.message.reply_text("🚫 আপনি এই কমান্ড ব্যবহার করার জন্য অনুমোদিত নন।")
        return

    if not context.args:
        await update.message.reply_text("❌ ব্যবহার: <code>/unban [Chat ID]</code>", parse_mode='HTML')
        return

    target_identifier = context.args[0]
    target_chat_id = await asyncio.to_thread(find_user_by_username_or_id, target_identifier)

    if target_chat_id is None:
        await update.message.reply_text(f"❌ '{target_identifier}' এর জন্য কোনো ইউজার খুঁজে পাওয়া যায়নি। সঠিক Chat ID দিন।")
        return
    
    if await asyncio.to_thread(update_user_ban_status, target_chat_id, 0):
        try:
            await context.bot.send_message(
                chat_id=target_chat_id,
                text="✅ আপনার অ্যাকাউন্ট অ্যাডমিন দ্বারা **UNBAN** করা হয়েছে। আপনি এখন বটটি ব্যবহার করতে পারেন।",
                parse_mode='Markdown'
            )
            await update.message.reply_text(f"✅ ইউজার <code>{target_chat_id}</code> সফলভাবে **UNBAN** করা হয়েছে।", parse_mode='HTML')
        except error.TelegramError:
            await update.message.reply_text(f"✅ ইউজার <code>{target_chat_id}</code> সফলভাবে **UNBAN** করা হয়েছে, কিন্তু তাকে নোটিফাই করা যায়নি (সম্ভবত সে বটকে ব্লক করেছিল)।", parse_mode='HTML')
    else:
        await update.message.reply_text(f"❌ ইউজার <code>{target_chat_id}</code> আনব্যান করার সময় ডেটাবেসে ত্রুটি দেখা দিয়েছে।", parse_mode='HTML')

async def admin_number_check_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ বাতিল করুন", callback_data="admin_panel_start_callback")]])
    
    await query.edit_message_text(
        "🔎 <b>Number Check User</b>\n\n"
        "অনুগ্রহ করে যে নম্বরটির তথ্য জানতে চান, সেটি **সম্পূর্ণ আন্তর্জাতিক ফরম্যাটে** (+ সহ অথবা + ছাড়া) দিন।",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    return ADMIN_WAITING_FOR_NUMBER

async def admin_receive_number_for_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    number_input = update.message.text.strip()
    
    clean_number = number_input.lstrip('+').replace(' ', '')
    
    if not clean_number.isdigit():
        await update.message.reply_text(
            "❌ **Invalid Number!** অনুগ্রহ করে সঠিক নাম্বার দেন + সহ।",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_start_callback")]])
        )
        return ADMIN_PANEL_MENU
        
    user_info = await asyncio.to_thread(get_user_by_last_assigned_number, clean_number)
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_start_callback")]])
    
    if user_info:
        username = "N/A"
        try:
             user_tg_info = await context.bot.get_chat(user_info['chat_id'])
             username = f"@{user_tg_info.username}" if user_tg_info.username else f"User ID: {user_info['chat_id']}"
        except error.TelegramError:
             pass 
        
        otp_display = user_info['otp'] if user_info['otp'] else "Not Received"

        message = (
            "✅ <b>User Information Found</b>\n\n"
            f"📞 <b>Number:</b> <code>+{user_info['number']}</code>\n"
            f"👤 <b>Username/ID:</b> <b>{username}</b>\n"
            f"🆔 <b>Chat ID:</b> <code>{user_info['chat_id']}</code>\n"
            f"🌍 <b>Country:</b> <b>{user_info['country']}</b>\n"
            f"🔑 <b>Last Otp:</b> <code>{otp_display}</code>"
        )
        
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='HTML')
    
    else:
        await update.message.reply_text(
            f"❌ **No User Found**\n\n"
            f"নম্বর <code>{number_input}</code> কোনো সক্রিয় বা শেষ অ্যাসাইনড ইউজারের সাথে মেলেনি।",
            reply_markup=keyboard, 
            parse_mode='HTML'
        )
        
    return ADMIN_PANEL_MENU

def configure_bot_handlers(application: Application):
    """Configures all Telegram bot handlers."""
    # 1. Start & Cancel Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_conversation))
    
    application.add_handler(CommandHandler("ban", ban_user_command, filters=filters.User(ADMIN_ID)))
    application.add_handler(CommandHandler("unban", unban_user_command, filters=filters.User(ADMIN_ID)))
    
    application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join_status$")) 

    get_number_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📱 Get Number$"), get_number_start), 
            CallbackQueryHandler(get_number_start, pattern="^get_number_start_callback$"), 
            CallbackQueryHandler(call_change_number, pattern="^change_number$") 
        ],
        states={
            COUNTRY_SELECT: [ 
                CallbackQueryHandler(handle_country_assignment_callback, pattern="^assign_.*"), 
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)], 
        per_chat=True,
        allow_reentry=True 
    )

    withdraw_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Withdraw$"), withdraw_start)], 
        states={
            WAITING_FOR_BINANCE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_binance_id)],
            WAITING_FOR_WITHDRAW_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_withdraw_amount),
                CallbackQueryHandler(execute_withdraw_callback, pattern="^withdraw_execute$"),
                CallbackQueryHandler(cancel_withdraw_callback, pattern="^cancel_withdrawal$")
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        per_chat=True,
    )
    
    admin_panel_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🔑 Admin Panel$") & filters.User(ADMIN_ID), start_admin_panel),
            CallbackQueryHandler(start_admin_panel, pattern="^admin_panel_start_callback$|^admin_back_to_main$"), 
        ],
        states={
            ADMIN_PANEL_MENU: [
                CallbackQueryHandler(handle_admin_panel),
            ],
            ADMIN_VIEW_WITHDRAW: [
                CallbackQueryHandler(handle_withdraw_action, pattern="^withdraw_action_.*"), 
                CallbackQueryHandler(admin_view_withdraw_start, pattern="^admin_view_withdraw$"), # Next Request handler
                CallbackQueryHandler(start_admin_panel, pattern="^admin_panel_start_callback$") 
            ],
            ADMIN_INVENTORY_MENU: [
                CallbackQueryHandler(admin_handle_inventory_actions), 
            ],
            ADMIN_COUNTRY_MANAGE: [
                CallbackQueryHandler(admin_handle_country_manage_actions),
            ],
            ADMIN_WAITING_FOR_FILE: [
                
                MessageHandler(filters.ALL & ~filters.COMMAND, receive_bulk_number_file), 
                CallbackQueryHandler(admin_manage_inventory, pattern="^admin_manage_inventory$") 
            ],
            ADMIN_CONFIRM_DELETE: [
                CallbackQueryHandler(admin_bulk_delete_execute, pattern="^admin_delete_all_execute$"),
                CallbackQueryHandler(admin_bulk_delete_execute_country, pattern="^admin_delete_country_execute_.*"),
         
                CallbackQueryHandler(admin_handle_country_manage_actions, pattern="^manage_country_.*"),
                CallbackQueryHandler(admin_handle_inventory_actions, pattern="^admin_manage_inventory$") 
            ],
            ADMIN_BROADCAST_START: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_confirm),
                CallbackQueryHandler(start_admin_panel, pattern="^admin_panel_start_callback$") 
            ],
            ADMIN_BROADCAST_CONFIRM: [
                CallbackQueryHandler(admin_broadcast_execute, pattern="^admin_broadcast_execute$"),
                CallbackQueryHandler(start_admin_panel, pattern="^admin_panel_start_callback$") 
            ],
            ADMIN_WAITING_FOR_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_number_for_check),
                CallbackQueryHandler(start_admin_panel, pattern="^admin_panel_start_callback$")
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        per_chat=True,
        allow_reentry=True
    )

    # এই অংশটি configure_bot_handlers ফাংশনের ভেতরে থাকবে
    application.add_handler(CallbackQueryHandler(refresh_traffic_callback, pattern="^refresh_traffic$"))
    application.add_handler(get_number_handler)
    application.add_handler(withdraw_handler)
    application.add_handler(admin_panel_handler)
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_message))

def main_bot_checker():
    """Initializes the database and bot application."""
    setup_database() 
    
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    configure_bot_handlers(application) 
    return application

if __name__ == '__main__':
    bot_application = main_bot_checker() 
    
    print("✅ Personal Number Bot Started (Without API Polling)...")
    
    bot_application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    print("✅ Application stopped cleanly.")
