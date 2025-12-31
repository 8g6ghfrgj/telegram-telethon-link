import os
import tempfile
import logging
import asyncio
from typing import List, Set, Dict, Optional
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.types import Message

from config import EXPORT_DIR
from link_utils import URL_REGEX, clean_link, is_allowed_link

# ======================
# Logging Configuration
# ======================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# Constants
# ======================

# الملفات المدعومة وامتداداتها
SUPPORTED_EXTENSIONS = {
    '.pdf': 'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.txt': 'text/plain',
    '.rtf': 'application/rtf',
    '.odt': 'application/vnd.oasis.opendocument.text',
    '.csv': 'text/csv',
    '.html': 'text/html',
    '.htm': 'text/html',
    '.xml': 'text/xml',
    '.json': 'application/json',
}

# الحد الأقصى لحجم الملف (50 ميجابايت)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# حجم الكتلة للقراءة
CHUNK_SIZE = 1024 * 1024  # 1MB

# ======================
# Helper Functions
# ======================

def is_file_supported(filename: str, mime_type: str = None) -> bool:
    """
    التحقق مما إذا كان نوع الملف مدعومًا
    
    Args:
        filename: اسم الملف
        mime_type: نوع MIME (اختياري)
        
    Returns:
        bool: True إذا كان الملف مدعومًا
    """
    if not filename:
        return False
    
    # الحصول على امتداد الملف
    file_ext = os.path.splitext(filename.lower())[1]
    
    # التحقق من الامتداد
    if file_ext in SUPPORTED_EXTENSIONS:
        return True
    
    # التحقق من نوع MIME
    if mime_type and mime_type in SUPPORTED_EXTENSIONS.values():
        return True
    
    return False

def get_file_extension(filename: str) -> str:
    """
    الحصول على امتداد الملف
    
    Args:
        filename: اسم الملف
        
    Returns:
        str: امتداد الملف
    """
    return os.path.splitext(filename.lower())[1]

# ======================
# Main Extraction Function
# ======================

async def extract_links_from_file(
    client: TelegramClient,
    message: Message
) -> List[str]:
    """
    استخراج الروابط من ملفات متنوعة
    
    Args:
        client: عميل Telethon
        message: رسالة تحتوي على ملف
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    if not message or not message.file:
        logger.debug("No file in message")
        return []
    
    # التحقق من حجم الملف
    file_size = message.file.size or 0
    if file_size > MAX_FILE_SIZE:
        logger.warning(f"File too large: {file_size} bytes (max: {MAX_FILE_SIZE})")
        return []
    
    filename = message.file.name or "unknown_file"
    mime_type = message.file.mime_type or ""
    
    # التحقق مما إذا كان الملف مدعومًا
    if not is_file_supported(filename, mime_type):
        logger.debug(f"Unsupported file type: {filename} ({mime_type})")
        return []
    
    links: Set[str] = set()
    
    try:
        logger.info(f"Processing file: {filename} ({file_size} bytes)")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # إنشاء مسار للملف المؤقت
            temp_path = os.path.join(tmpdir, filename)
            
            # تحميل الملف
            logger.debug(f"Downloading file to: {temp_path}")
            await client.download_media(message, temp_path)
            
            # استخراج الروابط حسب نوع الملف
            file_ext = get_file_extension(filename)
            
            if file_ext == '.pdf' or mime_type == 'application/pdf':
                file_links = await extract_from_pdf_async(temp_path)
            elif file_ext == '.docx' or 'wordprocessingml.document' in mime_type:
                file_links = await extract_from_docx_async(temp_path)
            elif file_ext == '.txt' or mime_type == 'text/plain':
                file_links = await extract_from_txt_async(temp_path)
            elif file_ext == '.rtf' or mime_type == 'application/rtf':
                file_links = await extract_from_rtf_async(temp_path)
            elif file_ext == '.odt' or 'opendocument.text' in mime_type:
                file_links = await extract_from_odt_async(temp_path)
            elif file_ext in ['.html', '.htm'] or 'text/html' in mime_type:
                file_links = await extract_from_html_async(temp_path)
            elif file_ext == '.xml' or 'text/xml' in mime_type:
                file_links = await extract_from_xml_async(temp_path)
            elif file_ext == '.json' or 'application/json' in mime_type:
                file_links = await extract_from_json_async(temp_path)
            elif file_ext == '.csv' or 'text/csv' in mime_type:
                file_links = await extract_from_csv_async(temp_path)
            else:
                # محاولة استخراج كملف نصي عام
                file_links = await extract_generic_text_async(temp_path)
            
            # تنظيف وفلترة الروابط
            for link in file_links:
                cleaned = clean_link(link)
                if cleaned and is_allowed_link(cleaned):
                    links.add(cleaned)
            
            logger.info(f"Extracted {len(links)} links from file: {filename}")
            
            return list(links)
            
    except Exception as e:
        logger.error(f"Error extracting links from file {filename}: {e}")
        return []

# ======================
# PDF Extraction
# ======================

async def extract_from_pdf_async(path: str) -> List[str]:
    """
    استخراج الروابط من ملف PDF بشكل غير متزامن
    
    Args:
        path: مسار ملف PDF
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    try:
        # تشغيل في thread منفصل لتجنب حظر event loop
        return await asyncio.get_event_loop().run_in_executor(
            None, extract_from_pdf_sync, path
        )
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return []

def extract_from_pdf_sync(path: str) -> List[str]:
    """
    استخراج النص من ملف PDF (متزامن)
    
    Args:
        path: مسار ملف PDF
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    links: Set[str] = set()
    
    try:
        # محاولة استخدام PyPDF2 أولاً
        try:
            from PyPDF2 import PdfReader
            
            reader = PdfReader(path)
            logger.debug(f"PDF has {len(reader.pages)} pages")
            
            for page_num, page in enumerate(reader.pages, 1):
                try:
                    text = page.extract_text() or ""
                    if text:
                        page_links = URL_REGEX.findall(text)
                        links.update(page_links)
                        logger.debug(f"Page {page_num}: Found {len(page_links)} links")
                except Exception as e:
                    logger.warning(f"Error extracting text from PDF page {page_num}: {e}")
                    continue
            
            if links:
                logger.info(f"PyPDF2 extracted {len(links)} links from PDF")
                return list(links)
            
        except ImportError:
            logger.warning("PyPDF2 is not installed")
        except Exception as e:
            logger.warning(f"PyPDF2 failed: {e}")
        
        # محاولة استخدام pdfplumber كبديل
        try:
            import pdfplumber
            
            with pdfplumber.open(path) as pdf:
                logger.debug(f"pdfplumber opened PDF with {len(pdf.pages)} pages")
                
                for page_num, page in enumerate(pdf.pages, 1):
                    try:
                        text = page.extract_text() or ""
                        if text:
                            page_links = URL_REGEX.findall(text)
                            links.update(page_links)
                    except Exception as e:
                        logger.warning(f"Error extracting text with pdfplumber page {page_num}: {e}")
                        continue
                
                if links:
                    logger.info(f"pdfplumber extracted {len(links)} links from PDF")
                    return list(links)
                
        except ImportError:
            logger.warning("pdfplumber is not installed")
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e}")
        
        # محاولة القراءة المباشرة كملف نصي ثنائي
        try:
            with open(path, 'rb') as f:
                content = f.read()
                
                # البحث عن أنماط URLs في البيانات الثنائية
                import re
                url_pattern = rb'https?://[^\x00-\x1F\x7F-\xFF<>"\s]+'
                binary_matches = re.findall(url_pattern, content)
                
                for match in binary_matches:
                    try:
                        url = match.decode('utf-8', errors='ignore')
                        links.add(url)
                    except:
                        pass
                
                if binary_matches:
                    logger.info(f"Binary search found {len(binary_matches)} URL patterns")
                    
        except Exception as e:
            logger.warning(f"Binary extraction failed: {e}")
    
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
    
    return list(links)

# ======================
# DOCX Extraction
# ======================

async def extract_from_docx_async(path: str) -> List[str]:
    """
    استخراج الروابط من ملف DOCX بشكل غير متزامن
    
    Args:
        path: مسار ملف DOCX
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, extract_from_docx_sync, path
        )
    except Exception as e:
        logger.error(f"DOCX extraction error: {e}")
        return []

def extract_from_docx_sync(path: str) -> List[str]:
    """
    استخراج النص من ملف DOCX (متزامن)
    
    Args:
        path: مسار ملف DOCX
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    links: Set[str] = set()
    
    try:
        from docx import Document
        
        doc = Document(path)
        logger.debug(f"DOCX document opened")
        
        # استخراج من الفقرات
        for para_num, para in enumerate(doc.paragraphs, 1):
            if para.text:
                para_links = URL_REGEX.findall(para.text)
                links.update(para_links)
                if para_links:
                    logger.debug(f"Paragraph {para_num}: Found {len(para_links)} links")
        
        # استخراج من الجداول
        for table_num, table in enumerate(doc.tables, 1):
            for row_num, row in enumerate(table.rows, 1):
                for cell_num, cell in enumerate(row.cells, 1):
                    if cell.text:
                        cell_links = URL_REGEX.findall(cell.text)
                        links.update(cell_links)
                        if cell_links:
                            logger.debug(f"Table {table_num}, Row {row_num}, Cell {cell_num}: Found {len(cell_links)} links")
        
        # استخراج من الرؤوس والتذييلات
        for section in doc.sections:
            # الرأس
            header = section.header
            if header:
                for para in header.paragraphs:
                    if para.text:
                        links.update(URL_REGEX.findall(para.text))
            
            # التذييل
            footer = section.footer
            if footer:
                for para in footer.paragraphs:
                    if para.text:
                        links.update(URL_REGEX.findall(para.text))
        
        logger.info(f"Extracted {len(links)} links from DOCX")
        return list(links)
    
    except ImportError:
        logger.warning("python-docx is not installed")
        return []
    except Exception as e:
        logger.error(f"DOCX extraction failed: {e}")
        return []

# ======================
# Text File Extraction
# ======================

async def extract_from_txt_async(path: str) -> List[str]:
    """
    استخراج الروابط من ملف نصي
    
    Args:
        path: مسار الملف النصي
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, extract_from_txt_sync, path
        )
    except Exception as e:
        logger.error(f"TXT extraction error: {e}")
        return []

def extract_from_txt_sync(path: str) -> List[str]:
    """
    استخراج النص من ملف نصي (متزامن)
    
    Args:
        path: مسار الملف النصي
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    links: Set[str] = set()
    
    try:
        # محاولة فتح الملف بتشفيرات مختلفة
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1256', 'windows-1256', 'ascii']
        
        for encoding in encodings:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    # قراءة الملف بشكل متقطع للكفاءة
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        
                        chunk_links = URL_REGEX.findall(chunk)
                        links.update(chunk_links)
                
                logger.info(f"Successfully read TXT with {encoding} encoding")
                break  # نجح، توقف عن المحاولة
                
            except UnicodeDecodeError:
                logger.debug(f"Failed with encoding {encoding}")
                continue
            except Exception as e:
                logger.warning(f"Error reading with encoding {encoding}: {e}")
                continue
        
        logger.info(f"Extracted {len(links)} links from TXT")
        return list(links)
    
    except Exception as e:
        logger.error(f"TXT extraction failed: {e}")
        return []

# ======================
# RTF Extraction
# ======================

async def extract_from_rtf_async(path: str) -> List[str]:
    """
    استخراج الروابط من ملف RTF
    
    Args:
        path: مسار ملف RTF
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, extract_from_rtf_sync, path
        )
    except Exception as e:
        logger.error(f"RTF extraction error: {e}")
        return []

def extract_from_rtf_sync(path: str) -> List[str]:
    """
    استخراج النص من ملف RTF (متزامن)
    
    Args:
        path: مسار ملف RTF
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    links: Set[str] = set()
    
    try:
        # محاولة استخدام striprtf
        try:
            from striprtf.striprtf import rtf_to_text
            
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                rtf_content = f.read()
                text_content = rtf_to_text(rtf_content)
                links.update(URL_REGEX.findall(text_content))
            
            logger.info(f"striprtf extracted {len(links)} links from RTF")
            return list(links)
        
        except ImportError:
            logger.warning("striprtf is not installed, trying basic extraction")
            
            # استخراج بسيط باستخدام regex
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
                # البحث عن نص بين أقواس في RTF
                import re
                
                # البحث عن نص غير تنسيقي
                text_matches = re.findall(r'\\\'(..)|(\\u\d+)|([a-zA-Z0-9\s,.!?:/=+_-]+)', content)
                
                extracted_text = ' '.join([''.join(match) for match in text_matches])
                links.update(URL_REGEX.findall(extracted_text))
                
                # البحث المباشر عن URLs
                links.update(URL_REGEX.findall(content))
            
            logger.info(f"Basic extraction found {len(links)} links in RTF")
            return list(links)
    
    except Exception as e:
        logger.error(f"RTF extraction failed: {e}")
        return []

# ======================
# ODT Extraction
# ======================

async def extract_from_odt_async(path: str) -> List[str]:
    """
    استخراج الروابط من ملف ODT
    
    Args:
        path: مسار ملف ODT
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, extract_from_odt_sync, path
        )
    except Exception as e:
        logger.error(f"ODT extraction error: {e}")
        return []

def extract_from_odt_sync(path: str) -> List[str]:
    """
    استخراج النص من ملف ODT (متزامن)
    
    Args:
        path: مسار ملف ODT
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    links: Set[str] = set()
    
    try:
        # ODT هو ملف ZIP يحتوي على XML
        import zipfile
        from xml.etree import ElementTree as ET
        
        with zipfile.ZipFile(path, 'r') as odt_file:
            # قراءة محتوى المستند
            content_xml = odt_file.read('content.xml')
            
            # تحليل XML
            namespaces = {
                'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
                'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0'
            }
            
            root = ET.fromstring(content_xml)
            
            # استخراج النص من جميع عناصر النص
            for elem in root.findall('.//text:p', namespaces):
                if elem.text:
                    links.update(URL_REGEX.findall(elem.text))
            
            for elem in root.findall('.//text:span', namespaces):
                if elem.text:
                    links.update(URL_REGEX.findall(elem.text))
            
            logger.info(f"Extracted {len(links)} links from ODT")
            return list(links)
    
    except Exception as e:
        logger.error(f"ODT extraction failed: {e}")
        return []

# ======================
# HTML Extraction
# ======================

async def extract_from_html_async(path: str) -> List[str]:
    """
    استخراج الروابط من ملف HTML
    
    Args:
        path: مسار ملف HTML
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, extract_from_html_sync, path
        )
    except Exception as e:
        logger.error(f"HTML extraction error: {e}")
        return []

def extract_from_html_sync(path: str) -> List[str]:
    """
    استخراج النص من ملف HTML (متزامن)
    
    Args:
        path: مسار ملف HTML
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    links: Set[str] = set()
    
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
            # البحث عن جميع الروابط في HTML
            import re
            
            # روابط في سمة href
            href_pattern = r'href=[\'"]?([^\'" >]+)[\'"]?'
            href_matches = re.findall(href_pattern, content, re.IGNORECASE)
            links.update(href_matches)
            
            # روابط في سمة src
            src_pattern = r'src=[\'"]?([^\'" >]+)[\'"]?'
            src_matches = re.findall(src_pattern, content, re.IGNORECASE)
            links.update(src_matches)
            
            # روابط نصية عادية
            links.update(URL_REGEX.findall(content))
        
        logger.info(f"Extracted {len(links)} links from HTML")
        return list(links)
    
    except Exception as e:
        logger.error(f"HTML extraction failed: {e}")
        return []

# ======================
# XML Extraction
# ======================

async def extract_from_xml_async(path: str) -> List[str]:
    """
    استخراج الروابط من ملف XML
    
    Args:
        path: مسار ملف XML
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, extract_from_xml_sync, path
        )
    except Exception as e:
        logger.error(f"XML extraction error: {e}")
        return []

def extract_from_xml_sync(path: str) -> List[str]:
    """
    استخراج النص من ملف XML (متزامن)
    
    Args:
        path: مسار ملف XML
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    links: Set[str] = set()
    
    try:
        import xml.etree.ElementTree as ET
        
        tree = ET.parse(path)
        root = tree.getroot()
        
        # استخراج النص من جميع العناصر
        def extract_text(element):
            text_parts = []
            
            if element.text:
                text_parts.append(element.text)
            
            for child in element:
                text_parts.extend(extract_text(child))
            
            if element.tail:
                text_parts.append(element.tail)
            
            return text_parts
        
        all_text_parts = extract_text(root)
        full_text = ' '.join(all_text_parts)
        
        links.update(URL_REGEX.findall(full_text))
        
        logger.info(f"Extracted {len(links)} links from XML")
        return list(links)
    
    except Exception as e:
        logger.error(f"XML extraction failed: {e}")
        return []

# ======================
# JSON Extraction
# ======================

async def extract_from_json_async(path: str) -> List[str]:
    """
    استخراج الروابط من ملف JSON
    
    Args:
        path: مسار ملف JSON
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, extract_from_json_sync, path
        )
    except Exception as e:
        logger.error(f"JSON extraction error: {e}")
        return []

def extract_from_json_sync(path: str) -> List[str]:
    """
    استخراج النص من ملف JSON (متزامن)
    
    Args:
        path: مسار ملف JSON
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    links: Set[str] = set()
    
    try:
        import json
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # تحويل JSON إلى نص للبحث عن الروابط
        json_text = json.dumps(data)
        links.update(URL_REGEX.findall(json_text))
        
        # البحث المتعمق في الهياكل المتداخلة
        def find_urls_in_structure(obj):
            if isinstance(obj, str):
                links.update(URL_REGEX.findall(obj))
            elif isinstance(obj, dict):
                for value in obj.values():
                    find_urls_in_structure(value)
            elif isinstance(obj, list):
                for item in obj:
                    find_urls_in_structure(item)
        
        find_urls_in_structure(data)
        
        logger.info(f"Extracted {len(links)} links from JSON")
        return list(links)
    
    except Exception as e:
        logger.error(f"JSON extraction failed: {e}")
        return []

# ======================
# CSV Extraction
# ======================

async def extract_from_csv_async(path: str) -> List[str]:
    """
    استخراج الروابط من ملف CSV
    
    Args:
        path: مسار ملف CSV
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, extract_from_csv_sync, path
        )
    except Exception as e:
        logger.error(f"CSV extraction error: {e}")
        return []

def extract_from_csv_sync(path: str) -> List[str]:
    """
    استخراج النص من ملف CSV (متزامن)
    
    Args:
        path: مسار ملف CSV
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    links: Set[str] = set()
    
    try:
        import csv
        
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            # محاولة قراءة بتنسيقات مختلفة
            for delimiter in [',', ';', '\t', '|']:
                try:
                    reader = csv.reader(f, delimiter=delimiter)
                    
                    for row in reader:
                        for cell in row:
                            if cell:
                                links.update(URL_REGEX.findall(cell))
                    
                    # إذا وصلنا إلى هنا، كان التنسيق صحيحًا
                    logger.info(f"CSV read successfully with delimiter '{delimiter}'")
                    break
                    
                except:
                    # إعادة تعيين المؤشر لبداية الملف
                    f.seek(0)
                    continue
        
        # إذا فشلت جميع المحاولات، قراءة كملف نصي
        if not links:
            f.seek(0)
            content = f.read()
            links.update(URL_REGEX.findall(content))
        
        logger.info(f"Extracted {len(links)} links from CSV")
        return list(links)
    
    except Exception as e:
        logger.error(f"CSV extraction failed: {e}")
        return []

# ======================
# Generic Text Extraction
# ======================

async def extract_generic_text_async(path: str) -> List[str]:
    """
    استخراج نص عام من أي ملف
    
    Args:
        path: مسار الملف
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, extract_generic_text_sync, path
        )
    except Exception as e:
        logger.error(f"Generic text extraction error: {e}")
        return []

def extract_generic_text_sync(path: str) -> List[str]:
    """
    استخراج نص عام (متزامن)
    
    Args:
        path: مسار الملف
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    links: Set[str] = set()
    
    try:
        # محاولة قراءة الملف كنص ثنائي
        with open(path, 'rb') as f:
            content = f.read()
            
            # محاولة فك التشفير كنص
            try:
                text = content.decode('utf-8', errors='ignore')
                links.update(URL_REGEX.findall(text))
            except:
                # البحث مباشرة عن أنماط URLs في البيانات الثنائية
                import re
                url_pattern = rb'https?://[^\x00-\x1F\x7F-\xFF<>"\s]+'
                binary_matches = re.findall(url_pattern, content)
                
                for match in binary_matches:
                    try:
                        url = match.decode('utf-8', errors='ignore')
                        links.add(url)
                    except:
                        pass
        
        logger.info(f"Generic extraction found {len(links)} links")
        return list(links)
    
    except Exception as e:
        logger.error(f"Generic text extraction failed: {e}")
        return []

# ======================
# Batch Processing
# ======================

async def extract_links_from_files_batch(
    client: TelegramClient,
    messages: List[Message]
) -> Dict[str, List[str]]:
    """
    استخراج الروابط من مجموعة من الملفات
    
    Args:
        client: عميل Telethon
        messages: قائمة بالرسائل التي تحتوي على ملفات
        
    Returns:
        dict: نتائج الاستخراج
    """
    results = {}
    
    for message in messages:
        try:
            filename = message.file.name or "unknown_file"
            links = await extract_links_from_file(client, message)
            
            if links:
                results[filename] = links
                logger.info(f"Extracted {len(links)} links from {filename}")
            
        except Exception as e:
            logger.error(f"Error processing file in batch: {e}")
    
    return results

# ======================
# Export Functions
# ======================

def save_extracted_links(filename: str, links: List[str]) -> str:
    """
    حفظ الروابط المستخرجة إلى ملف
    
    Args:
        filename: اسم الملف الأصلي
        links: قائمة الروابط
        
    Returns:
        str: مسار الملف المحفوظ
    """
    try:
        if not links:
            return ""
        
        # إنشاء اسم للملف المحفوظ
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(filename))[0]
        export_filename = f"{base_name}_links_{timestamp}.txt"
        
        # إنشاء مسار التصدير
        export_path = os.path.join(EXPORT_DIR, "file_extractions")
        os.makedirs(export_path, exist_ok=True)
        
        # المسار الكامل
        full_path = os.path.join(export_path, export_filename)
        
        # كتابة الروابط إلى الملف
        with open(full_path, 'w', encoding='utf-8') as f:
            for link in links:
                f.write(link + "\n")
        
        logger.info(f"Saved {len(links)} links to {full_path}")
        return full_path
    
    except Exception as e:
        logger.error(f"Error saving extracted links: {e}")
        return ""

# ======================
# Test Functions
# ======================

async def test_file_extractors():
    """
    اختبار جميع وظائف استخراج الملفات
    """
    print("\n" + "="*50)
    print("🧪 Testing File Extractors Module")
    print("="*50)
    
    # اختبار دعم الملفات
    print("\n1. Testing file support:")
    test_files = [
        "document.pdf",
        "data.docx",
        "notes.txt",
        "file.rtf",
        "document.odt",
        "page.html",
        "data.xml",
        "config.json",
        "data.csv",
        "unknown.xyz"
    ]
    
    for filename in test_files:
        supported = is_file_supported(filename)
        status = "✅" if supported else "❌"
        print(f"   {status} {filename}: {supported}")
    
    # اختبار استخراج النص من ملفات نصية
    print("\n2. Testing text extraction:")
    
    # إنشاء ملف نصي اختباري
    test_content = """
    Here are some test links:
    Telegram: https://t.me/test_channel
    WhatsApp: https://chat.whatsapp.com/abc123
    Another: https://t.me/joinchat/def456
    """
    
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(test_content)
        temp_file = f.name
    
    try:
        # اختبار استخراج من ملف نصي
        links = await extract_from_txt_async(temp_file)
        print(f"   📄 TXT extraction: Found {len(links)} links")
        for link in links:
            print(f"      • {link}")
    
    finally:
        # تنظيف الملف المؤقت
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    print("\n" + "="*50)
    print("✅ File Extractors test completed successfully!")
    print("="*50)

# ======================
# Main Test
# ======================

if __name__ == "__main__":
    import asyncio
    
    # تشغيل الاختبار
    asyncio.run(test_file_extractors())
