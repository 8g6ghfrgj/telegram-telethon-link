import os
import tempfile
import logging
from typing import List, Set
import asyncio

from telethon import TelegramClient
from telethon.tl.types import Message

from link_utils import URL_REGEX

# ======================
# Logging
# ======================

logger = logging.getLogger(__name__)

# ======================
# Constants
# ======================

SUPPORTED_EXTENSIONS = {
    '.pdf': 'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.txt': 'text/plain',
    '.rtf': 'application/rtf',
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# ======================
# Public API
# ======================

async def extract_links_from_file(
    client: TelegramClient,
    message: Message
) -> List[str]:
    """
    استخراج الروابط من ملفات متنوعة
    يدعم: PDF, DOCX, TXT, RTF
    """
    if not message.file:
        return []
    
    # التحقق من حجم الملف
    if message.file.size > MAX_FILE_SIZE:
        logger.warning(f"File too large: {message.file.size} bytes")
        return []
    
    filename = message.file.name or "file"
    mime_type = message.file.mime_type or ""
    file_ext = os.path.splitext(filename.lower())[1]
    
    # التحقق من أن الملف مدعوم
    if file_ext not in SUPPORTED_EXTENSIONS and mime_type not in SUPPORTED_EXTENSIONS.values():
        logger.debug(f"Unsupported file type: {filename} ({mime_type})")
        return []
    
    links: Set[str] = set()
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, filename)
            
            # تحميل الملف
            logger.info(f"Downloading file: {filename}")
            await client.download_media(message, path)
            
            # استخراج الروابط حسب نوع الملف
            if file_ext == '.pdf' or mime_type == 'application/pdf':
                file_links = await _extract_from_pdf_async(path)
            elif file_ext == '.docx' or 'wordprocessingml.document' in mime_type:
                file_links = await _extract_from_docx_async(path)
            elif file_ext == '.txt' or mime_type == 'text/plain':
                file_links = await _extract_from_txt_async(path)
            elif file_ext == '.rtf' or mime_type == 'application/rtf':
                file_links = await _extract_from_rtf_async(path)
            else:
                # محاولة استخراج كملف نصي عام
                file_links = await _extract_generic_text_async(path)
            
            # إضافة الروابط المستخرجة
            for link in file_links:
                links.add(link)
            
            logger.info(f"Extracted {len(links)} links from file: {filename}")
            
    except Exception as e:
        logger.error(f"Error extracting links from file {filename}: {e}")
    
    return list(links)

# ======================
# PDF Extraction
# ======================

async def _extract_from_pdf_async(path: str) -> List[str]:
    """استخراج النص من PDF بشكل غير متزامن"""
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, _extract_from_pdf_sync, path
        )
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return []

def _extract_from_pdf_sync(path: str) -> List[str]:
    """استخراج النص من PDF (متزامن)"""
    links: Set[str] = set()
    
    try:
        # محاولة استخدام PyPDF2 أولاً
        try:
            from PyPDF2 import PdfReader
            
            reader = PdfReader(path)
            for page in reader.pages:
                text = page.extract_text() or ""
                links.update(URL_REGEX.findall(text))
            
            if links:
                return list(links)
        
        except ImportError:
            logger.warning("PyPDF2 not installed, trying alternatives")
        except Exception as e:
            logger.warning(f"PyPDF2 failed: {e}")
        
        # محاولة استخدام pdfplumber كبديل
        try:
            import pdfplumber
            
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    links.update(URL_REGEX.findall(text))
        
        except ImportError:
            logger.warning("pdfplumber not installed")
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e}")
    
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
    
    return list(links)

# ======================
# DOCX Extraction
# ======================

async def _extract_from_docx_async(path: str) -> List[str]:
    """استخراج النص من DOCX بشكل غير متزامن"""
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, _extract_from_docx_sync, path
        )
    except Exception as e:
        logger.error(f"DOCX extraction error: {e}")
        return []

def _extract_from_docx_sync(path: str) -> List[str]:
    """استخراج النص من DOCX (متزامن)"""
    links: Set[str] = set()
    
    try:
        from docx import Document
        
        doc = Document(path)
        
        # فقرات
        for para in doc.paragraphs:
            if para.text:
                links.update(URL_REGEX.findall(para.text))
        
        # جداول
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text:
                        links.update(URL_REGEX.findall(cell.text))
    
    except ImportError:
        logger.warning("python-docx not installed")
    except Exception as e:
        logger.error(f"DOCX extraction failed: {e}")
    
    return list(links)

# ======================
# Text File Extraction
# ======================

async def _extract_from_txt_async(path: str) -> List[str]:
    """استخراج النص من ملف نصي"""
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, _extract_from_txt_sync, path
        )
    except Exception as e:
        logger.error(f"TXT extraction error: {e}")
        return []

def _extract_from_txt_sync(path: str) -> List[str]:
    """استخراج النص من ملف نصي (متزامن)"""
    links: Set[str] = set()
    
    try:
        # محاولة فتح الملف بتشفيرات مختلفة
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1256', 'windows-1256']
        
        for encoding in encodings:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    content = f.read()
                    links.update(URL_REGEX.findall(content))
                break  # نجح، توقف عن المحاولة
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.warning(f"Failed to read with encoding {encoding}: {e}")
    
    except Exception as e:
        logger.error(f"TXT extraction failed: {e}")
    
    return list(links)

# ======================
# RTF Extraction
# ======================

async def _extract_from_rtf_async(path: str) -> List[str]:
    """استخراج النص من RTF"""
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, _extract_from_rtf_sync, path
        )
    except Exception as e:
        logger.error(f"RTF extraction error: {e}")
        return []

def _extract_from_rtf_sync(path: str) -> List[str]:
    """استخراج النص من RTF (متزامن)"""
    links: Set[str] = set()
    
    try:
        # محاولة استخدام striprtf
        try:
            from striprtf.striprtf import rtf_to_text
            
            with open(path, 'r', encoding='utf-8') as f:
                rtf_content = f.read()
                text_content = rtf_to_text(rtf_content)
                links.update(URL_REGEX.findall(text_content))
        
        except ImportError:
            logger.warning("striprtf not installed, trying basic extraction")
            
            # استخراج بسيط باستخدام regex
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # البحث عن نصوص في RTF
                import re
                text_matches = re.findall(r'\\\'(..)|([a-zA-Z0-9\s,.!?]+)', content)
                extracted_text = ' '.join([''.join(match) for match in text_matches])
                links.update(URL_REGEX.findall(extracted_text))
    
    except Exception as e:
        logger.error(f"RTF extraction failed: {e}")
    
    return list(links)

# ======================
# Generic Text Extraction
# ======================

async def _extract_generic_text_async(path: str) -> List[str]:
    """استخراج نص عام من أي ملف"""
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, _extract_generic_text_sync, path
        )
    except Exception as e:
        logger.error(f"Generic text extraction error: {e}")
        return []

def _extract_generic_text_sync(path: str) -> List[str]:
    """استخراج نص عام (متزامن)"""
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
    
    except Exception as e:
        logger.error(f"Generic text extraction failed: {e}")
    
    return list(links)

# ======================
# Helper Functions
# ======================

def is_file_supported(filename: str, mime_type: str = "") -> bool:
    """التحقق مما إذا كان نوع الملف مدعومًا"""
    file_ext = os.path.splitext(filename.lower())[1]
    
    if file_ext in SUPPORTED_EXTENSIONS:
        return True
    
    if mime_type in SUPPORTED_EXTENSIONS.values():
        return True
    
    return False

# ======================
# Quick Test
# ======================

if __name__ == "__main__":
    import sys
    
    print("🧪 Testing file extractors...")
    print(f"Supported extensions: {list(SUPPORTED_EXTENSIONS.keys())}")
    
    # اختبار دعم المكتبات
    print("\n📚 Checking required libraries:")
    
    libraries = {
        'PyPDF2': 'PyPDF2',
        'python-docx': 'docx',
        'pdfplumber': 'pdfplumber',
        'striprtf': 'striprtf'
    }
    
    for lib_name, import_name in libraries.items():
        try:
            __import__(import_name)
            print(f"  ✅ {lib_name} is installed")
        except ImportError:
            print(f"  ⚠️  {lib_name} is NOT installed (optional)")
    
    print("\n✅ File extractors module is ready!")
