import cloudscraper as cs
import pandas as pd
from bs4 import BeautifulSoup as bs

def get_leagues(club_id):
    url = f"https://cricclubs.com/TitansCricket/viewAllLeagues.do"
    scraper = cs.create_scraper()
    response = scraper.get(url)
    if response.status_code == 200:
        soup = bs(response.text, "html.parser")
        leagues = []
        # Find all links containing league IDs
        for a in soup.find_all('a', href=True):
            href = a['href']
            if 'league' in href.lower():
                print(f"Found link: {href} - {a.text.strip()}")
            if 'viewLeague.do?league=' in href:
                league_id = href.split('league=')[1].split('&')[0]
                league_name = a.text.strip()
                if league_name:  # Ensure name is not empty
                    leagues.append({'League ID': league_id, 'League Name': league_name})
        df = pd.DataFrame(leagues)
        # Filter for leagues containing 'titans', 'second', 'league' (case-insensitive) and exclude 'school'
        name_lower = df['League Name'].str.lower()
        df = df[name_lower.str.contains('titans') & name_lower.str.contains('second') & name_lower.str.contains('league') & ~name_lower.str.contains('school')]
        # Add URL column
        df['URL'] = 'https://cricclubs.com/TitansCricket/viewLeague.do?league=' + df['League ID']
        print(f"Successfully retrieved {len(df)} leagues after filtering.")
        return df
    else:
        raise Exception(f"Failed to retrieve data. Status code: {response.status_code}")

if __name__ == "__main__":
    club_id = input("Enter club ID: ")
    df = get_leagues(club_id)
    if df is not None:
        df.to_csv('scraper_leagueslist.csv', index=False)
        print("Data saved to scraper_leagueslist.csv")