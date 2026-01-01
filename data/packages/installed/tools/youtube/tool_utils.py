"""
IndieBiz 도구 공통 유틸리티
==========================
여러 도구에서 공용으로 사용하는 함수들
"""

import os

# 공통 출력 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")


def markdown_to_html(markdown_text: str, title: str, date_str: str,
                     doc_type: str = "default") -> str:
    """
    Markdown을 HTML로 변환

    Args:
        markdown_text: 변환할 마크다운 텍스트
        title: 문서 제목
        date_str: 날짜 문자열
        doc_type: 문서 타입 ("newspaper", "magazine", "report", "default")

    Returns:
        HTML 문자열
    """
    import markdown

    # Markdown → HTML 변환
    html_body = markdown.markdown(
        markdown_text,
        extensions=['extra', 'nl2br', 'sane_lists', 'toc']
    )

    # 문서 타입별 설정
    type_config = {
        "newspaper": {
            "class": "newspaper",
            "subtitle": f"{date_str} | IndieBiz AI 신문 시스템"
        },
        "magazine": {
            "class": "magazine",
            "subtitle": f"{date_str} | IndieBiz Magazine"
        },
        "report": {
            "class": "report",
            "subtitle": f"{date_str} | IndieBiz 블로그 인사이트"
        },
        "default": {
            "class": "document",
            "subtitle": date_str
        }
    }

    config = type_config.get(doc_type, type_config["default"])

    # 공통 스타일
    style = """
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
            line-height: 1.8;
            background-color: #f5f5f5;
            color: #1a1a1a;
        }

        .newspaper, .magazine, .report, .document {
            max-width: 1200px;
            margin: 20px auto;
            background: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        /* 헤더 */
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }

        h1 {
            font-size: 42px;
            font-weight: bold;
            margin-bottom: 10px;
        }

        .subtitle {
            font-size: 14px;
            opacity: 0.9;
        }

        /* 본문 */
        .content {
            padding: 40px;
        }

        /* 목차 */
        .toc {
            background: #f9f9f9;
            border-left: 4px solid #667eea;
            padding: 20px 30px;
            margin-bottom: 40px;
        }

        .toc h2 {
            font-size: 18px;
            margin-bottom: 15px;
            color: #667eea;
            border: none;
        }

        .toc ul {
            list-style: none;
        }

        .toc li {
            margin-bottom: 8px;
            padding-left: 20px;
            position: relative;
        }

        .toc li::before {
            content: '▸';
            position: absolute;
            left: 0;
            color: #667eea;
        }

        .toc a {
            color: #333;
            text-decoration: none;
            transition: color 0.3s;
        }

        .toc a:hover {
            color: #667eea;
        }

        /* 섹션 */
        h2 {
            font-size: 28px;
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            margin: 40px 0 20px 0;
        }

        /* 기사/항목 */
        h3 {
            font-size: 20px;
            color: #333;
            margin: 25px 0 10px 0;
            line-height: 1.4;
        }

        p {
            margin-bottom: 15px;
            line-height: 1.8;
            color: #444;
        }

        strong {
            color: #667eea;
        }

        /* 링크 */
        a {
            color: #667eea;
            text-decoration: none;
            border-bottom: 1px solid transparent;
            transition: all 0.3s;
        }

        a:hover {
            border-bottom-color: #667eea;
        }

        /* 버튼형 링크 */
        p a {
            display: inline-block;
            padding: 8px 16px;
            background: #f0f0f0;
            border-radius: 4px;
            border: none;
            font-weight: 500;
        }

        p a:hover {
            background: #667eea;
            color: white;
        }

        /* 구분선 */
        hr {
            border: none;
            height: 1px;
            background: #e0e0e0;
            margin: 30px 0;
        }

        /* 푸터 */
        .footer {
            background: #f9f9f9;
            border-top: 2px solid #e0e0e0;
            padding: 30px 40px;
            margin-top: 40px;
        }

        .footer h2 {
            font-size: 18px;
            border: none;
            margin: 0 0 15px 0;
            color: #667eea;
        }

        .footer ul {
            list-style: none;
            color: #666;
            font-size: 14px;
        }

        .footer li {
            padding: 5px 0;
            padding-left: 20px;
            position: relative;
        }

        .footer li::before {
            content: '•';
            position: absolute;
            left: 0;
            color: #667eea;
        }

        /* 반응형 */
        @media (max-width: 768px) {
            .newspaper, .magazine, .report, .document {
                margin: 10px;
            }

            .header, .content, .footer {
                padding: 20px;
            }

            h1 {
                font-size: 28px;
            }

            h2 {
                font-size: 22px;
            }

            h3 {
                font-size: 18px;
            }
        }
    </style>
    """

    # 최종 HTML
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {date_str}</title>
    {style}
</head>
<body>
    <div class="{config['class']}">
        <div class="header">
            <h1>{title}</h1>
            <div class="subtitle">{config['subtitle']}</div>
        </div>
        <div class="content">
            {html_body}
        </div>
    </div>
</body>
</html>"""

    return html


def save_as_html(content: str, title: str, date_str: str,
                 filename_prefix: str, doc_type: str = "default") -> dict:
    """
    마크다운 콘텐츠를 HTML로 변환하여 저장

    Args:
        content: 마크다운 콘텐츠
        title: 문서 제목
        date_str: 날짜 문자열 (예: "2024년 12월 26일")
        filename_prefix: 파일명 접두사 (예: "신문", "잡지")
        doc_type: 문서 타입

    Returns:
        {'success': True, 'filepath': '...', 'filename': '...'}
    """
    from datetime import datetime

    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    # 파일명용 날짜
    date_filename = datetime.now().strftime("%Y%m%d")

    # HTML 변환
    html_content = markdown_to_html(content, title, date_str, doc_type)

    # 파일 저장
    filename = f"{filename_prefix}_{date_filename}.html"
    filepath = os.path.join(OUTPUTS_DIR, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return {
        'success': True,
        'filepath': filepath,
        'filename': filename
    }
