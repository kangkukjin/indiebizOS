import json

def generate_newspaper(news_data_str):
    try:
        # The news_data_str is a list of JSON strings from the parallel execution
        news_list = json.loads(news_data_str)
        
        html_content = """
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>데일리 AI 신문</title>
            <style>
                body { font-family: 'Times New Roman', serif; background-color: #f4f1ea; color: #333; margin: 0; padding: 20px; }
                .container { max-width: 1000px; margin: auto; border: 1px solid #ccc; padding: 40px; background: #fff; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
                header { text-align: center; border-bottom: 4px double #333; margin-bottom: 20px; padding-bottom: 10px; }
                header h1 { font-size: 50px; margin: 0; text-transform: uppercase; letter-spacing: 2px; }
                .date { font-style: italic; margin-top: 5px; }
                .newspaper-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
                .section { margin-bottom: 30px; border-bottom: 1px solid #eee; padding-bottom: 10px; }
                .section-title { font-size: 24px; border-bottom: 2px solid #333; margin-bottom: 15px; padding-bottom: 5px; color: #1a1a1a; }
                .article { margin-bottom: 15px; }
                .article-title { font-size: 18px; font-weight: bold; margin: 0 0 5px 0; color: #000; text-decoration: none; display: block; }
                .article-title:hover { text-decoration: underline; }
                .article-meta { font-size: 12px; color: #666; margin-bottom: 5px; }
                .article-summary { font-size: 14px; line-height: 1.5; color: #444; }
                footer { text-align: center; margin-top: 40px; font-size: 12px; color: #888; border-top: 1px solid #ccc; padding-top: 10px; }
            </style>
        </head>
        <body>
            <div class="container">
                <header>
                    <h1>Daily AI Newspaper</h1>
                    <div class="date">2026년 2월 24일 화요일</div>
                </header>
                <div class="newspaper-grid">
        """
        
        for item_str in news_list:
            item = json.loads(item_str)
            query = item.get('query', '뉴스')
            results = item.get('results', [])
            
            html_content += f'<div class="section"><h2 class="section-title">{query}</h2>'
            
            for article in results:
                title = article.get('title', '제목 없음')
                url = article.get('url', '#')
                source = article.get('source', '알 수 없음')
                published = article.get('published', '')
                summary = article.get('summary', '')
                
                html_content += f"""
                    <div class="article">
                        <a href="{url}" class="article-title" target="_blank">{title}</a>
                        <div class="article-meta">{source} | {published}</div>
                        <div class="article-summary">{summary}</div>
                    </div>
                """
            html_content += '</div>'
            
        html_content += """
                </div>
                <footer>
                    &copy; 2026 IndieBiz AI Newspaper Service. All rights reserved.
                </footer>
            </div>
        </body>
        </html>
        """
        
        with open('newspaper.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        print("newspaper.html created successfully.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import sys
    # Reading from a file because the data might be too large for command line arguments
    with open('news_data.json', 'r', encoding='utf-8') as f:
        data = f.read()
    generate_newspaper(data)
