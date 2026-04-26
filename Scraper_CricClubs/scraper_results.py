import re
from urllib.parse import urljoin

import cloudscraper as cs
import pandas as pd
from bs4 import BeautifulSoup as bs


BASE_URL = "https://cricclubs.com"
RESULTS_TABLE_ID = "schedule-table1"


def fetch_html(url):
    print(f"Fetching HTML from URL: {url}")
    scraper = cs.create_scraper()
    response = scraper.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch HTML: HTTP {response.status_code}")
        return None
    return response.text


def build_absolute_url(href):
    if not href:
        return ""
    return urljoin(BASE_URL, href)


def extract_query_value(url, key):
    match = re.search(rf"[?&]{key}=([^&]+)", url)
    return match.group(1) if match else ""


def split_score_summary(score_summary):
    parts = re.findall(r"([^:]+):\s*([0-9]+/[0-9]+\([0-9.]+\))", score_summary)
    parsed = {
        "SCORE_SUMMARY_TEAM_1": "",
        "SCORE_SUMMARY_TEAM_1_SCORE": "",
        "SCORE_SUMMARY_TEAM_2": "",
        "SCORE_SUMMARY_TEAM_2_SCORE": "",
    }

    if len(parts) >= 1:
        parsed["SCORE_SUMMARY_TEAM_1"] = parts[0][0].strip()
        parsed["SCORE_SUMMARY_TEAM_1_SCORE"] = parts[0][1].strip()

    if len(parts) >= 2:
        parsed["SCORE_SUMMARY_TEAM_2"] = parts[1][0].strip()
        parsed["SCORE_SUMMARY_TEAM_2_SCORE"] = parts[1][1].strip()

    return parsed


def parse_results_from_html(html, source_url=""):
    soup = bs(html, "html.parser")
    table = soup.find("table", {"id": RESULTS_TABLE_ID})

    if not table:
        print(f"Results table with id '{RESULTS_TABLE_ID}' not found.")
        return None

    rows = table.find_all("tr")
    data = []
    league_id = extract_query_value(source_url, "league")
    club_id = extract_query_value(source_url, "clubId")

    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 8:
            continue

        team_one_link = cells[3].find("a", href=True)
        team_two_link = cells[4].find("a", href=True)
        scorecard_link = cells[6].find("a", href=True)

        score_summary_raw = cells[6].get_text(" ", strip=True)
        score_summary_split = split_score_summary(score_summary_raw)
        team_one_url = build_absolute_url(team_one_link["href"] if team_one_link else "")
        team_two_url = build_absolute_url(team_two_link["href"] if team_two_link else "")
        scorecard_url = build_absolute_url(scorecard_link["href"] if scorecard_link else "")

        row_data = {
            "SNO": cells[0].get_text(" ", strip=True),
            "LEAGUE_ID": league_id,
            "CLUB_ID": club_id,
            "MATCH_TYPE": cells[1].get_text(" ", strip=True),
            "DATE": cells[2].get_text(" ", strip=True),
            "TEAM_ONE": cells[3].get_text(" ", strip=True),
            "TEAM_ONE_URL": team_one_url,
            "TEAM_ONE_ID": extract_query_value(team_one_url, "teamId"),
            "TEAM_ONE_CLUB_ID": extract_query_value(team_one_url, "clubId"),
            "TEAM_TWO": cells[4].get_text(" ", strip=True),
            "TEAM_TWO_URL": team_two_url,
            "TEAM_TWO_ID": extract_query_value(team_two_url, "teamId"),
            "TEAM_TWO_CLUB_ID": extract_query_value(team_two_url, "clubId"),
            "RESULT": cells[5].get_text(" ", strip=True),
            "SCORES_SUMMARY_RAW": score_summary_raw,
            "SCORECARD_URL": scorecard_url,
            "POINTS": cells[7].get_text(" ", strip=True),
        }
        row_data.update(score_summary_split)
        data.append(row_data)

    if not data:
        print("No data rows found in the results table.")
        return None

    df = pd.DataFrame(data)
    print(f"Parsed results table with shape: {df.shape}")
    print(f"Successfully retrieved {len(df)} match rows from the HTML.")
    return df


if __name__ == "__main__":
    url = input("Enter the results URL to fetch HTML from: ").strip()
    if not url:
        print("No URL provided.")
        raise SystemExit(1)

    html = fetch_html(url)
    if html is None:
        raise SystemExit(1)

    df = parse_results_from_html(html, url)
    if df is not None:
        df.to_csv("scrape_results.csv", index=False)
        print("Data saved to scrape_results.csv")
