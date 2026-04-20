"""문서 파일(.pages, .docx, .pdf) → 텍스트 변환"""

import subprocess
from pathlib import Path

MAX_CHARS = 100_000  # ~25k 토큰


def convert_document(file_path: str) -> dict:
    """
    문서 파일을 텍스트로 변환.
    Returns: {"text": str, "error": str|None}
    """
    path = Path(file_path)

    if not path.exists():
        return {"text": "", "error": f"파일이 존재하지 않음: {file_path}"}

    ext = path.suffix.lower()

    if ext in ('.pages', '.docx', '.doc', '.rtf'):
        result = _convert_with_textutil(file_path)
    elif ext == '.pdf':
        result = _convert_pdf(file_path)
    else:
        return {"text": "", "error": f"지원하지 않는 형식: {ext}"}

    # 길이 제한
    if result.get("text") and len(result["text"]) > MAX_CHARS:
        result["text"] = result["text"][:MAX_CHARS] + f"\n\n[... 문서가 너무 길어 {MAX_CHARS}자까지만 포함됨 ...]"

    return result


def _convert_with_textutil(file_path: str) -> dict:
    """macOS textutil로 텍스트 추출"""
    try:
        result = subprocess.run(
            ['textutil', '-convert', 'txt', '-stdout', file_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return {"text": result.stdout, "error": None}
        else:
            return {"text": "", "error": f"textutil 오류: {result.stderr.strip()}"}
    except FileNotFoundError:
        return {"text": "", "error": "textutil을 찾을 수 없음 (macOS 전용)"}
    except subprocess.TimeoutExpired:
        return {"text": "", "error": "변환 시간 초과 (30초)"}
    except Exception as e:
        return {"text": "", "error": str(e)}


def _convert_pdf(file_path: str) -> dict:
    """PDF 텍스트 추출 (PyMuPDF 사용, 없으면 안내)"""
    try:
        import fitz
        doc = fitz.open(file_path)
        pages_text = []
        for page in doc:
            pages_text.append(page.get_text())
        text = "\n\n---\n\n".join(pages_text)
        doc.close()
        return {"text": text, "error": None}
    except ImportError:
        # PyMuPDF 없으면 macOS의 mdimport 시도
        try:
            result = subprocess.run(
                ['mdimport', '-d2', file_path],
                capture_output=True, text=True, timeout=30
            )
            if result.stdout.strip():
                return {"text": result.stdout, "error": None}
        except Exception:
            pass
        return {"text": "", "error": "PDF 변환에 PyMuPDF(fitz) 설치 필요: pip install pymupdf"}
    except Exception as e:
        return {"text": "", "error": str(e)}
