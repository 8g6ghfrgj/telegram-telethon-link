import re
from urllib.parse import urlparse, quote
from typing import List, Tuple, Optional
import config

class LinkProcessor:
    @staticmethod
    def clean_link(link: str) -> str:
        """
        تنظيف الرابط من المسافات والرموز غير المرغوبة
        
        Args:
            link: الرابط الخام
            
        Returns:
            str: الرابط النظيف
        """
        if not link:
            return ""
        
        # إزالة المسافات من البداية والنهاية
        link = link.strip()
        
        # إزالة الرموز الخاصة غير المرغوبة
        link = re.sub(r'[<>()\[\]{}"\'*]', '', link)
        
        # إزالة المسافات الداخلية المتعددة
        link = re.sub(r'\s+', '', link)
        
        # إزالة البادئات الشائعة
        prefixes = [
            'joinchat/', '+', 'https://', 'http://', 
            'www.', 't.me/', 'telegram.me/', '@'
        ]
        
        for prefix in prefixes:
            if link.startswith(prefix):
                link = link[len(prefix):]
        
        # التحقق وإضافة البروتوكول إذا لزم
        if not link.startswith(('http://', 'https://')):
            if any(domain in link for domain in config.WHATSAPP_DOMAINS + config.TELEGRAM_DOMAINS):
                link = f"https://{link}"
        
        return link
    
    @staticmethod
    def extract_links(text: str) -> List[str]:
        """
        استخراج جميع الروابط من النص
        
        Args:
            text: النص الخام
            
        Returns:
            list: قائمة الروابط المستخرجة
        """
        if not text:
            return []
        
        # نمط للعثور على الروابط
        url_pattern = r'(https?://[^\s<>"\'()]+|t\.me/[^\s<>"\'()]+|telegram\.me/[^\s<>"\'()]+|chat\.whatsapp\.com/[^\s<>"\'()]+|wa\.me/[^\s<>"\'()]+)'
        
        matches = re.findall(url_pattern, text)
        
        # تنظيف الروابط
        cleaned_links = []
        for match in matches:
            cleaned = LinkProcessor.clean_link(match)
            if cleaned:
                cleaned_links.append(cleaned)
        
        return list(set(cleaned_links))  # إزالة التكرارات
    
    @staticmethod
    def categorize_link(link: str) -> Tuple[str, str]:
        """
        تصنيف الرابط حسب المنصة والنوع
        
        Args:
            link: الرابط
            
        Returns:
            tuple: (platform, link_type)
        """
        link_lower = link.lower()
        
        # فحص روابط الواتساب أولاً
        for domain in config.WHATSAPP_DOMAINS:
            if domain in link_lower:
                if 'chat.whatsapp.com' in link_lower:
                    return 'whatsapp', 'group'
                elif 'wa.me' in link_lower:
                    return 'whatsapp', 'phone'
                else:
                    return 'whatsapp', 'group'
        
        # فحص روابط التليجرام
        for domain in config.TELEGRAM_DOMAINS:
            if domain in link_lower:
                # أنماط روابط التليجرام
                if '+' in link_lower or 'joinchat' in link_lower:
                    return 'telegram', 'private_group'
                elif '/c/' in link_lower or '/channel/' in link_lower:
                    return 'telegram', 'channel'
                elif '/bot' in link_lower or 'bot=' in link_lower:
                    return 'telegram', 'bot'
                elif re.search(r't\.me/\w+/\d+', link_lower):
                    return 'telegram', 'message'
                else:
                    # يمكن أن تكون مجموعة عامة أو قناة
                    return 'telegram', 'public_group'
        
        return 'unknown', 'unknown'
    
    @staticmethod
    def is_valid_telegram_link(link: str) -> bool:
        """التحقق من صحة رابط التليجرام"""
        link = link.lower()
        
        # التحقق من النطاقات
        if not any(domain in link for domain in config.TELEGRAM_DOMAINS):
            return False
        
        # تحليل الرابط
        try:
            parsed = urlparse(link)
            path = parsed.path.strip('/')
            
            if not path:
                return False
            
            # الأنماط المقبولة:
            # t.me/username
            # t.me/username/123 (رسالة)
            # t.me/c/123456789 (قناة خاصة)
            # t.me/joinchat/ABCDEF (مجموعة خاصة)
            
            pattern = r'^[a-zA-Z0-9_]+(/[a-zA-Z0-9_]+)?$'
            return bool(re.match(pattern, path))
            
        except:
            return False
    
    @staticmethod
    def is_valid_whatsapp_link(link: str) -> bool:
        """التحقق من صحة رابط الواتساب"""
        link = link.lower()
        
        if not any(domain in link for domain in config.WHATSAPP_DOMAINS):
            return False
        
        try:
            parsed = urlparse(link)
            
            if 'chat.whatsapp.com' in link:
                # يجب أن يحتوي على مسار
                path = parsed.path.strip('/')
                return len(path) > 0
            elif 'wa.me' in link:
                # رابط رقم واتساب
                path = parsed.path.strip('/')
                return path.isdigit()
            
            return True
            
        except:
            return False
    
    @staticmethod
    def normalize_link(link: str) -> str:
        """
        توحيد تنسيق الرابط
        
        Args:
            link: الرابط
            
        Returns:
            str: الرابط الموحد
        """
        link = LinkProcessor.clean_link(link)
        
        if not link:
            return ""
        
        # إضافة https:// إذا لم تكن موجودة
        if not link.startswith(('http://', 'https://')):
            link = f"https://{link}"
        
        # إزالة المسارات الزائدة
        try:
            parsed = urlparse(link)
            
            # للواتساب: إزالة الاستعلامات غير الضرورية
            if 'whatsapp.com' in parsed.netloc:
                parsed = parsed._replace(query='', fragment='')
                link = parsed.geturl()
            
            # للتليجرام: إزالة القيم غير الضرورية
            elif 't.me' in parsed.netloc or 'telegram.me' in parsed.netloc:
                # إزالة الاستعلامات التي لا تؤثر على المحتوى
                if 'start' in parsed.query:
                    parsed = parsed._replace(query='')
                    link = parsed.geturl()
        
        except:
            pass
        
        return link.rstrip('/')
    
    @staticmethod
    def get_link_display_name(link: str) -> str:
        """
        الحصول على اسم عرضي للرابط
        
        Args:
            link: الرابط
            
        Returns:
            str: الاسم العرضي
        """
        try:
            parsed = urlparse(link)
            path = parsed.path.strip('/')
            
            if not path:
                return link
            
            # للتليجرام
            if 't.me' in parsed.netloc or 'telegram.me' in parsed.netloc:
                if path.startswith('c/'):
                    return f"قناة: {path[2:]}"
                elif path.startswith('joinchat/'):
                    return f"مجموعة خاصة"
                elif '/' in path:
                    parts = path.split('/')
                    return f"@{parts[0]} - رسالة"
                else:
                    return f"@{path}"
            
            # للواتساب
            elif 'chat.whatsapp.com' in parsed.netloc:
                return "مجموعة واتساب"
            elif 'wa.me' in parsed.netloc:
                return f"واتساب: {path}"
            
            return link
            
        except:
            return link

# وظائف للمساعدة (للتوافق مع الكود القديم)
def clean_link(link: str) -> str:
    """وظيفة مساعدة لتنظيف الرابط"""
    return LinkProcessor.clean_link(link)

def extract_links(text: str) -> List[str]:
    """وظيفة مساعدة لاستخراج الروابط"""
    return LinkProcessor.extract_links(text)

def is_valid_link(link: str) -> bool:
    """التحقق من صحة الرابط"""
    return (LinkProcessor.is_valid_telegram_link(link) or 
            LinkProcessor.is_valid_whatsapp_link(link))
