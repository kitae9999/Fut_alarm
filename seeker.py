import cloudscraper
import json
import os
import schedule
import time
import requests
from bs4 import BeautifulSoup

# --- python-dotenv를 이용해 .env 파일 로드 ---
from dotenv import load_dotenv
load_dotenv()  # .env 파일을 읽어 환경 변수로 등록

# ----- [환경 변수] Discord Webhook URL 불러오기 -----
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", None)
# None이면 웹훅 기능 미사용

WATCHLIST_FILE = "watchlist.json"
watchlist = []

def load_watchlist():
    """
    watchlist.json 파일이 존재하면 로드, 없으면 빈 리스트 반환
    """
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    return []

def save_watchlist():
    """
    현재 watchlist 리스트를 watchlist.json 파일에 저장
    """
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, indent=2, ensure_ascii=False)


def send_discord_message(content):
    """
    Discord 웹훅을 이용해 message(문자열)를 지정된 채널에 전송
    (DISCORD_WEBHOOK_URL이 설정된 경우에만)
    """
    if not DISCORD_WEBHOOK_URL:
        # 환경 변수에 설정이 안 되어 있으면 simply return
        return

    payload = {
        "content": content
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[Discord Webhook 에러] {e}")


def search_futbin_players(query):
    """
    Futbin 검색 API를 호출하여
    JSON 형태의 선수 목록(배열)을 반환
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
    Futbin 선수 상세 페이지에서 가격을 가져옴 (특정 CSS 셀렉터 이용)
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
            return None  # 가격 정보를 찾지 못함

    except Exception as e:
        print(f"[에러 발생] {e}")
        return None


def show_watchlist():
    """
    현재 워치리스트 출력
    """
    if not watchlist:
        print("\n[안내] 워치리스트가 비어있습니다.")
    else:
        print("\n=== 현재 워치리스트 ===")
        for idx, item in enumerate(watchlist):
            print(
                f"{idx}. {item['name']} / "
                f"URL: {item['url']} / "
                f"희망가격: {item['desired_price']}"
            )


def check_watchlist_prices():
    """
    (스케줄러에 의해 주기적으로 또는 수동으로) 
    워치리스트 내 모든 선수의 현재 가격을 확인:
    희망 가격 이하이면 콘솔에 안내 + 디스코드 웹훅 메시지
    """
    if not watchlist:
        print("[안내] 워치리스트가 비어 있어, 가격 확인을 건너뜁니다.")
        return

    print("\n[Info] 워치리스트를 확인합니다...")
    for player in watchlist:
        current_price = get_player_price(player["url"])
        if current_price is None:
            print(f" - {player['name']}: 가격 정보를 가져오지 못했습니다.")
            continue

        print(f" - {player['name']} 현재 가격: {current_price} (희망: {player['desired_price']})")

        if current_price <= player["desired_price"]:
            msg = (f"[알림] {player['name']} 가격이 {current_price} (희망가 {player['desired_price']}) 이하!")
            # 콘솔 출력
            print(msg)
            # Discord 전송 (환경 변수에 Webhook이 설정되어 있다면)
            send_discord_message(msg + f"\n{player['url']}")


def search_and_add_player():
    """
    1) 사용자에게 선수 이름 입력
    2) 검색 결과 중 하나 선택 → 가격 확인
    3) 워치리스트에 희망가격과 함께 추가
    """
    player_name = input("\n검색할 선수 이름을 입력하세요: ")
    results = search_futbin_players(player_name)
    if not results:
        print("[오류] 검색 결과가 없거나 요청 실패.")
        return

    # 검색 결과 출력
    print(f"\n=== '{player_name}' 검색 결과 ===")
    for idx, player_info in enumerate(results):
        rating_square = player_info.get("ratingSquare", {})
        rating_value = rating_square.get("rating", "N/A")

        print(
            f"{idx}. "
            f"id={player_info.get('id', 'N/A')}, "
            f"version={player_info.get('version', 'N/A')}, "
            f"rating={rating_value}, "
            f"name={player_info.get('name', 'N/A')}"
        )

    # 인덱스 선택
    choice_idx = input("\n가격을 확인할 선수 번호를 입력하세요: ")
    try:
        choice_idx = int(choice_idx)
        chosen_player = results[choice_idx]
    except (ValueError, IndexError):
        print("[오류] 잘못된 인덱스.")
        return

    # 상세 페이지 URL
    location_obj = chosen_player.get("location", {})
    relative_url = location_obj.get("url")
    if not relative_url:
        print("[오류] 선수 상세 URL이 없습니다.")
        return

    full_url = "https://www.futbin.com" + relative_url
    print(f"\n선택된 선수 상세 페이지: {full_url}")

    # 현재 가격
    price_result = get_player_price(full_url)
    if price_result is None:
        print("[오류] 가격 정보를 찾을 수 없습니다.")
    else:
        print(f"선택된 선수의 현재 가격: {price_result} 코인")

    # 워치리스트에 추가
    add_choice = input("\n이 선수를 워치리스트에 추가하시겠습니까? (y/n): ")
    if add_choice.lower() == 'y':
        try:
            desired_price = int(input("희망 가격을 입력하세요 (숫자만): "))
        except ValueError:
            print("잘못된 입력입니다. 숫자를 입력해야 합니다.")
            return

        new_item = {
            "name": chosen_player.get('name', 'N/A'),
            "url": full_url,
            "desired_price": desired_price
        }
        watchlist.append(new_item)
        save_watchlist()
        print("[안내] 워치리스트에 추가하였습니다.")


def main_menu_loop():
    """
    메인 메뉴: 
     1) 선수 검색 후 워치리스트 추가
     2) 워치리스트 보기
     3) 워치리스트 가격 확인(즉시)
     4) 프로그램 종료
    """
    while True:
        print("\n=== 메뉴 ===")
        print("1. 선수 검색 및 워치리스트 추가")
        print("2. 워치리스트 보기")
        print("3. 워치리스트 가격 확인 (즉시)")
        print("4. 종료")
        cmd = input("선택: ")

        if cmd == '1':
            search_and_add_player()
        elif cmd == '2':
            show_watchlist()
        elif cmd == '3':
            check_watchlist_prices()
        elif cmd == '4':
            print("[안내] 프로그램을 종료합니다.")
            break
        else:
            print("[오류] 잘못된 입력입니다.")

def main():
    global watchlist
    # 1) watchlist 로드
    watchlist = load_watchlist()
    if watchlist:
        print(f"[안내] watchlist.json 로드 완료 (총 {len(watchlist)}명).")
    else:
        print("[안내] 기존 워치리스트가 없습니다.")

    # 2) 30분마다 자동 확인
    schedule.every(30).minutes.do(check_watchlist_prices)

    while True:
        main_menu_loop()  # 메뉴 실행 (메뉴에서 4번 종료 선택 시 break)

        # 메뉴 4번 실행 → while 루프 탈출
        break

    # 여기서는 프로그램 종료
    # (원한다면 별도 쓰레드나 무한 루프로 schedule.run_pending()을 계속 돌려 백그라운드 구동 가능)
    # while True:
    #     schedule.run_pending()
    #     time.sleep(1)

if __name__ == "__main__":
    main()