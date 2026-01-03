#!/usr/bin/env python3
"""
Goodreads shelf scraper - exports all books from public shelves to JSON
"""
import requests
from bs4 import BeautifulSoup
import json
import time
import sys
from urllib.parse import urljoin

USER_ID = "76529348"
BASE_URL = f"https://www.goodreads.com/review/list/{USER_ID}"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def fetch_shelf(shelf_name, page=1):
    """Fetch a page from a specific shelf"""
    params = {
        'shelf': shelf_name,
        'page': page,
        'per_page': 100,
        'print': 'true'  # Gets simplified HTML
    }
    
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Error fetching {shelf_name} page {page}: {e}", file=sys.stderr)
        return None

def parse_books(html):
    """Parse book data from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    books = []
    
    for row in soup.find_all('tr', class_='bookalike review'):
        try:
            book = {}
            
            # Book ID
            book_id = row.get('id', '').replace('review_', '')
            book['id'] = book_id
            
            # Title and link
            title_tag = row.find('td', class_='field title')
            if title_tag:
                link = title_tag.find('a')
                if link:
                    book['title'] = link.get('title', '').strip()
                    book['url'] = urljoin('https://www.goodreads.com', link.get('href', ''))
            
            # Author
            author_tag = row.find('td', class_='field author')
            if author_tag:
                author_link = author_tag.find('a')
                if author_link:
                    book['author'] = author_link.text.strip()
            
            # ISBN
            isbn_tag = row.find('td', class_='field isbn')
            if isbn_tag:
                isbn_div = isbn_tag.find('div', class_='value')
                if isbn_div:
                    book['isbn'] = isbn_div.text.strip()
            
            # Rating
            rating_tag = row.find('td', class_='field rating')
            if rating_tag:
                stars = rating_tag.find_all('span', class_='staticStar p10')
                book['rating'] = len([s for s in stars if 'p10' in s.get('class', [])])
            
            # Shelves
            shelves_tag = row.find('td', class_='field shelves')
            if shelves_tag:
                shelf_links = shelves_tag.find_all('a')
                book['shelves'] = [s.text.strip() for s in shelf_links]
            
            # Date read
            date_tag = row.find('td', class_='field date_read')
            if date_tag:
                date_div = date_tag.find('div', class_='value')
                if date_div:
                    book['date_read'] = date_div.text.strip()
            
            # Date added
            date_added_tag = row.find('td', class_='field date_added')
            if date_added_tag:
                date_div = date_added_tag.find('div', class_='value')
                if date_div:
                    book['date_added'] = date_div.text.strip()
            
            # Average rating
            avg_rating_tag = row.find('td', class_='field avg_rating')
            if avg_rating_tag:
                rating_div = avg_rating_tag.find('div', class_='value')
                if rating_div:
                    book['avg_rating'] = rating_div.text.strip()
            
            # Number of pages
            pages_tag = row.find('td', class_='field num_pages')
            if pages_tag:
                pages_div = pages_tag.find('div', class_='value')
                if pages_div:
                    book['pages'] = pages_div.text.strip()
            
            # Review/notes
            review_tag = row.find('td', class_='field review')
            if review_tag:
                review_div = review_tag.find('div', class_='value')
                if review_div:
                    spans = review_div.find_all('span', style='display:none')
                    if spans:
                        book['review'] = spans[0].text.strip()
            
            if book.get('title'):
                books.append(book)
                
        except Exception as e:
            print(f"Error parsing book row: {e}", file=sys.stderr)
            continue
    
    return books

def scrape_all_shelves():
    """Scrape all shelves"""
    shelves = ['read', 'currently-reading', 'to-read']
    all_books = []
    
    for shelf in shelves:
        print(f"Scraping {shelf}...", file=sys.stderr)
        page = 1
        
        while True:
            html = fetch_shelf(shelf, page)
            if not html:
                break
            
            books = parse_books(html)
            if not books:
                break
            
            all_books.extend(books)
            print(f"  Page {page}: {len(books)} books", file=sys.stderr)
            
            # Check if there's a next page
            soup = BeautifulSoup(html, 'html.parser')
            next_link = soup.find('a', class_='next_page')
            if not next_link or 'disabled' in next_link.get('class', []):
                break
            
            page += 1
            time.sleep(2)  # Be nice to Goodreads
    
    return all_books

if __name__ == '__main__':
    print("Starting Goodreads scraper...", file=sys.stderr)
    books = scrape_all_shelves()
    
    # Output JSON to stdout
    result = {
        'user_id': USER_ID,
        'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'total_books': len(books),
        'books': books
    }
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nTotal books scraped: {len(books)}", file=sys.stderr)