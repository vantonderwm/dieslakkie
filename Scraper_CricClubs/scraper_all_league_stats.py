import cloudscraper as cs
import pandas as pd
from bs4 import BeautifulSoup as bs
import re
import os
from io import BytesIO
from scraper_pointstable import get_pointstable
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_league_data(league_id, data_type, club_id):
    base_url = f"https://www.cricclubs.com/view{data_type}.do?league={league_id}&club={club_id}"
    scraper = cs.create_scraper()
    print(f"Fetching URL: {base_url}")
    response = scraper.get(base_url)
    if response.status_code == 200:
        soup = bs(response.text, "html.parser")
        if data_type == 'Results':
            text = soup.get_text()
            lines = text.split('\n')
            matches = []
            current_date = None
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                # Look for date pattern (single digit or two-digit day followed by month and year)
                if line and line[0].isdigit() and 'Mar' in line or 'Feb' in line or 'Jan' in line or 'Nov' in line or 'Oct' in line or 'Dec' in line or 'Apr' in line or 'May' in line or 'Jun' in line or 'Jul' in line or 'Aug' in line or 'Sep' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        current_date = parts[0] + ' ' + parts[1] + ' ' + parts[2] if len(parts) >= 3 else line
                        i += 1
                        continue
                elif current_date and 'V' in line and not line.startswith('Titans'):
                    # Extract match teams
                    match_teams = line
                    i += 1
                    # Get result on next line
                    if i < len(lines):
                        result = lines[i].strip()
                        if result and not result.startswith('League') and not result.startswith('Ball'):
                            matches.append({'Date': current_date, 'Teams': match_teams, 'Result': result})
                i += 1
            
            if matches:
                df = pd.DataFrame(matches)
                df[['Team1', 'Team2']] = df['Teams'].str.split('V', expand=True)
                df['Team1'] = df['Team1'].str.strip()
                df['Team2'] = df['Team2'].str.strip()
                df = df[['Date', 'Team1', 'Team2', 'Result']]
                print(f"Successfully retrieved {len(df)} rows from {data_type}.")
                return df
        # For other data_types, try to find table
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')
            data = []
            for row in rows:
                cols = row.find_all(['td', 'th'])
                cols = [col.text.strip() for col in cols]
                if cols:
                    data.append(cols)
            if data:
                df = pd.DataFrame(data[1:], columns=data[0])
                print(f"Successfully retrieved {len(df)} rows from {data_type}.")
                return df
        print(f"No data found for {data_type}.")
        return pd.DataFrame()
    else:
        print(f"Failed to retrieve {data_type}. Status code: {response.status_code}")
        return pd.DataFrame()

def main():
    # Read the leagues list
    df_leagues = pd.read_csv('scraper_leagueslist.csv')
    df_leagues = df_leagues[df_leagues['League ID'] == 18]  # only 18 for testing
    
    club_id = input("Enter club ID: ")
    
    # Create directories for outputs
    data_types = ['Results', 'Batting', 'Bowling', 'Fielding', 'Ranking']
    for dt in data_types:
        os.makedirs(f'_csv_{dt.lower()}', exist_ok=True)
        os.makedirs(f'_xlsx_{dt.lower()}', exist_ok=True)
    
    for index, row in df_leagues.iterrows():
        league_id = str(row['League ID'])
        league_name = row['League Name']
        
        # Extract year
        years = re.findall(r'\b(20\d{2})\b', league_name)
        if len(years) == 2:
            year = f"{years[0]}_{years[1]}"
        elif len(years) == 1:
            year = years[0]
        else:
            year = 'Original'
        
        for data_type in data_types:
            try:
                df = get_league_data(league_id, data_type, club_id)
                if df is not None and not df.empty:
                    csv_filename = f"_csv_{data_type.lower()}/TitansSecondLeague_Season{year}_{data_type.lower()}.csv"
                    excel_filename = f"_xlsx_{data_type.lower()}/TitansSecondLeague_Season{year}_{data_type.lower()}.xlsx"
                    df.to_csv(csv_filename, index=False)
                    df.to_excel(excel_filename, index=False)
                    print(f"Data saved to {csv_filename} and {excel_filename}")
            except Exception as e:
                print(f"Failed to retrieve {data_type} for league {league_id}: {e}")

if __name__ == "__main__":
    main()