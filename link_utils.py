import re
from typing import List, Set
from telethon.tl.types import Message

URL_REGEX = re.compile(r"(https?://[^\s<>\"]+)", re.IGNORECASE)

PLATFORM_PATTERNS = {
    "telegram": re.compile(r"(t\.me|telegram\.me)", re.IGNORECASE),
    "whatsapp": re.compile(r"(wa\.me|chat\.whatsapp\.com)", re.IGNORECASE),
}

TG_PATTERNS = {
    "channel": re.compile(r"https?://t\.me/([A-Za-z0-9_]+)$", re.I),
    "private_group": re.compile(r"https?://t\.me/joinchat/([A-Za-z0-9_-]+)", re.I),
    "public_group": re.compile(r"https?://t\.me/\+([A-Za-z0-9]+)", re.I),
    "bot": re.compile(r"https?://t\.me/([A-Za-z0-9_]+)bot(\?|$)", re.I),
    "message": re.compile(r"https?://t\.me/(c/)?([A-Za-z0-9_]+)/(\d+)", re.I),
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

def classify_platform(url: str) -> str:
    url_lower = url.lower()
    for platform, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(url_lower):
            return platform
    return "other"

def classify_telegram_link(url: str) -> str:
    url_lower = url.lower()
    
    for link_type, pattern in TG_PATTERNS.items():
        if pattern.search(url_lower):
            return link_type
    
    parsed_url = url_lower.split('//')[-1].split('/')[-1]
    if parsed_url.startswith('joinchat/'):
        return "private_group"
    elif parsed_url.startswith('+'):
        return "public_group"
    elif parsed_url.endswith('bot'):
        return "bot"
    elif any(char.isdigit() for char in parsed_url) and len(parsed_url) > 5:
        return "message"
    elif re.match(r'^[A-Za-z0-9_]+$', parsed_url):
        return "channel"
    
    return "unknown"
