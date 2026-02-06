import arxiv
import os
import requests
import feedparser
import xml.etree.ElementTree as ET
import html
import re
from typing import Optional

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:

    if tool_name == "search_openalex":
        return _search_openalex(tool_input)

    elif tool_name == "search_arxiv":
        client = arxiv.Client()
        query = tool_input.get("query")
        max_results = tool_input.get("max_results", 5)
        
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance
        )
        
        results = []
        for result in client.results(search):
            paper_info = (
                f"Title: {result.title}\n"
                f"ArXiv ID: {result.entry_id.split('/')[-1]}\n"
                f"Authors: {', '.join(author.name for author in result.authors)}\n"
                f"Published: {result.published.strftime('%Y-%m-%d')}\n"
                f"Summary: {result.summary[:200]}...\n"
                "--------------------------------------"
            )
            results.append(paper_info)
        
        if not results:
            return "No papers found for the given query."
        
        return "\n".join(results)

    elif tool_name == "download_arxiv_pdf":
        client = arxiv.Client()
        arxiv_id = tool_input.get("arxiv_id")
        filename = tool_input.get("filename")

        # Ensure download directory exists within project_path
        download_dir = os.path.join(project_path, "papers")
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        search = arxiv.Search(id_list=[arxiv_id])
        paper = next(client.results(search), None)

        if paper:
            # If filename not provided, use a sanitized version of the title
            if not filename:
                filename = "".join([c if c.isalnum() else "_" for c in paper.title]) + ".pdf"

            path = paper.download_pdf(dirpath=download_dir, filename=filename)
            return f"Paper '{paper.title}' downloaded successfully to: {path}"
        else:
            return f"Could not find paper with ID: {arxiv_id}"

    elif tool_name == "search_semantic_scholar":
        return _search_semantic_scholar(tool_input)

    elif tool_name == "search_google_scholar":
        return _search_google_scholar(tool_input)

    elif tool_name == "search_pubmed":
        return _search_pubmed(tool_input, project_path)

    elif tool_name == "download_pubmed_pdf":
        return _download_pubmed_pdf(tool_input, project_path)

    elif tool_name == "fetch_pew_research":
        return _fetch_rss("https://www.pewresearch.org/feed/", "Pew Research Center", tool_input.get("limit", 10))

    elif tool_name == "search_guardian":
        return _search_guardian(tool_input)

    elif tool_name == "fetch_world_bank_data":
        return _fetch_world_bank_data(tool_input)

    elif tool_name == "search_books":
        return _search_books(tool_input)

    else:
        return f"Unknown tool: {tool_name}"


def _search_semantic_scholar(tool_input: dict) -> str:
    """
    Semantic Scholar API를 사용한 논문 검색

    Rate Limit: 인증 없이 5분당 100건 (429 에러 시 재시도)
    API 문서: https://api.semanticscholar.org/api-docs/
    """
    import time

    query = tool_input.get("query")
    max_results = tool_input.get("max_results", 5)
    year_from = tool_input.get("year_from")

    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,authors,year,citationCount,abstract,url,openAccessPdf"
    }

    if year_from:
        params["year"] = f"{year_from}-"

    # Rate limit 대응: 최대 3번 재시도
    max_retries = 3
    retry_delay = 2  # 초

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=15)

            # Rate limit (429) 처리
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # 점진적 대기
                    continue
                else:
                    return "Semantic Scholar API 요청 한도 초과. 잠시 후 다시 시도하거나, OpenAlex 또는 arXiv를 사용해주세요."

            response.raise_for_status()
            data = response.json()

            papers = data.get("data", [])
            if not papers:
                return f"'{query}' 검색 결과가 없습니다."

            total = data.get("total", len(papers))
            results = []
            results.append(f"Semantic Scholar 검색 결과: '{query}' (총 {total:,}건 중 {len(papers)}건 표시)\n")

            for i, paper in enumerate(papers, 1):
                authors = ", ".join([a.get("name", "Unknown") for a in paper.get("authors", [])[:3]])
                if len(paper.get("authors", [])) > 3:
                    authors += " et al."

                abstract = paper.get("abstract", "")
                if abstract:
                    abstract = abstract[:200] + "..." if len(abstract) > 200 else abstract
                else:
                    abstract = "No abstract available"

                pdf_url = ""
                if paper.get("openAccessPdf"):
                    pdf_url = f"\nPDF (Open Access): {paper['openAccessPdf'].get('url', '')}"

                separator = "-" * 60
                paper_info = (
                    f"[{i}] {paper.get('title', 'Unknown')}\n"
                    f"Authors: {authors}\n"
                    f"Year: {paper.get('year', 'Unknown')} | Citations: {paper.get('citationCount', 0)}\n"
                    f"URL: {paper.get('url', '')}{pdf_url}\n"
                    f"Abstract: {abstract}\n"
                    f"{separator}"
                )
                results.append(paper_info)

            return "\n".join(results)

        except requests.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return f"Semantic Scholar 검색 오류: {str(e)}"

    return "Semantic Scholar 검색 실패. 다른 검색 도구를 사용해주세요."


def _search_google_scholar(tool_input: dict) -> str:
    """Google Scholar 검색 (scholarly 라이브러리 사용)"""
    query = tool_input.get("query")
    max_results = tool_input.get("max_results", 5)

    try:
        from scholarly import scholarly

        search_query = scholarly.search_pubs(query)

        results = []
        for i, paper in enumerate(search_query):
            if i >= max_results:
                break

            bib = paper.get("bib", {})
            title = bib.get("title", "Unknown")
            authors = bib.get("author", "Unknown")
            if isinstance(authors, list):
                authors = ", ".join(authors[:3])
                if len(bib.get("author", [])) > 3:
                    authors += " et al."
            year = bib.get("pub_year", "Unknown")
            abstract = bib.get("abstract", "No abstract available")
            if abstract and len(abstract) > 200:
                abstract = abstract[:200] + "..."

            citations = paper.get("num_citations", 0)
            url = paper.get("pub_url", paper.get("eprint_url", ""))

            paper_info = (
                f"Title: {title}\n"
                f"Authors: {authors}\n"
                f"Year: {year}\n"
                f"Citations: {citations}\n"
                f"URL: {url}\n"
                f"Abstract: {abstract}\n"
                "--------------------------------------"
            )
            results.append(paper_info)

        if not results:
            return "No papers found for the given query."

        return "\n".join(results)

    except ImportError:
        return "Error: 'scholarly' library not installed. Run: pip install scholarly"
    except Exception as e:
        return f"Error searching Google Scholar: {str(e)}"


def _search_pubmed(tool_input: dict, project_path: str = ".") -> str:
    """PubMed API를 사용한 의학/생명과학 논문 검색 (PMC ID 포함)"""
    query = tool_input.get("query")
    max_results = tool_input.get("max_results", 5)

    # Step 1: Search for paper IDs
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json"
    }

    try:
        search_response = requests.get(search_url, params=search_params, timeout=15)
        search_response.raise_for_status()
        search_data = search_response.json()

        id_list = search_data.get("esearchresult", {}).get("idlist", [])

        if not id_list:
            return "No papers found for the given query."

        # Step 2: Fetch paper details with PMC links
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json"
        }

        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=15)
        fetch_response.raise_for_status()
        fetch_data = fetch_response.json()

        # Step 3: Get PMC IDs using elink
        pmc_ids = _get_pmc_ids(id_list)

        results = []
        result_data = fetch_data.get("result", {})

        for pmid in id_list:
            paper = result_data.get(pmid, {})
            if not paper or pmid == "uids":
                continue

            title = paper.get("title", "Unknown")
            authors_list = paper.get("authors", [])
            authors = ", ".join([a.get("name", "") for a in authors_list[:3]])
            if len(authors_list) > 3:
                authors += " et al."

            pub_date = paper.get("pubdate", "Unknown")
            journal = paper.get("source", "Unknown")

            # PMC ID가 있으면 표시
            pmcid = pmc_ids.get(pmid)
            pmc_info = ""
            if pmcid:
                pmc_info = f"\nPMC ID: {pmcid} (Free full text available - use download_pubmed_pdf)"

            paper_info = (
                f"Title: {title}\n"
                f"Authors: {authors}\n"
                f"Journal: {journal}\n"
                f"Published: {pub_date}\n"
                f"PMID: {pmid}{pmc_info}\n"
                f"URL: https://pubmed.ncbi.nlm.nih.gov/{pmid}/\n"
                "--------------------------------------"
            )
            results.append(paper_info)

        if not results:
            return "No papers found for the given query."

        return "\n".join(results)

    except requests.RequestException as e:
        return f"Error searching PubMed: {str(e)}"


def _get_pmc_ids(pmid_list: list) -> dict:
    """PMID 목록에서 PMC ID 매핑을 가져옴"""
    if not pmid_list:
        return {}

    link_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    link_params = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "id": ",".join(pmid_list),
        "retmode": "json"
    }

    try:
        response = requests.get(link_url, params=link_params, timeout=15)
        response.raise_for_status()
        data = response.json()

        pmc_ids = {}
        linksets = data.get("linksets", [])

        for linkset in linksets:
            pmid = str(linkset.get("ids", [None])[0])
            linksetdbs = linkset.get("linksetdbs", [])

            for linksetdb in linksetdbs:
                if linksetdb.get("dbto") == "pmc":
                    links = linksetdb.get("links", [])
                    if links:
                        pmc_ids[pmid] = f"PMC{links[0]}"
                        break

        return pmc_ids

    except Exception:
        return {}


def _download_pubmed_pdf(tool_input: dict, project_path: str = ".") -> str:
    """PMC에서 무료 전문 PDF 다운로드 (OA API 사용)"""
    import xml.etree.ElementTree as ET
    import tarfile
    import io
    import urllib.request
    import urllib.error

    pmcid = tool_input.get("pmcid", "").strip()
    filename = tool_input.get("filename")

    if not pmcid:
        return "Error: PMC ID is required"

    # PMC 접두사 정규화
    if not pmcid.upper().startswith("PMC"):
        pmcid = f"PMC{pmcid}"
    pmcid = pmcid.upper()

    # 다운로드 디렉토리 생성
    download_dir = os.path.join(project_path, "papers")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    try:
        # 1. OA API로 다운로드 링크 가져오기
        oa_url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}"
        oa_response = requests.get(oa_url, timeout=30)
        oa_response.raise_for_status()

        # XML 파싱
        root = ET.fromstring(oa_response.text)
        error = root.find(".//error")
        if error is not None:
            return f"Error: {error.text}"

        link = root.find(".//link")
        if link is None:
            return f"Error: No download link available for {pmcid}. This paper may not be open access."

        href = link.get("href")
        file_format = link.get("format", "")

        if not href:
            return f"Error: Could not find download URL for {pmcid}"

        # 2. 파일 다운로드 (FTP 및 HTTP 지원)
        if href.startswith("ftp://"):
            # FTP는 urllib 사용
            with urllib.request.urlopen(href, timeout=120) as response:
                download_content = response.read()
        else:
            # HTTP/HTTPS는 requests 사용
            download_response = requests.get(href, timeout=60)
            download_response.raise_for_status()
            download_content = download_response.content

        # 파일명 설정
        if not filename:
            filename = f"{pmcid}.pdf"
        elif not filename.endswith(".pdf"):
            filename += ".pdf"

        file_path = os.path.join(download_dir, filename)

        # 3. tar.gz인 경우 PDF 추출
        if file_format == "tgz" or href.endswith(".tar.gz"):
            tar_content = io.BytesIO(download_content)
            with tarfile.open(fileobj=tar_content, mode="r:gz") as tar:
                # PDF 파일 찾기
                pdf_found = False
                for member in tar.getmembers():
                    if member.name.endswith(".pdf"):
                        pdf_file = tar.extractfile(member)
                        if pdf_file:
                            with open(file_path, "wb") as f:
                                f.write(pdf_file.read())
                            pdf_found = True
                            break

                if not pdf_found:
                    # PDF가 없으면 전체 tar.gz 저장
                    tar_path = os.path.join(download_dir, f"{pmcid}.tar.gz")
                    with open(tar_path, "wb") as f:
                        f.write(download_content)
                    return f"Paper archive downloaded to: {tar_path} (PDF not found in archive, may contain other formats)"
        else:
            # 직접 PDF인 경우
            with open(file_path, "wb") as f:
                f.write(download_content)

        return f"Paper downloaded successfully to: {file_path}"

    except requests.RequestException as e:
        return f"Error downloading PDF: {str(e)}"
    except urllib.error.URLError as e:
        return f"Error downloading from FTP: {str(e)}"
    except ET.ParseError as e:
        return f"Error parsing OA API response: {str(e)}"
    except tarfile.TarError as e:
        return f"Error extracting archive: {str(e)}"


def _search_openalex(tool_input: dict) -> str:
    """
    OpenAlex API를 사용한 학술 논문 검색

    OpenAlex는 세계 최대 오픈 학술 데이터베이스로 2.6억+ 논문을 보유하고 있습니다.
    모든 학문 분야를 커버하며, 완전 무료로 API 키 없이 사용 가능합니다.

    API 문서: https://docs.openalex.org/
    """
    query = tool_input.get("query")
    max_results = min(tool_input.get("max_results", 10), 200)  # 최대 200개
    year_from = tool_input.get("year_from")
    year_to = tool_input.get("year_to")
    open_access = tool_input.get("open_access", False)
    sort_by = tool_input.get("sort_by", "relevance")

    # API 엔드포인트
    url = "https://api.openalex.org/works"

    # 필터 구성
    filters = []

    # 연도 필터
    if year_from and year_to:
        filters.append(f"publication_year:{year_from}-{year_to}")
    elif year_from:
        filters.append(f"publication_year:>{year_from - 1}")
    elif year_to:
        filters.append(f"publication_year:<{year_to + 1}")

    # 오픈액세스 필터
    if open_access:
        filters.append("is_oa:true")

    # 정렬 옵션
    sort_mapping = {
        "relevance": "relevance_score:desc",
        "cited": "cited_by_count:desc",
        "recent": "publication_date:desc"
    }
    sort_param = sort_mapping.get(sort_by, "relevance_score:desc")

    # 요청 파라미터
    params = {
        "search": query,
        "per-page": max_results,
        "sort": sort_param,
        "select": "id,title,authorships,publication_year,cited_by_count,doi,open_access,abstract_inverted_index,primary_location"
    }

    if filters:
        params["filter"] = ",".join(filters)

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        works = data.get("results", [])
        total_count = data.get("meta", {}).get("count", 0)

        if not works:
            return f"'{query}' 검색 결과가 없습니다."

        results = []
        results.append(f"OpenAlex 검색 결과: '{query}' (총 {total_count:,}건 중 {len(works)}건 표시)\n")

        for i, work in enumerate(works, 1):
            # 제목
            title = work.get("title", "제목 없음")

            # 저자 추출
            authorships = work.get("authorships", [])
            authors = []
            for auth in authorships[:3]:
                author_name = auth.get("author", {}).get("display_name", "Unknown")
                authors.append(author_name)
            if len(authorships) > 3:
                authors.append("et al.")
            authors_str = ", ".join(authors) if authors else "저자 정보 없음"

            # 발행연도, 인용수
            year = work.get("publication_year", "Unknown")
            citations = work.get("cited_by_count", 0)

            # DOI
            doi = work.get("doi", "")
            doi_str = f"\nDOI: {doi}" if doi else ""

            # 오픈액세스 PDF URL
            oa_info = work.get("open_access", {})
            oa_url = oa_info.get("oa_url", "")
            oa_str = f"\nPDF (Open Access): {oa_url}" if oa_url else ""

            # 저널/출처 정보
            primary_loc = work.get("primary_location", {}) or {}
            source = primary_loc.get("source", {}) or {}
            journal = source.get("display_name", "")
            journal_str = f"\nJournal: {journal}" if journal else ""

            # 초록 복원 (inverted index에서)
            abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
            if abstract:
                abstract = abstract[:300] + "..." if len(abstract) > 300 else abstract
                abstract_str = f"\nAbstract: {abstract}"
            else:
                abstract_str = ""

            # OpenAlex ID에서 URL 생성
            work_id = work.get("id", "")
            openalex_url = work_id if work_id else ""

            separator = "-" * 60
            paper_info = (
                f"[{i}] {title}\n"
                f"Authors: {authors_str}\n"
                f"Year: {year} | Citations: {citations:,}{journal_str}{doi_str}{oa_str}{abstract_str}\n"
                f"OpenAlex: {openalex_url}\n"
                f"{separator}"
            )
            results.append(paper_info)

        return "\n".join(results)

    except requests.RequestException as e:
        return f"OpenAlex 검색 오류: {str(e)}"
    except Exception as e:
        return f"검색 처리 오류: {str(e)}"


def _reconstruct_abstract(inverted_index: dict) -> str:
    """
    OpenAlex의 abstract_inverted_index에서 원문 초록을 복원합니다.

    OpenAlex는 저장 공간 절약을 위해 초록을 inverted index 형태로 저장합니다.
    예: {"word1": [0, 5], "word2": [1, 3]} -> 위치 기반으로 단어 재배열
    """
    if not inverted_index:
        return ""

    try:
        # 위치-단어 매핑 생성
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))

        # 위치순 정렬 후 단어 연결
        word_positions.sort(key=lambda x: x[0])
        abstract = " ".join([word for pos, word in word_positions])

        return abstract
    except Exception:
        return ""

def _fetch_rss(url: str, source_name: str, limit: int = 10) -> str:
    """RSS 피드를 가져와서 파싱합니다 (feedparser 사용)."""
    try:
        feed = feedparser.parse(url)
        
        if not feed.entries:
            return f"{source_name}에서 기사를 찾을 수 없습니다."
            
        results = [f"### {source_name} 최신 소식 (최대 {limit}건)\n"]
        
        for i, entry in enumerate(feed.entries[:limit], 1):
            title = entry.get("title", "제목 없음")
            link = entry.get("link", "")
            pub_date = entry.get("published", entry.get("updated", ""))
            description = entry.get("summary", entry.get("description", ""))
            
            # HTML 태그 제거 및 언이스케이프
            description = re.sub('<[^<]+?>', '', description)
            description = html.unescape(description).strip()
            if len(description) > 200:
                description = description[:200] + "..."
                
            item_info = (
                f"[{i}] {title}\n"
                f"날짜: {pub_date}\n"
                f"링크: {link}\n"
                f"요약: {description}\n"
                "--------------------------------------"
            )
            results.append(item_info)
            
        return "\n".join(results)
        
    except Exception as e:
        return f"{source_name} RSS 가져오기 오류: {str(e)}"

def _search_guardian(tool_input: dict) -> str:
    """The Guardian API를 사용하여 기사를 검색합니다."""
    api_key = os.getenv("GUARDIAN_API_KEY")
    if not api_key:
        return "오류: GUARDIAN_API_KEY 환경 변수가 설정되지 않았습니다."
        
    query = tool_input.get("query")
    page_size = tool_input.get("page_size", 10)
    from_date = tool_input.get("from_date")
    to_date = tool_input.get("to_date")
    
    url = "https://content.guardianapis.com/search"
    params = {
        "q": query,
        "api-key": api_key,
        "page-size": page_size,
        "show-fields": "trailText,headline,shortUrl"
    }
    
    if from_date:
        params["from-date"] = from_date
    if to_date:
        params["to-date"] = to_date
        
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json().get("response", {})
        
        results_list = data.get("results", [])
        if not results_list:
            return f"'{query}'에 대한 가디언 기사를 찾을 수 없습니다."
            
        total = data.get("total", 0)
        output = [f"### The Guardian 검색 결과: '{query}' (총 {total:,}건 중 {len(results_list)}건 표시)\n"]
        
        for i, article in enumerate(results_list, 1):
            fields = article.get("fields", {})
            headline = fields.get("headline", article.get("webTitle", "제목 없음"))
            trail_text = fields.get("trailText", "요약 없음")
            # HTML 태그 제거
            import re
            trail_text = re.sub('<[^<]+?>', '', trail_text)
            trail_text = html.unescape(trail_text).strip()
            
            url = article.get("webUrl", "")
            date = article.get("webPublicationDate", "")[:10]
            section = article.get("sectionName", "")
            
            article_info = (
                f"[{i}] {headline}\n"
                f"날짜: {date} | 섹션: {section}\n"
                f"링크: {url}\n"
                f"요약: {trail_text}\n"
                "--------------------------------------"
            )
            output.append(article_info)
            
        return "\n".join(output)
        
    except Exception as e:
        return f"The Guardian API 검색 오류: {str(e)}"


def _fetch_world_bank_data(tool_input: dict) -> str:
    """World Bank API를 사용하여 국가별 지표 데이터를 가져옵니다."""
    indicator = tool_input.get("indicator")
    country = tool_input.get("country", "all")
    date = tool_input.get("date")
    per_page = tool_input.get("per_page", 50)
    
    # API URL 구성
    # 예: http://api.worldbank.org/v2/country/KOR/indicator/NY.GDP.MKTP.CD?format=json&date=2010:2022
    url = f"http://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
    params = {
        "format": "json",
        "per_page": per_page
    }
    if date:
        params["date"] = date
        
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # World Bank API 응답 구조: [metadata, data_list]
        if not data or len(data) < 2 or not data[1]:
            return f"지표 '{indicator}'(국가: {country})에 대한 데이터를 찾을 수 없습니다."
            
        data_list = data[1]
        
        indicator_name = data_list[0].get("indicator", {}).get("value", indicator)
        results = [f"### World Bank 데이터: {indicator_name} ({country})\n"]
        
        for entry in data_list:
            year = entry.get("date")
            value = entry.get("value")
            country_name = entry.get("country", {}).get("value")
            
            if value is not None:
                # 수치 포맷팅 (천 단위 콤마)
                if isinstance(value, (int, float)):
                    formatted_value = f"{value:,.2f}".rstrip('0').rstrip('.')
                else:
                    formatted_value = str(value)
                
                results.append(f"- {year} ({country_name}): {formatted_value}")
            else:
                results.append(f"- {year} ({country_name}): 데이터 없음")
                
        return "\n".join(results)
        
    except Exception as e:
        return f"World Bank API 요청 오류: {str(e)}"


def _search_books(tool_input: dict) -> str:
    """Google Books API를 사용한 도서 검색"""
    query = tool_input.get("query")
    max_results = tool_input.get("max_results", 5)
    order_by = tool_input.get("order_by", "relevance")

    url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": query,
        "maxResults": min(max_results, 40),
        "orderBy": order_by,
        "printType": "books"
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        items = data.get("items", [])
        if not items:
            return f"'{query}'에 대한 도서 검색 결과가 없습니다."

        results = [f"### Google Books 검색 결과: '{query}'\n"]

        for i, item in enumerate(items, 1):
            info = item.get("volumeInfo", {})
            title = info.get("title", "Unknown Title")
            authors = ", ".join(info.get("authors", ["Unknown Author"]))
            publisher = info.get("publisher", "Unknown Publisher")
            published_date = info.get("publishedDate", "Unknown Date")
            description = info.get("description", "No description available.")
            if len(description) > 300:
                description = description[:300] + "..."
            
            categories = ", ".join(info.get("categories", ["N/A"]))
            page_count = info.get("pageCount", "N/A")
            
            # ISBN 추출
            isbns = []
            for identifier in info.get("industryIdentifiers", []):
                isbns.append(f"{identifier.get('type')}: {identifier.get('identifier')}")
            isbn_str = ", ".join(isbns) if isbns else "N/A"

            book_info = (
                f"[{i}] {title}\n"
                f"- 저자: {authors}\n"
                f"- 출판: {publisher} ({published_date})\n"
                f"- ISBN: {isbn_str}\n"
                f"- 카테고리: {categories} | 페이지: {page_count}\n"
                f"- 요약: {description}\n"
                "--------------------------------------"
            )
            results.append(book_info)

        return "\n".join(results)

    except Exception as e:
        return f"Google Books API 요청 오류: {str(e)}"

