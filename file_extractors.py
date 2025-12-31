import os
import tempfile
from typing import List, Set
from telethon import TelegramClient
from telethon.tl.types import Message
from link_utils import URL_REGEX, clean_link, is_allowed_link

SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt'}
MAX_FILE_SIZE = 50 * 1024 * 1024

async def extract_links_from_file(client: TelegramClient, message: Message) -> List[str]:
    if not message.file or message.file.size > MAX_FILE_SIZE:
        return []
    
    filename = message.file.name or "file"
    file_ext = os.path.splitext(filename.lower())[1]
    
    if file_ext not in SUPPORTED_EXTENSIONS:
        return []
    
    links: Set[str] = set()
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, filename)
            await client.download_media(message, path)
            
            if file_ext == '.pdf':
                file_links = _extract_from_pdf(path)
            elif file_ext == '.docx':
                file_links = _extract_from_docx(path)
            elif file_ext == '.txt':
                file_links = _extract_from_txt(path)
            else:
                return []
            
            for link in file_links:
                cleaned = clean_link(link)
                if cleaned and is_allowed_link(cleaned):
                    links.add(cleaned)
            
            return list(links)
            
    except:
        return []

def _extract_from_pdf(path: str) -> List[str]:
    links = set()
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(path)
        for page in reader.pages:
            text = page.extract_text() or ""
            links.update(URL_REGEX.findall(text))
    except:
        pass
    return list(links)

def _extract_from_docx(path: str) -> List[str]:
    links = set()
    try:
        from docx import Document
        doc = Document(path)
        for para in doc.paragraphs:
            links.update(URL_REGEX.findall(para.text))
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    links.update(URL_REGEX.findall(cell.text))
    except:
        pass
    return list(links)

def _extract_from_txt(path: str) -> List[str]:
    links = set()
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            links.update(URL_REGEX.findall(content))
    except:
        pass
    return list(links)
