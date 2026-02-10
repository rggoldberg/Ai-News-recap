"""
Weekly AI News Recap -- Monday Morning Email
=============================================
Automated pipeline: RSS feeds -> Claude API -> email digest.
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
    content_html = entry.get("summary", entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "")
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

        # Try reverse attribute order (some sites put content before property)
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
    # Skip common tracker/pixel patterns
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
            feed = feedparser.parse(feed_info["url"])
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
    "You are writing a weekly AI news email for Ryan. He is a senior consultant at Deloitte, "
    "functional lead on Salesforce (focused on AgentForce), and deeply into AI dev tools "
    "(Cursor, Claude Code, vibe coding). He reads this every Monday morning with his coffee.\n\n"

    "VOICE AND TONE:\n"
    "- Write like a sharp friend who works in tech and actually reads this stuff, not like "
    "a newsletter robot. Think casual group chat energy meets actual analysis.\n"
    "- Vary your sentence structure. Mix short punchy takes with longer explanations. "
    "Do NOT start every bullet with the same pattern.\n"
    "- Have opinions. Say 'this matters because...' or 'honestly this is overhyped because...'\n"
    "- Use specific details, numbers, and names. Vague summaries are useless.\n"
    "- Do NOT use phrases like: 'in a move that', 'the landscape of', 'it remains to be seen', "
    "'represents a significant', 'in an increasingly', 'the implications are', 'a testament to', "
    "'poised to', 'game-changer', 'paradigm shift', 'ecosystem', 'synergy', 'leverage', "
    "'double-edged sword', 'raises important questions'. These are AI writing tells.\n"
    "- Do NOT start paragraphs with 'This week'. Vary your openings.\n"
    "- Contractions are good. Sentence fragments are fine. Be human.\n\n"

    "DEPTH OF ANALYSIS:\n"
    "- For each story, go beyond 'X company did Y'. Explain the second-order effects.\n"
    "- Connect dots between stories when possible (e.g., 'This is the third agent framework "
    "launch this month -- the market is clearly converging on...').\n"
    "- Include specific numbers, benchmarks, model names, or technical details when available.\n"
    "- For Salesforce/AgentForce stories: be specific about what changed, which clouds/products "
    "are affected, and what it means for implementation teams.\n"
    "- For frontier model releases: mention what improved, by how much, and whether it actually "
    "matters in practice vs. just benchmarks.\n"
    "- For dev tools: note what's actually usable now vs. what's just a demo.\n\n"

    "STRUCTURE:\n"
    "- Start with a 1-2 sentence cold open. No 'welcome to your weekly recap' preamble.\n"
    "- Group 5-10 top stories by theme, not by source.\n"
    "- Each story MUST include:\n"
    "  1. A bold headline that is the article title (linked to the article URL)\n"
    "  2. Source name and domain in small text below the headline\n"
    "  3. An image if one is provided in the article data (use the image_url field). "
    "Display it at max 500px wide, rounded corners, above the summary.\n"
    "  4. 2-4 sentence analysis (not just a summary -- your take on why it matters)\n"
    "  5. A one-line 'So what:' callout in bold that connects it to Ryan's work "
    "(Salesforce, consulting, dev tools, or general career relevance)\n"
    "- End with 'On My Radar' section: 2-3 things to watch next week, written as quick takes.\n\n"

    "HTML FORMAT:\n"
    "- Output clean HTML with inline styles only (email-safe, no external CSS).\n"
    "- Use a max-width of 600px, centered. Background #f5f5f5, content area white.\n"
    "- Font: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif.\n"
    "- Headings in #1a1a1a, body text in #333, links in #2563eb.\n"
    "- Images: max-width 100%, border-radius 8px, margin-bottom 12px. "
    "If no image_url is provided for a story, just skip the image -- do NOT use a placeholder.\n"
    "- Article source line: font-size 13px, color #888.\n"
    "- 'So what' callout: background #f0f7ff, padding 8px 12px, border-left 3px solid #2563eb, "
    "font-size 14px, margin-top 8px.\n"
    "- Clean spacing between stories. Subtle dividers (#eee) between sections.\n"
    "- Mobile-friendly: everything should look good at 375px wide too."
)

USER_PROMPT_TEMPLATE = (
    "Here are {count} AI news articles from the past week ({date_range}).\n\n"
    "Each article includes: title, summary, url, source, category, published date, "
    "image_url (may be empty), and domain.\n\n"
    "Analyze them and write my weekly AI news recap email. Remember: be specific, "
    "have opinions, connect the dots, and include the article links and images.\n\n"
    "ARTICLES:\n{articles_json}"
)


def generate_recap(articles):
    """Send articles to Claude and get back a formatted email digest."""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Trim articles to avoid token limits
    articles = articles[:60]

    date_end = datetime.now().strftime("%B %d, %Y")
    date_start = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%B %d")

    user_prompt = USER_PROMPT_TEMPLATE.format(
        count=len(articles),
        date_range=date_start + " - " + date_end,
        articles_json=json.dumps(articles, indent=2, default=str),
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
    articles = fetch_rss_articles()
    articles += fetch_newsapi_articles()

    if not articles:
        print("ERROR: No articles found. Check your feeds and internet connection.")
        return

    # 2. Deduplicate
    articles = deduplicate(articles)

    # 3. Enrich with OG images where missing
    articles = enrich_with_og_images(articles)

    # 4. Generate recap with Claude
    html_recap = generate_recap(articles)

    # 5. Save locally (always)
    save_local(html_recap)

    # 6. Send email (if configured)
    if SMTP_USER and SMTP_PASSWORD and EMAIL_TO:
        send_email(html_recap)
    else:
        print("Email not configured -- check .env file. Local copy saved.")

    print("Done!")


if __name__ == "__main__":
    main()
