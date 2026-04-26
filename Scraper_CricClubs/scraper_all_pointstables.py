import pandas as pd
import re
import os
from scraper_pointstable import get_pointstable

def main():
    # Read the leagues list
    df_leagues = pd.read_csv('scraper_leagueslist.csv')
    
    club_id = input("Enter club ID: ")
    
    # Create directories for outputs
    os.makedirs('_csv_scrapepointstables', exist_ok=True)
    os.makedirs('_xlsx_pointstables', exist_ok=True)
    
    for index, row in df_leagues.iterrows():
        league_id = str(row['League ID'])
        league_name = row['League Name']
        
        # Dynamically extract year for filename
        years = re.findall(r'\b(20\d{2})\b', league_name)
        if len(years) == 2:
            year = f"{years[0]}_{years[1]}"
        elif len(years) == 1:
            year = years[0]
        else:
            year = 'Original'
        
        try:
            df = get_pointstable(league_id, club_id)
            if df is not None:
                # Process columns as in the original scraper
                df.columns = ["SNO","TEAM","MAT","WON","LOST","NR","TIE","PTS","WIN%","NET RR","FOR","AGAINST"]
                df[['FOR_RUNS', 'FOR_OVERS']] = df['FOR'].str.split('/', expand=True)
                df[['AGAINST_RUNS', 'AGAINST_OVERS']] = df['AGAINST'].str.split('/', expand=True)
                
                # Clean filename
                csv_filename = f"_csv_scrapepointstables/TitansSecondLeague_Season{year}.csv"
                df.to_csv(csv_filename, index=False)
                
                print(f"Data saved to {csv_filename}")
        except Exception as e:
            print(f"Failed to retrieve data for league {league_id} ({league_name}): {e}")

if __name__ == "__main__":
    main()