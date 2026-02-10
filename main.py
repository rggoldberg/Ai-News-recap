"""
Weekly AI News Recap -- Monday Morning Email
=============================================
Automated pipeline: RSS feeds + AI Twitter -> Claude API -> email digest.
Runs via GitHub Actions every Monday at 7am EST.

Built by Ryan using AI-assisted development (Claude).
"""

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
from urllib.parse import urlparse

load_dotenv()

# -- Config --------------------------------------------------------------------

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")  # Gmail: use App Password
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)

# How many days back to look for news
LOOKBACK_DAYS = 7

# -- News Sources (28 feeds across 7 categories) ------------------------------

RSS_FEEDS = [

    # -- Enterprise AI / Salesforce --------------------------------------------
    {"name": "Salesforce Blog", "url": "https://www.salesforce.com/blog/feed", "category": "salesforce"},
    {"name": "Salesforce AI Blog", "url": "https://www.salesforce.com/blog/ai/feed", "category": "salesforce"},
    {"name": "Salesforce Developers", "url": "https://developer.salesforce.com/blogs/feed", "category": "salesforce"},
    {"name": "Salesforce Engineering", "url": "https://engineering.salesforce.com/feed/", "category": "salesforce"},
    {"name": "Microsoft AI Blog", "url": "https://blogs.microsoft.com/ai/feed/", "category": "enterprise_ai"},
    {"name": "AWS ML Blog", "url": "https://aws.amazon.com/blogs/machine-learning/feed/", "category": "enterprise_ai"},

    # -- Anthropic / Claude ----------------------------------------------------
    {"name": "Anthropic Blog", "url": "https://www.anthropic.com/feed.xml", "category": "anthropic"},

    # -- Frontier AI Labs ------------------------------------------------------
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "category": "frontier"},
    {"name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/", "category": "frontier"},
    {"name": "Meta AI Blog", "url": "https://ai.meta.com/blog/rss/", "category": "frontier"},
    {"name": "DeepMind Blog", "url": "https://deepmind.google/blog/rss.xml", "category": "frontier"},
    {"name": "Mistral AI Blog", "url": "https://mistral.ai/feed.xml", "category": "frontier"},

    # -- AI Dev Tools / Vibe Coding --------------------------------------------
    {"name": "HN Best - AI/LLM/Agents", "url": "https://hnrss.org/best?q=AI+OR+LLM+OR+Claude+OR+cursor+OR+agent", "category": "dev_tools"},
    {"name": "HN Best - Vibe Coding", "url": "https://hnrss.org/best?q=vibe+coding+OR+agentic+coding+OR+AI+coding", "category": "dev_tools"},
    {"name": "GitHub Blog", "url": "https://github.blog/feed/", "category": "dev_tools"},

    # -- Major AI News ---------------------------------------------------------
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "category": "general_ai"},
    {"name": "The Verge - AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "category": "general_ai"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab", "category": "general_ai"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "category": "general_ai"},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "category": "general_ai"},
    {"name": "Wired AI", "url": "https://www.wired.com/feed/tag/ai/latest/rss", "category": "general_ai"},

    # -- Consulting / Strategy -------------------------------------------------
    {"name": "Deloitte AI Insights", "url": "https://www2.deloitte.com/us/en/insights/focus/cognitive-technologies.rss.xml", "category": "consulting"},
    {"name": "McKinsey AI", "url": "https://www.mckinsey.com/rss/topic/artificial-intelligence.rss", "category": "consulting"},
    {"name": "HBR Technology", "url": "https://hbr.org/topic/subject/technology-and-analytics.rss", "category": "consulting"},

    # -- Thought Leaders / Substacks -------------------------------------------
    {"name": "Simon Willison", "url": "https://simonwillison.net/atom/everything/", "category": "thought_leadership"},
    {"name": "Import AI (Jack Clark)", "url": "https://importai.substack.com/feed", "category": "thought_leadership"},
    {"name": "The Batch (Andrew Ng)", "url": "https://www.deeplearning.ai/the-batch/feed/", "category": "thought_leadership"},
    {"name": "One Useful Thing (Ethan Mollick)", "url": "https://www.oneusefulthing.org/feed", "category": "thought_leadership"},
    {"name": "Ahead of AI (Sebastian Raschka)", "url": "https://magazine.sebastianraschka.com/feed", "category": "thought_leadership"},
]


# -- AI Twitter / X Tracking ---------------------------------------------------
# Key AI accounts whose posts often signal where things are heading.
# We use multiple RSS bridge services as fallbacks since they go up and down.

AI_TWITTER_ACCOUNTS = [
    # Lab leaders and researchers
    {"handle": "sama", "name": "Sam Altman (OpenAI)"},
    {"handle": "demaborya", "name": "Dario Amodei (Anthropic)"},
    {"handle": "ylecun", "name": "Yann LeCun (Meta)"},
    {"handle": "kaborya", "name": "Karina Nguyen (Anthropic)"},
    {"handle": "DrJimFan", "name": "Jim Fan (NVIDIA)"},
    {"handle": "svpino", "name": "Santiago (ML eng)"},
    {"handle": "swyx", "name": "swyx (AI eng)"},
    {"handle": "emaborya", "name": "Emad Mostaque"},
    # Dev tools / vibe coding voices
    {"handle": "mcaborya", "name": "Amanda Askell (Anthropic)"},
    {"handle": "karpathy", "name": "Andrej Karpathy"},
    {"handle": "alexaborya", "name": "Alex Albert (Anthropic)"},
    # AI commentary
    {"handle": "EthanMollick", "name": "Ethan Mollick"},
    {"handle": "emollick", "name": "Ethan Mollick (alt)"},
    {"handle": "bindureddy", "name": "Bindu Reddy (Abacus.AI)"},
]

# Nitter/RSS bridge instances to try (these rotate availability)
TWITTER_RSS_BRIDGES = [
    "https://nitter.privacydev.net/{handle}/rss",
    "https://nitter.poast.org/{handle}/rss",
    "https://nitter.woodland.cafe/{handle}/rss",
    "https://twiiit.com/{handle}/rss",
]

# Strict timeout for bridge requests (seconds)
BRIDGE_TIMEOUT = 4


def _fetch_feed_with_timeout(url, timeout=BRIDGE_TIMEOUT):
    """Fetch an RSS feed URL with a strict timeout using requests first."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AINewsBot/1.0)"},
        )
        if resp.status_code != 200:
            return None
        return feedparser.parse(resp.content)
    except (requests.Timeout, requests.ConnectionError, requests.RequestException):
        return None
    except Exception:
        return None


def _probe_bridges():
    """
    Quick probe: find the first working Nitter bridge by testing one account.
    Returns the working bridge template or None if all are dead.
    """
    test_handle = "karpathy"  # popular account, likely to have content
    for bridge_template in TWITTER_RSS_BRIDGES:
        url = bridge_template.format(handle=test_handle)
        print(f"  Probing {bridge_template.split('//{')[0]}//...")
        feed = _fetch_feed_with_timeout(url, timeout=3)
        if feed and feed.entries:
            print(f"  Found working bridge!")
            return bridge_template
    return None


def fetch_twitter_discourse(lookback_days=LOOKBACK_DAYS):
    """
    Fetch recent posts from key AI Twitter accounts via RSS bridges.
    Probes for a working bridge first, then fetches all accounts through it.
    If no bridge works, returns empty (the Reddit/HN fallback covers us).
    """
    cutoff = datetime.now() - timedelta(days=lookback_days)
    tweets = []

    # Step 1: Find a working bridge (fast fail if none work)
    working_bridge = _probe_bridges()
    if not working_bridge:
        print("  No working Nitter bridge found. Skipping direct Twitter feeds.")
        return tweets

    # Step 2: Fetch all accounts through the working bridge
    for account in AI_TWITTER_ACCOUNTS:
        try:
            url = working_bridge.format(handle=account["handle"])
            feed = _fetch_feed_with_timeout(url)

            if not feed or not feed.entries:
                continue

            for entry in feed.entries[:5]:
                published = None
                for date_field in ["published_parsed", "updated_parsed"]:
                    if hasattr(entry, date_field) and getattr(entry, date_field):
                        published = datetime(*getattr(entry, date_field)[:6])
                        break

                if published and published < cutoff:
                    continue

                text = entry.get("title", entry.get("summary", ""))
                text = re.sub(r"<[^>]+>", "", text)[:500]

                # Skip retweets and very short posts
                if text.startswith("RT @") or len(text) < 30:
                    continue

                tweets.append({
                    "author": account["name"],
                    "handle": "@" + account["handle"],
                    "text": text,
                    "url": entry.get("link", ""),
                    "published": published.isoformat() if published else None,
                })

        except Exception:
            continue

    print(f"Fetched {len(tweets)} tweets from AI Twitter accounts")
    return tweets


def fetch_twitter_via_search_feeds():
    """
    Alternative: use HN/Reddit RSS for Twitter-adjacent AI discourse.
    These capture the most viral AI tweets that get reshared.
    Always works regardless of Nitter status.
    """
    search_feeds = [
        {
            "name": "Reddit r/LocalLLaMA Hot",
            "url": "https://www.reddit.com/r/LocalLLaMA/hot/.rss?limit=10",
        },
        {
            "name": "Reddit r/MachineLearning Hot",
            "url": "https://www.reddit.com/r/MachineLearning/hot/.rss?limit=10",
        },
        {
            "name": "Reddit r/artificial Hot",
            "url": "https://www.reddit.com/r/artificial/hot/.rss?limit=10",
        },
        {
            "name": "HN AI Discussions",
            "url": "https://hnrss.org/best?q=GPT+OR+Claude+OR+Gemini+OR+Llama+OR+AGI&comments=50",
        },
    ]

    discourse_items = []
    cutoff = datetime.now() - timedelta(days=LOOKBACK_DAYS)

    for feed_info in search_feeds:
        try:
            feed = _fetch_feed_with_timeout(feed_info["url"], timeout=5)
            if not feed or not feed.entries:
                continue
            for entry in feed.entries[:8]:
                published = None
                for date_field in ["published_parsed", "updated_parsed"]:
                    if hasattr(entry, date_field) and getattr(entry, date_field):
                        published = datetime(*getattr(entry, date_field)[:6])
                        break

                if published and published < cutoff:
                    continue

                title = entry.get("title", "")
                text = entry.get("summary", entry.get("description", ""))
                text = re.sub(r"<[^>]+>", "", text)[:400]

                discourse_items.append({
                    "source": feed_info["name"],
                    "title": title,
                    "text": text,
                    "url": entry.get("link", ""),
                    "published": published.isoformat() if published else None,
                })
        except Exception as e:
            print(f"WARNING: Failed to fetch {feed_info['name']}: {e}")

    print(f"Fetched {len(discourse_items)} items from AI community discourse")
    return discourse_items


# -- Image Extraction ----------------------------------------------------------

def extract_image_from_entry(entry):
    """Try to pull an image URL from an RSS entry using multiple strategies."""

    # Strategy 1: media:content or media:thumbnail (most RSS feeds)
    media_content = entry.get("media_content", [])
    if media_content:
        for media in media_content:
            url = media.get("url", "")
            if url and any(url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
                return url
            if url and media.get("medium") == "image":
                return url

    media_thumb = entry.get("media_thumbnail", [])
    if media_thumb:
        return media_thumb[0].get("url", "")

    # Strategy 2: enclosure (common in podcasts and some blogs)
    enclosures = entry.get("enclosures", [])
    for enc in enclosures:
        if enc.get("type", "").startswith("image/"):
            return enc.get("href", enc.get("url", ""))

    # Strategy 3: first <img> tag in the summary/content HTML
    content_html = entry.get("summary", "")
    if not content_html and entry.get("content"):
        content_html = entry.get("content", [{}])[0].get("value", "")
    if content_html:
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_html)
        if img_match:
            img_url = img_match.group(1)
            if img_url.startswith("http"):
                return img_url

    return ""


def fetch_og_image(article_url):
    """Fetch the Open Graph image from an article page as a fallback."""
    try:
        resp = requests.get(
            article_url,
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AINewsBot/1.0)"},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return ""

        # Only scan the first 20KB to keep it fast
        head_html = resp.text[:20000]

        # Look for og:image
        og_match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            head_html,
            re.IGNORECASE,
        )
        if og_match:
            return og_match.group(1)

        # Try reverse attribute order
        og_match_rev = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            head_html,
            re.IGNORECASE,
        )
        if og_match_rev:
            return og_match_rev.group(1)

    except Exception:
        pass

    return ""


def validate_image_url(url):
    """Quick check that an image URL is likely valid and not a tracker pixel."""
    if not url or not url.startswith("http"):
        return ""
    skip_patterns = ["1x1", "pixel", "tracking", "spacer", "blank", "feedburner"]
    url_lower = url.lower()
    for pattern in skip_patterns:
        if pattern in url_lower:
            return ""
    return url


# -- Fetch News ----------------------------------------------------------------

def fetch_rss_articles(lookback_days=LOOKBACK_DAYS):
    """Pull articles from all RSS feeds within the lookback window."""
    cutoff = datetime.now() - timedelta(days=lookback_days)
    articles = []

    for feed_info in RSS_FEEDS:
        try:
            feed = _fetch_feed_with_timeout(feed_info["url"], timeout=8)
            if not feed:
                print(f"WARNING: Timeout fetching {feed_info['name']}")
                continue
            for entry in feed.entries:
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
                link = entry.get("link", "")

                # Extract image from RSS entry
                image_url = validate_image_url(extract_image_from_entry(entry))

                # Extract domain for display
                domain = ""
                if link:
                    parsed = urlparse(link)
                    domain = parsed.netloc.replace("www.", "")

                articles.append({
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "source": feed_info["name"],
                    "category": feed_info["category"],
                    "published": published.isoformat() if published else None,
                    "image_url": image_url,
                    "domain": domain,
                })
        except Exception as e:
            print(f"WARNING: Failed to fetch {feed_info['name']}: {e}")

    print(f"Fetched {len(articles)} articles from {len(RSS_FEEDS)} feeds")
    return articles


def fetch_newsapi_articles(lookback_days=LOOKBACK_DAYS):
    """
    Optional: Pull from NewsAPI for broader coverage.
    Free key at https://newsapi.org (100 req/day).
    Set NEWSAPI_KEY in your secrets to enable.
    """
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        return []

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
                url = a.get("url", "")
                parsed = urlparse(url)
                domain = parsed.netloc.replace("www.", "") if url else ""
                articles.append({
                    "title": a.get("title", ""),
                    "summary": a.get("description", "")[:500],
                    "url": url,
                    "source": a.get("source", {}).get("name", "NewsAPI"),
                    "category": "newsapi",
                    "published": a.get("publishedAt"),
                    "image_url": validate_image_url(a.get("urlToImage", "")),
                    "domain": domain,
                })
        except Exception as e:
            print(f"WARNING: NewsAPI query failed: {e}")

    print(f"Fetched {len(articles)} articles from NewsAPI")
    return articles


# -- OG Image Enrichment -------------------------------------------------------

def enrich_with_og_images(articles, max_fetches=15):
    """
    For articles missing images, try to fetch OG images from the article page.
    Limited to max_fetches to keep runtime reasonable.
    """
    fetched = 0
    for a in articles:
        if a.get("image_url"):
            continue
        if fetched >= max_fetches:
            break
        if not a.get("url"):
            continue

        og_img = fetch_og_image(a["url"])
        if og_img:
            a["image_url"] = validate_image_url(og_img)
            fetched += 1

    print(f"Enriched {fetched} articles with OG images")
    return articles


# -- Deduplicate ---------------------------------------------------------------

def deduplicate(articles):
    """Remove duplicate articles by URL and similar titles."""
    seen_urls = set()
    seen_titles = set()
    unique = []

    for a in articles:
        url = a["url"].rstrip("/")
        title_key = a["title"].lower().strip()[:80]

        if url in seen_urls or title_key in seen_titles:
            continue

        seen_urls.add(url)
        seen_titles.add(title_key)
        unique.append(a)

    print(f"Deduplicated: {len(articles)} -> {len(unique)} articles")
    return unique


# -- Claude Summarization ------------------------------------------------------

SYSTEM_PROMPT = (
    "You write like a tech-savvy friend texting Ryan his Monday morning AI briefing. "
    "Not a newsletter. Not a corporate digest. More like if a really smart coworker "
    "spent their weekend reading everything and is now catching you up over coffee.\n\n"

    "Ryan's context: Senior consultant at Deloitte, Salesforce functional lead "
    "(AgentForce specifically), obsessed with AI dev tools like Cursor and Claude Code, "
    "and deep into vibe coding. He cares about what's real and what's noise.\n\n"

    "How to write this:\n\n"

    "Open with a cold take. One or two sentences that capture the vibe of the week. "
    "Something like 'Three separate companies launched agent frameworks this week and "
    "none of them can reliably book a flight. Here is what actually mattered.' Not "
    "'Welcome to your weekly AI recap.' Never that.\n\n"

    "Then cover 5-8 stories, grouped by theme. For each one:\n"
    "- Link the headline to the article URL\n"
    "- Show the source name in small gray text\n"
    "- If the article has an image_url, display it (max 500px wide, rounded). "
    "No image_url? Just skip it, no placeholder.\n"
    "- Write 2-4 sentences of actual analysis. Not a summary. Your take. "
    "What does this mean? Who wins? Who's screwed? Be specific: model names, "
    "numbers, benchmarks, which products are affected.\n"
    "- Add a short 'Why this matters for you:' line connecting it to Ryan's world "
    "(Salesforce, consulting, dev tools, career).\n\n"

    "After the stories, write a 'What AI Twitter was fighting about' section. "
    "You'll get community discourse data from Reddit and HN (and tweets if available). "
    "Pick 3-4 of the spiciest debates or most interesting threads. Who said what, "
    "why people cared, your read on it. This should feel like gossip, not analysis.\n\n"

    "Close with 'Stuff I'm watching' -- 2-3 quick one-liners about next week.\n\n"

    "HARD RULES:\n"
    "- Never use em-dashes. Not one. Use commas, periods, or just start a new sentence.\n"
    "- Banned phrases: 'in a move that', 'the landscape', 'it remains to be seen', "
    "'represents a significant', 'paradigm shift', 'game-changer', 'raises important "
    "questions', 'double-edged sword', 'poised to', 'the implications', 'a testament to', "
    "'in an increasingly'. If you catch yourself writing like a press release, stop.\n"
    "- Do not start consecutive paragraphs with the same word.\n"
    "- Contractions always. 'It is' -> 'it's'. 'Do not' -> 'don't'.\n"
    "- No emoji in body text. Section headers can have one if it feels natural.\n"
    "- Vary your rhythm. Short sentence. Then a longer one that unpacks the idea "
    "with some specifics. Then another short one. Like a real person writes.\n\n"

    "HTML: Output email-safe HTML, inline styles only. Max-width 600px, centered, "
    "white content on #f5f5f5 background. System font stack. Body text #333, "
    "links #2563eb, source text #999 at 13px. 'Why this matters' callout gets a "
    "subtle blue-left-border box. Keep it clean and mobile-friendly. No tables for layout."
)

USER_PROMPT_TEMPLATE = (
    "Here are {article_count} AI news articles from this week ({date_range}).\n\n"
    "ARTICLES:\n{articles_json}\n\n"
    "---\n\n"
    "AI TWITTER / COMMUNITY BUZZ ({tweet_count} tweets, "
    "{discourse_count} Reddit/HN threads):\n\n"
    "TWEETS:\n{tweets_json}\n\n"
    "COMMUNITY:\n{discourse_json}\n\n"
    "---\n\n"
    "Write the email. Sound like a person, not a newsletter. "
    "No em-dashes anywhere."
)


def generate_recap(articles, tweets, discourse):
    """Send articles + tweets + discourse to Claude for a rich email digest."""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Trim to avoid token limits
    articles = articles[:60]
    tweets = tweets[:40]
    discourse = discourse[:20]

    date_end = datetime.now().strftime("%B %d, %Y")
    date_start = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%B %d")

    user_prompt = USER_PROMPT_TEMPLATE.format(
        article_count=len(articles),
        date_range=date_start + " - " + date_end,
        articles_json=json.dumps(articles, indent=2, default=str),
        tweet_count=len(tweets),
        tweets_json=json.dumps(tweets, indent=2, default=str),
        discourse_count=len(discourse),
        discourse_json=json.dumps(discourse, indent=2, default=str),
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    html_content = response.content[0].text

    # Strip markdown code fences if Claude wraps the HTML
    html_content = re.sub(r"^```html?\s*\n?", "", html_content)
    html_content = re.sub(r"\n?```\s*$", "", html_content)

    # Final safety pass: replace any em-dashes that slipped through
    html_content = html_content.replace("\u2014", "--")  # em-dash
    html_content = html_content.replace("\u2013", "-")   # en-dash
    html_content = html_content.replace("\u2012", "-")   # figure dash

    print(f"Generated recap ({len(html_content)} chars)")
    return html_content


# -- Email ---------------------------------------------------------------------

def send_email(html_content):
    """Send the recap email via SMTP (Gmail-compatible)."""
    today = datetime.now().strftime("%B %d, %Y")
    subject = "AI Recap // " + today

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

    print(f"Email sent to {EMAIL_TO}")


def save_local(html_content):
    """Save a local copy for preview/debugging."""
    os.makedirs("output", exist_ok=True)
    filename = "output/recap_" + datetime.now().strftime("%Y%m%d") + ".html"
    with open(filename, "w") as f:
        f.write(html_content)
    print(f"Saved local copy: {filename}")


# -- Main ----------------------------------------------------------------------

def main():
    print("=" * 60)
    print("AI News Recap -- " + datetime.now().strftime("%A, %B %d %Y"))
    print("=" * 60)

    # 1. Fetch from all sources
    print("\n[1/6] Fetching RSS articles...")
    articles = fetch_rss_articles()
    articles += fetch_newsapi_articles()

    if not articles:
        print("ERROR: No articles found. Check your feeds and internet connection.")
        return

    # 2. Deduplicate
    print("\n[2/6] Deduplicating...")
    articles = deduplicate(articles)

    # 3. Enrich with OG images where missing
    print("\n[3/6] Enriching with images...")
    articles = enrich_with_og_images(articles)

    # 4. Fetch AI Twitter discourse
    print("\n[4/6] Fetching AI Twitter discourse...")
    tweets = fetch_twitter_discourse()
    discourse = fetch_twitter_via_search_feeds()

    # 5. Generate recap with Claude
    print("\n[5/6] Generating recap with Claude...")
    html_recap = generate_recap(articles, tweets, discourse)

    # 6. Save locally (always)
    save_local(html_recap)

    # 7. Send email (if configured)
    print("\n[6/6] Sending email...")
    if SMTP_USER and SMTP_PASSWORD and EMAIL_TO:
        send_email(html_recap)
    else:
        print("Email not configured. Check .env file. Local copy saved.")

    print("\nDone!")


if __name__ == "__main__":
    main()
