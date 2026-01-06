#!/usr/bin/env python3
"""
IMDB lists-only scraper
For ratings/watchlist: manually export CSV from IMDB once, commit to repo
This script only scrapes custom lists (fast, no rate limit issues)
"""
import requests
from bs4 import BeautifulSoup
import json
import time
import sys
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

USER_ID = "ur48993532"
BASE_URL = "https://www.imdb.com"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}

def fetch_page(url, retries=2):
    """Fetch a page with basic retry"""
    for attempt in range(retries):
        try:
            time.sleep(2)  # Conservative delay
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503 and attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"503 error, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"Error: {url} - {e}", file=sys.stderr)
                return None
        except Exception as e:
            print(f"Error: {url} - {e}", file=sys.stderr)
            return None
    return None

def scrape_single_list(list_id, list_name):
    """Scrape a single list"""
    print(f"  Scraping: {list_name}", file=sys.stderr)
    
    items = []
    page = 1
    
    while True:
        url = f"{BASE_URL}/list/{list_id}/?sort=list_order,asc&mode=detail&page={page}"
        html = fetch_page(url)
        
        if not html:
            break
        
        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.find_all('li', class_=re.compile('ipc-metadata-list-summary-item'))
        
        if not cards:
            cards = soup.find_all('div', class_=re.compile('lister-item'))
        
        if not cards:
            break
        
        for card in cards:
            item = {}
            
            title_link = card.find('a', href=re.compile(r'/title/tt\d+'))
            if title_link:
                href = title_link.get('href', '')
                match = re.search(r'/title/(tt\d+)', href)
                if match:
                    item['imdb_id'] = match.group(1)
                    item['url'] = f"{BASE_URL}/title/{item['imdb_id']}/"
                    
                    title_elem = card.find('h3', class_=re.compile('ipc-title__text'))
                    if not title_elem:
                        title_elem = title_link
                    if title_elem:
                        text = title_elem.get_text(strip=True)
                        item['title'] = re.sub(r'^\d+\.\s*', '', text)
            
            year_span = card.find('span', class_=re.compile('(lister-item-year|dli-title-metadata-item)'))
            if year_span:
                item['year'] = year_span.get_text(strip=True)
            
            rating_span = card.find('span', class_=re.compile('ipc-rating-star--rating'))
            if not rating_span:
                rating_span = card.find('span', class_='ipl-rating-star__rating')
            if rating_span:
                item['rating'] = rating_span.get_text(strip=True)
            
            if item.get('imdb_id'):
                items.append(item)
        
        if len(cards) > 0:
            print(f"    Page {page}: +{len(cards)} (total: {len(items)})", file=sys.stderr)
        
        next_button = soup.find('button', {'aria-label': 'Next'})
        if not next_button or 'disabled' in next_button.get('class', []):
            next_link = soup.find('a', class_='next-page')
            if not next_link:
                break
        
        page += 1
    
    return {
        'list_id': list_id,
        'list_name': list_name,
        'list_url': f"{BASE_URL}/list/{list_id}/",
        'item_count': len(items),
        'items': items
    }

def scrape_custom_lists():
    """Scrape all custom lists"""
    print("Finding custom lists...", file=sys.stderr)
    
    lists = []
    seen_ids = set()
    url = f"{BASE_URL}/user/{USER_ID}/lists"
    html = fetch_page(url)
    
    if not html:
        print("ERROR: Could not fetch lists page", file=sys.stderr)
        return lists
    
    soup = BeautifulSoup(html, 'html.parser')
    list_containers = soup.find_all('div', class_=re.compile('ipc-metadata-list-summary-item'))
    
    list_tasks = []
    for container in list_containers:
        link = container.find('a', href=re.compile(r'/list/ls\d+'))
        if not link:
            continue
            
        list_id_match = re.search(r'/list/(ls\d+)', link.get('href', ''))
        if not list_id_match:
            continue
        
        list_id = list_id_match.group(1)
        if list_id in seen_ids:
            continue
        seen_ids.add(list_id)
        
        title_elem = container.find('h3', class_=re.compile('ipc-title__text'))
        list_name = title_elem.get_text(strip=True) if title_elem else f"List {list_id}"
        list_name = re.sub(r'^\d+\.\s*', '', list_name)
        
        list_tasks.append((list_id, list_name))
    
    print(f"Found {len(list_tasks)} lists\n", file=sys.stderr)
    
    # Scrape lists with limited parallelism
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_to_list = {executor.submit(scrape_single_list, lid, lname): (lid, lname) 
                         for lid, lname in list_tasks}
        
        for future in as_completed(future_to_list):
            try:
                list_data = future.result()
                lists.append(list_data)
                print(f"  ✓ {list_data['list_name']}: {list_data['item_count']} items\n", file=sys.stderr)
            except Exception as e:
                lid, lname = future_to_list[future]
                print(f"  ✗ Error scraping {lname}: {e}\n", file=sys.stderr)
    
    return lists

if __name__ == '__main__':
    print("\n" + "="*60, file=sys.stderr)
    print("IMDB Lists Scraper", file=sys.stderr)
    print("="*60 + "\n", file=sys.stderr)
    
    print("NOTE: This only scrapes custom lists.", file=sys.stderr)
    print("For ratings/watchlist, manually export CSV from IMDB:\n", file=sys.stderr)
    print(f"  1. Ratings:   {BASE_URL}/user/{USER_ID}/ratings", file=sys.stderr)
    print(f"  2. Watchlist: {BASE_URL}/user/{USER_ID}/watchlist", file=sys.stderr)
    print("  3. Click 3 dots (⋮) → Export → Save as CSV\n", file=sys.stderr)
    print("="*60 + "\n", file=sys.stderr)
    
    start_time = time.time()
    
    result = {
        'user_id': USER_ID,
        'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'lists': scrape_custom_lists()
    }
    
    result['total_lists'] = len(result['lists'])
    result['total_items'] = sum(lst['item_count'] for lst in result['lists'])
    
    elapsed = time.time() - start_time
    
    print("\n" + "="*60, file=sys.stderr)
    print(f"Completed in {elapsed:.1f} seconds", file=sys.stderr)
    print(f"Lists: {result['total_lists']}, Items: {result['total_items']}", file=sys.stderr)
    print("="*60 + "\n", file=sys.stderr)
    
    print(json.dumps(result, indent=2, ensure_ascii=False))