#!/usr/bin/env python3
"""
IMDB scraper - exports ratings, watchlist, and reviews to JSON
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

def fetch_page(url):
    """Fetch a page"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def parse_title_from_card(card):
    """Parse title data from a card element"""
    title = {}
    
    # Title ID from data attribute or link
    title_link = card.find('a', href=re.compile(r'/title/tt\d+/'))
    if title_link:
        href = title_link.get('href', '')
        match = re.search(r'/title/(tt\d+)/', href)
        if match:
            title['imdb_id'] = match.group(1)
            title['url'] = f"{BASE_URL}/title/{title['imdb_id']}/"
    
    # Title name
    title_text = card.find('h3', class_=re.compile('ipc-title__text'))
    if title_text:
        # Remove numbering like "1. " from title
        text = title_text.get_text(strip=True)
        title['title'] = re.sub(r'^\d+\.\s*', '', text)
    
    # Year
    year_span = card.find('span', class_=re.compile('dli-title-metadata-item'))
    if year_span:
        title['year'] = year_span.get_text(strip=True)
    
    # Rating (if exists)
    rating_span = card.find('span', class_=re.compile('ipc-rating-star--rating'))
    if rating_span:
        title['rating'] = rating_span.get_text(strip=True)
    
    # Your rating (if exists) 
    your_rating = card.find('span', class_=re.compile('ipc-rating-star--base'))
    if your_rating:
        rating_text = your_rating.get_text(strip=True)
        match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
        if match:
            title['user_rating'] = match.group(1)
    
    # Metadata like duration, rating, etc
    metadata_items = card.find_all('span', class_=re.compile('dli-title-metadata-item'))
    if len(metadata_items) > 1:
        title['metadata'] = [item.get_text(strip=True) for item in metadata_items]
    
    return title if title.get('imdb_id') else None

def scrape_ratings():
    """Scrape user ratings"""
    print("Scraping ratings...", file=sys.stderr)
    
    ratings = []
    start = 1
    page = 1
    
    while True:
        url = f"{BASE_URL}/user/{USER_ID}/ratings/?sort=date_added,desc&mode=detail&start={start}"
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
                ratings.append(title)
        
        print(f"  Page {page}: {len(cards)} titles (total: {len(ratings)})", file=sys.stderr)
        
        # Check for next page button
        next_button = soup.find('button', {'aria-label': 'Next'})
        if not next_button or 'disabled' in next_button.get('class', []):
            break
        
        start += 250  # IMDB uses 250 items per page
        page += 1
        time.sleep(2)
    
    return ratings

def scrape_watchlist():
    """Scrape watchlist"""
    print("Scraping watchlist...", file=sys.stderr)
    
    watchlist = []
    start = 1
    page = 1
    
    while True:
        url = f"{BASE_URL}/user/{USER_ID}/watchlist/?sort=date_added,desc&mode=detail&start={start}"
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
                watchlist.append(title)
        
        print(f"  Page {page}: {len(cards)} titles (total: {len(watchlist)})", file=sys.stderr)
        
        next_button = soup.find('button', {'aria-label': 'Next'})
        if not next_button or 'disabled' in next_button.get('class', []):
            break
        
        start += 250
        page += 1
        time.sleep(2)
    
    return watchlist

def scrape_reviews():
    """Scrape user reviews"""
    print("Scraping reviews...", file=sys.stderr)
    
    reviews = []
    url = f"{BASE_URL}/user/{USER_ID}/reviews"
    html = fetch_page(url)
    
    if not html:
        return reviews
    
    soup = BeautifulSoup(html, 'html.parser')
    review_containers = soup.find_all('div', class_='review-container')
    
    for container in review_containers:
        review = {}
        
        # Title
        title_link = container.find('a', href=re.compile(r'/title/tt\d+/'))
        if title_link:
            href = title_link.get('href', '')
            match = re.search(r'/title/(tt\d+)/', href)
            if match:
                review['imdb_id'] = match.group(1)
                review['title'] = title_link.get_text(strip=True)
        
        # Rating
        rating_span = container.find('span', class_=re.compile('rating-other-user-rating'))
        if rating_span:
            rating_text = rating_span.get_text(strip=True)
            match = re.search(r'(\d+)/10', rating_text)
            if match:
                review['rating'] = match.group(1)
        
        # Review date
        date_span = container.find('span', class_='review-date')
        if date_span:
            review['date'] = date_span.get_text(strip=True)
        
        # Review text
        content_div = container.find('div', class_='content')
        if content_div:
            text_div = content_div.find('div', class_='text')
            if text_div:
                review['review_text'] = text_div.get_text(strip=True)
        
        if review.get('imdb_id'):
            reviews.append(review)
    
    print(f"  Found {len(reviews)} reviews", file=sys.stderr)
    return reviews

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
        
        list_data = {
            'list_id': list_id,
            'list_name': list_name,
            'items': []
        }
        
        # Fetch list contents with pagination
        print(f"  Scraping list: {list_name}", file=sys.stderr)
        start = 1
        list_page = 1
        
        while True:
            list_url = f"{BASE_URL}/list/{list_id}/?sort=list_order,asc&mode=detail&page={list_page}"
            list_html = fetch_page(list_url)
            
            if not list_html:
                break
            
            list_soup = BeautifulSoup(list_html, 'html.parser')
            
            # Try modern layout first
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
                if rating_span:
                    item['rating'] = rating_span.get_text(strip=True)
                
                if item.get('imdb_id'):
                    list_data['items'].append(item)
            
            print(f"    Page {list_page}: {len(cards)} items (total: {len(list_data['items'])})", file=sys.stderr)
            
            # Check for next page
            next_button = list_soup.find('button', {'aria-label': 'Next'})
            if not next_button or 'disabled' in next_button.get('class', []):
                break
            
            list_page += 1
            time.sleep(2)
        
        lists.append(list_data)
        time.sleep(2)
    
    print(f"  Total lists: {len(lists)}", file=sys.stderr)
    return lists

if __name__ == '__main__':
    print("Starting IMDB scraper...", file=sys.stderr)
    
    result = {
        'user_id': USER_ID,
        'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'ratings': scrape_ratings(),
        'watchlist': scrape_watchlist(),
        'reviews': scrape_reviews(),
        'custom_lists': scrape_custom_lists()
    }
    
    result['total_ratings'] = len(result['ratings'])
    result['total_watchlist'] = len(result['watchlist'])
    result['total_reviews'] = len(result['reviews'])
    result['total_lists'] = len(result['custom_lists'])
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nTotal - Ratings: {result['total_ratings']}, Watchlist: {result['total_watchlist']}, Reviews: {result['total_reviews']}, Lists: {result['total_lists']}", file=sys.stderr)