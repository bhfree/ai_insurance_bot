import re
import json
import argparse

from pypdf import PdfReader
from hanspell import spell_checker


parser = argparse.ArgumentParser()
parser.add_argument("--company_name", type=str, required=True)
parser.add_argument("--category", type=str, required=True)
parser.add_argument("--insurance_type", type=str, required=True)
parser.add_argument("--insurance_name", type=str, required=True)
parser.add_argument("--sales_date", type=str, required=True)
parser.add_argument("--index_title", type=str, required=True)
parser.add_argument("--file_path", type=str, required=True)
parser.add_argument("--start_page", type=int, required=True)
parser.add_argument("--end_page", type=int, required=True)

args = parser.parse_args()

company_name = args.company_name
category = args.category
insurance_type = args.insurance_type
insurance_name = args.insurance_name
sales_date = args.sales_date
index_title = args.index_title
file_path = args.file_path
start_page = int(args.start_page)
end_page = int(args.end_page)


INDEX_START_PATTERN = re.compile(r"^\s*제\s*\d+\s*[관조]|^\s*\[별표\s*\d+\]")
INDEX_END_PATTERN = re.compile(r"\s*\d+\s$")

REPLACE_WHITESPACE = re.compile(r"[\s\n]+")

EXTRACT_INDEX = re.compile(r"제\s*\d+\s*[관조]\s*【?[\s\w\‘\’\,\'\(\)\:\-]+】?\s\d{1,3}\s*|제\s*\d+\s*조의\d{1,2}\s*【?[\s\w\‘\’\,\'\(\)\:\-]+】?\s\d{1,3}\s*|\[별표\s*\d+\]\s*[\s\w\‘\’\,\'\(\)\:\-]+\s\d{1,3}\s*")
EXTRACT_ARTICLE = re.compile(r"(제\s*\d+\s*[관조])(【?[\s\w\‘\’\,\'\(\)\:\-]+】?)\s(\d+)")
EXTRACT_ARTICLE_WITH_CHAPTER = re.compile(r"(제\s*\d+\s*조의\s*\d{1,2})(【?[\s\w\‘\’\,\'\(\)\:\-]+】?)\s(\d+)")
EXTRACT_SEPARATE_SHEET = re.compile(r"(\[별표\s*\d+\])\s*(【?[\s\w\‘\’\,\'\(\)\:\-]+】?)\s(\d+)")

EXCLUDE_INDEX = re.compile(r"^\s*제\s*\d+조\s*\(|제\s\d+\s$|취급방침|제\d+호")


def read_pdf(file_path: str) -> str:
    """
    PDF 파일 읽기 함수
    """
    reader = PdfReader(file_path)
    text = ""
    pages = reader.pages
    for page in pages:
        text += page.extract_text()
    return (text, pages)


def extract_index(text: str) -> str:
    """
    목차 추출 함수
    """
    text = REPLACE_WHITESPACE.sub(" ", text)
    text = re.sub(r"\】(\d+)", r"】 \1", text)
    return EXTRACT_INDEX.findall(text)


def filter_index(index: list[str]) -> list[str]:
    """
    목차 필터링 함수
    """
    # 실제 목차만 필터링하는 추가 로직
    filtered_index = []
    for item in index:
        # 목차 형식 검증, 제[0-9]+관 또는 제[0-9]+조로 시작하고 숫자로 끝나는지
        if INDEX_START_PATTERN.search(item) is None or INDEX_END_PATTERN.search(item) is None:
            continue
        
        # "제[0-9]+조"로 시작하고 "("로 시작하는 목차 제거, "제 [0-9]+" 으로 끝나는 목차 제거
        if EXCLUDE_INDEX.search(item):
            continue

        filtered_index.append(item.strip())
    return filtered_index


def get_article_from_index(indexes: list[str]) -> list[tuple[str, str, str]]:
    """
    목차 조문, 페이지 추출 함수
    """
    def get_article(article_title: str, item: str) -> tuple[str, str, str]:
        return (article_title, f"{item[1]} {item[2].replace('【', '[').replace('】', ']').strip()}", item[3])
    
    articles = []
    for item in indexes:
        article_title = re.sub(r"\s*\d+\s*$", "", item)
        if match := EXTRACT_ARTICLE.match(item):
            articles.append(get_article(article_title, match))
        elif match := EXTRACT_ARTICLE_WITH_CHAPTER.match(item):
            articles.append(get_article(article_title, match))
        elif match := EXTRACT_SEPARATE_SHEET.match(item):
            articles.append(get_article(article_title, match))
    return articles


def get_safe_content(content: str) -> str:
    """
    안전한 콘텐츠 추출 함수
    """
    # 특수문자와 제어문자 제거
    content = re.sub(r"[\x00-\x1F\x7F-\x9F\uf000-\uffff]", "", content)
    return content.strip()


def process_index(text: str) -> list[str]:
    """
    목차 처리 함수
    """
    indexes = extract_index(text)
    filtered_indexes = filter_index(indexes)
    return get_article_from_index(filtered_indexes)


def process_page(page_params: list[str]) -> json:
    """
    페이지 조문 내용 추출 함수
    """
    return json.dumps(get_article_from_page(page_params), ensure_ascii=False)


def get_article_from_page(page_info: list[str]) -> list[object]:
    """
    페이지 조문 내용 추출 함수
    """
    company_name, category, insurance_name, insurance_type, sales_date, index_title, file_path, start_page, end_page = page_info
    articles = []
    
    # 목차 순회
    prev_article_number = 0
    chapter_title = None
    for loop_index, (origin_title, article_title, page_number) in enumerate(page_indexes):
        if int(page_number) < start_page:
            continue
        if int(page_number) > end_page:
            break
        if match := re.match("^제(\d+)관", origin_title.strip()):
            current_article_number = int(match[1])
            if current_article_number < prev_article_number:
                break
            prev_article_number = current_article_number
            chapter_title = origin_title
            
        # 다음 목차 조문 존재 여부 확인
        exists_next_page = loop_index+1 < len(page_indexes)
        next_start_page_number = int(page_indexes[loop_index+1][2]) if exists_next_page else end_page
        next_article_title = page_indexes[loop_index+1][0] if exists_next_page else None

        print("next_article_title", next_article_title)
        
        # 페이지 조문 내용 추출, 줄바꿈 제거
        content = ""
        for page in pages[int(page_number)-1:next_start_page_number]:
            content += page.extract_text()
        content = REPLACE_WHITESPACE.sub(" ", content)
        
        # content 조문 내용 추출
        if next_article_title:
            article_start_index = content.find(origin_title)
            next_article_start_index = content.find(next_article_title)
            if next_article_start_index >= 0:
                content = content[article_start_index:next_article_start_index]
            else:
                content = content[article_start_index:]
        else:
            # next_article_title 없는 경우 현재 목차 조문 시작 페이지부터 끝 페이지까지 조문 내용 추출
            content = content[content.find(origin_title):]

        if content:
            # 추출 데이터 추가
            articles.append({
                "company_name": company_name,
                "category": category,
                "insurance_name": insurance_name,
                "insurance_type": insurance_type,
                "sales_date": sales_date,
                "index_title": index_title,
                "file_path": file_path,
                "chapter_title": chapter_title,
                "article_title": article_title,
                "article_content": get_safe_content(content),
                "page_number": int(page_number)
            })
    return articles


text, pages = read_pdf(file_path)
page_indexes = process_index(text)

page_params = [company_name, category, insurance_name, insurance_type, sales_date, index_title, file_path, start_page, end_page]
page_contents = process_page(page_params)


"""
[json 예시]
{
    "company_name": "농협생명보험", 
    "category": "암보험", 
    "insurance_name": "369뉴테크NH암보험", 
    "insurance_type": "무배당", 
    "sales_date": "2025-01", 
    "index_title": "369뉴테크NH암보험 |무배당|_2404 주계약 약관", 
    "file_path": "/Users/woojinlee/Desktop/ai_insurance_bot/김백현_농협생명보험_흥국생명보험_KB라이프생명보험/농협생명보험/369뉴테크NH암보험(무배당)/저용량-369뉴테크NH암보험(무배당)_2404_최종_241220.pdf", 
    "article_title": "제1관 목적 및 용어의 정의", 
    "content": "", 
    "page_number": 45
}
"""
# 추출 데이터 저장
with open(f"{company_name}_{category}_{insurance_name}_{insurance_type}_{sales_date}_{index_title}.json", "w+") as f:
    f.write(page_contents)


# 실행 예시
# python3 extract_insurance_article.py --company_name="농협생명보험" --category="암보험" --insurance_type="무배당" --insurance_name="369뉴테크NH암보험" --sales_date="2025-01" --index_title="369뉴테크NH암보험 |무배당|_2404 주계약 약관" --file "/Users/woojinlee/Desktop/ai_insurance_bot/김백현_농협생명보험_흥국생명보험_KB라이프생명보험/농협생명보험/369뉴테크NH암보험(무배당)/저용량-369뉴테크NH암보험(무배당)_2404_최종_241220.pdf" --start_page 45 --end_page 103
