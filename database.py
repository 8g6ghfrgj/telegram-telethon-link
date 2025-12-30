import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from config import DATABASE_PATH


# ======================
# Connection
# ======================

def get_connection():
    return sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )


# ======================
# Init Database
# ======================

def init_db():
    """
    إنشاء الجداول الجديدة مع حقول التصنيف والفحص
    """

    dir_name = os.path.dirname(DATABASE_PATH)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    conn = get_connection()
    cur = conn.cursor()

    # جدول الجلسات
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_string TEXT NOT NULL UNIQUE,
            phone_number TEXT,
            added_date TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            last_used TEXT
        )
    """)

    # جدول الروابط - محدث مع حقول جديدة
    cur.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            platform TEXT NOT NULL,           -- telegram / whatsapp
            link_type TEXT,                   -- channel / public_group / private_group / bot / message
            source_account TEXT,
            chat_id TEXT,
            message_date TEXT,
            is_verified INTEGER DEFAULT 0,    -- 0 = غير مفحص, 1 = مفحص
            verification_date TEXT,
            verification_result TEXT,         -- valid / invalid / private
            metadata TEXT,                    -- JSON مع معلومات إضافية
            collected_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # جدول إحصائيات الجمع
    cur.execute("""
        CREATE TABLE IF NOT EXISTS collection_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            start_time TEXT,
            end_time TEXT,
            status TEXT,                      -- running / paused / stopped / completed
            total_collected INTEGER DEFAULT 0,
            telegram_collected INTEGER DEFAULT 0,
            whatsapp_collected INTEGER DEFAULT 0,
            verified_count INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        )
    """)

    # إنشاء الفهارس
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_links_platform_type
        ON links (platform, link_type)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_links_verified
        ON links (is_verified, verification_result)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_links_date
        ON links (collected_date DESC)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_active
        ON sessions (is_active)
    """)

    conn.commit()
    conn.close()


# ======================
# Session Management
# ======================

def add_session(session_string: str, phone_number: str = None) -> bool:
    """
    إضافة جلسة جديدة
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT OR IGNORE INTO sessions 
            (session_string, phone_number, added_date, is_active)
            VALUES (?, ?, ?, ?)
            """,
            (session_string, phone_number, datetime.now().isoformat(), 1)
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        print(f"Error adding session: {e}")
        return False
    finally:
        conn.close()


def get_sessions(active_only: bool = True) -> List[Dict]:
    """
    الحصول على قائمة الجلسات
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if active_only:
        cur.execute("""
            SELECT id, session_string, phone_number, added_date, is_active
            FROM sessions 
            WHERE is_active = 1
            ORDER BY added_date DESC
        """)
    else:
        cur.execute("""
            SELECT id, session_string, phone_number, added_date, is_active
            FROM sessions 
            ORDER BY added_date DESC
        """)

    rows = cur.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def update_session_status(session_id: int, is_active: bool):
    """
    تحديث حالة الجلسة
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        UPDATE sessions 
        SET is_active = ?, last_used = ?
        WHERE id = ?
        """,
        (1 if is_active else 0, datetime.now().isoformat(), session_id)
    )
    
    conn.commit()
    conn.close()


def delete_session(session_id: int) -> bool:
    """
    حذف جلسة
    """
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ======================
# Link Management
# ======================

def save_link(
    url: str,
    platform: str,
    link_type: str = None,
    source_account: str = None,
    chat_id: str = None,
    message_date = None,
    is_verified: bool = False,
    verification_result: str = None,
    metadata: Dict = None
) -> bool:
    """
    حفظ رابط جديد مع التصنيف والفحص
    """
    if not url or not platform:
        return False

    conn = get_connection()
    cur = conn.cursor()

    try:
        # تنظيف URL (إزالة النجوم والمسافات)
        cleaned_url = url.strip().replace('*', '')
        
        # تحويل metadata إلى JSON
        metadata_json = json.dumps(metadata) if metadata else None
        
        cur.execute(
            """
            INSERT OR IGNORE INTO links
            (url, platform, link_type, source_account, chat_id, 
             message_date, is_verified, verification_result, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cleaned_url,
                platform,
                link_type,
                source_account,
                chat_id,
                message_date.isoformat() if message_date else None,
                1 if is_verified else 0,
                verification_result,
                metadata_json
            )
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        print(f"Error saving link: {e}")
        return False
    finally:
        conn.close()


def update_link_verification(url: str, is_verified: bool, result: str, metadata: Dict = None):
    """
    تحديث حالة فحص الرابط
    """
    conn = get_connection()
    cur = conn.cursor()
    
    metadata_json = json.dumps(metadata) if metadata else None
    
    cur.execute(
        """
        UPDATE links 
        SET is_verified = ?, 
            verification_result = ?,
            verification_date = ?,
            metadata = COALESCE(?, metadata)
        WHERE url = ?
        """,
        (
            1 if is_verified else 0,
            result,
            datetime.now().isoformat(),
            metadata_json,
            url
        )
    )
    
    conn.commit()
    conn.close()


# ======================
# Statistics & Queries
# ======================

def get_link_stats() -> Dict:
    """
    إحصائيات شاملة للروابط
    """
    conn = get_connection()
    cur = conn.cursor()

    stats = {}
    
    # إحصائيات حسب المنصة
    cur.execute("""
        SELECT platform, COUNT(*) as count
        FROM links
        GROUP BY platform
    """)
    stats['by_platform'] = {row[0]: row[1] for row in cur.fetchall()}
    
    # إحصائيات حسب نوع التليجرام
    cur.execute("""
        SELECT link_type, COUNT(*) as count
        FROM links
        WHERE platform = 'telegram'
        GROUP BY link_type
    """)
    stats['telegram_by_type'] = {row[0]: row[1] for row in cur.fetchall()}
    
    # إحصائيات الفحص
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(is_verified) as verified,
            SUM(CASE WHEN verification_result = 'valid' THEN 1 ELSE 0 END) as valid
        FROM links
    """)
    row = cur.fetchone()
    stats['verification'] = {
        'total': row[0] or 0,
        'verified': row[1] or 0,
        'valid': row[2] or 0
    }
    
    conn.close()
    return stats


def get_links_by_type(
    platform: str,
    link_type: str = None,
    verified_only: bool = False,
    limit: int = 100,
    offset: int = 0
) -> List[Dict]:
    """
    جلب الروابط حسب المنصة والنوع
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    query = "SELECT * FROM links WHERE platform = ?"
    params = [platform]
    
    if link_type:
        query += " AND link_type = ?"
        params.append(link_type)
    
    if verified_only:
        query += " AND is_verified = 1"
    
    query += " ORDER BY collected_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


# ======================
# Collection Stats
# ======================

def start_collection_session(session_id: int) -> int:
    """
    بدء جلسة جمع جديدة
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO collection_stats 
        (session_id, start_time, status)
        VALUES (?, ?, ?)
        """,
        (session_id, datetime.now().isoformat(), 'running')
    )
    
    conn.commit()
    collection_id = cur.lastrowid
    conn.close()
    
    return collection_id


def update_collection_stats(
    collection_id: int,
    status: str = None,
    telegram_count: int = 0,
    whatsapp_count: int = 0,
    verified_count: int = 0
):
    """
    تحديث إحصائيات الجمع
    """
    conn = get_connection()
    cur = conn.cursor()
    
    updates = []
    params = []
    
    if status:
        updates.append("status = ?")
        params.append(status)
    
    if telegram_count > 0:
        updates.append("telegram_collected = telegram_collected + ?")
        params.append(telegram_count)
    
    if whatsapp_count > 0:
        updates.append("whatsapp_collected = whatsapp_collected + ?")
        params.append(whatsapp_count)
    
    if verified_count > 0:
        updates.append("verified_count = verified_count + ?")
        params.append(verified_count)
    
    if updates:
        params.append(collection_id)
        query = f"""
            UPDATE collection_stats 
            SET {', '.join(updates)}, 
                total_collected = total_collected + ?,
                end_time = ?
            WHERE id = ?
        """
        total_increment = telegram_count + whatsapp_count
        params.insert(-1, total_increment)
        params.insert(-1, datetime.now().isoformat() if status == 'completed' else None)
        
        cur.execute(query, params)
        conn.commit()
    
    conn.close()


# ======================
# Export Functions
# ======================

def export_links_by_type(platform: str, link_type: str = None) -> Optional[str]:
    """
    تصدير الروابط حسب النوع
    """
    conn = get_connection()
    cur = conn.cursor()
    
    if link_type:
        cur.execute("""
            SELECT url FROM links
            WHERE platform = ? AND link_type = ?
            ORDER BY collected_date ASC
        """, (platform, link_type))
        filename = f"links_{platform}_{link_type}.txt"
    else:
        cur.execute("""
            SELECT url FROM links
            WHERE platform = ?
            ORDER BY collected_date ASC
        """, (platform,))
        filename = f"links_{platform}.txt"
    
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return None
    
    from config import EXPORT_DIR
    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, filename)
    
    with open(path, "w", encoding="utf-8") as f:
        for (url,) in rows:
            f.write(url + "\n")
    
    return path


# ======================
# Initialize Database
# ======================

if __name__ == "__main__":
    init_db()
    print("✅ Database initialized successfully!")
