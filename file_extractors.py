import os
import re
import tempfile
import logging
import asyncio
from typing import List, Set, Dict, Optional
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.types import Message

from config import BASE_DIR
from link_utils import extract_links_from_text, clean_link, is_allowed_link

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

# الملفات المدعومة
SUPPORTED_EXTENSIONS = {
    '.pdf': 'PDF Document',
    '.docx': 'Word Document',
    '.txt': 'Text File',
    '.rtf': 'Rich Text Format',
    '.odt': 'OpenDocument Text',
    '.doc': 'Old Word Document',
}

# أنواع MIME المدعومة
SUPPORTED_MIME_TYPES = {
    'application/pdf': 'PDF',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
    'application/msword': 'DOC',
    'text/plain': 'TXT',
    'application/rtf': 'RTF',
    'application/vnd.oasis.opendocument.text': 'ODT',
}

# الحد الأقصى لحجم الملف (50 ميجابايت)
MAX_FILE_SIZE = 50 * 1024 * 1024

# الحد الأدنى لحجم الملف (100 بايت)
MIN_FILE_SIZE = 100

# أنماط الملفات غير المدعومة
UNSUPPORTED_PATTERNS = [
    r'\.exe$', r'\.dll$', r'\.bat$', r'\.sh$', r'\.py$',
    r'\.zip$', r'\.rar$', r'\.7z$', r'\.tar$', r'\.gz$',
]

# ======================
# Helper Functions
# ======================

def is_file_supported(filename: str, mime_type: str = None) -> bool:
    """
    التحقق مما إذا كان نوع الملف مدعوماً
    
    Args:
        filename: اسم الملف
        mime_type: نوع MIME (اختياري)
        
    Returns:
        bool: True إذا كان الملف مدعوماً
    """
    if not filename:
        return False
    
    # التحقق من الأنماط غير المدعومة
    filename_lower = filename.lower()
    for pattern in UNSUPPORTED_PATTERNS:
        if re.search(pattern, filename_lower):
            return False
    
    # التحقق من الامتداد
    file_ext = os.path.splitext(filename_lower)[1]
    if file_ext in SUPPORTED_EXTENSIONS:
        return True
    
    # التحقق من نوع MIME
    if mime_type and mime_type in SUPPORTED_MIME_TYPES:
        return True
    
    return False

def is_file_size_valid(file_size: int) -> bool:
    """
    التحقق من حجم الملف
    
    Args:
        file_size: حجم الملف بالبايت
        
    Returns:
        bool: True إذا كان الحجم مقبولاً
    """
    if not file_size:
        return False
    
    return MIN_FILE_SIZE <= file_size <= MAX_FILE_SIZE

def get_file_type(filename: str, mime_type: str = None) -> str:
    """
    الحصول على نوع الملف
    
    Args:
        filename: اسم الملف
        mime_type: نوع MIME
        
    Returns:
        str: نوع الملف
    """
    if not filename:
        return "unknown"
    
    filename_lower = filename.lower()
    file_ext = os.path.splitext(filename_lower)[1]
    
    if file_ext in SUPPORTED_EXTENSIONS:
        return SUPPORTED_EXTENSIONS[file_ext]
    
    if mime_type and mime_type in SUPPORTED_MIME_TYPES:
        return SUPPORTED_MIME_TYPES[mime_type]
    
    return "unknown"

# ======================
# Main Extraction Function
# ======================

async def extract_links_from_file(
    client: TelegramClient,
    message: Message
) -> List[str]:
    """
    استخراج الروابط من ملف
    
    Args:
        client: عميل Telethon
        message: رسالة تحتوي على ملف
        
    Returns:
        list: قائمة بالروابط المستخرجة
    """
    if not message or not message.file:
        logger.debug("No file in message")
        return []
    
    try:
        filename = message.file.name or "unknown"
        file_size = message.file.size or 0
        mime_type = message.file.mime_type or ""
        
        logger.info(f"Processing file: {filename} ({file_size} bytes, {mime_type})")
        
        # التحقق من دعم الملف
        if not is_file_supported(filename, mime_type):
            logger.warning(f"Unsupported file type: {filename} ({mime_type})")
            return []
        
        # التحقق من حجم الملف
        if not is_file_size_valid(file_size):
            logger.warning(f"Invalid file size: {file_size} bytes")
            return []
        
        file_type = get_file_type(filename, mime_type)
        logger.info(f"Extracting from {file_type}: {filename}")
        
        # استخراج الروابط حسب نوع الملف
        links = await _extract_by_file_type(client, message, filename, file_type)
        
        logger.info(f"Extracted {len(links)} links from {filename}")
        return links
        
    except Exception as e:
        logger.error(f"Error extracting links from file: {e}")
        return []

async def _extract_by_file_type(
    client: TelegramClient,
    message: Message,
    filename: str,
    file_type: str
) -> List[str]:
    """
    استخراج الروابط حسب نوع الملف
    
    Args:
        client: عميل Telethon
        message: الرسالة
        filename: اسم الملف
        file_type: نوع الملف
        
    Returns:
        list: قائمة بالروابط
    """
    filename_lower = filename.lower()
    
    if filename_lower.endswith('.pdf') or file_type == 'PDF':
        return await _extract_from_pdf(client, message)
    
    elif filename_lower.endswith('.docx') or file_type in ['DOCX', 'Word Document']:
        return await _extract_from_docx(client, message)
    
    elif filename_lower.endswith('.doc') or file_type == 'DOC':
        return await _extract_from_doc(client, message)
    
    elif filename_lower.endswith('.txt') or file_type == 'TXT':
        return await _extract_from_txt(client, message)
    
    elif filename_lower.endswith('.rtf') or file_type == 'RTF':
        return await _extract_from_rtf(client, message)
    
    elif filename_lower.endswith('.odt') or file_type == 'ODT':
        return await _extract_from_odt(client, message)
    
    else:
        # محاولة الاستخراج كملف نصي عام
        return await _extract_generic(client, message)

# ======================
# PDF Extraction
# ======================

async def _extract_from_pdf(client: TelegramClient, message: Message) -> List[str]:
    """
    استخراج الروابط من ملف PDF
    
    Args:
        client: عميل Telethon
        message: الرسالة
        
    Returns:
        list: قائمة بالروابط
    """
    links = set()
    
    try:
        # محاولة استخدام PyPDF2
        try:
            links.update(await _extract_from_pdf_pypdf2(client, message))
        except ImportError:
            logger.warning("PyPDF2 not installed")
        except Exception as e:
            logger.warning(f"PyPDF2 failed: {e}")
        
        # إذا لم نحصل على روابط، نجرب pdfplumber
        if not links:
            try:
                links.update(await _extract_from_pdf_pdfplumber(client, message))
            except ImportError:
                logger.warning("pdfplumber not installed")
            except Exception as e:
                logger.warning(f"pdfplumber failed: {e}")
        
        # فلترة الروابط
        return _filter_links(list(links))
        
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return []

async def _extract_from_pdf_pypdf2(client: TelegramClient, message: Message) -> List[str]:
    """
    استخراج من PDF باستخدام PyPDF2
    """
    links = set()
    
    try:
        from PyPDF2 import PdfReader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "document.pdf")
            await client.download_media(message, filepath)
            
            reader = PdfReader(filepath)
            
            for page_num, page in enumerate(reader.pages, 1):
                try:
                    text = page.extract_text() or ""
                    if text:
                        page_links = extract_links_from_text(text)
                        links.update(page_links)
                        
                        # استخراج من التعليقات التوضيحية (Annotations)
                        if hasattr(page, 'annotations') and page.annotations:
                            for annotation in page.annotations:
                                if hasattr(annotation, 'get') and annotation.get('/A'):
                                    uri = annotation['/A'].get('/URI')
                                    if uri:
                                        links.add(uri)
                except Exception as e:
                    logger.warning(f"Error extracting from PDF page {page_num}: {e}")
                    continue
        
        return list(links)
        
    except Exception as e:
        raise e

async def _extract_from_pdf_pdfplumber(client: TelegramClient, message: Message) -> List[str]:
    """
    استخراج من PDF باستخدام pdfplumber
    """
    links = set()
    
    try:
        import pdfplumber
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "document.pdf")
            await client.download_media(message, filepath)
            
            with pdfplumber.open(filepath) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    try:
                        # استخراج النص
                        text = page.extract_text() or ""
                        if text:
                            page_links = extract_links_from_text(text)
                            links.update(page_links)
                        
                        # استخراج الروابط (Hyperlinks)
                        if hasattr(page, 'hyperlinks'):
                            for link in page.hyperlinks:
                                if link and hasattr(link, 'uri'):
                                    links.add(link.uri)
                    except Exception as e:
                        logger.warning(f"Error extracting from PDF page {page_num} with pdfplumber: {e}")
                        continue
        
        return list(links)
        
    except Exception as e:
        raise e

# ======================
# DOCX Extraction
# ======================

async def _extract_from_docx(client: TelegramClient, message: Message) -> List[str]:
    """
    استخراج الروابط من ملف DOCX
    
    Args:
        client: عميل Telethon
        message: الرسالة
        
    Returns:
        list: قائمة بالروابط
    """
    links = set()
    
    try:
        from docx import Document
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "document.docx")
            await client.download_media(message, filepath)
            
            doc = Document(filepath)
            
            # استخراج من الفقرات
            for para in doc.paragraphs:
                if para.text:
                    para_links = extract_links_from_text(para.text)
                    links.update(para_links)
            
            # استخراج من الجداول
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text:
                            cell_links = extract_links_from_text(cell.text)
                            links.update(cell_links)
            
            # استخراج من الرؤوس والتذييلات
            for section in doc.sections:
                # الرأس
                header = section.header
                if header:
                    for para in header.paragraphs:
                        if para.text:
                            header_links = extract_links_from_text(para.text)
                            links.update(header_links)
                
                # التذييل
                footer = section.footer
                if footer:
                    for para in footer.paragraphs:
                        if para.text:
                            footer_links = extract_links_from_text(para.text)
                            links.update(footer_links)
            
            # استخراج من الروابط التشعبية
            try:
                # البحث عن جميع العناصر التي قد تحتوي على روابط
                for element in doc.element.iter():
                    if element.tag.endswith('}hyperlink'):
                        # الحصول على الرابط من السمة
                        for attr in element.attrib:
                            if 'href' in attr.lower():
                                link_url = element.attrib[attr]
                                if link_url:
                                    links.add(link_url)
            except:
                pass
        
        return _filter_links(list(links))
        
    except ImportError:
        logger.warning("python-docx not installed")
        return []
    except Exception as e:
        logger.error(f"DOCX extraction error: {e}")
        return []

# ======================
# DOC Extraction (Old Word Format)
# ======================

async def _extract_from_doc(client: TelegramClient, message: Message) -> List[str]:
    """
    استخراج الروابط من ملف DOC (التنسيق القديم)
    
    Args:
        client: عميل Telethon
        message: الرسالة
        
    Returns:
        list: قائمة بالروابط
    """
    try:
        # محاولة تحويل DOC إلى DOCX أو استخراج كملف نصي
        return await _extract_generic(client, message)
        
    except Exception as e:
        logger.error(f"DOC extraction error: {e}")
        return []

# ======================
# Text File Extraction
# ======================

async def _extract_from_txt(client: TelegramClient, message: Message) -> List[str]:
    """
    استخراج الروابط من ملف نصي
    
    Args:
        client: عميل Telethon
        message: الرسالة
        
    Returns:
        list: قائمة بالروابط
    """
    links = set()
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "document.txt")
            await client.download_media(message, filepath)
            
            # محاولة فتح الملف بتشفيرات مختلفة
            encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1256', 'windows-1256', 'ascii']
            
            for encoding in encodings:
                try:
                    with open(filepath, 'r', encoding=encoding, errors='ignore') as f:
                        content = f.read()
                        file_links = extract_links_from_text(content)
                        links.update(file_links)
                    break  # نجح، توقف عن المحاولة
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    logger.warning(f"Failed to read with encoding {encoding}: {e}")
                    continue
        
        return _filter_links(list(links))
        
    except Exception as e:
        logger.error(f"TXT extraction error: {e}")
        return []

# ======================
# RTF Extraction
# ======================

async def _extract_from_rtf(client: TelegramClient, message: Message) -> List[str]:
    """
    استخراج الروابط من ملف RTF
    
    Args:
        client: عميل Telethon
        message: الرسالة
        
    Returns:
        list: قائمة بالروابط
    """
    links = set()
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "document.rtf")
            await client.download_media(message, filepath)
            
            # محاولة استخدام striprtf
            try:
                from striprtf.striprtf import rtf_to_text
                
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    rtf_content = f.read()
                    text_content = rtf_to_text(rtf_content)
                    file_links = extract_links_from_text(text_content)
                    links.update(file_links)
                    
            except ImportError:
                logger.warning("striprtf not installed, trying basic extraction")
                
                # استخراج بسيط باستخدام regex
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                    # البحث عن نص في RTF (نمط بسيط)
                    import re
                    # البحث عن نص بين الأقواس
                    text_pattern = r'\\\'(..)|\\u-?\d+\?|([a-zA-Z0-9\s\.,!?\-\+\(\)\[\]\{\}]+)'
                    text_matches = re.findall(text_pattern, content)
                    
                    extracted_text = ' '.join([''.join(match) for match in text_matches])
                    file_links = extract_links_from_text(extracted_text)
                    links.update(file_links)
                    
                    # البحث عن روابط مباشرة في RTF
                    url_pattern = r'\\field\{\\\*\\fldinst HYPERLINK "([^"]+)"\}'
                    url_matches = re.findall(url_pattern, content, re.IGNORECASE)
                    links.update(url_matches)
        
        return _filter_links(list(links))
        
    except Exception as e:
        logger.error(f"RTF extraction error: {e}")
        return []

# ======================
# ODT Extraction
# ======================

async def _extract_from_odt(client: TelegramClient, message: Message) -> List[str]:
    """
    استخراج الروابط من ملف ODT
    
    Args:
        client: عميل Telethon
        message: الرسالة
        
    Returns:
        list: قائمة بالروابط
    """
    links = set()
    
    try:
        import zipfile
        from xml.etree import ElementTree as ET
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "document.odt")
            await client.download_media(message, filepath)
            
            with zipfile.ZipFile(filepath, 'r') as odt_file:
                # قراءة محتوى المستند
                if 'content.xml' in odt_file.namelist():
                    content_xml = odt_file.read('content.xml')
                    
                    # تحليل XML
                    namespaces = {
                        'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
                        'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
                        'draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0'
                    }
                    
                    try:
                        root = ET.fromstring(content_xml)
                        
                        # استخراج النص من جميع عناصر النص
                        for elem in root.findall('.//text:p', namespaces):
                            if elem.text:
                                elem_links = extract_links_from_text(elem.text)
                                links.update(elem_links)
                        
                        for elem in root.findall('.//text:span', namespaces):
                            if elem.text:
                                elem_links = extract_links_from_text(elem.text)
                                links.update(elem_links)
                        
                        # البحث عن روابط
                        for elem in root.findall('.//text:a', namespaces):
                            href = elem.get('{http://www.w3.org/1999/xlink}href')
                            if href:
                                links.add(href)
                                
                    except Exception as e:
                        logger.warning(f"Error parsing ODT XML: {e}")
                
                # محاولة قراءة كملف نصي بسيط
                try:
                    # قراءة جميع الملفات النصية في الأرشيف
                    for file_info in odt_file.infolist():
                        if file_info.filename.endswith('.xml') or file_info.filename.endswith('.txt'):
                            try:
                                content = odt_file.read(file_info.filename).decode('utf-8', errors='ignore')
                                file_links = extract_links_from_text(content)
                                links.update(file_links)
                            except:
                                continue
                except:
                    pass
        
        return _filter_links(list(links))
        
    except ImportError:
        logger.warning("Could not process ODT file (missing libraries)")
        return []
    except Exception as e:
        logger.error(f"ODT extraction error: {e}")
        return []

# ======================
# Generic Text Extraction
# ======================

async def _extract_generic(client: TelegramClient, message: Message) -> List[str]:
    """
    استخراج نص عام من أي ملف
    
    Args:
        client: عميل Telethon
        message: الرسالة
        
    Returns:
        list: قائمة بالروابط
    """
    links = set()
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "document")
            await client.download_media(message, filepath)
            
            # محاولة قراءة الملف كنص ثنائي
            with open(filepath, 'rb') as f:
                content = f.read()
                
                # محاولة فك التشفير كنص
                try:
                    text = content.decode('utf-8', errors='ignore')
                    file_links = extract_links_from_text(text)
                    links.update(file_links)
                except:
                    # البحث مباشرة عن أنماط URLs في البيانات الثنائية
                    import re
                    # نمط للعثور على URLs في البيانات الثنائية
                    url_pattern = rb'https?://[^\x00-\x1F\x7F-\xFF<>"\s]+'
                    binary_matches = re.findall(url_pattern, content)
                    
                    for match in binary_matches:
                        try:
                            url = match.decode('utf-8', errors='ignore')
                            if url:
                                links.add(url)
                        except:
                            pass
        
        return _filter_links(list(links))
        
    except Exception as e:
        logger.error(f"Generic extraction error: {e}")
        return []

# ======================
# Link Filtering
# ======================

def _filter_links(links: List[str]) -> List[str]:
    """
    فلترة وتنظيف الروابط المستخرجة
    
    Args:
        links: قائمة الروابط الخام
        
    Returns:
        list: قائمة بالروابط النظيفة والمسموح بها
    """
    if not links:
        return []
    
    filtered_links = set()
    
    for link in links:
        try:
            # تنظيف الرابط
            cleaned = clean_link(link)
            if not cleaned:
                continue
            
            # التحقق مما إذا كان الرابط مسموحاً به
            if is_allowed_link(cleaned):
                filtered_links.add(cleaned)
                
        except Exception as e:
            logger.debug(f"Error filtering link {link}: {e}")
            continue
    
    return list(filtered_links)

# ======================
# Batch Processing
# ======================

async def extract_links_from_files_batch(
    client: TelegramClient,
    messages: List[Message],
    max_concurrent: int = 3
) -> Dict[str, List[str]]:
    """
    استخراج الروابط من مجموعة من الملفات بشكل متزامن
    
    Args:
        client: عميل Telethon
        messages: قائمة الرسائل
        max_concurrent: الحد الأقصى للملفات المعالجة في نفس الوقت
        
    Returns:
        dict: نتائج الاستخراج لكل ملف
    """
    results = {}
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_message(message: Message):
        async with semaphore:
            filename = message.file.name if message.file else "unknown"
            links = await extract_links_from_file(client, message)
            return filename, links
    
    # إنشاء مهام للمعالجة
    tasks = []
    for message in messages:
        if message and message.file:
            task = asyncio.create_task(process_message(message))
            tasks.append(task)
    
    # انتظار اكتمال جميع المهام
    for task in asyncio.as_completed(tasks):
        try:
            filename, links = await task
            results[filename] = links
        except Exception as e:
            logger.error(f"Error processing file in batch: {e}")
    
    return results

# ======================
# Test Functions
# ======================

def test_file_support():
    """اختبار دعم أنواع الملفات"""
    print("\n" + "="*50)
    print("🧪 Testing File Support")
    print("="*50)
    
    test_files = [
        ("document.pdf", "application/pdf"),
        ("report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("notes.txt", "text/plain"),
        ("file.rtf", "application/rtf"),
        ("document.odt", "application/vnd.oasis.opendocument.text"),
        ("script.exe", "application/x-msdownload"),
        ("archive.zip", "application/zip"),
    ]
    
    for filename, mime_type in test_files:
        supported = is_file_supported(filename, mime_type)
        status = "✅ مدعوم" if supported else "❌ غير مدعوم"
        file_type = get_file_type(filename, mime_type)
        print(f"{status} {filename} ({mime_type}) -> {file_type}")
    
    print("\n📊 حجم الملفات:")
    test_sizes = [50, 100, 50000000, 60000000, 100000000]
    for size in test_sizes:
        valid = is_file_size_valid(size)
        status = "✅ مقبول" if valid else "❌ مرفوض"
        print(f"{status} {size:,} بايت")
    
    print("\n" + "="*50)

async def test_extraction():
    """اختبار وظائف الاستخراج"""
    print("\n🧪 Testing Extraction Functions")
    
    # هذا اختبار نظري بدون عميل حقيقي
    print("✅ File extractors module is ready!")
    print("📋 الملفات المدعومة:")
    for ext, desc in SUPPORTED_EXTENSIONS.items():
        print(f"  • {ext} - {desc}")
    
    print("\n📦 المكتبات المطلوبة:")
    libraries = [
        ("PyPDF2", "لملفات PDF"),
        ("python-docx", "لملفات DOCX"),
        ("pdfplumber", "لتحسين استخراج PDF"),
        ("striprtf", "لملفات RTF"),
    ]
    
    for lib_name, purpose in libraries:
        try:
            __import__(lib_name.replace('-', '_'))
            print(f"  ✅ {lib_name} - {purpose}")
        except ImportError:
            print(f"  ⚠️  {lib_name} - {purpose} (اختياري)")

# ======================
# Main Test
# ======================

if __name__ == "__main__":
    print("🔧 Testing File Extractors Module")
    
    # اختبار دعم الملفات
    test_file_support()
    
    # اختبار وظائف الاستخراج
    import asyncio
    asyncio.run(test_extraction())
    
    print("\n" + "="*50)
    print("✅ File extractors module test completed successfully!")
    print("="*50)
