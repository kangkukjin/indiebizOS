import json
import datetime

# Data from previous steps (mocked for the script, I will replace with actual data)
# Since I cannot directly pass the 'results' variable to the script easily, 
# I will use the data I just received.

data_raw = """
[
  {"query": "AI", "results": [...]},
  {"query": "청주", "results": [...]},
  ...
]
"""

# I will construct the data list from the results I got.
# I'll use a more robust way: I'll read the results from the previous tool calls.
# Actually, I'll just write the HTML generation logic and use the data I have in context.

keywords = ["AI", "청주", "세종", "문화", "여행", "과학", "경제", "주식", "만화", "영화", "드라마", "책"]

def generate_html(all_news):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = f'''
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>IndieBiz 일간 신문</title>
        <style>
            body {{ font-family: 'Noto Serif KR', serif; background-color: #f4f1ea; color: #333; line-height: 1.6; margin: 0; padding: 20px; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; box-shadow: 0 0 20px rgba(0,0,0,0.1); border: 1px solid #ddd; }}
            header {{ text-align: center; border-bottom: 4px double #333; padding-bottom: 20px; margin-bottom: 30px; }}
            header h1 {{ font-size: 3.5em; margin: 0; font-family: 'Georgia', serif; text-transform: uppercase; letter-spacing: 2px; }}
            .date {{ font-style: italic; color: #666; margin-top: 10px; }}
            .newspaper-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 30px; }}
            .section {{ border-bottom: 1px solid #eee; padding-bottom: 20px; }}
            .section h2 {{ border-left: 5px solid #333; padding-left: 10px; margin-bottom: 15px; background: #f9f9f9; padding: 5px 10px; }}
            .news-item {{ margin-bottom: 15px; }}
            .news-item a {{ text-decoration: none; color: #1a0dab; font-weight: bold; font-size: 1.1em; }}
            .news-item a:hover {{ text-decoration: underline; }}
            .summary {{ font-size: 0.9em; color: #555; margin-top: 5px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
            .source {{ font-size: 0.8em; color: #888; margin-top: 2px; }}
            footer {{ text-align: center; margin-top: 50px; border-top: 1px solid #ddd; padding-top: 20px; color: #777; font-size: 0.9em; }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>IndieBiz Daily</h1>
                <div class="date">발행일: {now}</div>
            </header>
            <div class="newspaper-grid">
    '''
    
    for section in all_news:
        query = section.get('query', '알 수 없음')
        results = section.get('results', [])
        html += f'<div class="section"><h2>{query}</h2>'
        for item in results[:7]:
            title = item.get('title', '제목 없음')
            url = item.get('url', '#')
            summary = item.get('summary', '')
            source = item.get('source', '')
            html += f'''
                <div class="news-item">
                    <a href="{url}" target="_blank">{title}</a>
                    <div class="source">{source}</div>
                    <div class="summary">{summary}</div>
                </div>
            '''
        html += '</div>'
        
    html += '''
            </div>
            <footer>
                &copy; 2026 IndieBiz OS News Service. All rights reserved.
            </footer>
        </div>
    </body>
    </html>
    '''
    return html

# Actual data processing will happen in the next step.
