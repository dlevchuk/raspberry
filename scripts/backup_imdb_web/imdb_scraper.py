#!/usr/bin/env python3
"""
IMDB custom lists scraper - exports all custom lists to JSON
"""
import requests
from bs4 import BeautifulSoup
import json
import time
import sys
import re

USER_ID = "ur48993532"
BASE_URL = "https://www.imdb.com"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}

def fetch_page(url, retries=3):
    """Fetch a page with retry logic"""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503:
                wait_time = (attempt + 1) * 10
                print(f"503 error, waiting {wait_time}s before retry {attempt+1}/{retries}...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                print(f"Error fetching {url}: {e}", file=sys.stderr)
                return None
        except Exception as e:
            print(f"Error fetching {url}: {e}", file=sys.stderr)
            return None
    
    print(f"Failed after {retries} retries: {url}", file=sys.stderr)
    return None

def scrape_custom_lists():
    """Scrape user's custom lists"""
    print("Scraping custom lists...", file=sys.stderr)
    
    lists = []
    seen_ids = set()
    url = f"{BASE_URL}/user/{USER_ID}/lists"
    html = fetch_page(url)
    
    if not html:
        return lists
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all list containers
    list_containers = soup.find_all('div', class_=re.compile('ipc-metadata-list-summary-item'))
    
    for container in list_containers:
        # Find list link
        link = container.find('a', href=re.compile(r'/list/ls\d+'))
        if not link:
            continue
            
        list_id_match = re.search(r'/list/(ls\d+)', link.get('href', ''))
        if not list_id_match:
            continue
        
        list_id = list_id_match.group(1)
        
        # Skip duplicates
        if list_id in seen_ids:
            continue
        seen_ids.add(list_id)
        
        # Get list name from title
        title_elem = container.find('h3', class_=re.compile('ipc-title__text'))
        list_name = title_elem.get_text(strip=True) if title_elem else f"List {list_id}"
        # Remove numbering
        list_name = re.sub(r'^\d+\.\s*', '', list_name)
        
        list_data = {
            'list_id': list_id,
            'list_name': list_name,
            'list_url': f"{BASE_URL}/list/{list_id}/",
            'items': []
        }
        
        # Fetch list contents with pagination
        print(f"  Scraping list: {list_name}", file=sys.stderr)
        list_page = 1
        
        while True:
            list_url = f"{BASE_URL}/list/{list_id}/?sort=list_order,asc&mode=detail&page={list_page}"
            list_html = fetch_page(list_url)
            
            if not list_html:
                break
            
            list_soup = BeautifulSoup(list_html, 'html.parser')
            
            # Try modern layout
            cards = list_soup.find_all('li', class_=re.compile('ipc-metadata-list-summary-item'))
            
            # Fallback to old layout
            if not cards:
                cards = list_soup.find_all('div', class_=re.compile('lister-item'))
            
            if not cards:
                break
            
            for card in cards:
                item = {}
                
                # Title link
                title_link = card.find('a', href=re.compile(r'/title/tt\d+'))
                if title_link:
                    href = title_link.get('href', '')
                    match = re.search(r'/title/(tt\d+)', href)
                    if match:
                        item['imdb_id'] = match.group(1)
                        item['url'] = f"{BASE_URL}/title/{item['imdb_id']}/"
                        
                        # Get title text
                        title_elem = card.find('h3', class_=re.compile('ipc-title__text'))
                        if not title_elem:
                            title_elem = card.find('a', href=re.compile(r'/title/tt\d+'))
                        if title_elem:
                            text = title_elem.get_text(strip=True)
                            item['title'] = re.sub(r'^\d+\.\s*', '', text)
                
                # Year
                year_span = card.find('span', class_=re.compile('(lister-item-year|dli-title-metadata-item)'))
                if year_span:
                    item['year'] = year_span.get_text(strip=True)
                
                # Rating
                rating_span = card.find('span', class_=re.compile('ipc-rating-star--rating'))
                if not rating_span:
                    rating_span = card.find('span', class_='ipl-rating-star__rating')
                if rating_span:
                    item['rating'] = rating_span.get_text(strip=True)
                
                if item.get('imdb_id'):
                    list_data['items'].append(item)
            
            print(f"    Page {list_page}: {len(cards)} items (total: {len(list_data['items'])})", file=sys.stderr)
            
            # Check for next page
            next_button = list_soup.find('button', {'aria-label': 'Next'})
            if not next_button or 'disabled' in next_button.get('class', []):
                # Also try old pagination
                next_link = list_soup.find('a', class_='next-page')
                if not next_link:
                    break
            
            list_page += 1
            time.sleep(5)
        
        lists.append(list_data)
        time.sleep(5)
    
    print(f"  Total lists: {len(lists)}", file=sys.stderr)
    return lists

if __name__ == '__main__':
    print("Starting IMDB lists scraper...", file=sys.stderr)
    
    result = {
        'user_id': USER_ID,
        'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'lists': scrape_custom_lists()
    }
    
    result['total_lists'] = len(result['lists'])
    result['total_items'] = sum(len(lst['items']) for lst in result['lists'])
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nTotal - Lists: {result['total_lists']}, Items: {result['total_items']}", file=sys.stderr)