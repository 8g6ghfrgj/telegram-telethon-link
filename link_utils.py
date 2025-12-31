import re
from typing import List, Optional, Tuple, Dict
from telethon.tl.types import Message

from config import VERIFY_LINKS, BLACKLISTED_DOMAINS

URL_REGEX = re.compile(r"(https?://[^\s<>\"]+)", re.IGNORECASE)

PLATFORM_PATTERNS = {
    "telegram": re.compile(r"(t\.me|telegram\.me)", re.IGNORECASE),
    "whatsapp": re.compile(r"(wa\.me|chat\.whatsapp\.com)", re.IGNORECASE),
}

def clean_link(url: str) -> str:
    if not url:
        return ""
    cleaned = url.strip().replace('*', '').replace(' ', '')
    cleaned = re.sub(r'^[^a-zA-Z0-9]+', '', cleaned)
    cleaned = re.sub(r'[^a-zA-Z0-9]+$', '', cleaned)
    return cleaned

def extract_links_from_message(message: Message) -> List[str]:
    links = set()
    
    text = message.text or message.message or ""
    if text:
        for url in URL_REGEX.findall(text):
            cleaned = clean_link(url)
            if cleaned:
                links.add(cleaned)
    
    if hasattr(message, 'caption') and message.caption:
        for url in URL_REGEX.findall(message.caption):
            cleaned = clean_link(url)
            if cleaned:
                links.add(cleaned)
    
    if hasattr(message, 'reply_markup') and message.reply_markup:
        for row in message.reply_markup.rows:
            for button in row.buttons:
                if hasattr(button, "url") and button.url:
                    cleaned = clean_link(button.url)
                    if cleaned:
                        links.add(cleaned)
    
    return list(links)

def is_allowed_link(url: str) -> bool:
    if not url or len(url) < 10:
        return False
    
    for blacklisted in BLACKLISTED_DOMAINS:
        if blacklisted in url:
            return False
    
    platform = classify_platform(url)
    return platform in ["telegram", "whatsapp"]

def classify_platform(url: str) -> str:
    url_lower = url.lower()
    
    for platform, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(url_lower):
            return platform
    
    return "other"

def classify_telegram_link(url: str) -> str:
    url_lower = url.lower()
    
    if re.search(r"t\.me/joinchat/", url_lower):
        return "private_group"
    elif re.search(r"t\.me/\+", url_lower):
        return "public_group"
    elif re.search(r"t\.me/.*bot(\?|$)", url_lower):
        return "bot"
    elif re.search(r"t\.me/(c/)?.*/\d+", url_lower):
        return "message"
    elif re.search(r"t\.me/[A-Za-z0-9_]+$", url_lower):
        return "channel"
    
    return "unknown"

async def verify_links_batch(urls: List[str]) -> List[Dict]:
    if not VERIFY_LINKS or not urls:
        return []
    
    results = []
    for url in urls:
        platform = classify_platform(url)
        if platform == "telegram":
            link_type = classify_telegram_link(url)
        elif platform == "whatsapp":
            link_type = "group" if "chat.whatsapp.com" in url else "phone"
        else:
            link_type = "other"
        
        results.append({
            'url': url,
            'is_valid': True,
            'platform': platform,
            'link_type': link_type,
            'metadata': {}
        })
    
    return results
