#!/usr/bin/env python3
"""
Goodreads shelf scraper - exports all books from public shelves to JSON using public RSS feeds
"""
import requests
import json
import time
import sys
import warnings
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# Suppress BeautifulSoup's XML-parsed-as-HTML warnings since we use html.parser for standard library compatibility
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

USER_ID = "76529348"
BASE_URL = f"https://www.goodreads.com/review/list_rss/{USER_ID}"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def clean_cdata(text):
    """Strip raw CDATA wrapper if it exists (some parsers don't strip it automatically for all tags)"""
    if not text:
        return ""
    text = text.strip()
    if text.startswith("<![CDATA[") and text.endswith("]]>"):
        text = text[9:-3].strip()
    return text

def format_date(date_str):
    """Parse RSS RFC-822 date and format as 'MMM DD, YYYY' to match original backup style, e.g. 'Feb 25, 2021'"""
    if not date_str or not isinstance(date_str, str):
        return "not set"
    try:
        cleaned = clean_cdata(date_str)
        dt = parsedate_to_datetime(cleaned)
        return dt.strftime('%b %d, %Y')
    except Exception:
        return "not set"

def fetch_shelf(shelf_name, page=1):
    """Fetch a page from a specific shelf RSS feed"""
    params = {
        'shelf': shelf_name,
        'page': page,
    }
    
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Error fetching {shelf_name} page {page}: {e}", file=sys.stderr)
        return None

def parse_books(xml_content, main_shelf):
    """Parse book data from RSS XML"""
    if not xml_content:
        return []
    soup = BeautifulSoup(xml_content, 'html.parser')
    items = soup.find_all('item')
    books = []
    
    for item in items:
        try:
            book = {}
            
            # Book ID
            book_id_tag = item.find('book_id')
            book_id = clean_cdata(book_id_tag.text if book_id_tag else "")
            if not book_id:
                book_tag = item.find('book')
                if book_tag:
                    book_id = book_tag.get('id', '')
            
            if not book_id:
                continue
                
            book['id'] = book_id
            
            # Title
            title_tag = item.find('title')
            book['title'] = clean_cdata(title_tag.text if title_tag else "")
            
            # URL
            # Default to reconstructed robust URL
            book['url'] = f"https://www.goodreads.com/book/show/{book_id}"
            
            # Try to extract the full slugged URL from description if available
            desc_tag = item.find('description')
            if desc_tag:
                desc_soup = BeautifulSoup(desc_tag.text, 'html.parser')
                link_tag = desc_soup.find('a')
                if link_tag and link_tag.get('href'):
                    href = link_tag.get('href')
                    if '?' in href:
                        href = href.split('?')[0]
                    book['url'] = href
            
            # Author
            author_tag = item.find('author_name')
            book['author'] = clean_cdata(author_tag.text if author_tag else "")
            
            # ISBN
            isbn_tag = item.find('isbn')
            book['isbn'] = clean_cdata(isbn_tag.text if isbn_tag else "")
            
            # Rating
            rating_tag = item.find('user_rating')
            try:
                book['rating'] = int(rating_tag.text.strip()) if rating_tag else 0
            except ValueError:
                book['rating'] = 0
            
            # Shelves
            shelves_tag = item.find('user_shelves')
            shelves = []
            if shelves_tag and shelves_tag.text.strip():
                shelves = [clean_cdata(s) for s in shelves_tag.text.split(',') if s.strip()]
            
            # Ensure the main shelf is included in the shelves list (just like original)
            if main_shelf not in shelves:
                shelves.append(main_shelf)
            book['shelves'] = shelves
            
            # Date read
            read_tag = item.find('user_read_at')
            book['date_read'] = format_date(read_tag.text if read_tag else "")
            
            # Date added
            added_tag = item.find('user_date_added')
            book['date_added'] = format_date(added_tag.text if added_tag else "")
            
            # Average rating
            avg_rating_tag = item.find('average_rating')
            book['avg_rating'] = clean_cdata(avg_rating_tag.text if avg_rating_tag else "")
            
            # Number of pages
            pages = "not set"
            book_tag = item.find('book')
            if book_tag:
                pages_tag = book_tag.find('num_pages')
                if pages_tag and pages_tag.text.strip():
                    pages = f"{clean_cdata(pages_tag.text)}\n        pp"
            book['pages'] = pages
            
            # Review/notes
            review_tag = item.find('user_review')
            book['review'] = clean_cdata(review_tag.text if review_tag else "")
            
            if book.get('title'):
                books.append(book)
                
        except Exception as e:
            print(f"Error parsing book: {e}", file=sys.stderr)
            continue
            
    return books

def scrape_all_shelves():
    """Scrape all shelves using RSS pagination"""
    shelves = ['read', 'currently-reading', 'to-read']
    all_books = []
    
    # Track book IDs to avoid duplicating books that might belong to multiple shelves
    seen_ids = set()
    
    for shelf in shelves:
        print(f"Scraping {shelf}...", file=sys.stderr)
        page = 1
        
        while page <= 100:  # Safe upper limit to prevent any potential infinite loops
            xml_content = fetch_shelf(shelf, page)
            if not xml_content:
                break
            
            books = parse_books(xml_content, shelf)
            if not books:
                break
            
            new_books_count = 0
            for book in books:
                if book['id'] not in seen_ids:
                    seen_ids.add(book['id'])
                    all_books.append(book)
                    new_books_count += 1
                else:
                    # If we've already seen this book, it could be on multiple shelves (e.g. read and a custom shelf).
                    # Let's find it and merge the shelf lists to make sure it lists all shelves!
                    for existing_book in all_books:
                        if existing_book['id'] == book['id']:
                            for s in book['shelves']:
                                if s not in existing_book['shelves']:
                                    existing_book['shelves'].append(s)
                            break
            
            print(f"  Page {page}: parsed {len(books)} books ({new_books_count} new)", file=sys.stderr)
            
            # If the page has fewer than 100 items, we have reached the end of the shelf
            if len(books) < 100:
                break
                
            page += 1
            time.sleep(2)  # Respectful rate limiting
            
    return all_books

if __name__ == '__main__':
    print("Starting Goodreads scraper (RSS Mode)...", file=sys.stderr)
    books = scrape_all_shelves()
    
    # Output JSON to stdout
    result = {
        'user_id': USER_ID,
        'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'total_books': len(books),
        'books': books
    }
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nTotal unique books scraped: {len(books)}", file=sys.stderr)