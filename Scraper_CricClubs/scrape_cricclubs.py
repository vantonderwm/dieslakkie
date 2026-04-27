import cloudscraper as cs
import pandas as pd
from bs4 import BeautifulSoup as bs
import re
import os
from scraper_results import build_absolute_url, extract_query_value, parse_results_from_html
from scraper_scorecard import (
    normalize_scorecard_url,
    fetch_html as fetch_scorecard_html,
    parse_scorecard,
    save_outputs as save_scorecard_outputs,
)

base_url = "https://cricclubs.com/TitansCricket"
output_dir = "output"

scraper = cs.create_scraper()

# Utility functions

def get_html(url):
    print(f"Fetching: {url}")
    response = scraper.get(url)
    if response.status_code != 200:
        print(f"Failed: {response.status_code}")
        return None
    return response.text


def parse_table(html, table_id, expected_columns=None):
    soup = bs(html, 'html.parser')
    table = soup.find('table', {'id': table_id})

    if not table:
        print(f"Table not found: {table_id}")
        return None

    rows = table.find_all('tr')
    data = []

    for row in rows[1:]:
        cells = row.find_all(['th', 'td'])
        row_data = []

        for cell in cells:
            link = cell.find('a')
            text = link.get_text(strip=True) if link else cell.get_text(strip=True)
            row_data.append(text)

        if row_data:
            data.append(row_data)

    if not data:
        return None

    df = pd.DataFrame(data)

    if expected_columns and len(df.columns) == len(expected_columns):
        df.columns = expected_columns

    return df


def normalize_team_key(value):
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def extract_player_ids(html, table_id):
    soup = bs(html, "html.parser")
    table = soup.find("table", {"id": table_id})

    if not table:
        return []

    player_ids = []
    for row in table.find_all("tr")[1:]:
        player_link = row.find("a", href=True)
        player_url = build_absolute_url(player_link["href"] if player_link else "")
        player_ids.append(extract_query_value(player_url, "playerId"))

    return player_ids


def enrich_stat_df(df, html, table_id, league_id, club_id, team_lookup):
    df = df.copy()
    player_ids = extract_player_ids(html, table_id)
    team_column = "TEAM" if "TEAM" in df.columns else "TEAM_IMG"
    team_ids = [
        team_lookup.get(normalize_team_key(team_name), "")
        for team_name in df[team_column].tolist()
    ]

    df.insert(1, "LEAGUE_ID", league_id)
    df.insert(2, "CLUB_ID", club_id)
    df.insert(4, "PLAYER_ID", player_ids[: len(df)])
    insert_at = df.columns.get_loc(team_column) + 1
    df.insert(insert_at, "TEAM_ID", team_ids)
    return df


def extract_year(league_name):
    match = re.search(r'(20\d{2})', league_name)
    return match.group(1) if match else "unknown"


def ensure_folder(path):
    os.makedirs(path, exist_ok=True)


# Leagues, points table, and results require separate handling as they don't all
# follow the same player-stat table structure.

def get_leagues():
    url = f"{base_url}/viewAllLeagues.do"
    html = get_html(url)

    soup = bs(html, "html.parser")
    leagues = []

    for a in soup.find_all('a', href=True):
        href = a['href']

        if 'viewLeague.do?league=' in href:
            league_id = href.split('league=')[1].split('&')[0]
            league_name = a.text.strip()

            if league_name:
                leagues.append({
                    'League ID': league_id,
                    'League Name': league_name
                })

    df = pd.DataFrame(leagues)

    name_lower = df['League Name'].str.lower()
    df = df[
        name_lower.str.contains('titans') &
        name_lower.str.contains('second') &
        name_lower.str.contains('league') &
        ~name_lower.str.contains('school')
    ]

    print(f"Found {len(df)} leagues after filtering")
    return df


# Points table is separate as it doesn't follow the same HTML structure as the
# other stats tables.

def get_points_table(league_id, club_id):
    url = f"{base_url}/viewPointsTable.do?league={league_id}&clubId={club_id}"
    html = get_html(url)

    if not html:
        return None

    soup = bs(html, "html.parser")
    table = soup.find("table", {"id": "point-table"})

    if not table or not table.find("tbody"):
        print("Points table failed")
        return None

    data = []
    for row in table.find("tbody").find_all("tr", recursive=False):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) != 12:
            continue

        team_link = cells[1].find("a", href=True)
        team_url = build_absolute_url(team_link["href"] if team_link else "")

        row_data = {
            "SNO": cells[0].get_text(" ", strip=True),
            "LEAGUE_ID": league_id,
            "CLUB_ID": club_id,
            "TEAM": cells[1].get_text(" ", strip=True),
            "TEAM_URL": team_url,
            "TEAM_ID": extract_query_value(team_url, "teamId"),
            "TEAM_CLUB_ID": extract_query_value(team_url, "clubId"),
            "MAT": cells[2].get_text(" ", strip=True),
            "WON": cells[3].get_text(" ", strip=True),
            "LOST": cells[4].get_text(" ", strip=True),
            "NR": cells[5].get_text(" ", strip=True),
            "TIE": cells[6].get_text(" ", strip=True),
            "PTS": cells[7].get_text(" ", strip=True),
            "WIN%": cells[8].get_text(" ", strip=True),
            "NET RR": cells[9].get_text(" ", strip=True),
            "FOR": cells[10].get_text(" ", strip=True),
            "AGAINST": cells[11].get_text(" ", strip=True),
        }
        data.append(row_data)

    if not data:
        return None

    df = pd.DataFrame(data)
    df[["FOR_RUNS", "FOR_OVERS"]] = df["FOR"].str.split("/", expand=True)
    df[["AGAINST_RUNS", "AGAINST_OVERS"]] = df["AGAINST"].str.split("/", expand=True)
    return df


def get_results_table(league_id, club_id):
    url = f"{base_url}/viewLeagueResults.do?league={league_id}&clubId={club_id}"
    html = get_html(url)

    if not html:
        return None

    return parse_results_from_html(html, url)


def get_scorecard_frames(scorecard_url, league_id, league_name):
    full_scorecard_url = normalize_scorecard_url(scorecard_url)
    html = fetch_scorecard_html(full_scorecard_url)

    if not html:
        return None, None, None

    summary_df, batting_df, bowling_df = parse_scorecard(html, full_scorecard_url)

    if not summary_df.empty:
        summary_df.insert(1, "LEAGUE_ID", league_id)
        summary_df["LEAGUE_NAME"] = league_name

    if not batting_df.empty:
        batting_df.insert(1, "LEAGUE_ID", league_id)
        batting_df["LEAGUE_NAME"] = league_name

    if not bowling_df.empty:
        bowling_df.insert(1, "LEAGUE_ID", league_id)
        bowling_df["LEAGUE_NAME"] = league_name

    save_scorecard_outputs(summary_df, batting_df, bowling_df, html)
    return summary_df, batting_df, bowling_df


# Configuration for stats

STAT_CONFIG = {
    "batting": {
        "url": "viewLeagueBatting.do",
        "table_id": "tableBattingRecords",
        "columns": ["SNO","PLAYER","TEAM_IMG","BLANK","TEAM","MAT","INS","NO","RUNS","BALLS","AVG","SR","HS","100s","75s","50s","25s","0s","6s","4s"]
    },
    "bowling": {
        "url": "viewLeagueBowling.do",
        "table_id": "tableBowlingRecords",
        "columns": ["SNO","PLAYER","TEAM_IMG","BLANK","TEAM","MAT","INS","OVERS","RUNS","WKTS","BBF","MDNS","DOTS","ECON","AVE","SR","HATTRICK","4W","5W","WIDES","NB"]
    },
    "fielding": {
        "url": "viewLeagueFielding.do",
        "table_id": "tableFieldingRecords",
        "columns": ["SNO","PLAYER","TEAM_IMG","BLANK","TEAM","CATCHES","WK_CATCHES","DIRECT_RO","INDIRECT_RO","RUNS","STUMPINGS","TOTAL"]
    },
    "ranking": {
        "url": "viewLeagueRanking.do",
        "table_id": "tablePlayerRankings",
        "columns": ["SNO","PLAYER","TEAM","TEAM_IMG","BLANK","MAT","BATTING_RANK","BOWLING_RANK","FIELDING_RANK","OTHER_RANK","MOM","TOTAL_RANK"]
    }
}

# Main function to run the scraper

def run_scraper(club_id):
    leagues_df = get_leagues()
    total_leagues = len(leagues_df)

    # Store combined data per year
    yearly_data = {}
    all_results = []
    all_stats = {stat: [] for stat in STAT_CONFIG}
    all_stats["points"] = []
    all_scorecard_batting = []
    all_scorecard_bowling = []
    all_scorecard_summary = []

    for league_index, row in enumerate(leagues_df.iterrows(), start=1):
        _, row = row
        league_id = row['League ID']
        league_name = row['League Name']
        year = extract_year(league_name)

        print(f"\n[{league_index}/{total_leagues}] Processing league: {league_name} (league_id={league_id})")

        if year not in yearly_data:
            yearly_data[year] = {stat: [] for stat in STAT_CONFIG}
            yearly_data[year]["points"] = []
            yearly_data[year]["result"] = []

        # Points
        print(f"  - Points table")
        df_points = get_points_table(league_id, club_id)
        team_lookup = {}
        if df_points is not None:
            df_points["League Name"] = league_name
            yearly_data[year]["points"].append(df_points)
            all_stats["points"].append(df_points)
            team_lookup = {
                normalize_team_key(team_name): team_id
                for team_name, team_id in zip(df_points["TEAM"], df_points["TEAM_ID"])
            }

        # Stats
        for stat, config in STAT_CONFIG.items():
            print(f"  - {stat.capitalize()} records")
            url = f"{base_url}/{config['url']}?league={league_id}&clubId={club_id}"
            html = get_html(url)

            if not html:
                continue

            df = parse_table(html, config['table_id'], config['columns'])

            if df is not None:
                df = enrich_stat_df(df, html, config["table_id"], league_id, club_id, team_lookup)
                df["League Name"] = league_name
                yearly_data[year][stat].append(df)
                all_stats[stat].append(df)

        # Results
        print("  - Results")
        df_results = get_results_table(league_id, club_id)
        if df_results is not None:
            df_results["League Name"] = league_name
            yearly_data[year]["result"].append(df_results)
            all_results.append(df_results)

            scorecard_urls = [url for url in df_results["SCORECARD_URL"].dropna() if str(url).strip()]
            total_scorecards = len(scorecard_urls)
            print(f"  - Scorecards: {total_scorecards} found")

            for scorecard_index, scorecard_url in enumerate(scorecard_urls, start=1):
                progress_pct = round((scorecard_index / total_scorecards) * 100) if total_scorecards else 100
                print(
                    f"    [{scorecard_index}/{total_scorecards} | {progress_pct}%] "
                    f"Processing scorecard: {scorecard_url}"
                )
                summary_df, batting_df, bowling_df = get_scorecard_frames(
                    scorecard_url,
                    league_id,
                    league_name,
                )

                if summary_df is not None and not summary_df.empty:
                    all_scorecard_summary.append(summary_df)

                if batting_df is not None and not batting_df.empty:
                    all_scorecard_batting.append(batting_df)

                if bowling_df is not None and not bowling_df.empty:
                    all_scorecard_bowling.append(bowling_df)

    # Save per year
    for year, stats in yearly_data.items():
        year_folder = os.path.join(output_dir, year)
        ensure_folder(year_folder)

        print(f"\nSaving data for year {year}")

        for stat, dfs in stats.items():
            if dfs:
                combined_df = pd.concat(dfs, ignore_index=True)
                filename = os.path.join(year_folder, f"{stat}.csv")
                combined_df.to_csv(filename, index=False)
                print(f"Saved: {filename}")

    if all_results:
        combined_results_df = pd.concat(all_results, ignore_index=True)
        results_filename = os.path.join(output_dir, "result.csv")
        combined_results_df.to_csv(results_filename, index=False)
        print(f"Saved: {results_filename}")

    for stat, dfs in all_stats.items():
        if dfs:
            combined_df = pd.concat(dfs, ignore_index=True)
            filename = os.path.join(output_dir, f"{stat}.csv")
            combined_df.to_csv(filename, index=False)
            print(f"Saved: {filename}")

    if all_scorecard_summary:
        combined_df = pd.concat(all_scorecard_summary, ignore_index=True)
        filename = os.path.join(output_dir, "match_summary_scorecard.csv")
        combined_df.to_csv(filename, index=False)
        print(f"Saved: {filename}")

    if all_scorecard_batting:
        combined_df = pd.concat(all_scorecard_batting, ignore_index=True)
        filename = os.path.join(output_dir, "batting_scorecard.csv")
        combined_df.to_csv(filename, index=False)
        print(f"Saved: {filename}")

    if all_scorecard_bowling:
        combined_df = pd.concat(all_scorecard_bowling, ignore_index=True)
        filename = os.path.join(output_dir, "bowling_scorecard.csv")
        combined_df.to_csv(filename, index=False)
        print(f"Saved: {filename}")

# Entry point

if __name__ == "__main__":
    club_id = input("Enter club ID: ").strip()
    run_scraper(club_id)
