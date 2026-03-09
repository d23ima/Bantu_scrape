import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime
import re
from supabase import create_client, Client
import time

# ---------- CONFIGURATION ----------
# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# List of sources (url, is_rss, name, language)
SOURCES = [
    {"url": "https://www.theafricareport.com/feed", "is_rss": True, "name": "The Africa Report"},
    {"url": "https://www.jeuneafrique.com/rss", "is_rss": True, "name": "Jeune Afrique"},
    {"url": "https://mg.co.za/feed", "is_rss": True, "name": "Mail & Guardian"},
    {"url": "https://www.news24.com/feeds", "is_rss": True, "name": "News24"},
    {"url": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf", "is_rss": True, "name": "AllAfrica"},
    {"url": "https://www.bbc.com/news/world/africa", "is_rss": False, "name": "BBC Africa"},  # will scrape homepage
    # Add more sources (up to 20-30) following the pattern
]

# Positive keywords (expand as needed)
POSITIVE_KEYWORDS = [
    "launch", "funding", "breakthrough", "peace", "award", "discovery",
    "partnership", "investment", "innovation", "success", "milestone",
    "agreement", "treaty", "election", "progress", "growth", "expansion",
    "opening", "inauguration", "celebration", "victory", "win", "record",
    "signed", "deal", "cooperation", "development", "improvement"
]

# Official domains (for original source tracing)
OFFICIAL_DOMAINS = [
    "gov.", ".gov", "statehouse", "presidency", "parliament",
    "au.int", "afdb.org", "un.org", "africa-union", "ecowas",
    "comesa.int", "eac.int", "igad.int", "sadc.int"
]

# ---------- HELPER FUNCTIONS ----------
def is_positive(title, content):
    text = (title + " " + content).lower()
    for kw in POSITIVE_KEYWORDS:
        if kw in text:
            return True
    return False

def extract_original_source(article_url, article_content):
    """Look for links to official domains in the article content."""
    soup = BeautifulSoup(article_content, 'html.parser')
    for link in soup.find_all('a', href=True):
        href = link['href']
        for dom in OFFICIAL_DOMAINS:
            if dom in href:
                # Found an official link – return it (simplified: first match)
                return href
    return None

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def article_exists(url):
    result = supabase.table("articles").select("id").eq("url", url).execute()
    return len(result.data) > 0

def save_article(article):
    supabase.table("articles").insert(article).execute()

def fetch_rss_entries(feed_url):
    feed = feedparser.parse(feed_url)
    entries = []
    for entry in feed.entries[:10]:  # limit to 10 per source to avoid overload
        title = entry.get("title", "")
        link = entry.get("link", "")
        published = entry.get("published_parsed")
        if published:
            published_dt = datetime(*published[:6])
        else:
            published_dt = datetime.now()
        summary = entry.get("summary", "")[:500]  # short summary
        # fetch full content (optional, but helpful for positivity check)
        try:
            resp = requests.get(link, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            # get main text (simplified: all paragraph text)
            paras = soup.find_all('p')
            content = " ".join([p.get_text() for p in paras])
        except:
            content = summary
        entries.append({
            "title": title,
            "url": link,
            "published_at": published_dt.isoformat(),
            "summary": summary,
            "content": content
        })
    return entries

def scrape_homepage_links(source_url, source_name):
    """For non-RSS sources, scrape article links from homepage."""
    try:
        resp = requests.get(source_url, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = []
        # naive: find all <a> tags with href that look like article links
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('/') or href.startswith(source_url):
                full_url = href if href.startswith('http') else requests.compat.urljoin(source_url, href)
                # avoid duplicates and non-article pages (this is heuristic)
                if len(href) > 30 and ('article' in href or 'story' in href or 'news' in href):
                    links.append(full_url)
        # limit to first 10 unique links
        unique_links = list(set(links))[:10]
        entries = []
        for link in unique_links:
            try:
                art_resp = requests.get(link, timeout=10)
                art_soup = BeautifulSoup(art_resp.text, 'html.parser')
                title = art_soup.find('h1').get_text() if art_soup.find('h1') else "No title"
                # get paragraphs
                paras = art_soup.find_all('p')
                content = " ".join([p.get_text() for p in paras])
                published = datetime.now()  # can't easily get date without parsing; fallback
                entries.append({
                    "title": title[:200],
                    "url": link,
                    "published_at": published.isoformat(),
                    "summary": content[:500],
                    "content": content
                })
            except:
                continue
        return entries
    except Exception as e:
        print(f"Error scraping {source_url}: {e}")
        return []

# ---------- MAIN LOOP ----------
def main():
    for source in SOURCES:
        print(f"Processing {source['name']}...")
        if source["is_rss"]:
            entries = fetch_rss_entries(source["url"])
        else:
            entries = scrape_homepage_links(source["url"], source["name"])

        for entry in entries:
            # check if already in DB
            if article_exists(entry["url"]):
                continue

            # positivity check
            if not is_positive(entry["title"], entry.get("content", "")):
                continue

            # try to trace original source
            primary_url = extract_original_source(entry["url"], entry.get("content", ""))
            if not primary_url:
                primary_url = entry["url"]  # fallback

            article_data = {
                "title": entry["title"],
                "url": entry["url"],
                "source_name": source["name"],
                "published_at": entry["published_at"],
                "summary": entry["summary"],
                "content": entry.get("content", "")[:10000],  # limit length
                "primary_source_url": primary_url
            }

            # save to supabase
            save_article(article_data)

            # send telegram notification
            msg = f"<b>{entry['title']}</b>\n"
            msg += f"Source: {source['name']}\n"
            msg += f"Original: {primary_url}\n"
            msg += f"{entry['summary']}..."
            send_telegram(msg)

            # be gentle with rate limits
            time.sleep(1)

if __name__ == "__main__":
    main()
