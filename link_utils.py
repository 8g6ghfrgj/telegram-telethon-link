import re
import asyncio
import aiohttp
from typing import List, Dict, Tuple, Optional
from urllib.parse import urlparse, urlunparse

from config import VERIFY_LINKS, VERIFY_TIMEOUT


# ==================================================
# Regex
# ==================================================

URL_REGEX = re.compile(
    r"(https?://[^\s<>\"]+)",
    re.IGNORECASE
)

TG_DOMAIN_REGEX = re.compile(r"(t\.me|telegram\.me)", re.I)
WA_GROUP_REGEX = re.compile(r"chat\.whatsapp\.com/([A-Za-z0-9]+)", re.I)
WA_ME_REGEX = re.compile(r"wa\.me/", re.I)


# ==================================================
# تنظيف الرابط
# ==================================================

def clean_link(url: str) -> Optional[str]:
    if not url:
        return None

    url = url.strip().replace("*", "").replace(" ", "")

    # إزالة الرموز الغريبة
    url = re.sub(r'^[^\w]+', '', url)
    url = re.sub(r'[^\w/]+$', '', url)

    # توحيد http / https
    if url.startswith("http://"):
        url = url.replace("http://", "https://", 1)

    return url


# ==================================================
# توحيد الرابط (منع التكرار)
# ==================================================

def normalize_link(url: str) -> Optional[str]:
    """
    يجعل كل الروابط التي تؤدي لنفس المجموعة متطابقة
    """
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")

        # Telegram
        if TG_DOMAIN_REGEX.search(parsed.netloc):
            return f"https://t.me{path}"

        # WhatsApp groups
        if WA_GROUP_REGEX.search(url):
            code = WA_GROUP_REGEX.search(url).group(1)
            return f"https://chat.whatsapp.com/{code}"

        return None
    except Exception:
        return None


# ==================================================
# تحديد المنصة
# ==================================================

def classify_platform(url: str) -> Optional[str]:
    if TG_DOMAIN_REGEX.search(url):
        return "telegram"
    if WA_GROUP_REGEX.search(url):
        return "whatsapp"
    return None


# ==================================================
# تصنيف روابط Telegram (بدون رسائل وبوتات)
# ==================================================

def classify_telegram_link(url: str) -> Optional[str]:
    """
    يرجع:
    - channel
    - public_group
    - private_group
    """
    path = urlparse(url).path.strip("/")

    # استبعاد روابط الرسائل
    if re.search(r"/\d+$", path):
        return None

    # استبعاد البوتات
    if path.endswith("bot"):
        return None

    if path.startswith("+") or "joinchat" in path:
        return "private_group"

    if re.match(r"^[A-Za-z0-9_]+$", path):
        return "channel_or_public_group"

    return None


# ==================================================
# فلترة الرابط (القانون النهائي)
# ==================================================

def is_allowed_link(url: str) -> bool:
    if not url:
        return False

    # رفض wa.me
    if WA_ME_REGEX.search(url):
        return False

    platform = classify_platform(url)
    if platform == "telegram":
        return classify_telegram_link(url) is not None

    if platform == "whatsapp":
        return True

    return False


# ==================================================
# استخراج الروابط من الرسالة
# ==================================================

def extract_links_from_text(text: str) -> List[str]:
    if not text:
        return []

    found = set()

    for raw in URL_REGEX.findall(text):
        cleaned = clean_link(raw)
        if not cleaned:
            continue

        normalized = normalize_link(cleaned)
        if normalized and is_allowed_link(normalized):
            found.add(normalized)

    return list(found)


# ==================================================
# فحص الروابط (نشط / ميت)
# ==================================================

async def verify_link(url: str) -> bool:
    if not VERIFY_LINKS:
        return True

    try:
        timeout = aiohttp.ClientTimeout(total=VERIFY_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, allow_redirects=True) as response:
                return response.status == 200
    except Exception:
        return False


async def verify_links_batch(urls: List[str]) -> List[str]:
    """
    يرجع فقط الروابط النشطة
    """
    semaphore = asyncio.Semaphore(5)
    valid = []

    async def check(url):
        async with semaphore:
            if await verify_link(url):
                valid.append(url)

    tasks = [check(url) for url in urls]
    await asyncio.gather(*tasks, return_exceptions=True)
    return valid
