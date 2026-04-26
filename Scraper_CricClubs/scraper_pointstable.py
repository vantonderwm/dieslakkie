import cloudscraper as cs
import pandas as pd
from io import BytesIO

def get_pointstable(league_id, club_id):
    url = f"https://cricclubs.com/TitansCricket/viewPointsTableExcel.do?league={league_id}&year=null&clubId={club_id}"
    scraper = cs.create_scraper()
    response = scraper.get(url)
    if response.status_code == 200:
        df = pd.read_csv(BytesIO(response.content), encoding='ISO-8859-1')
        print(f"Successfully retrieved {len(df)} teams from the points table.")
        return df
    else:
        raise Exception(f"Failed to retrieve data. Status code: {response.status_code}")

if __name__ == "__main__":
    league_id = input("Enter league ID: ")
    club_id = input("Enter club ID: ")
    df = get_pointstable(league_id, club_id)
    if df is not None:
        df.columns = ["SNO","TEAM","MAT","WON","LOST","NR","TIE","PTS","WIN%","NET RR","FOR","AGAINST"]
        df[['FOR_RUNS', 'FOR_OVERS']] = df['FOR'].str.split('/', expand=True)
        df[['AGAINST_RUNS', 'AGAINST_OVERS']] = df['AGAINST'].str.split('/', expand=True)

        # Store data
        df.to_csv("scrape_pointstable.csv", index=False)
        df.to_excel("scrape_pointstable.xlsx", index=False)

        print("Data saved to scrape_pointstable.csv and scrape_pointstable.xlsx")