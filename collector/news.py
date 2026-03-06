"""
뉴스 수집 모듈 (NewsAPI + RSS 피드 fallback)
"""
import requests
import feedparser


RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
]


class NewsCollector:

    def __init__(self, api_key: str, coins: dict):
        self.api_key = api_key
        self.coins   = coins

    def collect(self, coin: str) -> list[dict]:
        results  = []
        keywords = [k.lower() for k in self.coins[coin]]

        # ① NewsAPI
        if self.api_key:
            try:
                params = {
                    "q":        self.coins[coin][0],
                    "language": "en",
                    "sortBy":   "publishedAt",
                    "pageSize": 50,
                    "apiKey":   self.api_key,
                }
                articles = requests.get("https://newsapi.org/v2/everything",
                                        params=params, timeout=10
                                        ).json().get("articles", [])
                for a in articles:
                    title = a.get("title") or ""
                    results.append({
                        "source":     "news",
                        "text":       title,
                        "influence":  5,
                        "created_at": a.get("publishedAt", ""),
                    })
            except Exception as e:
                print(f"[NewsAPI] Error: {e}")

        # ② RSS fallback
        for feed_url in RSS_FEEDS:
            try:
                for entry in feedparser.parse(feed_url).entries[:30]:
                    title = entry.get("title", "")
                    if any(k in title.lower() for k in keywords):
                        results.append({
                            "source":     "news",
                            "text":       title,
                            "influence":  5,
                            "created_at": entry.get("published", ""),
                        })
            except Exception as e:
                print(f"[RSS] Error: {e}")

        return results
