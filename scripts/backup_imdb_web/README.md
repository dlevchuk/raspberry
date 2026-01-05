# IMDB Backup

Automated backup script for IMDB data. This script scrapes your IMDB ratings, watchlist, reviews, and custom lists and exports them to JSON format.

## Overview

The `imdb_scraper.py` script fetches all your IMDB data from public pages and exports them as a structured JSON file. Unlike the cookie-based backup script, this version uses web scraping and doesn't require authentication cookies.

## Features

- Scrapes multiple data types:
  - **Ratings** - All titles you've rated with your personal ratings
  - **Watchlist** - All titles in your watchlist
  - **Reviews** - All your written reviews
  - **Custom Lists** - All your custom lists with their items
- Exports comprehensive title data including:
  - IMDB ID and URL
  - Title name and year
  - Personal rating and average IMDB rating
  - Metadata (duration, content rating, etc.)
  - Review text and dates (for reviews)
- Handles pagination automatically
- Includes rate limiting (2 second delay between pages)
- Outputs structured JSON with metadata

## Usage

### Manual Execution

```bash
python3 imdb_scraper.py > imdb_backup.json
```

The script outputs JSON to stdout and progress messages to stderr.

### Automated Backup

You can set up automated backups using cron or a similar scheduler:

```bash
# Run daily at 2:00 AM
0 2 * * * cd /path/to/backup_imdb_web && python3 imdb_scraper.py > imdb_backup.json
```

## Configuration

To use this script with a different IMDB user, modify the `USER_ID` constant in `imdb_scraper.py`:

```python
USER_ID = "ur48993532"  # Replace with your IMDB user ID
```

You can find your user ID in your IMDB profile URL: `https://www.imdb.com/user/{USER_ID}/`

## Dependencies

- Python 3.x
- `requests` - HTTP library for fetching pages
- `beautifulsoup4` - HTML parsing

Install dependencies:
```bash
pip install requests beautifulsoup4
```

## Output Format

The script generates a JSON file with the following structure:

```json
{
  "user_id": "ur48993532",
  "scraped_at": "2024-01-01 12:00:00 UTC",
  "total_ratings": 150,
  "total_watchlist": 45,
  "total_reviews": 12,
  "total_lists": 3,
  "ratings": [
    {
      "imdb_id": "tt0111161",
      "title": "The Shawshank Redemption",
      "year": "1994",
      "user_rating": "10",
      "rating": "9.3",
      "url": "https://www.imdb.com/title/tt0111161/",
      "metadata": ["142 min", "R"]
    }
  ],
  "watchlist": [
    {
      "imdb_id": "tt1375666",
      "title": "Inception",
      "year": "2010",
      "url": "https://www.imdb.com/title/tt1375666/"
    }
  ],
  "reviews": [
    {
      "imdb_id": "tt0111161",
      "title": "The Shawshank Redemption",
      "rating": "10",
      "date": "15 January 2023",
      "review_text": "An amazing film..."
    }
  ],
  "custom_lists": [
    {
      "list_id": "ls123456789",
      "list_name": "My Favorite Movies",
      "items": [
        {
          "imdb_id": "tt0111161",
          "title": "The Shawshank Redemption",
          "year": "(1994)",
          "rating": "9.3"
        }
      ]
    }
  ]
}
```

## Notes

- The script respects IMDB's rate limits with a 2-second delay between page requests
- Only public pages are accessible (private profiles cannot be scraped)
- The script uses a User-Agent header to avoid being blocked
- Error handling is included for network issues and parsing errors
- IMDB's HTML structure may change over time, which could break the scraper

## Files

- `imdb_scraper.py` - Main scraper script

