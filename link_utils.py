import re
import logging
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urlparse, parse_qs
import hashlib
from datetime import datetime

from config import (
    IGNORED_PATTERNS, BLACKLISTED_DOMAINS,
    TELEGRAM_PUBLIC_GROUP_PATTERNS, TELEGRAM_PRIVATE_GROUP_PATTERNS,
    WHATSAPP_LINK_PATTERNS
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
    """التحقق من صحة تنسيق الرابط (بدون تطبيع داخلي)"""
    if not url or not isinstance(url, str):
        return False
    
    url = url.strip()
    
    # تحقق من التنسيق الأساسي
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}'  # domain
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
            
            username = username.lower()
            
            # تصفية أسماء غير صالحة
            if username == 'c':  # روابط القنوات t.me/c/123456
                return None
            if len(username) < 2:  # أسماء قصيرة جداً
                return None
            
            return username
    
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
            invite_hash = match.group(1)
            if len(invite_hash) >= 5:  # تأكد أنه hash صالح
                return invite_hash
    
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
            message_id = match.group(1)
            if message_id.isdigit():
                return message_id
    
    return None

def is_telegram_public_group_link(url: str) -> Tuple[bool, str]:
    """التحقق مما إذا كان الرابط مجموعة تيليجرام عامة مع مستوى الثقة"""
    # الأنماط المباشرة = ثقة عالية
    for pattern in TELEGRAM_PUBLIC_GROUP_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True, 'high'
    
    # الأنماط العامة = ثقة متوسطة
    if re.match(r'^https?://t\.me/[A-Za-z0-9_]+$', url, re.IGNORECASE):
        username = extract_telegram_username(url)
        if username and len(username) >= 3:
            return True, 'medium'
    
    return False, ''

def is_telegram_private_group_link(url: str) -> Tuple[bool, str]:
    """التحقق مما إذا كان الرابط مجموعة تيليجرام خاصة مع مستوى الثقة"""
    # الأنماط المباشرة = ثقة عالية
    for pattern in TELEGRAM_PRIVATE_GROUP_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True, 'high'
    
    # روابط الدعوة = ثقة متوسطة
    invite_hash = extract_telegram_invite_hash(url)
    if invite_hash and len(invite_hash) >= 10:
        return True, 'medium'
    
    return False, ''

def classify_telegram_link(url: str) -> Tuple[str, Dict, str]:
    """تصنيف رابط تيليجرام مع تفاصيل ومستوى الثقة"""
    details = {}
    
    # 1. تحقق من طلب الانضمام أولاً - ثقة عالية
    invite_hash = extract_telegram_invite_hash(url)
    if invite_hash:
        details['invite_hash'] = invite_hash
        details['confidence'] = 'high'
        return 'join_request', details, 'high'
    
    # 2. تحقق من المجموعات الخاصة - ثقة متوسطة إلى عالية
    is_private, confidence = is_telegram_private_group_link(url)
    if is_private:
        if invite_hash:
            details['invite_hash'] = invite_hash
        details['confidence'] = confidence
        return 'private_group', details, confidence
    
    # 3. تحقق من المجموعات العامة - ثقة متوسطة إلى عالية
    is_public, confidence = is_telegram_public_group_link(url)
    if is_public:
        username = extract_telegram_username(url)
        if username:
            details['username'] = username
        details['confidence'] = confidence
        return 'public_group', details, confidence
    
    # 4. أي حالة أخرى - ثقة منخفضة أو غير معروفة
    username = extract_telegram_username(url)
    if username:
        details['username'] = username
    
    message_id = extract_telegram_message_id(url)
    if message_id:
        details['message_id'] = message_id
    
    return 'unknown', details, 'low'

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
            group_id = match.group(1)
            if len(group_id) >= 5:  # تأكد أنه ID صالح
                return group_id
    
    return None

def extract_whatsapp_phone_number(url: str) -> Optional[str]:
    """استخراج رقم الهاتف من رابط واتساب"""
    pattern = r'wa\.me/([0-9]+)'
    match = re.search(pattern, url, re.IGNORECASE)
    
    if match:
        phone = match.group(1)
        # تنظيف الرقم
        phone = re.sub(r'[^0-9]', '', phone)
        if len(phone) >= 8:  # تأكد أنه رقم صالح
            return phone
    
    return None

def is_whatsapp_group_link(url: str) -> Tuple[bool, str]:
    """التحقق مما إذا كان الرابط مجموعة واتساب مع مستوى الثقة"""
    for pattern in WHATSAPP_LINK_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            # تأكد أنه ليس رابط هاتف
            if 'wa.me/' in url and re.match(r'https?://wa\.me/[0-9]+', url, re.IGNORECASE):
                return False, ''
            
            group_id = extract_whatsapp_group_id(url)
            if group_id:
                # روابط مع ID واضح = ثقة عالية
                if len(group_id) >= 10:
                    return True, 'high'
                else:
                    return True, 'medium'
    
    return False, ''

def classify_whatsapp_link(url: str) -> Tuple[str, Dict, str]:
    """تصنيف رابط واتساب مع تفاصيل ومستوى الثقة"""
    details = {}
    
    # 1. تحقق من المجموعات - ثقة متوسطة إلى عالية
    is_group, confidence = is_whatsapp_group_link(url)
    if is_group:
        group_id = extract_whatsapp_group_id(url)
        if group_id:
            details['group_id'] = group_id
        details['confidence'] = confidence
        return 'group', details, confidence
    
    # 2. تحقق من روابط الهاتف - ثقة عالية
    phone_number = extract_whatsapp_phone_number(url)
    if phone_number:
        details['phone_number'] = phone_number
        return 'phone', details, 'high'
    
    return 'unknown', details, 'low'

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
        'can_verify': False,
        'confidence': 'low',
        'ignored': False,
        'ignore_reason': ''
        # لا يوجد 'reason' هنا - فقط للفشل
    }
    
    try:
        # تطبيع الرابط (مرة واحدة فقط)
        normalized = normalize_url(url)
        result['normalized_url'] = normalized
        result['url_hash'] = hashlib.md5(normalized.encode()).hexdigest()
        
        # التحقق من الصحة الأساسية (بدون تطبيع داخلي)
        if not is_valid_url(url):  # نستخدم url الأصلية للتحقق
            result['is_valid'] = False
            return result
        
        # التحقق مما إذا كان يجب تجاهله
        ignored, ignore_reason = is_url_ignored(normalized)
        if ignored:
            result['is_valid'] = True  # صالح لكن ممنوع
            result['ignored'] = True
            result['ignore_reason'] = ignore_reason
            return result
        
        result['is_valid'] = True
        
        # اكتشاف المنصة
        platform = detect_platform(normalized)
        result['platform'] = platform
        
        # تصنيف حسب المنصة
        if platform == 'telegram':
            link_type, details, confidence = classify_telegram_link(normalized)
            result['link_type'] = link_type
            result['details'] = details
            result['confidence'] = confidence
            
            # تحديد إذا كان يمكن التحقق منه
            if link_type in ['public_group', 'private_group', 'join_request']:
                result['can_verify'] = True
            else:
                result['can_verify'] = False
        
        elif platform == 'whatsapp':
            link_type, details, confidence = classify_whatsapp_link(normalized)
            result['link_type'] = link_type
            result['details'] = details
            result['confidence'] = confidence
            
            # تحديد إذا كان يمكن التحقق منه
            if link_type == 'group':
                result['can_verify'] = True
            else:
                result['can_verify'] = False
        
        else:
            # منصات أخرى غير قابلة للتحقق
            result['can_verify'] = False
            result['confidence'] = 'low'
        
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing link {url}: {e}")
        # عند الخطأ، نرجع النتيجة الأساسية مع is_valid = False
        result['is_valid'] = False
        return result

def analyze_links_batch(urls: List[str]) -> Dict:
    """تحليل مجموعة من الروابط دفعة واحدة"""
    results = {
        'total': len(urls),
        'valid': 0,
        'invalid': 0,
        'ignored': 0,
        'can_verify': 0,
        'by_platform': {},
        'by_type': {},
        'by_confidence': {'high': 0, 'medium': 0, 'low': 0},
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
            
            if analysis['can_verify']:
                results['can_verify'] += 1
            
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
            
            # إحصائيات الثقة
            confidence = analysis.get('confidence', 'low')
            if confidence in results['by_confidence']:
                results['by_confidence'][confidence] += 1
    
    return results

# ======================
# Link Filtering
# ======================

def filter_links_by_verifiability(urls: List[str], min_confidence: str = 'low') -> Tuple[List[Dict], Dict]:
    """تصفية الروابط حسب قابلية التحقق ومستوى الثقة"""
    verifiable = []
    stats = {
        'total': len(urls),
        'verifiable': 0,
        'ignored': 0,
        'invalid': 0,
        'telegram': 0,
        'whatsapp': 0,
        'by_confidence': {'high': 0, 'medium': 0, 'low': 0},
        'ignored_reasons': {}
    }
    
    # ترتيب مستويات الثقة
    confidence_levels = {'high': 3, 'medium': 2, 'low': 1}
    min_level = confidence_levels.get(min_confidence, 1)
    
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
        
        # التحقق من قابلية التحقق ومستوى الثقة
        if analysis['can_verify']:
            confidence = analysis.get('confidence', 'low')
            confidence_value = confidence_levels.get(confidence, 0)
            
            if confidence_value >= min_level:
                verifiable.append(analysis)
                stats['verifiable'] += 1
                
                # إحصائيات الثقة
                if confidence in stats['by_confidence']:
                    stats['by_confidence'][confidence] += 1
                
                if analysis['platform'] == 'telegram':
                    stats['telegram'] += 1
                elif analysis['platform'] == 'whatsapp':
                    stats['whatsapp'] += 1
    
    return verifiable, stats

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
        
        # التحقق من الصحة الأساسية (بدون تطبيع داخلي)
        if not is_valid_url(url):
            continue
        
        # التحقق من التكرار
        url_hash = hashlib.md5(normalized.encode()).hexdigest()
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
        r'[A-Za-z]{2,63}'  # TLD
        r'(?:[/\w .?=&%-]*)?',  # path and query
        re.IGNORECASE
    )
    
    urls = url_pattern.findall(text)
    return clean_url_list(urls)

# ======================
# Test Functions
# ======================

def test_link_analysis():
    """اختبار تحليل الروابط"""
    test_urls = [
        "https://t.me/test_group",
        "https://t.me/+ABC123def",
        "https://t.me/c/123456",  # رابط قناة
        "https://chat.whatsapp.com/ABC123def",
        "https://wa.me/966501234567",
        "https://t.me/test_group/123",  # رابط رسالة
        "https://t.me/a",  # رابط قصير جداً
        "https://t.me/very_long_username_test_here",  # اسم طويل
        "https://t.me/+inv",  # invite قصير جداً
        "https://facebook.com/groups/test"  # منصة أخرى
    ]
    
    print("🔍 اختبار تحليل الروابط...")
    print("=" * 80)
    
    for url in test_urls:
        analysis = analyze_link(url)
        
        print(f"\n📌 الرابط: {url}")
        print(f"   📱 المنصة: {analysis['platform']}")
        print(f"   🏷️  النوع: {analysis['link_type']}")
        print(f"   ✅ صالح: {analysis['is_valid']}")
        print(f"   🔍 قابل للتحقق: {analysis['can_verify']}")
        print(f"   ⭐ الثقة: {analysis.get('confidence', 'N/A')}")
        
        if analysis['ignored']:
            print(f"   ⏭️  متجاهل: {analysis.get('ignore_reason', 'N/A')}")
        
        if analysis['details']:
            print(f"   🔍 التفاصيل: {analysis['details']}")
    
    print("\n" + "=" * 80)
    
    # اختبار دفعة مع تصفية
    print("\n📊 تحليل دفعة من الروابط...")
    verifiable_links, stats = filter_links_by_verifiability(test_urls, 'medium')
    
    print(f"   📈 الإجمالي: {stats['total']}")
    print(f"   ✅ صالحة للتحقق: {stats['verifiable']}")
    print(f"   ❌ غير صالحة: {stats['invalid']}")
    print(f"   ⏭️  متجاهلة: {stats['ignored']}")
    
    print(f"\n   📱 حسب المنصة:")
    print(f"      • تليجرام: {stats['telegram']}")
    print(f"      • واتساب: {stats['whatsapp']}")
    
    print(f"\n   ⭐ حسب الثقة:")
    for conf_level, count in stats['by_confidence'].items():
        if count > 0:
            print(f"      • {conf_level}: {count}")
    
    # اختبار link_utils مع bot.py
    print("\n" + "=" * 80)
    print("🎯 كيف يستخدمها bot.py:")
    print("=" * 80)
    
    example_url = "https://t.me/test_group"
    analysis = analyze_link(example_url)
    
    print(f"\nالرابط: {example_url}")
    print(f"يمكن لـ bot.py أن:")
    
    if analysis['can_verify']:
        print(f"1. استخدام can_verify = {analysis['can_verify']} للمتابعة")
        print(f"2. استخدام confidence = {analysis['confidence']} لترتيب الأولويات")
        print(f"3. تمرير details إلى Telethon للتحقق: {analysis['details']}")
        print(f"4. القرار النهائي في bot.py بناءً على نتيجة Telethon")
    else:
        print(f"1. تجاهل الرابط (can_verify = False)")
        print(f"2. الثقة: {analysis.get('confidence', 'N/A')}")
        if analysis['ignored']:
            print(f"3. السبب: {analysis.get('ignore_reason', 'N/A')}")

# ======================
# Main Entry Point
# ======================

if __name__ == "__main__":
    print("🔧 تشغيل اختبار link_utils.py...")
    print("⚡ هذا الملف يوفر أدوات تحليل وتصنيف الروابط")
    
    # اختبار الدوال الأساسية
    print("\n" + "=" * 80)
    test_link_analysis()
    
    print("\n✅ اختبار link_utils.py اكتمل بنجاح!")
