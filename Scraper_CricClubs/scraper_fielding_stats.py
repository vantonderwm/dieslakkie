import pandas as pd
from bs4 import BeautifulSoup as bs
import cloudscraper as cs


def fetch_and_save_html(url, output_file_path):
    print(f"Fetching HTML from URL: {url}")
    scraper = cs.create_scraper()
    response = scraper.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch HTML: HTTP {response.status_code}")
        return None
    html = response.text
    with open(output_file_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"HTML saved to: {output_file_path}")
    return html


def parse_fielding_from_html_file(html_file_path):
    print(f"Reading HTML from file: {html_file_path}")
    with open(html_file_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = bs(html, 'html.parser')
    
    # Find the fielding table
    table = soup.find('table', {'id': 'tableFieldingRecords'})
    if not table:
        print("Fielding table with id 'tableFieldingRecords' not found.")
        return None
    
    rows = table.find_all('tr')
    data = []
    for row in rows[1:]:  # Skip header row
        cells = row.find_all(['th', 'td'])
        row_data = []
        for cell in cells:
            # Extract text, preferring link text if present (for runs, etc.)
            text = cell.get_text(strip=True)
            link = cell.find('a')
            if link and link.get_text(strip=True):
                text = link.get_text(strip=True)
            row_data.append(text)
        if row_data:  # Only add non-empty rows
            data.append(row_data)
    
    if data:
        df = pd.DataFrame(data)
        print(f"Parsed table with shape: {df.shape}")
        print(f"Successfully retrieved {len(df)} fielders from the HTML file.")
        return df
    else:
        print("No data rows found in the table.")
        return None

if __name__ == "__main__":
    # Enter the URL
    url = input("Enter the URL to fetch HTML from: ").strip()
    if not url:
        print("No URL provided.")
        exit(1)
    
    html_file_path = "fetched_html.txt"  # Save fetched HTML to this file
    html = fetch_and_save_html(url, html_file_path)
    if html is None:
        exit(1)
    
    df = parse_fielding_from_html_file(html_file_path)
    if df is not None:
        print(f"DataFrame shape: {df.shape}")
        print(f"Columns: {df.columns}")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            print(f"Flattened columns: {df.columns}")
        expected_columns = ["SNO","PLAYER","TEAM_IMG","BLANK","CATCHES","WK_CATCHES","DIRECT_RO","INDIRECT_RO","RUNS","STUMPINGS","TOTAL"]
        if len(df.columns) == len(expected_columns):
            df.columns = expected_columns
        else:
            print(f"Column count mismatch: expected {len(expected_columns)}, got {len(df.columns)}")
            print("Skipping column rename.")

        # Store data
        df.to_csv("scrape_fielding_stats.csv", index=False)

        print("Data saved to scrape_fielding_stats.csv")