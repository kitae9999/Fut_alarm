import cloudscraper
import json
from bs4 import BeautifulSoup

def search_futbin_players(query):
    """
    Futbin 검색 API를 호출하여
    JSON 형태의 선수 목록(배열)을 반환하는 함수
    """
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'mobile': False
        }
    )

    url = "https://www.futbin.com/players/search"
    params = {
        "targetPage": "PLAYER_PAGE",
        "query": query,
        "year": "25",
        "evolutions": "false"
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/110.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9"
    }

    response = scraper.get(url, headers=headers, params=params)
    response.raise_for_status()

    try:
        data = response.json()
        return data  # [{...}, {...}, ...]
    except json.JSONDecodeError:
        print("JSON이 아닌 응답입니다.\n", response.text[:500])
        return None


def get_player_price(url):
    """
    Futbin 선수 상세 페이지에서
    가격을 가져오는 함수 (특정 CSS 셀렉터 이용)
    """
    try:
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )

        response = scraper.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        price_div = soup.select_one(
            "body > div > div.player-page.medium-column.displaying-market-prices > "
            "div.column > div.m-column.relative > div.player-header-section > div > "
            "div.player-header-prices-section > "
            "div.price-box.player-price-not-pc.price-box-original-player > div.column > "
            "div.price.inline-with-icon.lowest-price-1"
        )
        if price_div:
            price_text = price_div.get_text(strip=True).replace(',', '')
            return int(price_text)
        else:
            return "가격 정보를 찾을 수 없습니다."

    except Exception as e:
        return f"에러 발생: {e}"


if __name__ == "__main__":
    # 1) 사용자에게 이름 입력받기
    player_name = input("검색할 선수 이름을 입력하세요: ")

    # 2) Futbin 검색
    results = search_futbin_players(player_name)
    if not results:
        print("검색 결과가 없거나 오류가 발생했습니다.")
        exit()

    # 3) 검색 결과 출력
    print(f"\n=== '{player_name}' 검색 결과 ===")
    for idx, player_info in enumerate(results):
        # ratingSquare 내부의 rating 추출
        rating_square = player_info.get("ratingSquare", {})
        rating_value = rating_square.get("rating", "N/A")

        print(
            f"{idx}. "
            f"id={player_info.get('id', 'N/A')}, "
            f"version={player_info.get('version', 'N/A')}, "
            f"rating={rating_value}, "
            f"name={player_info.get('name', 'N/A')}"
        )

    # 4) 사용자가 선택할 선수 인덱스
    choice_idx = input("\n가격을 확인할 선수 번호를 입력하세요: ")
    try:
        choice_idx = int(choice_idx)
        chosen_player = results[choice_idx]
    except (ValueError, IndexError):
        print("잘못된 인덱스입니다. 프로그램을 종료합니다.")
        exit()

    # 5) 상세 페이지 URL 가져오기
    location_obj = chosen_player.get("location", {})
    relative_url = location_obj.get("url")
    if not relative_url:
        print("선수 상세 URL을 찾을 수 없습니다.")
        exit()

    # 전체 URL
    full_url = "https://www.futbin.com" + relative_url
    print(f"\n선택된 선수 상세 페이지: {full_url}")

    # 6) 선택된 선수 가격 가져오기
    price_result = get_player_price(full_url)
    print(f"선택된 선수의 현재 가격: {price_result} 코인")