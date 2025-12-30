import re
import tempfile
from typing import List
from telethon import TelegramClient
from telethon.tl.types import Message

URL_REGEX = re.compile(r"(https?://[^\s]+)", re.I)

async def extract_links_from_file(client: TelegramClient, message: Message) -> List[str]:
    if not message.file:
        return []

    links = set()

    with tempfile.TemporaryDirectory() as tmp:
        path = await client.download_media(message.file, file=tmp)
        if not path:
            return []

        try:
            with open(path, "r", errors="ignore") as f:
                content = f.read()
                for url in URL_REGEX.findall(content):
                    links.add(url.strip())
        except Exception:
            pass

    return list(links)
