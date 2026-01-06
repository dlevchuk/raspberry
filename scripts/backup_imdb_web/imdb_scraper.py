#!/usr/bin/env python3
"""
IMDB scraper - exports ratings, watchlist, and lists to JSON
Optimized for speed with adaptive delays and batching
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

# Adaptive delay - starts fast, slows down if we hit rate limits
current_delay = 1.0
max_delay = 10.0
consecutive_success = 0

def fetch_page(url, retries=2):
    """Fetch a page with adaptive retry logic"""
    global current_delay, consecutive_success
    
    for attempt in range(retries):
        try:
            time.sleep(current_delay)
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            
            # Success - speed up
            consecutive_success += 1
            if consecutive_success > 5 and current_delay > 1.0:
                current_delay = max(1.0, current_delay * 0.8)
            
            return resp.text
            
        except requests.exceptions.HTTPError as e:
            consecutive_success = 0
            if e.response.status_code == 503:
                # Rate limited - slow down significantly
                current_delay = min(max_delay, current_delay * 2)
                wait_time = current_delay * (attempt + 1)
                print(f"503 error, adjusting delay to {current_delay:.1f}s, waiting {wait_time:.1f}s...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                print(f"Error {e.response.status_code}: {url}", file=sys.stderr)
                return None
        except Exception as e:
            print(f"Error fetching {url}: {e}", file=sys.stderr)
            return None
    
    return None

def parse_title_from_card(card):
    """Parse title data from a card element"""
    title = {}
    
    # Title ID
    title_link = card.find('a', href=re.compile(r'/title/tt\d+'))
    if title_link:
        href = title_link.get('href', '')
        match = re.search(r'/title/(tt\d+)', href)
        if match:
            title['imdb_id'] = match.group(1)
            title['url'] = f"{BASE_URL}/title/{title['imdb_id']}/"
    
    # Title name
    title_text = card.find('h3', class_=re.compile('ipc-title__text'))
    if title_text:
        text = title_text.get_text(strip=True)
        title['title'] = re.sub(r'^\d+\.\s*', '', text)
    
    # Year
    year_span = card.find('span', class_=re.compile('dli-title-metadata-item'))
    if year_span:
        title['year'] = year_span.get_text(strip=True)
    
    # Rating
    rating_span = card.find('span', class_=re.compile('ipc-rating-star--rating'))
    if rating_span:
        title['rating'] = rating_span.get_text(strip=True)
    
    # Your rating
    your_rating = card.find('span', class_=re.compile('ipc-rating-star--base'))
    if your_rating:
        rating_text = your_rating.get_text(strip=True)
        match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
        if match:
            title['user_rating'] = match.group(1)
    
    return title if title.get('imdb_id') else None

def scrape_section(section_type, max_items=None):
    """Generic scraper for ratings/watchlist"""
    print(f"Scraping {section_type}...", file=sys.stderr)
    
    items = []
    start = 1
    page = 1
    
    while True:
        if max_items and len(items) >= max_items:
            break
            
        url = f"{BASE_URL}/user/{USER_ID}/{section_type}/?sort=date_added,desc&mode=detail&start={start}"
        html = fetch_page(url)
        if not html:
            break
        
        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.find_all('li', class_=re.compile('ipc-metadata-list-summary-item'))
        
        if not cards:
            break
        
        for card in cards:
            title = parse_title_from_card(card)
            if title:
                items.append(title)
        
        print(f"  {section_type} page {page}: +{len(cards)} (total: {len(items)})", file=sys.stderr)
        
        # Check for next page
        next_button = soup.find('button', {'aria-label': 'Next'})
        if not next_button or 'disabled' in next_button.get('class', []):
            break
        
        start += 250
        page += 1
    
    return items

def scrape_single_list(list_id, list_name):
    """Scrape a single list - for parallel processing"""
    print(f"  Scraping list: {list_name}", file=sys.stderr)
    
    items = []
    list_page = 1
    
    while True:
        list_url = f"{BASE_URL}/list/{list_id}/?sort=list_order,asc&mode=detail&page={list_page}"
        list_html = fetch_page(list_url)
        
        if not list_html:
            break
        
        list_soup = BeautifulSoup(list_html, 'html.parser')
        cards = list_soup.find_all('li', class_=re.compile('ipc-metadata-list-summary-item'))
        
        if not cards:
            cards = list_soup.find_all('div', class_=re.compile('lister-item'))
        
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
        
        print(f"    {list_name} page {list_page}: +{len(cards)} (total: {len(items)})", file=sys.stderr)
        
        next_button = list_soup.find('button', {'aria-label': 'Next'})
        if not next_button or 'disabled' in next_button.get('class', []):
            next_link = list_soup.find('a', class_='next-page')
            if not next_link:
                break
        
        list_page += 1
    
    return {
        'list_id': list_id,
        'list_name': list_name,
        'list_url': f"{BASE_URL}/list/{list_id}/",
        'items': items
    }

def scrape_custom_lists():
    """Scrape all custom lists in parallel"""
    print("Scraping custom lists...", file=sys.stderr)
    
    lists = []
    seen_ids = set()
    url = f"{BASE_URL}/user/{USER_ID}/lists"
    html = fetch_page(url)
    
    if not html:
        return lists
    
    soup = BeautifulSoup(html, 'html.parser')
    list_containers = soup.find_all('div', class_=re.compile('ipc-metadata-list-summary-item'))
    
    # Collect all list IDs first
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
    
    # Scrape lists in parallel (max 3 concurrent)
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_list = {executor.submit(scrape_single_list, lid, lname): (lid, lname) 
                         for lid, lname in list_tasks}
        
        for future in as_completed(future_to_list):
            try:
                list_data = future.result()
                lists.append(list_data)
            except Exception as e:
                lid, lname = future_to_list[future]
                print(f"Error scraping list {lname}: {e}", file=sys.stderr)
    
    print(f"  Total lists: {len(lists)}", file=sys.stderr)
    return lists

if __name__ == '__main__':
    print("Starting IMDB scraper (optimized)...", file=sys.stderr)
    start_time = time.time()
    
    result = {
        'user_id': USER_ID,
        'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'ratings': scrape_section('ratings'),
        'watchlist': scrape_section('watchlist'),
        'custom_lists': scrape_custom_lists()
    }
    
    result['total_ratings'] = len(result['ratings'])
    result['total_watchlist'] = len(result['watchlist'])
    result['total_lists'] = len(result['custom_lists'])
    result['total_list_items'] = sum(len(lst['items']) for lst in result['custom_lists'])
    
    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed/60:.1f} minutes", file=sys.stderr)
    print(f"Ratings: {result['total_ratings']}, Watchlist: {result['total_watchlist']}, Lists: {result['total_lists']} ({result['total_list_items']} items)", file=sys.stderr)
    
    print(json.dumps(result, indent=2, ensure_ascii=False))