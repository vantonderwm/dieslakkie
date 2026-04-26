import cloudscraper as cs
import pandas as pd
from bs4 import BeautifulSoup as bs
from io import BytesIO
import re
import os

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


def extract_year(league_name):
    match = re.search(r'(20\d{2})', league_name)
    return match.group(1) if match else "unknown"


def ensure_folder(path):
    os.makedirs(path, exist_ok=True)


# Leagues and points table require separate handling as they don't follow the same HTML structure as the other stats tables

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


# Points table is separate as it doesn't follow the same HTML structure as the other stats tables

def get_points_table(league_id, club_id):
    url = f"{base_url}/viewPointsTableExcel.do?league={league_id}&year=null&clubId={club_id}"

    response = scraper.get(url)
    if response.status_code != 200:
        print("Points table failed")
        return None

    df = pd.read_csv(BytesIO(response.content), encoding='ISO-8859-1')

    df.columns = ["SNO","TEAM","MAT","WON","LOST","NR","TIE","PTS","WIN%","NET RR","FOR","AGAINST"]

    df[['FOR_RUNS', 'FOR_OVERS']] = df['FOR'].str.split('/', expand=True)
    df[['AGAINST_RUNS', 'AGAINST_OVERS']] = df['AGAINST'].str.split('/', expand=True)

    return df


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
        "columns": ["SNO","PLAYER","TEAM_IMG","BLANK","MAT","TEAM","INS","OVERS","RUNS","WKTS","BBF","MDNS","DOTS","ECON","AVE","SR","HATTRICK","4W","5W","WIDES","NB"]
    },
    "fielding": {
        "url": "viewLeagueFielding.do",
        "table_id": "tableFieldingRecords",
        "columns": ["SNO","PLAYER","TEAM_IMG","BLANK","CATCHES","WK_CATCHES","DIRECT_RO","INDIRECT_RO","RUNS","STUMPINGS","TOTAL"]
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

    # Store combined data per year
    yearly_data = {}

    for _, row in leagues_df.iterrows():
        league_id = row['League ID']
        league_name = row['League Name']
        year = extract_year(league_name)

        print(f"\nProcessing: {league_name}")

        if year not in yearly_data:
            yearly_data[year] = {stat: [] for stat in STAT_CONFIG}
            yearly_data[year]["points"] = []

        # Stats
        for stat, config in STAT_CONFIG.items():
            url = f"{base_url}/{config['url']}?league={league_id}&clubId={club_id}"
            html = get_html(url)

            if not html:
                continue

            df = parse_table(html, config['table_id'], config['columns'])

            if df is not None:
                df["League Name"] = league_name
                yearly_data[year][stat].append(df)

        # Points
        df_points = get_points_table(league_id, club_id)
        if df_points is not None:
            df_points["League Name"] = league_name
            yearly_data[year]["points"].append(df_points)

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

# Entry point

if __name__ == "__main__":
    club_id = input("Enter club ID: ").strip()
    run_scraper(club_id)