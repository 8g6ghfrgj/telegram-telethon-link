import re
import asyncio
import aiohttp
from typing import List, Optional, Tuple, Dict
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from telethon.tl.types import Message

from config import VERIFY_LINKS, VERIFY_TIMEOUT, BLACKLISTED_DOMAINS


# ======================
# Regex لاستخراج الروابط
# ======================

URL_REGEX = re.compile(
    r"(https?://[^\s<>\"]+)",
    re.IGNORECASE
)


# ======================
# أنماط المنصات (محدودة للتليجرام والواتساب فقط)
# ======================

PLATFORM_PATTERNS = {
    "telegram": re.compile(r"(t\.me|telegram\.me)", re.IGNORECASE),
    "whatsapp": re.compile(r"(wa\.me|chat\.whatsapp\.com)", re.IGNORECASE),
}


# ======================
# أنماط محددة لروابط التليجرام
# ======================

TG_PATTERNS = {
    "channel": re.compile(r"https?://t\.me/([A-Za-z0-9_]+)$", re.I),  # t.me/username
    "private_group": re.compile(r"https?://t\.me/joinchat/([A-Za-z0-9_-]+)", re.I),  # روابط الانضمام
    "public_group": re.compile(r"https?://t\.me/\+([A-Za-z0-9]+)", re.I),  # روابط المجموعات العامة
    "bot": re.compile(r"https?://t\.me/([A-Za-z0-9_]+)bot(\?|$)", re.I),  # بوتات
    "message": re.compile(r"https?://t\.me/(c/)?([A-Za-z0-9_]+)/(\d+)", re.I),  # روابط رسائل
}


# ======================
# تنظيف الروابط
# ======================

def clean_link(url: str) -> str:
    """
    تنظيف الرابط من الزوائد (نجوم، مسافات، إلخ)
    """
    if not url:
        return ""
    
    # إزالة المسافات والنجوم
    cleaned = url.strip().replace('*', '').replace(' ', '')
    
    # إزالة الأحرف الغريبة في البداية والنهاية
    cleaned = re.sub(r'^[^a-zA-Z0-9]+', '', cleaned)
    cleaned = re.sub(r'[^a-zA-Z0-9]+$', '', cleaned)
    
    return cleaned


# ======================
# استخراج الروابط من الرسالة
# ======================

def extract_links_from_message(message: Message) -> List[str]:
    """
    استخراج الروابط من رسالة التليجرام
    """
    links = set()
    
    # النص الأساسي
    text = message.text or message.message or ""
    if text:
        for url in URL_REGEX.findall(text):
            cleaned = clean_link(url)
            if cleaned and is_allowed_link(cleaned):
                links.add(cleaned)
    
    # الكابتشن (إذا كانت صورة/فيديو)
    if hasattr(message, 'caption') and message.caption:
        for url in URL_REGEX.findall(message.caption):
            cleaned = clean_link(url)
            if cleaned and is_allowed_link(cleaned):
                links.add(cleaned)
    
    # أزرار Inline
    if hasattr(message, 'reply_markup') and message.reply_markup:
        for row in message.reply_markup.rows:
            for button in row.buttons:
                if hasattr(button, "url") and button.url:
                    cleaned = clean_link(button.url)
                    if cleaned and is_allowed_link(cleaned):
                        links.add(cleaned)
    
    # الروابط المخفية (الكيانات)
    if hasattr(message, 'entities') and message.entities:
        for entity in message.entities:
            if hasattr(entity, 'url') and entity.url:
                cleaned = clean_link(entity.url)
                if cleaned and is_allowed_link(cleaned):
                    links.add(cleaned)
    
    return list(links)


# ======================
# فحص الروابط المسموح بها
# ======================

def is_allowed_link(url: str) -> bool:
    """
    التحقق إذا كان الرابط مسموحًا به (تليجرام أو واتساب فقط)
    """
    # تجاهل الروابط الفارغة
    if not url or len(url) < 10:
        return False
    
    # تجاهل الروابط الممنوعة
    for blacklisted in BLACKLISTED_DOMAINS:
        if blacklisted in url:
            return False
    
    # السماح فقط بالتليجرام والواتساب
    platform = classify_platform(url)
    return platform in ["telegram", "whatsapp"]


# ======================
# تصنيف المنصة
# ======================

def classify_platform(url: str) -> str:
    """
    تحديد المنصة (تليجرام / واتساب)
    """
    url_lower = url.lower()
    
    for platform, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(url_lower):
            return platform
    
    return "other"


# ======================
# تصنيف روابط التليجرام
# ======================

def classify_telegram_link(url: str) -> str:
    """
    تحديد نوع رابط التليجرام
    """
    url_lower = url.lower()
    
    for link_type, pattern in TG_PATTERNS.items():
        if pattern.search(url_lower):
            return link_type
    
    # إذا لم يتطابق مع الأنواع المعروفة
    parsed = urlparse(url_lower)
    path = parsed.path.strip('/')
    
    if path.startswith('joinchat/'):
        return "private_group"
    elif path.startswith('+'):
        return "public_group"
    elif path.endswith('bot'):
        return "bot"
    elif re.search(r'/\d+$', path):
        return "message"
    elif re.match(r'^[A-Za-z0-9_]+$', path):
        return "channel"
    
    return "unknown"


# ======================
# فحص الروابط عبر الإنترنت
# ======================

async def verify_telegram_link(session: aiohttp.ClientSession, url: str) -> Tuple[bool, str, Dict]:
    """
    فحص رابط تليجرام عبر الإنترنت
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        async with session.get(url, headers=headers, timeout=VERIFY_TIMEOUT) as response:
            html = await response.text()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # البحث عن أزرار الاشتراك/الانضمام
            subscribe_button = soup.find(text=re.compile(r'اشتراك|Subscribe', re.I))
            join_button = soup.find(text=re.compile(r'انضم|Join', re.I))
            send_message_button = soup.find(text=re.compile(r'رسالة|Message', re.I))
            
            metadata = {
                'title': soup.title.string if soup.title else None,
                'description': soup.find('meta', attrs={'name': 'description'})['content'] 
                             if soup.find('meta', attrs={'name': 'description'}) else None,
                'status_code': response.status
            }
            
            # تحديد النوع بناءً على محتوى الصفحة
            link_type = classify_telegram_link(url)
            
            if response.status == 200:
                # فحص محتوى الصفحة
                if subscribe_button:
                    # قناة (زر اشتراك)
                    return True, "channel", metadata
                elif join_button:
                    # مجموعة (زر انضم)
                    return True, "group", metadata
                elif send_message_button:
                    # بوت أو حساب شخصي
                    return True, "bot", metadata
                else:
                    # صفحة تعمل لكن بدون أزرار واضحة
                    return True, link_type, metadata
            elif response.status == 404:
                return False, "invalid", metadata
            else:
                return False, "error", metadata
                
    except asyncio.TimeoutError:
        return False, "timeout", {}
    except Exception as e:
        print(f"Error verifying link {url}: {e}")
        return False, "error", {}


async def verify_whatsapp_link(session: aiohttp.ClientSession, url: str) -> Tuple[bool, str, Dict]:
    """
    فحص رابط واتساب
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        async with session.get(url, headers=headers, timeout=VERIFY_TIMEOUT, allow_redirects=True) as response:
            metadata = {
                'status_code': response.status,
                'final_url': str(response.url)
            }
            
            if response.status == 200:
                return True, "active", metadata
            elif response.status == 404:
                return False, "invalid", metadata
            else:
                return False, "error", metadata
                
    except asyncio.TimeoutError:
        return False, "timeout", {}
    except Exception as e:
        print(f"Error verifying WhatsApp link {url}: {e}")
        return False, "error", {}


async def verify_link(url: str) -> Tuple[bool, str, str, Dict]:
    """
    فحص الرابط العام (يختار الوظيفة المناسبة حسب المنصة)
    """
    if not VERIFY_LINKS:
        platform = classify_platform(url)
        link_type = classify_telegram_link(url) if platform == "telegram" else "group"
        return True, platform, link_type, {}
    
    async with aiohttp.ClientSession() as session:
        platform = classify_platform(url)
        
        if platform == "telegram":
            is_valid, result, metadata = await verify_telegram_link(session, url)
            if is_valid:
                # تحديد النوع النهائي بناءً على الفحص
                if result == "channel":
                    link_type = "channel"
                elif result == "group":
                    # محاولة تحديد إذا كانت عامة أو خاصة
                    if "joinchat" in url.lower():
                        link_type = "private_group"
                    elif url.lower().startswith("https://t.me/+"):
                        link_type = "public_group"
                    else:
                        link_type = "group"
                else:
                    link_type = result
                return True, platform, link_type, metadata
            else:
                return False, platform, result, metadata
                
        elif platform == "whatsapp":
            is_valid, result, metadata = await verify_whatsapp_link(session, url)
            if is_valid:
                # روابط واتساب تكون عادةً مجموعات
                link_type = "group" if "chat.whatsapp.com" in url else "phone"
                return True, platform, link_type, metadata
            else:
                return False, platform, result, metadata
                
        else:
            return False, "other", "not_supported", {}


# ======================
# فحص مجمع للروابط
# ======================

async def verify_links_batch(urls: List[str]) -> List[Dict]:
    """
    فحص مجموعة من الروابط بشكل متزامن
    """
    if not urls:
        return []
    
    results = []
    semaphore = asyncio.Semaphore(5)  # 5 عمليات متزامنة كحد أقصى
    
    async def verify_with_semaphore(url):
        async with semaphore:
            is_valid, platform, link_type, metadata = await verify_link(url)
            return {
                'url': url,
                'is_valid': is_valid,
                'platform': platform,
                'link_type': link_type,
                'metadata': metadata
            }
    
    tasks = [verify_with_semaphore(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # تصفية النتائج الفاشلة
    valid_results = []
    for result in results:
        if isinstance(result, Exception):
            print(f"Error in batch verification: {result}")
        else:
            valid_results.append(result)
    
    return valid_results


# ======================
# تصدير الروابط
# ======================

def format_links_for_export(links: List[Dict]) -> str:
    """
    تنسيق الروابط للتصدير
    """
    if not links:
        return ""
    
    output = []
    for link in links:
        url = link.get('url', '')
        platform = link.get('platform', 'unknown')
        link_type = link.get('link_type', 'unknown')
        
        output.append(f"{url} | {platform} | {link_type}")
    
    return "\n".join(output)


# ======================
# اختبار الوظائف
# ======================

if __name__ == "__main__":
    # أمثلة للاختبار
    test_links = [
        "https://t.me/python_ar",
        "https://t.me/joinchat/abcdefg",
        "https://t.me/+1234567890",
        "https://t.me/example_bot",
        "https://t.me/c/1234567890/123",
        "https://chat.whatsapp.com/abcdefg123",
        "https://wa.me/1234567890"
    ]
    
    print("📋 اختبار تنظيف الروابط:")
    for link in test_links:
        cleaned = clean_link(f" * {link} * ")
        print(f"  {cleaned}")
    
    print("\n📋 اختبار تصنيف التليجرام:")
    for link in test_links:
        if "t.me" in link:
            link_type = classify_telegram_link(link)
            print(f"  {link} -> {link_type}")
