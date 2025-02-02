import discord
import cloudscraper
import json
import os
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from discord.ext import commands

# ----- 환경 변수 로드 -----
load_dotenv()
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")  # 디스코드 봇 토큰
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

WATCHLIST_FILE = "watchlist.json"
watchlist = []
search_results = {}  # 사용자별 검색 결과 저장 (유저 ID -> 선수 리스트)

intents = discord.Intents.default()
intents.message_content = True  # 메시지 읽기 활성화

bot = commands.Bot(command_prefix="!", intents=intents)

# --- watchlist 로드 및 저장 ---
def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_watchlist():
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, indent=2, ensure_ascii=False)

# --- Futbin 검색 ---
def search_futbin_players(query):
    scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
    url = "https://www.futbin.com/players/search"
    params = {"targetPage": "PLAYER_PAGE", "query": query, "year": "25", "evolutions": "false"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/110.0.0.0 Safari/537.36"}
    
    response = scraper.get(url, headers=headers, params=params)
    try:
        return response.json()
    except json.JSONDecodeError:
        return None

# --- 선수 가격 가져오기 ---
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

# --- 디스코드 봇 명령어 ---
@bot.event
async def on_ready():
    print(f"✅ {bot.user} 봇이 온라인입니다!")

@bot.command(name="선수검색", description="Futbin에서 선수를 검색합니다.")
async def search_player(ctx, player_name: str):
    results = search_futbin_players(player_name)
    if not results:
        await ctx.send(f"❌ '{player_name}'에 대한 검색 결과가 없습니다.")
        return

    search_results[ctx.author.id] = results[:10]  # 최대 10개 저장

    embed = discord.Embed(title=f"🔎 '{player_name}' 검색 결과 (가격 제외)", color=0x00ff00)
    for idx, player in enumerate(results[:10]):  
        name = player.get("name", "N/A")
        version = player.get("version", "N/A")
        rating = player.get("ratingSquare", {}).get("rating", "N/A")

        embed.add_field(name=f"{idx + 1}. {name} (⭐{rating}) {version}",
                        value="🔍 가격 확인: `!선수선택 번호` 입력",
                        inline=False)

    embed.set_footer(text="원하는 선수의 가격을 보려면 !선수선택 번호 를 입력하세요.")
    await ctx.send(embed=embed)

@bot.command(name="선수선택", description="선수 가격을 조회하고 워치리스트에 추가할 수 있습니다.")
async def select_player(ctx, index: int):
    user_id = ctx.author.id
    if user_id not in search_results or not search_results[user_id]:
        await ctx.send("❌ 먼저 `!선수검색 선수이름` 을 실행하세요!")
        return

    if index < 1 or index > len(search_results[user_id]):
        await ctx.send(f"❌ 잘못된 번호입니다! (1 ~ {len(search_results[user_id])} 사이의 숫자를 입력하세요.)")
        return

    selected_player = search_results[user_id][index - 1]
    name = selected_player.get("name", "N/A")
    player_url = "https://www.futbin.com" + selected_player.get("location", {}).get("url", "")

    # 현재 가격 가져오기
    price = get_player_price(player_url)
    price_text = f"{price} 코인" if price else "가격 정보 없음"

    embed = discord.Embed(title=f"💰 {name} 가격 확인", color=0xffd700)
    embed.add_field(name="현재 가격", value=price_text, inline=False)
    embed.add_field(name="상세보기", value=f"[Futbin 페이지]({player_url})", inline=False)
    embed.set_footer(text=f"!워치리스트추가 {index} 희망가 를 입력하여 추가할 수 있습니다.")

    await ctx.send(embed=embed)

@bot.command(name="워치리스트추가", description="선수를 워치리스트에 추가합니다.")
async def add_player(ctx, index: int, price: int):
    user_id = ctx.author.id
    if user_id not in search_results or not search_results[user_id]:
        await ctx.send("❌ 먼저 `!선수검색 선수이름` 을 실행하세요!")
        return

    if index < 1 or index > len(search_results[user_id]):
        await ctx.send(f"❌ 잘못된 번호입니다! (1 ~ {len(search_results[user_id])} 사이의 숫자를 입력하세요.)")
        return

    selected_player = search_results[user_id][index - 1]
    name = selected_player.get("name", "N/A")
    player_url = "https://www.futbin.com" + selected_player.get("location", {}).get("url", "")

    new_player = {"name": name, "url": player_url, "desired_price": price}
    watchlist.append(new_player)
    save_watchlist()

    await ctx.send(f"✅ `{name}` 선수가 {price} 코인 희망 가격으로 워치리스트에 추가되었습니다!")
    del search_results[user_id]

# --- 봇 실행 ---
watchlist = load_watchlist()
bot.run(TOKEN)