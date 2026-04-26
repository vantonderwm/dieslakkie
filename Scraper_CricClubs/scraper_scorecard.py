import os
import re
from urllib.parse import urlparse, parse_qs
from html import unescape

import cloudscraper as cs
import pandas as pd
from bs4 import BeautifulSoup as bs

from scraper_results import build_absolute_url, extract_query_value


BASE_URL = "https://cricclubs.com"
CLUB_PREFIX = "/TitansCricket"
OUTPUT_DIR = "output"


def ensure_folder(path):
    os.makedirs(path, exist_ok=True)


def extract_year(league_name):
    match = re.search(r"(20\d{2})", league_name)
    return match.group(1) if match else "unknown"


def normalize_scorecard_url(url):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    match_id = query.get("matchId", [""])[0]
    club_id = query.get("clubId", [""])[0]
    return f"{BASE_URL}{CLUB_PREFIX}/fullScorecard.do?matchId={match_id}&clubId={club_id}"


def fetch_html(url):
    print(f"Fetching HTML from URL: {url}")
    scraper = cs.create_scraper()
    response = scraper.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch HTML: HTTP {response.status_code}")
        return None
    return response.text


def format_date_yyyymmdd(display_date):
    match = re.match(r"(\d{2})/(\d{2})/(\d{4})", display_date.strip())
    if not match:
        return ""
    day, month, year = match.groups()
    return f"{year}{month}{day}"


def clean_text(value):
    cleaned = unescape(str(value))
    replacements = {
        "\xa0": " ",
        "â€ ": "",
        "â€": "†",
        "â€ ": "†",
        "â€™": "'",
        "â€“": "-",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return " ".join(cleaned.split())


def overs_to_balls(overs_text):
    text = clean_text(overs_text)
    if not text:
        return ""
    if "." not in text:
        return text
    overs, balls = text.split(".", 1)
    if not overs.isdigit() or not balls.isdigit():
        return ""
    return str(int(overs) * 6 + int(balls))


def parse_extras_breakdown(extras_text):
    values = {"b": "0", "lb": "0", "w": "0", "nb": "0", "p": "0"}
    for key, value in re.findall(r"\b(b|lb|w|nb|p)\s+(\d+)", clean_text(extras_text)):
        values[key] = value
    return values


def extract_match_summary(soup, source_url):
    summary = soup.find("div", {"class": "match-summary"})
    if not summary:
        return None

    league_name_node = summary.find("h3")
    meta_node = summary.find("h3", {"class": "ms-league-name"})
    league_name = league_name_node.get_text(" ", strip=True) if league_name_node else ""

    match_type = ""
    match_date = ""
    if meta_node:
        meta_text = " ".join(meta_node.stripped_strings)
        parts = [part.strip() for part in meta_text.split("|")]
        if len(parts) >= 2:
            match_type = parts[0]
            match_date = parts[1]
        else:
            span = meta_node.find("span")
            match_type = meta_node.contents[0].strip() if meta_node.contents else ""
            match_date = span.get_text(" ", strip=True) if span else ""

    team_links = summary.find_all("a", href=True)
    team_urls = [
        build_absolute_url(link["href"])
        for link in team_links
        if "viewTeam.do" in link["href"]
    ][:2]
    team_ids = [extract_query_value(url, "teamId") for url in team_urls]
    team_names = [
        clean_text(node.get_text(" ", strip=True))
        for node in summary.select("span.teamName")
    ][:2]

    meta_description = soup.find("meta", attrs={"name": "description"})
    description = meta_description.get("content", "") if meta_description else ""
    match_result = clean_text(description.split(";")[0]) if description else ""

    match_id = extract_query_value(source_url, "matchId")
    club_id = extract_query_value(source_url, "clubId")

    return {
        "MATCH_ID": match_id,
        "CLUB_ID": club_id,
        "LEAGUE_NAME": league_name,
        "LEAGUE_YEAR": extract_year(league_name),
        "MATCH_TYPE": match_type,
        "MATCH_DATE": match_date,
        "MATCH_DATE_KEY": format_date_yyyymmdd(match_date),
        "TEAM_ONE": team_names[0] if len(team_names) > 0 else "",
        "TEAM_ONE_ID": team_ids[0] if len(team_ids) > 0 else "",
        "TEAM_TWO": team_names[1] if len(team_names) > 1 else "",
        "TEAM_TWO_ID": team_ids[1] if len(team_ids) > 1 else "",
        "TEAM_ONE_URL": team_urls[0] if len(team_urls) > 0 else "",
        "TEAM_TWO_URL": team_urls[1] if len(team_urls) > 1 else "",
        "RESULT": match_result,
        "SOURCE_URL": source_url,
    }


def clean_batter_name(name):
    return name.rstrip("*† ").strip()


def extract_player_id_from_links(links):
    for link in links:
        href = link.get("href", "")
        if "viewPlayer.do" in href:
            return extract_query_value(build_absolute_url(href), "playerId")
    return ""


def parse_batting_table(table, innings_number, match_summary):
    innings_header = clean_text(table.find("thead").find("th").get_text(" ", strip=True))
    innings_team = innings_header.split(" innings")[0].strip()
    rows = []
    innings_summary = None

    tbody = table.find("tbody")
    for row in tbody.find_all("tr", recursive=False):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) < 7:
            continue

        batter_cell = cells[0]
        batter_text = clean_text(batter_cell.get_text(" ", strip=True))
        if batter_text.startswith("Extras"):
            extras = parse_extras_breakdown(cells[1].get_text(" ", strip=True))
            if innings_summary is None:
                innings_summary = {}
            innings_summary.update(
                {
                    "BYES": extras["b"],
                    "LEG_BYES": extras["lb"],
                    "WIDES": extras["w"],
                    "NO_BALLS": extras["nb"],
                    "PENALTY": extras["p"],
                    "EXTRAS": clean_text(cells[2].get_text(" ", strip=True)),
                }
            )
            continue

        if batter_text.startswith("Total"):
            total_meta = clean_text(cells[1].get_text(" ", strip=True))
            wickets_match = re.search(r"(\d+)\s+wickets?", total_meta)
            overs_match = re.search(r"(\d+(?:\.\d+)?)\s+overs?", total_meta)
            if innings_summary is None:
                innings_summary = {}
            innings_summary.update(
                {
                    "TOTAL_RUNS": clean_text(cells[2].get_text(" ", strip=True)),
                    "WICKETS": wickets_match.group(1) if wickets_match else "",
                    "TOTAL_OVERS": overs_match.group(1) if overs_match else "",
                    "TOTAL_BALLS": overs_to_balls(overs_match.group(1) if overs_match else ""),
                }
            )
            continue

        player_link = batter_cell.find("a", href=True)
        dismissal_player_links = [
            link
            for link in cells[1].find_all("a", href=True)
            if "viewPlayer.do" in link.get("href", "")
        ]
        dismissal_player_names = [clean_text(link.get_text(" ", strip=True)) for link in dismissal_player_links]
        dismissal_player_ids = [
            extract_query_value(build_absolute_url(link.get("href", "")), "playerId")
            for link in dismissal_player_links
        ]

        row_data = {
            "MATCH_ID": match_summary["MATCH_ID"],
            "LEAGUE_NAME": match_summary["LEAGUE_NAME"],
            "LEAGUE_YEAR": match_summary["LEAGUE_YEAR"],
            "CLUB_ID": match_summary["CLUB_ID"],
            "MATCH_DATE": match_summary["MATCH_DATE"],
            "MATCH_DATE_KEY": match_summary["MATCH_DATE_KEY"],
            "TEAM_ONE_ID": match_summary["TEAM_ONE_ID"],
            "TEAM_TWO_ID": match_summary["TEAM_TWO_ID"],
            "INNINGS": innings_number,
            "INNINGS_TEAM": innings_team,
            "PLAYER": clean_batter_name(clean_text(player_link.get_text(" ", strip=True)) if player_link else batter_text),
            "PLAYER_ID": extract_player_id_from_links([player_link] if player_link else []),
            "DISMISSAL_TEXT": clean_text(cells[1].get_text(" ", strip=True)),
            "DISMISSAL_PLAYER_1": dismissal_player_names[0] if len(dismissal_player_names) > 0 else "",
            "DISMISSAL_PLAYER_1_ID": dismissal_player_ids[0] if len(dismissal_player_ids) > 0 else "",
            "DISMISSAL_PLAYER_2": dismissal_player_names[1] if len(dismissal_player_names) > 1 else "",
            "DISMISSAL_PLAYER_2_ID": dismissal_player_ids[1] if len(dismissal_player_ids) > 1 else "",
            "DISMISSAL_PLAYER_IDS": ",".join(filter(None, dismissal_player_ids)),
            "RUNS": clean_text(cells[2].get_text(" ", strip=True)),
            "BALLS": clean_text(cells[3].get_text(" ", strip=True)),
            "FOURS": clean_text(cells[4].get_text(" ", strip=True)),
            "SIXES": clean_text(cells[5].get_text(" ", strip=True)),
            "STRIKE_RATE": clean_text(cells[6].get_text(" ", strip=True)),
        }
        rows.append(row_data)

    batting_df = pd.DataFrame(rows)
    return batting_df, innings_summary or {}


def parse_bowling_table(table, innings_number, match_summary, innings_team):
    batting_team_id = match_summary["TEAM_ONE_ID"] if innings_team == match_summary["TEAM_ONE"] else match_summary["TEAM_TWO_ID"]
    bowling_team_id = match_summary["TEAM_TWO_ID"] if batting_team_id == match_summary["TEAM_ONE_ID"] else match_summary["TEAM_ONE_ID"]
    bowling_team_name = match_summary["TEAM_TWO"] if batting_team_id == match_summary["TEAM_ONE_ID"] else match_summary["TEAM_ONE"]
    rows = []
    tbody = table.find("tbody")
    for row in tbody.find_all("tr", recursive=False):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) < 8:
            continue

        bowler_cell = cells[1]
        player_link = bowler_cell.find("a", href=True)
        extras_text = cells[8].get_text(" ", strip=True) if len(cells) > 8 else ""

        row_data = {
            "MATCH_ID": match_summary["MATCH_ID"],
            "LEAGUE_NAME": match_summary["LEAGUE_NAME"],
            "LEAGUE_YEAR": match_summary["LEAGUE_YEAR"],
            "CLUB_ID": match_summary["CLUB_ID"],
            "MATCH_DATE": match_summary["MATCH_DATE"],
            "MATCH_DATE_KEY": match_summary["MATCH_DATE_KEY"],
            "TEAM_ONE_ID": match_summary["TEAM_ONE_ID"],
            "TEAM_TWO_ID": match_summary["TEAM_TWO_ID"],
            "INNINGS": innings_number,
            "BATTING_TEAM": innings_team,
            "BATTING_TEAM_ID": batting_team_id,
            "BOWLING_TEAM": bowling_team_name,
            "BOWLING_TEAM_ID": bowling_team_id,
            "PLAYER": clean_text(player_link.get_text(" ", strip=True)).replace("*", "").strip() if player_link else clean_text(bowler_cell.get_text(" ", strip=True)),
            "PLAYER_ID": extract_player_id_from_links([player_link] if player_link else []),
            "OVERS": clean_text(cells[2].get_text(" ", strip=True)),
            "MAIDENS": clean_text(cells[3].get_text(" ", strip=True)),
            "DOT_BALLS": clean_text(cells[4].get_text(" ", strip=True)),
            "RUNS": clean_text(cells[5].get_text(" ", strip=True)),
            "WICKETS": clean_text(cells[6].get_text(" ", strip=True)),
            "ECONOMY": clean_text(cells[7].get_text(" ", strip=True)),
            "EXTRAS_TEXT": clean_text(extras_text),
        }
        rows.append(row_data)

    return pd.DataFrame(rows)


def parse_scorecard(html, source_url):
    soup = bs(html, "html.parser")
    summary = extract_match_summary(soup, source_url)
    if summary is None:
        raise ValueError("Match summary not found.")

    scorecard_tab = soup.find(id="tab2default")
    if scorecard_tab is None:
        raise ValueError("Full scorecard tab not found.")

    tables = scorecard_tab.find_all("table", recursive=True)
    batting_frames = []
    bowling_frames = []
    innings_summaries = []

    current_innings = 0
    current_team = ""

    for table in tables:
        first_header = table.find("th")
        first_header_text = first_header.get_text(" ", strip=True) if first_header else ""

        if " innings" in first_header_text and table.find("thead"):
            current_innings += 1
            batting_df, innings_summary = parse_batting_table(table, current_innings, summary)
            if not batting_df.empty:
                current_team = batting_df["INNINGS_TEAM"].iloc[0]
                batting_frames.append(batting_df)
            else:
                current_team = first_header_text.split(" innings")[0].strip()

            batting_team_id = summary["TEAM_ONE_ID"] if current_team == summary["TEAM_ONE"] else summary["TEAM_TWO_ID"]
            bowling_team_id = summary["TEAM_TWO_ID"] if batting_team_id == summary["TEAM_ONE_ID"] else summary["TEAM_ONE_ID"]
            bowling_team_name = summary["TEAM_TWO"] if batting_team_id == summary["TEAM_ONE_ID"] else summary["TEAM_ONE"]
            innings_summary_row = {
                "MATCH_ID": summary["MATCH_ID"],
                "LEAGUE_NAME": summary["LEAGUE_NAME"],
                "LEAGUE_YEAR": summary["LEAGUE_YEAR"],
                "CLUB_ID": summary["CLUB_ID"],
                "MATCH_TYPE": summary["MATCH_TYPE"],
                "MATCH_DATE": summary["MATCH_DATE"],
                "MATCH_DATE_KEY": summary["MATCH_DATE_KEY"],
                "RESULT": summary["RESULT"],
                "INNINGS": current_innings,
                "BATTING_TEAM_ID": batting_team_id,
                "BOWLING_TEAM_ID": bowling_team_id,
                "BATTING_TEAM_NAME": current_team,
                "BOWLING_TEAM_NAME": bowling_team_name,
                "TOTAL_RUNS": innings_summary.get("TOTAL_RUNS", ""),
                "TOTAL_BALLS": innings_summary.get("TOTAL_BALLS", ""),
                "BYES": innings_summary.get("BYES", "0"),
                "LEG_BYES": innings_summary.get("LEG_BYES", "0"),
                "WICKETS": innings_summary.get("WICKETS", ""),
                "WIDES": innings_summary.get("WIDES", "0"),
                "NO_BALLS": innings_summary.get("NO_BALLS", "0"),
                "PENALTY": innings_summary.get("PENALTY", "0"),
            }
            innings_summaries.append(innings_summary_row)
            continue

        if first_header_text.startswith("Bowling") and current_innings > 0:
            bowling_df = parse_bowling_table(table, current_innings, summary, current_team)
            if not bowling_df.empty:
                bowling_frames.append(bowling_df)

    batting_df = pd.concat(batting_frames, ignore_index=True) if batting_frames else pd.DataFrame()
    bowling_df = pd.concat(bowling_frames, ignore_index=True) if bowling_frames else pd.DataFrame()
    summary_df = pd.DataFrame(innings_summaries)
    return summary_df, batting_df, bowling_df


def build_file_stem(summary):
    return f"{summary['MATCH_DATE_KEY']}_{summary['CLUB_ID']}_{summary['TEAM_ONE_ID']}v{summary['TEAM_TWO_ID']}"


def save_outputs(summary_df, batting_df, bowling_df, html):
    summary = summary_df.iloc[0].to_dict()
    league_folder = os.path.join(OUTPUT_DIR, summary["LEAGUE_YEAR"], "scorecards")
    ensure_folder(league_folder)
    stem = f"{summary['MATCH_DATE_KEY']}_{summary['CLUB_ID']}_{summary['BATTING_TEAM_ID']}v{summary['BOWLING_TEAM_ID']}"

    summary_path = os.path.join(league_folder, f"match_summary_{stem}.csv")
    raw_path = os.path.join(league_folder, f"raw_scorecard_{stem}.html")
    summary_df.to_csv(summary_path, index=False)
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(html)

    if not batting_df.empty:
        batting_path = os.path.join(league_folder, f"batting_{stem}.csv")
        batting_df.to_csv(batting_path, index=False)

    if not bowling_df.empty:
        bowling_path = os.path.join(league_folder, f"bowling_{stem}.csv")
        bowling_df.to_csv(bowling_path, index=False)

    print(f"Saved: {summary_path}")
    print(f"Saved: {raw_path}")


if __name__ == "__main__":
    url = input("Enter the scorecard URL: ").strip()
    if not url:
        print("No URL provided.")
        raise SystemExit(1)

    full_scorecard_url = normalize_scorecard_url(url)
    html = fetch_html(full_scorecard_url)
    if html is None:
        raise SystemExit(1)

    summary_df, batting_df, bowling_df = parse_scorecard(html, full_scorecard_url)
    save_outputs(summary_df, batting_df, bowling_df, html)
