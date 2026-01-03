# Goodreads Backup

Automated backup script for Goodreads books from public shelves. This script scrapes your Goodreads reading lists and exports them to JSON format.

## Overview

The `goodreads_scraper.py` script fetches all books from your public Goodreads shelves (read, currently-reading, to-read) and exports them as a structured JSON file.

## Features

- Scrapes multiple shelves: `read`, `currently-reading`, `to-read`
- Exports comprehensive book data including:
  - Title, author, ISBN
  - Personal rating and average Goodreads rating
  - Shelves the book belongs to
  - Date read and date added
  - Number of pages
  - Review/notes
  - Book URL
- Handles pagination automatically
- Includes rate limiting (2 second delay between pages)
- Outputs structured JSON with metadata

## Usage

### Manual Execution

```bash
python3 goodreads_scraper.py > goodreads_backup.json
```

The script outputs JSON to stdout and progress messages to stderr.

### Automated Backup

The backup is automated via GitHub Actions workflow (`.github/workflows/goodreads_backup.yml`):
- **Schedule**: Runs every Sunday at 2:00 AM UTC
- **Manual trigger**: Can be triggered manually via `workflow_dispatch`
- **Output**: Automatically commits the updated `goodreads_backup.json` to the repository

## Configuration

To use this script with a different Goodreads user, modify the `USER_ID` constant in `goodreads_scraper.py`:

```python
USER_ID = "76529348"  # Replace with your Goodreads user ID
```

You can find your user ID in your Goodreads profile URL: `https://www.goodreads.com/user/show/{USER_ID}`

## Dependencies

- Python 3.11+
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
  "user_id": "76529348",
  "scraped_at": "2024-01-01 12:00:00 UTC",
  "total_books": 567,
  "books": [
    {
      "id": "12345678",
      "title": "Book Title",
      "author": "Author Name",
      "url": "https://www.goodreads.com/book/show/...",
      "isbn": "978-0-123456-78-9",
      "rating": 5,
      "avg_rating": "4.23",
      "shelves": ["read", "favorites"],
      "date_read": "2023-12-01",
      "date_added": "2023-11-15",
      "pages": "320",
      "review": "Great book!"
    }
  ]
}
```

## Notes

- The script respects Goodreads' rate limits with a 2-second delay between page requests
- Only public shelves are accessible (private shelves cannot be scraped)
- The script uses a User-Agent header to avoid being blocked
- Error handling is included for network issues and parsing errors

## Files

- `goodreads_scraper.py` - Main scraper script
- `goodreads_backup.json` - Generated backup file (committed to repository)

