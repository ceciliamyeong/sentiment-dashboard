from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CC_KEY = os.environ.get("CRYPTOCOMPARE_API_KEY")
SAN_KEY = os.environ.get("SANTIMENT_API_KEY")

SANTIMENT_URL = "https://api.santiment.net/graphql"

SLUGS = [
    "bitcoin", "ethereum", "solana", "binance-coin",
    "xrp", "dogecoin", "cardano", "avalanche", "chainlink", "polkadot"
]

# Reddit 서브레딧 목록 (크립토 + 금융)
SUBREDDITS = [
    "CryptoCurrency", "Bitcoin", "ethereum", "investing",
    "finance", "wallstreetbets", "stocks", "economy"
]

# ── 뉴스 API (CryptoCompare) ──────────────────────────────────
@app.get("/api/news")
async def get_news():
    if not CC_KEY:
        return {"error": "CRYPTOCOMPARE_API_KEY not set"}
    url = f"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&api_key={CC_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, timeout=10)
        return r.json()

# ── 코인 소셜 데이터 (Santiment) ───────────────────────────────
@app.get("/api/coins")
async def get_coins():
    if not SAN_KEY:
        return {"error": "SANTIMENT_API_KEY not set"}

    headers = {"Authorization": f"Apikey {SAN_KEY}"}
    results = []

    async with httpx.AsyncClient() as client:
        for slug in SLUGS:
            query = """
            {
              projectBySlug(slug: "%s") {
                name
                ticker
                socialVolume24h: aggregatedTimeseriesData(
                  metric: "social_volume_total"
                  from: "utc_now-1d"
                  to: "utc_now"
                  aggregation: SUM
                )
                socialVolume7d: aggregatedTimeseriesData(
                  metric: "social_volume_total"
                  from: "utc_now-7d"
                  to: "utc_now"
                  aggregation: SUM
                )
                sentiment: aggregatedTimeseriesData(
                  metric: "sentiment_balance_total"
                  from: "utc_now-1d"
                  to: "utc_now"
                  aggregation: AVG
                )
              }
            }
            """ % slug

            r = await client.post(
                SANTIMENT_URL,
                json={"query": query},
                headers=headers,
                timeout=15
            )
            data = r.json()
            if "errors" in data:
                continue

            project_list = data.get("data", {}).get("projectBySlug", [])
            if not project_list:
                continue

            p = project_list[0] if isinstance(project_list, list) else project_list
            vol_24h = p.get("socialVolume24h") or 0
            vol_7d  = p.get("socialVolume7d") or 0
            avg_7d  = vol_7d / 7 if vol_7d else 0
            change  = ((vol_24h - avg_7d) / avg_7d * 100) if avg_7d else 0
            # sentiment_balance_total 은 실제로 양수/음수 큰 값일 수 있음
            # 0 기준으로 50% 중립, 양수면 강세, 음수면 약세로 변환
            raw_sent = p.get("sentiment") or 0
            if raw_sent > 0:
                sentiment_pct = min(95, round(50 + (raw_sent / (abs(raw_sent) + 1)) * 45))
            elif raw_sent < 0:
                sentiment_pct = max(5, round(50 + (raw_sent / (abs(raw_sent) + 1)) * 45))
            else:
                sentiment_pct = 50

            results.append({
                "slug": slug,
                "name": p.get("name", slug),
                "symbol": p.get("ticker", slug.upper()),
                "social_volume_24h": round(vol_24h),
                "sentiment": sentiment_pct,
                "change_pct": round(change, 1),
            })

    results.sort(key=lambda x: x["social_volume_24h"], reverse=True)
    return {"data": results}

# ── 트렌딩 (Santiment) ─────────────────────────────────────────
@app.get("/api/trending")
async def get_trending():
    if not SAN_KEY:
        return {"error": "SANTIMENT_API_KEY not set"}

    query = """
    {
      getTrendingWords(from: "utc_now-1d", to: "utc_now", interval: "1d", size: 10) {
        datetime
        topWords { word score }
      }
    }
    """
    headers = {"Authorization": f"Apikey {SAN_KEY}"}
    async with httpx.AsyncClient() as client:
        r = await client.post(SANTIMENT_URL, json={"query": query}, headers=headers, timeout=15)
        return r.json()

# ── 금융 RSS 피드 (Reuters + Yahoo Finance) ───────────────────
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import email.utils

RSS_FEEDS = [
    {"url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines", "source": "MarketWatch", "category": "finance"},
    {"url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "source": "WSJ Markets", "category": "finance"},
    {"url": "https://rss.app/feeds/crypto-news.xml", "source": "Crypto News", "category": "crypto"},
    {"url": "https://cointelegraph.com/rss", "source": "CoinTelegraph", "category": "crypto"},
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "source": "CoinDesk", "category": "crypto"},
    {"url": "https://feeds.feedburner.com/TheHackersNews", "source": "Finance News", "category": "finance"},
]

@app.get("/api/reddit")
async def get_finance_feed():
    all_posts = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FinanceDashboard/1.0)"}

    async with httpx.AsyncClient() as client:
        for feed in RSS_FEEDS:
            try:
                r = await client.get(feed["url"], headers=headers, timeout=8, follow_redirects=True)
                if r.status_code != 200:
                    continue
                root = ET.fromstring(r.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                items = root.findall(".//item") or root.findall(".//atom:entry", ns)
                for item in items[:4]:
                    title = item.findtext("title") or item.findtext("atom:title", namespaces=ns) or ""
                    link = item.findtext("link") or item.findtext("atom:link", namespaces=ns) or ""
                    pub = item.findtext("pubDate") or item.findtext("atom:published", namespaces=ns) or ""

                    # 시간 파싱
                    try:
                        if pub:
                            dt = email.utils.parsedate_to_datetime(pub)
                            secs = int((datetime.now(timezone.utc) - dt).total_seconds())
                            if secs < 3600:
                                time_str = f"{secs//60}분 전"
                            elif secs < 86400:
                                time_str = f"{secs//3600}시간 전"
                            else:
                                time_str = f"{secs//86400}일 전"
                        else:
                            time_str = "최근"
                    except Exception:
                        time_str = "최근"

                    title = title.strip()
                    if title:
                        all_posts.append({
                            "subreddit": feed["source"],
                            "title": title,
                            "score": 0,
                            "comments": 0,
                            "url": link.strip(),
                            "category": feed["category"],
                            "time": time_str,
                        })
            except Exception:
                continue

    return {"data": all_posts[:24]}

# ── 헬스체크 ───────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "cc_key": "set" if CC_KEY else "missing",
        "san_key": "set" if SAN_KEY else "missing",
        "reddit": "no-auth-required",
    }
