import re
import asyncio
import aiohttp
from urllib.parse import urlparse
from typing import List, Dict, Tuple, Optional

# ==================================================
# Regex
# ==================================================

URL_REGEX = re.compile(
    r"(https?://[^\s<>\"]+)",
    re.IGNORECASE
)

# ==================================================
# Domains
# ==================================================

TELEGRAM_DOMAINS = ("t.me", "telegram.me")
WHATSAPP_DOMAIN = "chat.whatsapp.com"

# ==================================================
# Telegram patterns (المسموح فقط)
# ==================================================

TG_CHANNEL_OR_GROUP = re.compile(
    r"^https?://t\.me/[A-Za-z0-9_]+$",
    re.IGNORECASE
)

TG_PRIVATE_GROUP = re.compile(
    r"^https?://t\.me/\+[A-Za-z0-9_-]+$",
    re.IGNORECASE
)

# ❌ مرفوض
TG_MESSAGE = re.compile(r"/\d+$")
TG_BOT = re.compile(r"bot(\?|$)", re.IGNORECASE)

# ==================================================
# Cleaning
# ==================================================

def clean_link(url: str) -> str:
    if not url:
        return ""

    url = url.strip()
    url = url.replace("*", "")
    url = url.replace(" ", "")
    url = url.replace("\n", "")

    # إزالة الزوائد
    url = re.sub(r"[^\w:/\.\-\+\?=&]", "", url)

    # توحيد t.me
    if url.startswith("http://"):
        url = url.replace("http://", "https://", 1)

    if "telegram.me" in url:
        url = url.replace("telegram.me", "t.me")

    return url.rstrip("/")


# ==================================================
# Platform
# ==================================================

def classify_platform(url: str) -> Optional[str]:
    u = url.lower()

    if any(d in u for d in TELEGRAM_DOMAINS):
        return "telegram"

    if WHATSAPP_DOMAIN in u:
        return "whatsapp"

    return None


# ==================================================
# Allow rules
# ==================================================

def is_allowed_link(url: str) -> bool:
    if not url or len(url) < 10:
        return False

    platform = classify_platform(url)
    if not platform:
        return False

    # WhatsApp
    if platform == "whatsapp":
        return WHATSAPP_DOMAIN in url.lower()

    # Telegram
    if platform == "telegram":
        u = url.lower()

        # ❌ منع البوتات
        if TG_BOT.search(u):
            return False

        # ❌ منع روابط الرسائل
        if TG_MESSAGE.search(u):
            return False

        # ✅ قناة أو مجموعة عامة
        if TG_CHANNEL_OR_GROUP.match(u):
            return True

        # ✅ مجموعة خاصة
        if TG_PRIVATE_GROUP.match(u):
            return True

    return False


# ==================================================
# Telegram classification
# ==================================================

def classify_telegram_link(url: str) -> str:
    u = url.lower()

    if TG_PRIVATE_GROUP.match(u):
        return "private_group"

    if TG_CHANNEL_OR_GROUP.match(u):
        return "channel_or_group"

    return "unknown"


# ==================================================
# Extract links from text
# ==================================================

def extract_links_from_text(text: str) -> List[str]:
    if not text:
        return []

    links = set()
    for raw in URL_REGEX.findall(text):
        cleaned = clean_link(raw)
        if cleaned and is_allowed_link(cleaned):
            links.add(cleaned)

    return list(links)


# ==================================================
# Verify links (نشط / ميت)
# ==================================================

async def _verify_http(session: aiohttp.ClientSession, url: str) -> bool:
    try:
        async with session.get(url, timeout=10, allow_redirects=True) as resp:
            return resp.status in (200, 301, 302)
    except Exception:
        return False


async def verify_link(url: str) -> Tuple[bool, str, str, Dict]:
    platform = classify_platform(url)
    if not platform:
        return False, "unknown", "invalid", {}

    async with aiohttp.ClientSession() as session:
        is_alive = await _verify_http(session, url)

    if not is_alive:
        return False, platform, "dead", {}

    if platform == "telegram":
        link_type = classify_telegram_link(url)
        return True, platform, link_type, {}

    if platform == "whatsapp":
        return True, platform, "group", {}

    return False, "unknown", "invalid", {}


# ==================================================
# Batch verify
# ==================================================

async def verify_links_batch(urls: List[str]) -> List[Dict]:
    if not urls:
        return []

    semaphore = asyncio.Semaphore(5)
    results = []

    async def worker(u):
        async with semaphore:
            ok, platform, link_type, meta = await verify_link(u)
            return {
                "url": u,
                "is_valid": ok,
                "platform": platform,
                "link_type": link_type,
                "metadata": meta
            }

    tasks = [worker(u) for u in urls]
    for res in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(res, dict):
            results.append(res)

    return results
