from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import re

app = Flask(__name__)

REGISTRATION = "FA23-BAI-040"
NEWS_SOURCE = "Roze News"
BASE_URL = "https://en.rozenews.com.pk"
SEARCH_URL = "https://en.rozenews.com.pk/?s={keyword}"


def get_chrome_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    return driver


def summarize(text, max_sentences=4):
    text = text.strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    summary = " ".join(sentences[:max_sentences])
    return summary if summary else text[:500]


def scrape_roze_news(keyword):
    driver = get_chrome_driver()
    result = {
        "registration": REGISTRATION,
        "newssource": NEWS_SOURCE,
        "keyword": keyword,
        "url": "",
        "summary": ""
    }
    try:
        search_url = SEARCH_URL.format(keyword=keyword)
        driver.get(search_url)
        time.sleep(4)

        # Get first article URL
        article_url = None
        selectors = [
            "article h2 a", "article h3 a", ".post-title a",
            "h2.entry-title a", "h3.entry-title a", ".entry-title a",
            "main article a",
        ]
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    href = el.get_attribute("href")
                    if href and BASE_URL in href and "/wp-content/" not in href:
                        article_url = href
                        break
                if article_url:
                    break
            except Exception:
                continue

        if not article_url:
            links = driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href") or ""
                if (BASE_URL in href
                        and "/wp-content/" not in href
                        and "/category/" not in href
                        and href != BASE_URL + "/"
                        and len(href) > len(BASE_URL) + 5):
                    article_url = href
                    break

        if not article_url:
            result["summary"] = "No article found for this keyword."
            return result

        result["url"] = article_url

        # Extract preview/excerpt text from search results page (avoids bot block)
        summary_text = ""
        excerpt_selectors = [
            "article .entry-summary",
            "article .entry-content",
            "article p",
            ".post-excerpt",
            ".excerpt",
        ]
        for sel in excerpt_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                texts = [el.text.strip() for el in elements if el.text.strip() and len(el.text.strip()) > 30]
                if texts:
                    summary_text = " ".join(texts[:3])
                    break
            except Exception:
                continue

        # If still empty, try visiting article with extra headers
        if not summary_text or len(summary_text) < 50:
            try:
                driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {
                    "headers": {
                        "Referer": "https://www.google.com/",
                        "Accept-Language": "en-US,en;q=0.9",
                    }
                })
                driver.get(article_url)
                time.sleep(4)
                paragraphs = driver.find_elements(By.TAG_NAME, "p")
                texts = [p.text.strip() for p in paragraphs
                         if p.text.strip() and len(p.text.strip()) > 40
                         and "cookie" not in p.text.lower()
                         and "problem" not in p.text.lower()]
                if texts:
                    summary_text = " ".join(texts[:5])
            except Exception:
                pass

        result["summary"] = summarize(summary_text) if summary_text else "Could not extract article content."

    except Exception as e:
        result["summary"] = f"Error: {str(e)}"
    finally:
        driver.quit()

    return result


@app.route("/get", methods=["GET"])
def get_news():
    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return jsonify({"error": "keyword query parameter is required"}), 400
    return jsonify(scrape_roze_news(keyword))


@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "running",
        "registration": REGISTRATION,
        "newssource": NEWS_SOURCE,
        "usage": "GET /get?keyword=<your_keyword>"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000, debug=False)
