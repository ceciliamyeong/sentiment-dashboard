"""
Reddit PRAW 수집 모듈
"""
from datetime import datetime, timezone


SUBREDDITS = ["CryptoCurrency", "Bitcoin", "ethereum", "solana", "CryptoMarkets"]


class RedditCollector:

    def __init__(self, client_id: str, client_secret: str, coins: dict):
        import praw
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="crypto_sentiment/1.0",
        )
        self.coins = coins

    def collect(self, coin: str, limit: int = 150) -> list[dict]:
        keywords = [k.lower() for k in self.coins[coin]]
        results  = []

        for sub in SUBREDDITS:
            try:
                for post in self.reddit.subreddit(sub).hot(limit=limit):
                    if any(k in post.title.lower() for k in keywords):
                        influence = max(1, post.score + int(post.num_comments * 0.5))
                        results.append({
                            "source":     "reddit",
                            "text":       post.title,
                            "influence":  influence,
                            "created_at": datetime.fromtimestamp(
                                post.created_utc, tz=timezone.utc).isoformat(),
                        })
            except Exception as e:
                print(f"[Reddit/{sub}] Error: {e}")

        return results
