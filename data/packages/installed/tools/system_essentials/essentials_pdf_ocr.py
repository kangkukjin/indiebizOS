"""Local OCR for textless PDF pages; no remote upload or language-model calls."""
import csv
import io
import math
import shutil
import subprocess


def recognize_page(page):
    """Render one complete page and preserve OCR confidence/failure provenance."""
    engine = shutil.which('tesseract')
    result = {'engine': 'tesseract', 'status': 'unavailable', 'text': ''}
    if not engine:
        return {**result, 'error': '로컬 Tesseract OCR 엔진이 설치되어 있지 않습니다.'}
    try:
        languages = subprocess.run([engine, '--list-langs'], capture_output=True,
                                   timeout=10, check=True).stdout.decode('utf-8').splitlines()
        selected = [lang for lang in ('kor', 'eng') if lang in languages]
        if not selected:
            return {**result, 'error': 'Tesseract 한국어/영어 언어 데이터가 없습니다.'}
        result['languages'] = selected
        result['segmentation'] = 'single_block'
        # Preserve short separated lines too; automatic layout drops receipt totals.
        # Bound memory while rendering the whole page (never crop a source).
        scale = min(200 / 72, math.sqrt(20_000_000 / max(1, page.rect.width * page.rect.height)))
        import fitz
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
        response = subprocess.run([engine, 'stdin', 'stdout', '-l', '+'.join(selected),
                                   '--psm', '6', 'tsv'], input=pix.tobytes('png'),
                                  capture_output=True, timeout=45, check=True)
        lines, confidences = {}, []
        for row in csv.DictReader(io.StringIO(response.stdout.decode('utf-8')), delimiter='\t',
                                  quoting=csv.QUOTE_NONE):
            word = (row.get('text') or '').strip()
            if row.get('level') != '5' or not word:
                continue
            confidence = float(row['conf'])
            key = tuple(row[k] for k in ('block_num', 'par_num', 'line_num'))
            lines.setdefault(key, []).append(word)
            confidences.append(confidence)
        text = '\n'.join(' '.join(words) for words in lines.values())
        minimum = min(confidences) if confidences else None
        return {**result, 'text': text, 'status': ('low_confidence' if minimum < 50 else 'recognized')
                if text else 'no_text', 'confidence_min': minimum,
                'confidence_mean': round(sum(confidences) / len(confidences), 2) if confidences else None}
    except subprocess.TimeoutExpired:
        return {**result, 'status': 'failed', 'error': '페이지 OCR 처리 제한 시간을 초과했습니다.'}
    except Exception as exc:  # Rendering/decoder failure must preserve other pages too.
        return {**result, 'status': 'failed', 'error': f'로컬 OCR 실패: {type(exc).__name__}'}
