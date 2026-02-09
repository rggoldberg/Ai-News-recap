# “””
Weekly AI News Recap — Monday Morning Email

Automated pipeline: RSS feeds → Claude API → email digest.
Runs via GitHub Actions every Monday at 7am EST.

Built by Ryan using AI-assisted development (Claude).
“””

import os
import json
import re
import smtplib
import feedparser
import requests
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv(“ANTHROPIC_API_KEY”)
SMTP_HOST = os.getenv(“SMTP_HOST”, “smtp.gmail.com”)
SMTP_PORT = int(os.getenv(“SMTP_PORT”, 587))
SMTP_USER = os.getenv(“SMTP_USER”)
SMTP_PASSWORD = os.getenv(“SMTP_PASSWORD”)  # Gmail: use App Password
EMAIL_TO = os.getenv(“EMAIL_TO”)
EMAIL_FROM = os.getenv(“EMAIL_FROM”, SMTP_USER)

# How many days back to look for news

LOOKBACK_DAYS = 7

# ── News Sources (30+ feeds across 6 categories) ─────────────────────────────

RSS_FEEDS = [

```
# ── 🏢 Enterprise AI / Salesforce ─────────────────────────────────────────
{"name": "Salesforce Blog", "url": "https://www.salesforce.com/blog/feed", "category": "salesforce"},
{"name": "Salesforce AI Blog", "url": "https://www.salesforce.com/blog/ai/feed", "category": "salesforce"},
{"name": "Salesforce Developers", "url": "https://developer.salesforce.com/blogs/feed", "category": "salesforce"},
{"name": "Salesforce Engineering", "url": "https://engineering.salesforce.com/feed/", "category": "salesforce"},
{"name": "Microsoft AI Blog", "url": "https://blogs.microsoft.com/ai/feed/", "category": "enterprise_ai"},
{"name": "AWS ML Blog", "url": "https://aws.amazon.com/blogs/machine-learning/feed/", "category": "enterprise_ai"},

# ── 🤖 Anthropic / Claude ─────────────────────────────────────────────────
{"name": "Anthropic Blog", "url": "https://www.anthropic.com/feed.xml", "category": "anthropic"},

# ── 🧪 Frontier AI Labs ───────────────────────────────────────────────────
{"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "category": "frontier"},
{"name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/", "category": "frontier"},
{"name": "Meta AI Blog", "url": "https://ai.meta.com/blog/rss/", "category": "frontier"},
{"name": "DeepMind Blog", "url": "https://deepmind.google/blog/rss.xml", "category": "frontier"},
{"name": "Mistral AI Blog", "url": "https://mistral.ai/feed.xml", "category": "frontier"},

# ── 🛠️ AI Dev Tools / Vibe Coding ─────────────────────────────────────────
{"name": "HN Best - AI/LLM/Agents", "url": "https://hnrss.org/best?q=AI+OR+LLM+OR+Claude+OR+cursor+OR+agent", "category": "dev_tools"},
{"name": "HN Best - Vibe Coding", "url": "https://hnrss.org/best?q=vibe+coding+OR+agentic+coding+OR+AI+coding", "category": "dev_tools"},
{"name": "GitHub Blog", "url": "https://github.blog/feed/", "category": "dev_tools"},

# ── 📰 Major AI News ──────────────────────────────────────────────────────
{"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "category": "general_ai"},
{"name": "The Verge - AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "category": "general_ai"},
{"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab", "category": "general_ai"},
{"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "category": "general_ai"},
{"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "category": "general_ai"},
{"name": "Wired AI", "url": "https://www.wired.com/feed/tag/ai/latest/rss", "category": "general_ai"},

# ── 💼 Consulting / Strategy ──────────────────────────────────────────────
{"name": "Deloitte AI Insights", "url": "https://www2.deloitte.com/us/en/insights/focus/cognitive-technologies.rss.xml", "category": "consulting"},
{"name": "McKinsey AI", "url": "https://www.mckinsey.com/rss/topic/artificial-intelligence.rss", "category": "consulting"},
{"name": "HBR Technology", "url": "https://hbr.org/topic/subject/technology-and-analytics.rss", "category": "consulting"},

# ── 🧠 Thought Leaders / Substacks ────────────────────────────────────────
{"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/", "category": "thought_leadership"},
{"name": "Import AI (Jack Clark)", "url": "https://importai.substack.com/feed", "category": "thought_leadership"},
{"name": "The Batch (Andrew Ng)", "url": "https://www.deeplearning.ai/the-batch/feed/", "category": "thought_leadership"},
{"name": "One Useful Thing (Ethan Mollick)", "url": "https://www.oneusefulthing.org/feed", "category": "thought_leadership"},
{"name": "Ahead of AI (Sebastian Raschka)", "url": "https://magazine.sebastianraschka.com/feed", "category": "thought_leadership"},
```

]

# ── Fetch News ────────────────────────────────────────────────────────────────

def fetch_rss_articles(lookback_days: int = LOOKBACK_DAYS) -> list[dict]:
“”“Pull articles from all RSS feeds within the lookback window.”””
cutoff = datetime.now() - timedelta(days=lookback_days)
articles = []

```
for feed_info in RSS_FEEDS:
    try:
        feed = feedparser.parse(feed_info["url"])
        for entry in feed.entries:
            # Parse published date
            published = None
            for date_field in ["published_parsed", "updated_parsed"]:
                if hasattr(entry, date_field) and getattr(entry, date_field):
                    published = datetime(*getattr(entry, date_field)[:6])
                    break

            if published and published < cutoff:
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            summary = re.sub(r"<[^>]+>", "", summary)[:500]

            articles.append({
                "title": title,
                "summary": summary,
                "url": entry.get("link", ""),
                "source": feed_info["name"],
                "category": feed_info["category"],
                "published": published.isoformat() if published else None,
            })
    except Exception as e:
        print(f"⚠️  Failed to fetch {feed_info['name']}: {e}")

print(f"📰 Fetched {len(articles)} articles from {len(RSS_FEEDS)} feeds")
return articles
```

def fetch_newsapi_articles(lookback_days: int = LOOKBACK_DAYS) -> list[dict]:
“””
Optional: Pull from NewsAPI for broader coverage.
Free key at https://newsapi.org (100 req/day).
Set NEWSAPI_KEY in your secrets to enable.
“””
api_key = os.getenv(“NEWSAPI_KEY”)
if not api_key:
return []

```
cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
queries = [
    "artificial intelligence enterprise",
    "Salesforce AI AgentForce",
    "Anthropic Claude",
    "AI coding tools agents",
]

articles = []
for query in queries:
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "from": cutoff,
                "sortBy": "relevancy",
                "pageSize": 10,
                "apiKey": api_key,
            },
            timeout=10,
        )
        data = resp.json()
        for a in data.get("articles", []):
            articles.append({
                "title": a.get("title", ""),
                "summary": a.get("description", "")[:500],
                "url": a.get("url", ""),
                "source": a.get("source", {}).get("name", "NewsAPI"),
                "category": "newsapi",
                "published": a.get("publishedAt"),
            })
    except Exception as e:
        print(f"⚠️  NewsAPI query failed: {e}")

print(f"📰 Fetched {len(articles)} articles from NewsAPI")
return articles
```

# ── Deduplicate ───────────────────────────────────────────────────────────────

def deduplicate(articles: list[dict]) -> list[dict]:
“”“Remove duplicate articles by URL and similar titles.”””
seen_urls = set()
seen_titles = set()
unique = []

```
for a in articles:
    url = a["url"].rstrip("/")
    title_key = a["title"].lower().strip()[:80]

    if url in seen_urls or title_key in seen_titles:
        continue

    seen_urls.add(url)
    seen_titles.add(title_key)
    unique.append(a)

print(f"🧹 Deduplicated: {len(articles)} → {len(unique)} articles")
return unique
```

# ── Claude Summarization ──────────────────────────────────────────────────────

SYSTEM_PROMPT = “”“You are an AI news analyst creating a weekly recap email for Ryan,
a senior consultant at Deloitte who works as a functional lead on Salesforce technologies
with a focus on AI (specifically AgentForce). He’s also into AI dev tools (Cursor, Claude Code,
vibe coding), is a Claude Pro power user, and wants to stay sharp on frontier AI developments.

Your job: Read through this week’s AI news articles and produce a structured, scannable
Monday morning email digest.

RULES:

- Be direct and opinionated. Don’t just summarize — tell Ryan what matters and why.
- If something is relevant to his Salesforce/AgentForce work, flag it explicitly with a 🔵 emoji.
- If something affects his consulting practice or Deloitte, call it out with a 💼 emoji.
- If something relates to AI dev tools / vibe coding, flag with a 🛠️ emoji.
- Group by theme, not by source.
- Include 5-10 top stories max. Quality over quantity.
- For each story: 1-2 sentence summary + why it matters for Ryan + link.
- End with a “🔮 What to Watch” section with 2-3 things to keep an eye on next week.
- Keep the tone smart, casual, slightly witty. Not corporate newsletter energy.
- Output clean HTML email format with inline styles only (email-safe, no external CSS).
- Use a clean, modern email layout with good spacing and readability.
- Start with a brief 1-2 sentence “TLDR” of the week’s biggest theme.
  “””

USER_PROMPT_TEMPLATE = “”“Here are {count} AI news articles from the past week ({date_range}).

Please analyze them and create my weekly AI news recap email.

ARTICLES:
{articles_json}
“””

def generate_recap(articles: list[dict]) -> str:
“”“Send articles to Claude and get back a formatted email digest.”””
client = Anthropic(api_key=ANTHROPIC_API_KEY)

```
# Trim articles to avoid token limits
articles = articles[:60]

date_end = datetime.now().strftime("%B %d, %Y")
date_start = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%B %d")

user_prompt = USER_PROMPT_TEMPLATE.format(
    count=len(articles),
    date_range=f"{date_start} – {date_end}",
    articles_json=json.dumps(articles, indent=2, default=str),
)

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": user_prompt}],
)

html_content = response.content[0].text
print(f"✍️  Generated recap ({len(html_content)} chars)")
return html_content
```

# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(html_content: str):
“”“Send the recap email via SMTP (Gmail-compatible).”””
today = datetime.now().strftime(”%B %d, %Y”)
subject = f”🤖 Your AI News Recap — Week of {today}”

```
msg = MIMEMultipart("alternative")
msg["Subject"] = subject
msg["From"] = EMAIL_FROM
msg["To"] = EMAIL_TO

# Plain text fallback
plain_text = re.sub(r"<[^>]+>", "", html_content)
msg.attach(MIMEText(plain_text, "plain"))
msg.attach(MIMEText(html_content, "html"))

with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
    server.starttls()
    server.login(SMTP_USER, SMTP_PASSWORD)
    server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

print(f"📧 Email sent to {EMAIL_TO}")
```

def save_local(html_content: str):
“”“Save a local copy for preview/debugging.”””
os.makedirs(“output”, exist_ok=True)
filename = f”output/recap_{datetime.now().strftime(’%Y%m%d’)}.html”
with open(filename, “w”) as f:
f.write(html_content)
print(f”💾 Saved local copy: {filename}”)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
print(”=” * 60)
print(f”🚀 AI News Recap — {datetime.now().strftime(’%A, %B %d %Y’)}”)
print(”=” * 60)

```
# 1. Fetch from all sources
articles = fetch_rss_articles()
articles += fetch_newsapi_articles()

if not articles:
    print("❌ No articles found. Check your feeds and internet connection.")
    return

# 2. Deduplicate
articles = deduplicate(articles)

# 3. Generate recap with Claude
html_recap = generate_recap(articles)

# 4. Save locally (always)
save_local(html_recap)

# 5. Send email (if configured)
if SMTP_USER and SMTP_PASSWORD and EMAIL_TO:
    send_email(html_recap)
else:
    print("📧 Email not configured — check .env file. Local copy saved.")

print("✅ Done!")
```

if **name** == “**main**”:
main()
