import re
import logging
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urlparse, parse_qs
import hashlib

from config import (
    IGNORED_PATTERNS, BLACKLISTED_DOMAINS,
    TELEGRAM_PUBLIC_GROUP_PATTERNS, TELEGRAM_PRIVATE_GROUP_PATTERNS,
    TELEGRAM_CHANNEL_PATTERNS, WHATSAPP_LINK_PATTERNS,
    FILTER_CHANNELS, FILTER_EMPTY_GROUPS, FILTER_BANNED_GROUPS,
    FILTER_DEAD_LINKS
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
# Constants
# ======================

# روابط معروفة للقنوات الشهيرة (للتجاهل)
KNOWN_CHANNELS = {
    # قنوات إخبارية
    'telegram', 'telegramtips', 'telegramchannels',
    'telegramstore', 'telegramandroid', 'telegramios',
    
    # قنوات عربية
    'alarabiya', 'aljazeera', 'bbcnewsarabic',
    'skynewsarabia', 'cnnarabic', 'france24ar',
    
    # قنوات تقنية
    'tech', 'technology', 'android', 'ios', 'windows',
    
    # قنوات ترفيهية
    'movies', 'series', 'music', 'entertainment',
    
    # قنوات رياضية
    'sports', 'football', 'soccer', 'basketball'
}

# كلمات تشير إلى القنوات
CHANNEL_KEYWORDS = [
    'قناة', 'كانال', 'channel', 'news', 'اخبار',
    'بث', 'broadcast', 'رسمي', 'official',
    'اعلانات', 'announcements', 'اخباري', 'نشرات'
]

# كلمات تشير إلى المجموعات
GROUP_KEYWORDS = [
    'مجموعة', 'جروب', 'group', 'شات', 'chat',
    'دردشة', 'تحدث', 'talk', 'نقاش', 'discussion',
    'حوار', 'اجتماع', 'meeting', 'مجتمع', 'community'
]

# ======================
# URL Normalization
# ======================

def normalize_url(url: str) -> str:
    """تطبيع الرابط (إزالة الـ query parameters غير الضرورية)"""
    if not url or not isinstance(url, str):
        return ""
    
    url = url.strip()
    
    # إزالة المسافات الزائدة
    url = re.sub(r'\s+', '', url)
    
    # إضافة https:// إذا لم يكن موجوداً
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # تحليل الرابط
    parsed = urlparse(url)
    
    # تنظيف query parameters
    query_params = parse_qs(parsed.query)
    
    # إزالة parameters التتبع
    tracking_params = ['utm_', 'si=', 'ref=', 'share=', 'fbclid=', 'igshid=', 't=']
    clean_params = {}
    
    for key, values in query_params.items():
        if not any(key.startswith(param.rstrip('_')) for param in tracking_params):
            clean_params[key] = values
    
    # إعادة بناء query string نظيف
    if clean_params:
        clean_query = '&'.join(
            f"{key}={value[0]}" if len(value) == 1 else f"{key}={','.join(value)}"
            for key, value in clean_params.items()
        )
    else:
        clean_query = ''
    
    # إعادة بناء الرابط
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if clean_query:
        clean_url += f"?{clean_query}"
    
    # إزالة الـ trailing slash
    if clean_url.endswith('/'):
        clean_url = clean_url[:-1]
    
    # تحويل إلى حروف صغيرة (للتطبيع)
    clean_url = clean_url.lower()
    
    return clean_url

def get_url_hash(url: str) -> str:
    """إنشاء hash للرابط للتحقق من التكرار"""
    normalized = normalize_url(url)
    return hashlib.md5(normalized.encode()).hexdigest()

# ======================
# URL Validation
# ======================

def is_valid_url(url: str) -> bool:
    """التحقق من صحة تنسيق الرابط"""
    if not url or not isinstance(url, str):
        return False
    
    # تطبيع الرابط أولاً
    url = normalize_url(url)
    
    # تحقق من التنسيق الأساسي
    url_pattern = re.compile(
        r'^(https?://)?'  # http:// or https://
        r'(([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,6}'  # domain
        r'|localhost)'  # or localhost
        r'(:\d+)?'  # optional port
        r'(/.*)?$'  # optional path
    )
    
    return bool(url_pattern.match(url))

def is_url_ignored(url: str) -> Tuple[bool, str]:
    """التحقق مما إذا كان الرابط يجب تجاهله مع السبب"""
    if not url:
        return True, "رابط فارغ"
    
    url_lower = url.lower()
    
    # التحقق من الأنماط الممنوعة
    for pattern in IGNORED_PATTERNS:
        if re.search(pattern, url_lower, re.IGNORECASE):
            return True, f"يتطابق مع النمط الممنوع: {pattern}"
    
    # التحقق من النطاقات الممنوعة
    for domain in BLACKLISTED_DOMAINS:
        if domain.lower() in url_lower:
            return True, f"يتضمن النطاق الممنوع: {domain}"
    
    # تحقق من الروابط القصيرة (مشبوهة)
    if len(url) < 15:
        return True, "رابط قصير جداً (مشبوه)"
    
    # تحقق من الروابط الطويلة جداً (مشبوهة)
    if len(url) > 500:
        return True, "رابط طويل جداً (مشبوه)"
    
    return False, ""

# ======================
# Platform Detection
# ======================

def detect_platform(url: str) -> Optional[str]:
    """اكتشاف المنصة من الرابط"""
    url_lower = url.lower()
    
    if any(pattern in url_lower for pattern in ['t.me', 'telegram.me', 'tg://']):
        return 'telegram'
    elif any(pattern in url_lower for pattern in ['whatsapp.com', 'wa.me', 'chat.whatsapp.com']):
        return 'whatsapp'
    elif any(pattern in url_lower for pattern in ['facebook.com', 'fb.com', 'fb.me']):
        return 'facebook'
    elif any(pattern in url_lower for pattern in ['instagram.com', 'instagr.am']):
        return 'instagram'
    elif any(pattern in url_lower for pattern in ['twitter.com', 'x.com']):
        return 'twitter'
    elif any(pattern in url_lower for pattern in ['youtube.com', 'youtu.be']):
        return 'youtube'
    elif any(pattern in url_lower for pattern in ['linkedin.com']):
        return 'linkedin'
    elif any(pattern in url_lower for pattern in ['discord.com', 'discord.gg']):
        return 'discord'
    elif any(pattern in url_lower for pattern in ['signal.org', 'signal.me']):
        return 'signal'
    
    return 'other'

def is_telegram_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط خاص بتليجرام"""
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in ['t.me', 'telegram.me', 'tg://'])

def is_whatsapp_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط خاص بواتساب"""
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in ['whatsapp.com', 'wa.me', 'chat.whatsapp.com'])

# ======================
# Telegram Link Analysis
# ======================

def extract_telegram_username(url: str) -> Optional[str]:
    """استخراج اسم المستخدم من رابط تيليجرام"""
    patterns = [
        r't\.me/([A-Za-z0-9_]+)',
        r'telegram\.me/([A-Za-z0-9_]+)',
        r'tg://resolve\?domain=([A-Za-z0-9_]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            username = match.group(1)
            # إزالة أي query parameters
            if '?' in username:
                username = username.split('?')[0]
            if '/' in username:
                username = username.split('/')[0]
            return username.lower()
    
    return None

def extract_telegram_invite_hash(url: str) -> Optional[str]:
    """استخراج hash الدعوة من رابط تيليجرام الخاص"""
    patterns = [
        r't\.me/\+([A-Za-z0-9_-]+)',
        r'telegram\.me/\+([A-Za-z0-9_-]+)',
        r'tg://join\?invite=([A-Za-z0-9_-]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None

def extract_telegram_channel_id(url: str) -> Optional[str]:
    """استخراج معرف القناة من رابط تيليجرام"""
    patterns = [
        r't\.me/c/([0-9]+)',
        r'telegram\.me/c/([0-9]+)',
        r'tg://privatepost\?channel=([0-9]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None

def extract_telegram_message_id(url: str) -> Optional[str]:
    """استخراج معرف الرسالة من رابط تيليجرام"""
    patterns = [
        r't\.me/[A-Za-z0-9_]+/([0-9]+)',
        r'telegram\.me/[A-Za-z0-9_]+/([0-9]+)',
        r'tg://resolve\?domain=[A-Za-z0-9_]+&post=([0-9]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None

def is_telegram_channel_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط قناة تيليجرام"""
    # الأنماط المباشرة للقنوات
    for pattern in TELEGRAM_CHANNEL_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True
    
    # التحقق من روابط القنوات العامة
    username = extract_telegram_username(url)
    if username:
        # تحقق إذا كان اسم المستخدم يشير إلى قناة
        username_lower = username.lower()
        
        # كلمات تشير إلى القنوات
        for keyword in CHANNEL_KEYWORDS:
            if keyword in username_lower:
                return True
        
        # قنوات معروفة
        if username_lower in KNOWN_CHANNELS:
            return True
        
        # نمط أسماء القنوات (مثل ending with _channel)
        if username_lower.endswith(('_channel', 'channel', '_news', 'news')):
            return True
    
    return False

def is_telegram_group_link(url: str) -> Tuple[bool, str]:
    """التحقق مما إذا كان الرابط مجموعة تيليجرام مع النوع"""
    # روابط المجموعات العامة
    for pattern in TELEGRAM_PUBLIC_GROUP_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            # تحقق من أنه ليس قناة
            if is_telegram_channel_link(url):
                return False, "channel"
            return True, "public_group"
    
    # روابط المجموعات الخاصة
    for pattern in TELEGRAM_PRIVATE_GROUP_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True, "private_group"
    
    return False, "not_group"

def classify_telegram_link(url: str) -> Tuple[str, Dict]:
    """تصنيف رابط تيليجرام مع تفاصيل"""
    details = {}
    
    # استخراج المكونات
    username = extract_telegram_username(url)
    invite_hash = extract_telegram_invite_hash(url)
    channel_id = extract_telegram_channel_id(url)
    message_id = extract_telegram_message_id(url)
    
    if channel_id:
        details['channel_id'] = channel_id
        return 'channel', details
    
    if invite_hash:
        details['invite_hash'] = invite_hash
        
        # محاولة تحديد إذا كان مجموعة أو قناة
        if FILTER_CHANNELS:
            # المجموعات الخاصة عادة تحتوي على كلمات معينة
            if any(keyword in url.lower() for keyword in GROUP_KEYWORDS):
                return 'private_group', details
            else:
                return 'channel', details
        else:
            return 'private_group', details
    
    if username:
        details['username'] = username
        
        # تحليل اسم المستخدم
        username_lower = username.lower()
        
        # كلمات تشير إلى البوتات
        if username_lower.endswith('bot') or '_bot' in username_lower:
            return 'bot', details
        
        # كلمات تشير إلى المجموعات
        if any(keyword in username_lower for keyword in GROUP_KEYWORDS):
            return 'public_group', details
        
        # كلمات تشير إلى القنوات
        if any(keyword in username_lower for keyword in CHANNEL_KEYWORDS):
            if FILTER_CHANNELS:
                return 'channel', details
            else:
                return 'public_group', details
        
        # قنوات معروفة
        if username_lower in KNOWN_CHANNELS:
            if FILTER_CHANNELS:
                return 'channel', details
            else:
                return 'public_group', details
        
        # نمط أسماء القنوات
        if (username_lower.endswith(('_channel', 'channel', '_news', 'news')) or
            username_lower.startswith(('channel_', 'news_'))):
            if FILTER_CHANNELS:
                return 'channel', details
            else:
                return 'public_group', details
        
        # الافتراضي: مجموعة عامة
        return 'public_group', details
    
    if message_id:
        details['message_id'] = message_id
        return 'message', details
    
    return 'unknown', details

# ======================
# WhatsApp Link Analysis
# ======================

def extract_whatsapp_group_id(url: str) -> Optional[str]:
    """استخراج معرف مجموعة واتساب"""
    patterns = [
        r'chat\.whatsapp\.com/([A-Za-z0-9_-]+)',
        r'whatsapp\.com/channel/([A-Za-z0-9_-]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None

def extract_whatsapp_phone_number(url: str) -> Optional[str]:
    """استخراج رقم الهاتف من رابط واتساب"""
    pattern = r'wa\.me/([0-9]+)'
    match = re.search(pattern, url, re.IGNORECASE)
    
    if match:
        phone = match.group(1)
        # تنظيف الرقم
        phone = re.sub(r'[^0-9]', '', phone)
        return phone
    
    return None

def is_whatsapp_group_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط مجموعة واتساب"""
    for pattern in WHATSAPP_LINK_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            # تأكد أنه ليس رابط هاتف
            if 'wa.me/' in url and re.match(r'https?://wa\.me/[0-9]+', url, re.IGNORECASE):
                return False
            return True
    
    return False

def is_whatsapp_phone_link(url: str) -> bool:
    """التحقق مما إذا كان الرابط رقم واتساب"""
    pattern = r'https?://wa\.me/[0-9]+'
    return bool(re.match(pattern, url, re.IGNORECASE))

def classify_whatsapp_link(url: str) -> Tuple[str, Dict]:
    """تصنيف رابط واتساب مع تفاصيل"""
    details = {}
    
    group_id = extract_whatsapp_group_id(url)
    phone_number = extract_whatsapp_phone_number(url)
    
    if group_id:
        details['group_id'] = group_id
        return 'group', details
    
    if phone_number:
        details['phone_number'] = phone_number
        return 'phone', details
    
    return 'unknown', details

# ======================
# General Link Analysis
# ======================

def analyze_link(url: str) -> Dict:
    """تحليل شامل للرابط"""
    result = {
        'url': url,
        'normalized_url': '',
        'url_hash': '',
        'is_valid': False,
        'platform': 'unknown',
        'link_type': 'unknown',
        'details': {},
        'should_collect': False,
        'reason': '',
        'ignored': False,
        'ignore_reason': ''
    }
    
    try:
        # تطبيع الرابط
        normalized = normalize_url(url)
        result['normalized_url'] = normalized
        result['url_hash'] = get_url_hash(url)
        
        # التحقق من الصحة الأساسية
        if not is_valid_url(normalized):
            result['reason'] = 'تنسيق رابط غير صالح'
            return result
        
        # التحقق مما إذا كان يجب تجاهله
        ignored, ignore_reason = is_url_ignored(normalized)
        if ignored:
            result['ignored'] = True
            result['ignore_reason'] = ignore_reason
            result['reason'] = f'تم تجاهل الرابط: {ignore_reason}'
            return result
        
        result['is_valid'] = True
        
        # اكتشاف المنصة
        platform = detect_platform(normalized)
        result['platform'] = platform
        
        # تصنيف حسب المنصة
        if platform == 'telegram':
            link_type, details = classify_telegram_link(normalized)
            result['link_type'] = link_type
            result['details'] = details
            
            # تحديد إذا كان يجب جمعه
            if link_type in ['public_group', 'private_group']:
                result['should_collect'] = True
                result['reason'] = f'مجموعة تيليجرام ({link_type})'
            elif link_type == 'channel' and FILTER_CHANNELS:
                result['should_collect'] = False
                result['reason'] = 'قناة تيليجرام (مهملة)'
            else:
                result['should_collect'] = False
                result['reason'] = f'نوع رابط تيليجرام غير مجمع: {link_type}'
        
        elif platform == 'whatsapp':
            link_type, details = classify_whatsapp_link(normalized)
            result['link_type'] = link_type
            result['details'] = details
            
            # تحديد إذا كان يجب جمعه
            if link_type == 'group':
                result['should_collect'] = True
                result['reason'] = 'مجموعة واتساب'
            else:
                result['should_collect'] = False
                result['reason'] = f'نوع رابط واتساب غير مجمع: {link_type}'
        
        else:
            result['reason'] = f'منصة غير مدعومة: {platform}'
        
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing link {url}: {e}")
        result['reason'] = f'خطأ في التحليل: {str(e)}'
        return result

def analyze_links_batch(urls: List[str]) -> Dict:
    """تحليل مجموعة من الروابط دفعة واحدة"""
    results = {
        'total': len(urls),
        'valid': 0,
        'invalid': 0,
        'ignored': 0,
        'to_collect': 0,
        'by_platform': {},
        'by_type': {},
        'details': []
    }
    
    for url in urls:
        analysis = analyze_link(url)
        results['details'].append(analysis)
        
        if not analysis['is_valid']:
            results['invalid'] += 1
        elif analysis['ignored']:
            results['ignored'] += 1
        else:
            results['valid'] += 1
            
            if analysis['should_collect']:
                results['to_collect'] += 1
            
            # إحصائيات المنصة
            platform = analysis['platform']
            if platform not in results['by_platform']:
                results['by_platform'][platform] = 0
            results['by_platform'][platform] += 1
            
            # إحصائيات النوع
            link_type = analysis['link_type']
            key = f"{platform}_{link_type}"
            if key not in results['by_type']:
                results['by_type'][key] = 0
            results['by_type'][key] += 1
    
    return results

# ======================
# Link Filtering
# ======================

def filter_links_for_collection(urls: List[str]) -> Tuple[List[str], Dict]:
    """تصفية الروابط للجمع مع إحصائيات"""
    to_collect = []
    stats = {
        'total': len(urls),
        'collected': 0,
        'ignored': 0,
        'invalid': 0,
        'telegram_groups': 0,
        'whatsapp_groups': 0,
        'channels_skipped': 0,
        'ignored_reasons': {}
    }
    
    seen_hashes = set()
    
    for url in urls:
        analysis = analyze_link(url)
        
        if not analysis['is_valid']:
            stats['invalid'] += 1
            continue
        
        if analysis['ignored']:
            stats['ignored'] += 1
            reason = analysis.get('ignore_reason', 'unknown')
            if reason not in stats['ignored_reasons']:
                stats['ignored_reasons'][reason] = 0
            stats['ignored_reasons'][reason] += 1
            continue
        
        # التحقق من التكرار
        url_hash = analysis['url_hash']
        if url_hash in seen_hashes:
            continue
        seen_hashes.add(url_hash)
        
        if analysis['should_collect']:
            to_collect.append(analysis['normalized_url'])
            stats['collected'] += 1
            
            if analysis['platform'] == 'telegram' and analysis['link_type'] in ['public_group', 'private_group']:
                stats['telegram_groups'] += 1
            elif analysis['platform'] == 'whatsapp' and analysis['link_type'] == 'group':
                stats['whatsapp_groups'] += 1
        
        elif analysis['platform'] == 'telegram' and analysis['link_type'] == 'channel':
            stats['channels_skipped'] += 1
    
    return to_collect, stats

# ======================
# URL Generation
# ======================

def generate_telegram_public_group_url(username: str) -> str:
    """إنشاء رابط مجموعة تيليجرام عامة"""
    username = re.sub(r'[^A-Za-z0-9_]', '', username)
    return f"https://t.me/{username}"

def generate_telegram_private_group_url(invite_hash: str) -> str:
    """إنشاء رابط مجموعة تيليجرام خاصة"""
    invite_hash = re.sub(r'[^A-Za-z0-9_-]', '', invite_hash)
    return f"https://t.me/+{invite_hash}"

def generate_whatsapp_group_url(group_id: str) -> str:
    """إنشاء رابط مجموعة واتساب"""
    group_id = re.sub(r'[^A-Za-z0-9_-]', '', group_id)
    return f"https://chat.whatsapp.com/{group_id}"

# ======================
# URL Cleaning
# ======================

def clean_url_list(urls: List[str]) -> List[str]:
    """تنظيف قائمة الروابط"""
    cleaned = []
    seen = set()
    
    for url in urls:
        if not url or not isinstance(url, str):
            continue
        
        normalized = normalize_url(url)
        
        # التحقق من الصحة الأساسية
        if not is_valid_url(normalized):
            continue
        
        # التحقق من التكرار
        url_hash = get_url_hash(normalized)
        if url_hash in seen:
            continue
        
        # التحقق من التجاهل
        ignored, _ = is_url_ignored(normalized)
        if ignored:
            continue
        
        cleaned.append(normalized)
        seen.add(url_hash)
    
    return cleaned

def extract_urls_from_text(text: str) -> List[str]:
    """استخراج الروابط من النص"""
    if not text:
        return []
    
    # نمط للعثور على الروابط
    url_pattern = re.compile(
        r'https?://'  # http:// or https://
        r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+'  # domain
        r'[A-Za-z]{2,6}'  # TLD
        r'(?:[/\w .?=&%-]*)?',  # path and query
        re.IGNORECASE
    )
    
    urls = url_pattern.findall(text)
    return clean_url_list(urls)

# ======================
# Quality Checks
# ======================

def estimate_group_activity(url: str) -> str:
    """تقدير نشاط المجموعة من الرابط"""
    analysis = analyze_link(url)
    
    if not analysis['is_valid'] or not analysis['should_collect']:
        return 'unknown'
    
    platform = analysis['platform']
    link_type = analysis['link_type']
    
    if platform == 'telegram':
        if link_type == 'public_group':
            username = analysis['details'].get('username', '')
            if username:
                # المجموعات ذات الأسماء القصيرة عادة أكثر نشاطاً
                if len(username) <= 10:
                    return 'high'
                elif len(username) <= 20:
                    return 'medium'
                else:
                    return 'low'
        
        elif link_type == 'private_group':
            # المجموعات الخاصة عادة أكثر نشاطاً
            return 'high'
    
    elif platform == 'whatsapp':
        # مجموعات واتساب عادة نشطة
        return 'medium'
    
    return 'low'

def is_premium_group(url: str) -> bool:
    """التحقق مما إذا كانت المجموعة مميزة (محتملة)"""
    analysis = analyze_link(url)
    
    if not analysis['is_valid'] or not analysis['should_collect']:
        return False
    
    platform = analysis['platform']
    link_type = analysis['link_type']
    
    if platform == 'telegram' and link_type == 'public_group':
        username = analysis['details'].get('username', '')
        if username:
            # المجموعات ذات الأسماء القصيرة عادة مميزة
            if len(username) <= 8:
                return True
            
            # كلمات تشير إلى المجموعات المميزة
            premium_keywords = ['vip', 'premium', 'gold', 'elite', 'exclusive', 'private']
            if any(keyword in username.lower() for keyword in premium_keywords):
                return True
    
    return False

# ======================
# Export Utilities
# ======================

def format_links_for_export(links: List[str], platform: str = None, link_type: str = None) -> str:
    """تنسيق الروابط للتصدير"""
    if not links:
        return ""
    
    header = []
    if platform:
        header.append(f"المنصة: {platform}")
    if link_type:
        header.append(f"النوع: {link_type}")
    header.append(f"العدد: {len(links)}")
    header.append(f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    output = "# " + " | ".join(header) + "\n"
    output += "#" * 60 + "\n\n"
    
    for i, url in enumerate(links, 1):
        output += f"{url}\n"
    
    return output

def group_links_by_type(links: List[str]) -> Dict[str, List[str]]:
    """تجميع الروابط حسب النوع"""
    grouped = {
        'telegram_public_groups': [],
        'telegram_private_groups': [],
        'whatsapp_groups': [],
        'other': []
    }
    
    for url in links:
        analysis = analyze_link(url)
        
        if not analysis['is_valid'] or not analysis['should_collect']:
            continue
        
        platform = analysis['platform']
        link_type = analysis['link_type']
        
        if platform == 'telegram':
            if link_type == 'public_group':
                grouped['telegram_public_groups'].append(url)
            elif link_type == 'private_group':
                grouped['telegram_private_groups'].append(url)
        
        elif platform == 'whatsapp' and link_type == 'group':
            grouped['whatsapp_groups'].append(url)
        
        else:
            grouped['other'].append(url)
    
    return grouped

# ======================
# Test Functions
# ======================

def test_link_analysis():
    """اختبار تحليل الروابط"""
    test_urls = [
        "https://t.me/test_group",
        "https://t.me/+ABC123def",
        "https://t.me/channel_news",
        "https://chat.whatsapp.com/ABC123def",
        "https://wa.me/966501234567",
        "https://t.me/c/1234567890",
        "https://t.me/test_bot",
        "https://facebook.com/groups/test",
        "https://t.me/group_vip",
        "https://t.me/arabic_chat_group"
    ]
    
    print("🔍 اختبار تحليل الروابط...")
    print("=" * 80)
    
    for url in test_urls:
        analysis = analyze_link(url)
        
        print(f"\n📌 الرابط: {url}")
        print(f"   📱 المنصة: {analysis['platform']}")
        print(f"   🏷️  النوع: {analysis['link_type']}")
        print(f"   ✅ صالح: {analysis['is_valid']}")
        print(f"   🤖 يجب الجمع: {analysis['should_collect']}")
        print(f"   📝 السبب: {analysis['reason']}")
        
        if analysis['details']:
            print(f"   🔍 التفاصيل: {analysis['details']}")
    
    print("\n" + "=" * 80)
    
    # اختبار دفعة
    print("\n📊 تحليل دفعة من الروابط...")
    batch_results = analyze_links_batch(test_urls)
    
    print(f"   📈 الإجمالي: {batch_results['total']}")
    print(f"   ✅ الصالحة: {batch_results['valid']}")
    print(f"   ❌ غير الصالحة: {batch_results['invalid']}")
    print(f"   ⏭️  المتجاهلة: {batch_results['ignored']}")
    print(f"   🎯 للجمع: {batch_results['to_collect']}")
    
    print(f"\n   📱 حسب المنصة:")
    for platform, count in batch_results['by_platform'].items():
        print(f"      • {platform}: {count}")
    
    print(f"\n   🏷️  حسب النوع:")
    for link_type, count in batch_results['by_type'].items():
        print(f"      • {link_type}: {count}")

# ======================
# Main Entry Point
# ======================

if __name__ == "__main__":
    import sys
    
    print("🔧 تشغيل اختبار link_utils.py...")
    print("⚡ هذا الملف يوفر أدوات تحليل وتصنيف الروابط")
    
    # اختبار الدوال الأساسية
    test_url = "https://t.me/test_group"
    
    print(f"\n📌 مثال على الرابط: {test_url}")
    
    normalized = normalize_url(test_url)
    print(f"   🔄 تطبيع: {normalized}")
    
    url_hash = get_url_hash(test_url)
    print(f"   🔐 الـ Hash: {url_hash}")
    
    platform = detect_platform(test_url)
    print(f"   📱 المنصة: {platform}")
    
    is_group, group_type = is_telegram_group_link(test_url)
    print(f"   👥 مجموعة تيليجرام: {is_group} ({group_type})")
    
    is_channel = is_telegram_channel_link(test_url)
    print(f"   📢 قناة تيليجرام: {is_channel}")
    
    # تحليل شامل
    analysis = analyze_link(test_url)
    print(f"\n🔍 التحليل الشامل:")
    for key, value in analysis.items():
        if isinstance(value, dict) and value:
            print(f"   📊 {key}:")
            for k, v in value.items():
                print(f"      • {k}: {v}")
        elif value:
            print(f"   📊 {key}: {value}")
    
    # تشغيل اختبار كامل
    print("\n" + "=" * 80)
    test_link_analysis()
    
    print("\n✅ اختبار link_utils.py اكتمل بنجاح!")
