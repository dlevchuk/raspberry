# imdb-backup-lists (OUTDATED)

⚠️ **This script is outdated and no longer works due to changes in the IMDB website structure.**

## Use the Working Version Instead

Please use the updated script located in `../backup_imdb_web/` which uses web scraping and is compatible with the current IMDB site.

The working version:
- Uses web scraping instead of cookies (no authentication needed)
- Exports data as JSON format
- Scrapes ratings, watchlist, reviews, and custom lists
- Works with the current IMDB website structure

See `../backup_imdb_web/README.md` for usage instructions.

---

## Original Documentation (for reference only)

This script was a cookie-based tool to backup all your lists from IMDb including your watchlist and ratings. It created a .zip archive with .csv files exported from the site.

### Original Requirements:
- Python 3.x
- requests
- beautifulsoup4
- unidecode
- load_dotenv

### Original Setup (no longer works):
1. Copy your IMDb `at-main`, `ubid-main` and `uu` cookies from your browser
2. Create `imdb_cookie.json` file with the cookies
3. Create .env file for TOKENS
