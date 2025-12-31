import re
import asyncio
import logging
from typing import List, Optional, Tuple, Dict, Set
from urllib.parse import urlparse

from telethon.tl.types import Message

from config import VERIFY_LINKS, VERIFY_TIMEOUT, BLACKLISTED_DOMAINS

# ======================
# Logging Configuration
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Regex Patterns
# ======================

URL_REGEX = re.compile(
    r"(https?://[^\s<>\"]+)",
    re.IGNORECASE
)

# أنماط المنصات
PLATFORM_PATTERNS = {
    "telegram": re.compile(r"(t\.me|telegram\.me)", re.IGNORECASE),
    "whatsapp": re.compile(r"(wa\.me|chat\.whatsapp\.com)", re.IGNORECASE),
}

# أنماط محددة لروابط التليجرام
TELEGRAM_PATTERNS = {
    "channel": re.compile(r"https?://t\.me/([A-Za-z0-9_]+)$", re.I),
    "private_group": re.compile(r"https?://t\.me/joinchat/([A-Za-z0-9_-]+)", re.I),
    "public_group": re.compile(r"https?://t\.me/\+([A-Za-z0-9]+)", re.I),
    "bot": re.compile(r"https?://t\.me/([A-Za-z0-9_]+)bot(\?|$)", re.I),
    "message": re.compile(r"https?://t\.me/(c/)?([A-Za-z0-9_]+)/(\d+)", re.I),
}

# أنماط محددة لروابط الواتساب
WHATSAPP_PATTERNS = {
    "group": re.compile(r"https?://chat\.whatsapp\.com/([A-Za-z0-9]+)", re.I),
    "phone": re.compile(r"https?://wa\.me/(\d+)", re.I),
}

# ======================
# Link Cleaning Functions
# ======================

def clean_link(url: str) -> str:
    """
    تنظيف الرابط من الزوائد (نجوم، مسافات، إلخ)
    
    Args:
        url: الرابط الخام
        
    Returns:
        str: الرابط النظيف
    """
    if not url or not isinstance(url, str):
        return ""
    
    # إزالة المسافات والنجوم
    cleaned = url.strip().replace('*', '').replace(' ', '')
    
    # إزالة الأحرف الغريبة في البداية والنهاية
    cleaned = re.sub(r'^[^a-zA-Z0-9]+', '', cleaned)
    cleaned = re.sub(r'[^a-zA-Z0-9]+$', '', cleaned)
    
    # إزالة المتكررات من ///
    cleaned = re.sub(r'/{2,}', '/', cleaned)
    
    # التأكد من أن الرابط يبدأ بـ http:// أو https://
    if cleaned and not cleaned.startswith(('http://', 'https://')):
        cleaned = 'https://' + cleaned
    
    return cleaned

def is_valid_url(url: str) -> bool:
    """
    التحقق من صحة تنسيق الرابط
    
    Args:
        url: الرابط للتحقق
        
    Returns:
        bool: True إذا كان الرابط صالحاً
    """
    if not url:
        return False
    
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

# ======================
# Link Extraction Functions
# ======================

def extract_links_from_text(text: str) -> List[str]:
    """
    استخراج الروابط من النص
    
    Args:
        text: النص المستخرج منه الروابط
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    if not text:
        return []
    
    links = set()
    for url in URL_REGEX.findall(text):
        cleaned = clean_link(url)
        if cleaned and is_valid_url(cleaned):
            links.add(cleaned)
    
    return list(links)

def extract_links_from_message(message: Message) -> List[str]:
    """
    استخراج الروابط من رسالة تليجرام
    
    Args:
        message: كائن الرسالة من Telethon
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    links = set()
    
    # النص الأساسي للرسالة
    text = message.text or message.message or ""
    if text:
        links.update(extract_links_from_text(text))
    
    # الكابتشن (إذا كانت صورة/فيديو)
    if hasattr(message, 'caption') and message.caption:
        links.update(extract_links_from_text(message.caption))
    
    # أزرار Inline
    if hasattr(message, 'reply_markup') and message.reply_markup:
        for row in message.reply_markup.rows:
            for button in row.buttons:
                if hasattr(button, "url") and button.url:
                    cleaned = clean_link(button.url)
                    if cleaned and is_valid_url(cleaned):
                        links.add(cleaned)
    
    # الروابط المخفية (الكيانات)
    if hasattr(message, 'entities') and message.entities:
        for entity in message.entities:
            if hasattr(entity, 'url') and entity.url:
                cleaned = clean_link(entity.url)
                if cleaned and is_valid_url(cleaned):
                    links.add(cleaned)
    
    return list(links)

# ======================
# Link Filtering Functions
# ======================

def is_blacklisted(url: str) -> bool:
    """
    التحقق إذا كان الرابط في القائمة السوداء
    
    Args:
        url: الرابط للتحقق
        
    Returns:
        bool: True إذا كان الرابط ممنوعاً
    """
    if not url or not BLACKLISTED_DOMAINS:
        return False
    
    url_lower = url.lower()
    for blacklisted in BLACKLISTED_DOMAINS:
        if blacklisted and blacklisted.lower() in url_lower:
            return True
    
    return False

def is_allowed_link(url: str) -> bool:
    """
    التحقق إذا كان الرابط مسموحاً به (تليجرام أو واتساب فقط)
    
    Args:
        url: الرابط للتحقق
        
    Returns:
        bool: True إذا كان الرابط مسموحاً به
    """
    # تجاهل الروابط الفارغة أو القصيرة
    if not url or len(url) < 10:
        return False
    
    # تجاهل الروابط الممنوعة
    if is_blacklisted(url):
        return False
    
    # التحقق من صحة تنسيق الرابط
    if not is_valid_url(url):
        return False
    
    # السماح فقط بالتليجرام والواتساب
    platform = classify_platform(url)
    return platform in ["telegram", "whatsapp"]

def filter_links(links: List[str]) -> List[str]:
    """
    فلترة قائمة من الروابط وإرجاع المسموح بها فقط
    
    Args:
        links: قائمة الروابط الخام
        
    Returns:
        list: قائمة بالروابط المسموح بها
    """
    if not links:
        return []
    
    filtered_links = []
    for link in links:
        cleaned = clean_link(link)
        if cleaned and is_allowed_link(cleaned):
            filtered_links.append(cleaned)
    
    return filtered_links

# ======================
# Platform Classification
# ======================

def classify_platform(url: str) -> str:
    """
    تحديد المنصة (تليجرام / واتساب / أخرى)
    
    Args:
        url: الرابط للتصنيف
        
    Returns:
        str: اسم المنصة
    """
    if not url:
        return "unknown"
    
    url_lower = url.lower()
    
    for platform, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(url_lower):
            return platform
    
    return "other"

def classify_telegram_link(url: str) -> str:
    """
    تحديد نوع رابط التليجرام
    
    Args:
        url: رابط تليجرام
        
    Returns:
        str: نوع الرابط
    """
    if not url:
        return "unknown"
    
    url_lower = url.lower()
    
    for link_type, pattern in TELEGRAM_PATTERNS.items():
        if pattern.search(url_lower):
            return link_type
    
    # إذا لم يتطابق مع الأنواع المعروفة، نستخدم منطق بديل
    parsed = urlparse(url_lower)
    path = parsed.path.strip('/')
    
    if path.startswith('joinchat/'):
        return "private_group"
    elif path.startswith('+'):
        return "public_group"
    elif 'bot' in path:
        return "bot"
    elif re.search(r'/\d+$', path):
        return "message"
    elif re.match(r'^[A-Za-z0-9_]+$', path):
        return "channel"
    
    return "unknown"

def classify_whatsapp_link(url: str) -> str:
    """
    تحديد نوع رابط الواتساب
    
    Args:
        url: رابط واتساب
        
    Returns:
        str: نوع الرابط
    """
    if not url:
        return "unknown"
    
    url_lower = url.lower()
    
    for link_type, pattern in WHATSAPP_PATTERNS.items():
        if pattern.search(url_lower):
            return link_type
    
    if "chat.whatsapp.com" in url_lower:
        return "group"
    elif "wa.me" in url_lower:
        return "phone"
    
    return "unknown"

# ======================
# Link Verification Functions
# ======================

async def verify_telegram_link(url: str) -> Tuple[bool, str, Dict]:
    """
    فحص رابط تليجرام (وظيفة مبسطة)
    
    Args:
        url: رابط تليجرام للفحص
        
    Returns:
        tuple: (is_valid, link_type, metadata)
    """
    try:
        # في الإصدار المبسط، نستخدم التصنيف فقط
        # في الإصدار الكامل يمكن إضافة فحص HTTP هنا
        
        link_type = classify_telegram_link(url)
        
        metadata = {
            "platform": "telegram",
            "url": url,
            "verified_at": str(asyncio.get_event_loop().time())
        }
        
        # نعتبر جميع روابط التليجرام صالحة في الإصدار المبسط
        return True, link_type, metadata
        
    except Exception as e:
        logger.error(f"Error verifying telegram link {url}: {e}")
        return False, "error", {"error": str(e)}

async def verify_whatsapp_link(url: str) -> Tuple[bool, str, Dict]:
    """
    فحص رابط واتساب (وظيفة مبسطة)
    
    Args:
        url: رابط واتساب للفحص
        
    Returns:
        tuple: (is_valid, link_type, metadata)
    """
    try:
        link_type = classify_whatsapp_link(url)
        
        metadata = {
            "platform": "whatsapp",
            "url": url,
            "verified_at": str(asyncio.get_event_loop().time())
        }
        
        # نعتبر جميع روابط الواتساب صالحة في الإصدار المبسط
        return True, link_type, metadata
        
    except Exception as e:
        logger.error(f"Error verifying whatsapp link {url}: {e}")
        return False, "error", {"error": str(e)}

async def verify_link(url: str) -> Tuple[bool, str, str, Dict]:
    """
    فحص الرابط العام (يختار الوظيفة المناسبة حسب المنصة)
    
    Args:
        url: الرابط للفحص
        
    Returns:
        tuple: (is_valid, platform, link_type, metadata)
    """
    if not VERIFY_LINKS:
        # إذا كان الفحص معطلاً، نرجع قيماً افتراضية
        platform = classify_platform(url)
        if platform == "telegram":
            link_type = classify_telegram_link(url)
        elif platform == "whatsapp":
            link_type = classify_whatsapp_link(url)
        else:
            link_type = "other"
        
        return True, platform, link_type, {}
    
    # إذا كان الفحص مفعلاً، نستخدم الوظائف المناسبة
    platform = classify_platform(url)
    
    if platform == "telegram":
        is_valid, link_type, metadata = await verify_telegram_link(url)
        if is_valid:
            return True, platform, link_type, metadata
        else:
            return False, platform, link_type, metadata
            
    elif platform == "whatsapp":
        is_valid, link_type, metadata = await verify_whatsapp_link(url)
        if is_valid:
            return True, platform, link_type, metadata
        else:
            return False, platform, link_type, metadata
            
    else:
        return False, "other", "not_supported", {}

async def verify_links_batch(urls: List[str]) -> List[Dict]:
    """
    فحص مجموعة من الروابط بشكل متزامن
    
    Args:
        urls: قائمة الروابط للفحص
        
    Returns:
        list: قائمة بنتائج الفحص
    """
    if not urls:
        return []
    
    results = []
    
    # في الإصدار المبسط، نفحص الروابط بشكل متسلسل
    # في الإصدار الكامل يمكن استخدام asyncio.gather للفحص المتوازي
    for url in urls:
        try:
            is_valid, platform, link_type, metadata = await verify_link(url)
            
            results.append({
                'url': url,
                'is_valid': is_valid,
                'platform': platform,
                'link_type': link_type,
                'metadata': metadata
            })
            
        except Exception as e:
            logger.error(f"Error verifying link {url}: {e}")
            results.append({
                'url': url,
                'is_valid': False,
                'platform': 'error',
                'link_type': 'error',
                'metadata': {'error': str(e)}
            })
    
    return results

async def verify_links_batch_concurrent(urls: List[str], max_concurrent: int = 5) -> List[Dict]:
    """
    فحص مجموعة من الروابط بشكل متزامن مع التحكم في العدد
    
    Args:
        urls: قائمة الروابط للفحص
        max_concurrent: الحد الأقصى للعمليات المتزامنة
        
    Returns:
        list: قائمة بنتائج الفحص
    """
    if not urls:
        return []
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def verify_with_semaphore(url):
        async with semaphore:
            return await verify_link(url)
    
    tasks = []
    for url in urls:
        task = asyncio.create_task(verify_with_semaphore(url))
        tasks.append((url, task))
    
    results = []
    for url, task in tasks:
        try:
            is_valid, platform, link_type, metadata = await task
            
            results.append({
                'url': url,
                'is_valid': is_valid,
                'platform': platform,
                'link_type': link_type,
                'metadata': metadata
            })
            
        except Exception as e:
            logger.error(f"Error verifying link {url}: {e}")
            results.append({
                'url': url,
                'is_valid': False,
                'platform': 'error',
                'link_type': 'error',
                'metadata': {'error': str(e)}
            })
    
    return results

# ======================
# Link Analysis Functions
# ======================

def analyze_links(links: List[str]) -> Dict:
    """
    تحليل قائمة من الروابط وإرجاع إحصائيات
    
    Args:
        links: قائمة الروابط
        
    Returns:
        dict: إحصائيات التحليل
    """
    stats = {
        "total": len(links),
        "telegram": 0,
        "whatsapp": 0,
        "other": 0,
        "valid": 0,
        "invalid": 0,
        "by_type": {}
    }
    
    for link in links:
        # التحقق من الصحة الأساسية
        if is_valid_url(link):
            stats["valid"] += 1
        else:
            stats["invalid"] += 1
        
        # التصنيف حسب المنصة
        platform = classify_platform(link)
        if platform in stats:
            stats[platform] += 1
        else:
            stats["other"] += 1
        
        # التصنيف حسب النوع
        if platform == "telegram":
            link_type = classify_telegram_link(link)
        elif platform == "whatsapp":
            link_type = classify_whatsapp_link(link)
        else:
            link_type = "other"
        
        if link_type in stats["by_type"]:
            stats["by_type"][link_type] += 1
        else:
            stats["by_type"][link_type] = 1
    
    return stats

def get_unique_domains(links: List[str]) -> List[str]:
    """
    استخراج النطاقات الفريدة من قائمة الروابط
    
    Args:
        links: قائمة الروابط
        
    Returns:
        list: قائمة بالنطاقات الفريدة
    """
    domains = set()
    
    for link in links:
        try:
            parsed = urlparse(link)
            if parsed.netloc:
                domains.add(parsed.netloc)
        except:
            continue
    
    return sorted(list(domains))

# ======================
# Export Functions
# ======================

def format_links_for_export(links: List[Dict], include_metadata: bool = False) -> str:
    """
    تنسيق الروابط للتصدير
    
    Args:
        links: قائمة بالروابط مع بياناتها
        include_metadata: تضمين البيانات الوصفية
        
    Returns:
        str: النص المنسق
    """
    if not links:
        return ""
    
    output = []
    
    for link in links:
        url = link.get('url', '')
        platform = link.get('platform', 'unknown')
        link_type = link.get('link_type', 'unknown')
        
        if include_metadata and link.get('metadata'):
            metadata_str = str(link.get('metadata'))
            output.append(f"{url} | {platform} | {link_type} | {metadata_str}")
        else:
            output.append(f"{url} | {platform} | {link_type}")
    
    return "\n".join(output)

def export_links_by_platform(links: List[Dict]) -> Dict[str, str]:
    """
    تصدير الروابط مصنفة حسب المنصة
    
    Args:
        links: قائمة بالروابط مع بياناتها
        
    Returns:
        dict: نصوص مصنفة حسب المنصة
    """
    platforms = {}
    
    for link in links:
        platform = link.get('platform', 'other')
        url = link.get('url', '')
        
        if platform not in platforms:
            platforms[platform] = []
        
        platforms[platform].append(url)
    
    # تحويل إلى نصوص
    result = {}
    for platform, urls in platforms.items():
        result[platform] = "\n".join(urls)
    
    return result

# ======================
# Test Functions
# ======================

async def test_link_utils():
    """
    اختبار جميع وظائف link_utils
    """
    print("\n" + "="*50)
    print("🧪 Testing Link Utilities Module")
    print("="*50)
    
    # روابط اختبارية
    test_links = [
        " * https://t.me/python_ar * ",
        "  https://t.me/joinchat/abcdefg  ",
        "https://t.me/+1234567890",
        "https://t.me/test_bot",
        "https://t.me/c/1234567890/123",
        "https://chat.whatsapp.com/abc123def",
        "https://wa.me/1234567890",
        "https://example.com",
        "invalid url",
        "  *  https://t.me/telegram  *  "
    ]
    
    # 1. اختبار التنظيف
    print("\n1. Testing link cleaning:")
    for link in test_links[:3]:
        cleaned = clean_link(link)
        print(f"   '{link}' -> '{cleaned}'")
    
    # 2. اختبار التصنيف
    print("\n2. Testing platform classification:")
    test_classification = [
        "https://t.me/test",
        "https://chat.whatsapp.com/abc",
        "https://example.com"
    ]
    
    for link in test_classification:
        platform = classify_platform(link)
        print(f"   {link} -> {platform}")
    
    # 3. اختبار تصنيف التليجرام
    print("\n3. Testing telegram link classification:")
    telegram_links = [
        "https://t.me/channel",
        "https://t.me/joinchat/abc",
        "https://t.me/+invite",
        "https://t.me/test_bot",
        "https://t.me/c/123/456"
    ]
    
    for link in telegram_links:
        link_type = classify_telegram_link(link)
        print(f"   {link} -> {link_type}")
    
    # 4. اختبار الفلترة
    print("\n4. Testing link filtering:")
    filtered = filter_links(test_links)
    print(f"   Total links: {len(test_links)}")
    print(f"   Filtered links: {len(filtered)}")
    
    # 5. اختبار التحقق
    print("\n5. Testing link verification:")
    verification_links = test_links[:5]
    
    for link in verification_links:
        is_valid, platform, link_type, metadata = await verify_link(link)
        status = "✅" if is_valid else "❌"
        print(f"   {status} {link} -> {platform}/{link_type}")
    
    # 6. اختبار التحليل
    print("\n6. Testing link analysis:")
    stats = analyze_links(filtered)
    print(f"   Total: {stats['total']}")
    print(f"   Telegram: {stats['telegram']}")
    print(f"   WhatsApp: {stats['whatsapp']}")
    print(f"   Valid: {stats['valid']}")
    
    print("\n" + "="*50)
    print("✅ Link Utilities test completed successfully!")
    print("="*50)

# ======================
# Main Test
# ======================

if __name__ == "__main__":
    import asyncio
    
    # تشغيل الاختبار
    asyncio.run(test_link_utils())
