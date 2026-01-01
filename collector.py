import asyncio
import logging
import random
from datetime import datetime
from typing import List, Dict, Optional
from telethon import TelegramClient
from telethon.sessions import StringSession

from config import API_ID, API_HASH
from database import (
    get_sessions, add_link, update_session_usage,
    start_collection_session, update_collection_stats, end_collection_session
)

# ======================
# Logging
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Global Variables
# ======================

_collection_active = False
_collection_paused = False
_collection_session_id = None
_collection_stats = {
    'total_collected': 0,
    'telegram_collected': 0,
    'whatsapp_collected': 0,
    'public_groups': 0,
    'private_groups': 0,
    'whatsapp_groups': 0,
    'duplicate_links': 0,
    'inactive_links': 0,
    'channels_skipped': 0,
    'start_time': None,
    'end_time': None
}

# ======================
# Status Functions
# ======================

def is_collecting() -> bool:
    """التحقق مما إذا كان الجمع نشطاً"""
    return _collection_active

def is_paused() -> bool:
    """التحقق مما إذا كان الجمع موقفاً مؤقتاً"""
    return _collection_paused

def get_collection_status() -> Dict:
    """الحصول على حالة الجمع الحالية"""
    return {
        'active': _collection_active,
        'paused': _collection_paused,
        'session_id': _collection_session_id,
        'stats': _collection_stats.copy()
    }

def reset_collection_state():
    """إعادة تعيين حالة الجمع"""
    global _collection_active, _collection_paused, _collection_session_id
    global _collection_stats
    
    _collection_active = False
    _collection_paused = False
    _collection_session_id = None
    _collection_stats = {
        'total_collected': 0,
        'telegram_collected': 0,
        'whatsapp_collected': 0,
        'public_groups': 0,
        'private_groups': 0,
        'whatsapp_groups': 0,
        'duplicate_links': 0,
        'inactive_links': 0,
        'channels_skipped': 0,
        'start_time': None,
        'end_time': None
    }

# ======================
# Link Collection Functions
# ======================

def generate_sample_telegram_links(count: int = 50) -> List[Dict]:
    """إنشاء روابط تيليجرام عشوائية للاختبار"""
    sample_links = []
    
    # مجموعات عامة عشوائية
    public_groups = [
        "https://t.me/arabic_chat",
        "https://t.me/arabic_memes",
        "https://t.me/tech_arabic",
        "https://t.me/programming_arabic",
        "https://t.me/books_arabic",
        "https://t.me/movies_arabic",
        "https://t.me/music_arabic",
        "https://t.me/football_arabic",
        "https://t.me/cooking_arabic",
        "https://t.me/health_arabic"
    ]
    
    # مجموعات خاصة عشوائية
    private_groups = [
        "https://t.me/+ABC123def",
        "https://t.me/+XYZ789ghi",
        "https://t.me/+JKL456mno",
        "https://t.me/+PQR321stu",
        "https://t.me/+MNO654vwx"
    ]
    
    # إضافة روابط عشوائية
    for i in range(min(count, len(public_groups) + len(private_groups))):
        if i < len(public_groups):
            link_type = "public_group"
            url = public_groups[i]
        else:
            link_type = "private_group"
            url = private_groups[i - len(public_groups)]
        
        sample_links.append({
            'url': url,
            'platform': 'telegram',
            'link_type': link_type,
            'title': f"مجموعة تجريبية {i+1}",
            'members_count': random.randint(100, 10000)
        })
    
    return sample_links

def generate_sample_whatsapp_links(count: int = 20) -> List[Dict]:
    """إنشاء روابط واتساب عشوائية للاختبار"""
    sample_links = []
    
    for i in range(count):
        group_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', k=22))
        sample_links.append({
            'url': f"https://chat.whatsapp.com/{group_id}",
            'platform': 'whatsapp',
            'link_type': 'group',
            'title': f"مجموعة واتساب تجريبية {i+1}",
            'members_count': random.randint(50, 500)
        })
    
    return sample_links

async def collect_links_from_session(session_data: Dict) -> Dict:
    """جمع الروابط من جلسة واحدة (نظري)"""
    session_id = session_data.get('id')
    display_name = session_data.get('display_name', f"Session_{session_id}")
    
    logger.info(f"⏳ Collecting from session: {display_name}")
    
    try:
        # تحديث وقت الاستخدام
        from database import update_session_usage
        update_session_usage(session_id)
        
        # جمع الروابط (نظري - في الإصدار الحقيقي سيكون هنا اتصال بـ Telethon)
        links_collected = 0
        max_links = random.randint(10, 30)  # عدد عشوائي للروابط
        
        # إنشاء روابط عشوائية للاختبار
        all_sample_links = []
        
        # 70% روابط تيليجرام، 30% روابط واتساب
        telegram_count = int(max_links * 0.7)
        whatsapp_count = max_links - telegram_count
        
        telegram_links = generate_sample_telegram_links(telegram_count)
        whatsapp_links = generate_sample_whatsapp_links(whatsapp_count)
        
        all_sample_links = telegram_links + whatsapp_links
        
        # إضافة الروابط إلى قاعدة البيانات
        for link_data in all_sample_links:
            try:
                success, message = add_link(
                    url=link_data['url'],
                    platform=link_data['platform'],
                    link_type=link_data['link_type'],
                    title=link_data['title'],
                    members_count=link_data['members_count'],
                    session_id=session_id
                )
                
                if success:
                    links_collected += 1
                    
                    # تحديث الإحصائيات العالمية
                    global _collection_stats
                    _collection_stats['total_collected'] += 1
                    
                    if link_data['platform'] == 'telegram':
                        _collection_stats['telegram_collected'] += 1
                        if link_data['link_type'] == 'public_group':
                            _collection_stats['public_groups'] += 1
                        elif link_data['link_type'] == 'private_group':
                            _collection_stats['private_groups'] += 1
                    elif link_data['platform'] == 'whatsapp':
                        _collection_stats['whatsapp_collected'] += 1
                        _collection_stats['whatsapp_groups'] += 1
                
                else:
                    if message == 'duplicate':
                        _collection_stats['duplicate_links'] += 1
            
            except Exception as e:
                logger.error(f"Error adding link: {e}")
                continue
        
        logger.info(f"✅ Collected {links_collected} links from session {display_name}")
        
        return {
            'session_id': session_id,
            'display_name': display_name,
            'links_collected': links_collected,
            'status': 'success'
        }
        
    except Exception as e:
        logger.error(f"❌ Error collecting from session {display_name}: {e}")
        return {
            'session_id': session_id,
            'display_name': display_name,
            'links_collected': 0,
            'status': 'failed',
            'error': str(e)
        }

# ======================
# Main Collection Functions
# ======================

async def start_collection() -> bool:
    """بدء عملية جمع الروابط"""
    global _collection_active, _collection_paused, _collection_session_id, _collection_stats
    
    try:
        # التحقق من عدم وجود عملية جمع نشطة
        if _collection_active:
            logger.warning("⚠️ Collection is already active")
            return False
        
        # الحصول على الجلسات النشطة
        active_sessions = [s for s in get_sessions() if s.get('is_active')]
        if not active_sessions:
            logger.error("❌ No active sessions available")
            return False
        
        # إعادة تعيين حالة الجمع
        reset_collection_state()
        
        # بدء جلسة جمع جديدة
        _collection_session_id = start_collection_session()
        if not _collection_session_id:
            logger.error("❌ Failed to start collection session")
            return False
        
        # تحديث حالة الجمع
        _collection_active = True
        _collection_paused = False
        _collection_stats['start_time'] = datetime.now().isoformat()
        
        logger.info(f"🚀 Starting collection session {_collection_session_id} with {len(active_sessions)} active sessions")
        
        # جمع الروابط من كل جلسة
        collection_tasks = []
        
        for session in active_sessions:
            if not _collection_active:
                break
            
            # إنشاء مهمة جمع
            task = asyncio.create_task(collect_links_from_session(session))
            collection_tasks.append(task)
            
            # تأخير بين بدء مهام الجلسات
            await asyncio.sleep(1)
        
        # انتظار اكتمال جميع المهام
        try:
            results = await asyncio.gather(*collection_tasks, return_exceptions=True)
            
            # حساب النتائج
            successful = 0
            failed = 0
            total_links = 0
            
            for result in results:
                if isinstance(result, dict):
                    if result.get('status') == 'success':
                        successful += 1
                        total_links += result.get('links_collected', 0)
                    else:
                        failed += 1
            
            logger.info(f"📊 Collection completed: {successful} successful, {failed} failed, {total_links} total links")
            
        except Exception as e:
            logger.error(f"❌ Error in collection tasks: {e}")
        
        # إنهاء جلسة الجمع
        _collection_active = False
        _collection_stats['end_time'] = datetime.now().isoformat()
        
        # تحديث الإحصائيات النهائية
        update_collection_stats(_collection_session_id, _collection_stats)
        end_collection_session(_collection_session_id, 'completed')
        
        logger.info(f"✅ Collection completed. Total collected: {_collection_stats['total_collected']}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error starting collection: {e}")
        
        # إنهاء جلسة الجمع في حالة الخطأ
        if _collection_session_id:
            update_collection_stats(_collection_session_id, _collection_stats)
            end_collection_session(_collection_session_id, 'error')
        
        reset_collection_state()
        return False

async def stop_collection() -> bool:
    """إيقاف عملية جمع الروابط"""
    global _collection_active, _collection_paused
    
    if not _collection_active:
        logger.warning("⚠️ Collection is not active")
        return False
    
    logger.info("🛑 Stopping collection...")
    _collection_active = False
    _collection_paused = False
    
    # تحديث الإحصائيات النهائية
    if _collection_session_id:
        _collection_stats['end_time'] = datetime.now().isoformat()
        update_collection_stats(_collection_session_id, _collection_stats)
        end_collection_session(_collection_session_id, 'stopped')
    
    logger.info(f"✅ Collection stopped. Total collected: {_collection_stats['total_collected']}")
    return True

async def pause_collection() -> bool:
    """إيقاف جمع الروابط مؤقتاً"""
    global _collection_paused
    
    if not _collection_active:
        logger.warning("⚠️ Collection is not active")
        return False
    
    if _collection_paused:
        logger.warning("⚠️ Collection is already paused")
        return False
    
    logger.info("⏸️ Pausing collection...")
    _collection_paused = True
    return True

async def resume_collection() -> bool:
    """استئناف جمع الروابط"""
    global _collection_paused
    
    if not _collection_active:
        logger.warning("⚠️ Collection is not active")
        return False
    
    if not _collection_paused:
        logger.warning("⚠️ Collection is not paused")
        return False
    
    logger.info("▶️ Resuming collection...")
    _collection_paused = False
    return True

# ======================
# Test Function
# ======================

async def test_collection():
    """اختبار عملية الجمع"""
    print("🧪 Testing collection system...")
    
    # إنشاء جلسة تجريبية إذا لم تكن موجودة
    from database import get_sessions, add_session
    
    sessions = get_sessions()
    if not sessions:
        print("📝 Adding test session...")
        add_session(
            session_string="test_session_string",
            phone="+1234567890",
            user_id=123456789,
            username="testuser",
            display_name="Test Session"
        )
    
    # بدء الجمع
    success = await start_collection()
    
    if success:
        print("✅ Collection test completed successfully!")
        print(f"📊 Stats: {_collection_stats}")
    else:
        print("❌ Collection test failed!")
    
    return success

# ======================
# Main Entry Point for Testing
# ======================

if __name__ == "__main__":
    import sys
    
    async def main():
        """الدالة الرئيسية للاختبار"""
        print("🔧 Testing collector module...")
        
        # اختبار الجمع
        await test_collection()
        
        print("\n✅ Collector module test completed!")
    
    # تشغيل الاختبار
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
