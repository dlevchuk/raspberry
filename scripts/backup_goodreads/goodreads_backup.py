#!/usr/bin/env python3
import os
import time
from pathlib import Path
from dotenv import load_dotenv
import requests

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
import geckodriver_autoinstaller

load_dotenv()

username = os.environ.get("goodreads_user")
password = os.environ.get("goodreads_password")

def get_driver(download_path=".", driver_dir="."):
    os.environ["TMPDIR"] = download_path
    # set up a special download friendly firefox profile
    profile = webdriver.FirefoxProfile()
    # do not use the default download directory
    profile.set_preference("browser.download.folderList", 2)
    # turn off showing the download progress
    profile.set_preference("browser.download.manager.showWhenStarting", False)
    # set the download directory to where we want it
    profile.set_preference("browser.download.dir", download_path)
    # automatically download files like this instead of asking
    profile.set_preference("browser.helperApps.neverAsk.saveToDisk", "text/csv")
    profile.update_preferences()

    # let's be headless
    options = Options()
    options.headless = True
    options.profile = profile
    # start up selenium
    return webdriver.Firefox(options=options)

def telegram_bot_sendtext(bot_message):
   bot_token = os.environ.get("BOT_TOKEN")
   bot_chatID = os.environ.get("BOT_CHAT_ID")
   send_text = 'https://api.telegram.org/bot' + bot_token + '/sendMessage?chat_id=' + bot_chatID + '&parse_mode=Markdown&text=' + bot_message
   response = requests.get(send_text)


def login(browser, username, password):
    # original sign_in now just has a link to another page for signing in
    browser.get(
        "https://www.goodreads.com/ap/signin?language=en_US&openid.assoc_handle=amzn_goodreads_web_na&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.mode=checkid_setup&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.goodreads.com%2Fap-handler%2Fsign-in"
    )
    browser.find_element_by_id("ap_email").send_keys(username)
    browser.find_element_by_id("ap_password").send_keys(password)
    browser.find_element_by_id("signInSubmit").click()


def export_booklist(browser, timeout):
    # now that we are logged in, let's export our books
    browser.get("https://www.goodreads.com/review/import")
    elem = browser.find_element_by_xpath("//*[text()='Export Library']")
    elem.click()
    # wait for the export
    browser.implicitly_wait(timeout)
    export_link = browser.find_element_by_partial_link_text("Your export from")
    export_link.click()
    telegram_bot_sendtext("Start goodread acc export")

if __name__ == "__main__":
    curdir = str(Path(__file__).parent.absolute())
    backup_dir = curdir
    timeout_default = 120
    telegram_bot_sendtext("Start goodread account backup")

    try:
        geckodriver_autoinstaller.install()
    except TimeoutError as e:
        print(
            "Could not auto install or update gecko driver - unless this is the first run, it is safe to ignore this error as we can function without updating this."
        )
    driver = get_driver(download_path=backup_dir, driver_dir=backup_dir)
    try:
        login(driver, username, password)
        export_booklist(driver, timeout_default)
        # sleep a few seconds to give the download time to complete
        time.sleep(30)
    finally:
        driver.quit()
        telegram_bot_sendtext("End goodread account backup")
