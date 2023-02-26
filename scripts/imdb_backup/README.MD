# imdb-backup-lists

A simple tool to backup all your lists from IMDb including your watchlist and ratings. Creates a .zip archive with .csv files exported from the site. To prevent filesystem errors all personal lists are renamed to `ls0XXXXXXXX_latinized-list-name.csv`, but all original list titles (including multiline ones) are preserved in `titles.txt` in the same archive.

## Installation:

 Requirements

     Python 3.x
     requests
     beautifulsoup4
     unidecode
     load_dotenv


## How to run:

1. Copy your IMDb `at-main`, `ubid-main` and `uu` cookies from your browser:
   1. Open any page on IMDb.
   2. Open Developer tools in your browser:
      - Firefox: ≡ → Web Developer → Storage Inspector<br><br>
        ![Firefox](images/firefox.png)
      - Chrome: ⫶ → More tools → Developer tools → Application tab<br><br>
        ![Chrome](images/chrome.png)
   3. Expand "Cookies" in the left panel and select `http://www.imdb.com`.
   4. Find rows named `at-main`, `ubid-main` and `uu`, double click on their cells in the "Value" column and copy them.

2. Create a new file `imdb_cookie.json` in the script directory and paste the following data into it, replacing ellipses with your cookies from the previous step:
   ```json
   {
     "at-main": "...",
     "ubid-main": "...",
     "uu": "..."
   }
   ```
