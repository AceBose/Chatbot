import urllib
import requests
from bs4 import BeautifulSoup
import pandas as pd

seasons = {
    "winter" : ["december", "january", "february"],
    "spring" : ["march", "april", "may"],
    "summer" : ["june", "july", "august"],
    "fall" : ["september", "october", "november"],
}

months = {
    "january" : "winter",
    "february" : "winter",
    "march" : "spring",
    "april" : "spring",
    "may" : "spring",
    "june" : "summer",
    "july" : "summer",
    "august" : "summer",
    "september" : "fall",
    "october" : "fall",
    "november" : "fall",
    "december": "winter",
}


def main():
    recs = get_travel_df()
    month_options = recs.loc[recs.loc[:, "Month"] == 'january', :]
    temp_index = (month_options['Low Temp'] <= 75) & (month_options['High Temp'] >= 75)
    final_options = month_options.loc[temp_index, "Town"]
    print(final_options)
    # print(recs)


def get_travel_df():
    """Create dataframe of various travel recommendations and the temperatures they are at various months"""
    travel_df = pd.DataFrame(columns=["Town", "Low Temp", "High Temp", "Month"])
    for month in months.keys():
        travel_url = f'https://www.thebesttimetovisit.com/weather/wheretogoin{month}.php'
        req = requests.get(travel_url)
        soup = BeautifulSoup(req.text, "lxml")
        table = soup.find_all('table')[2]  # should be third table on page
        table_columns = ["Town", "Low Temp", "High Temp", "Wet Days", "Recs"]

        city_dicts = []
        for row in table.find_all('tr'):
            city_dict = {}
            columns = row.find_all('td')
            for i, column in enumerate(columns):
                city_dict[table_columns[i]] = column.get_text()

            city_dicts.append(city_dict)

        month_df = pd.DataFrame(data=city_dicts, columns=table_columns)
        month_df = month_df.dropna(axis=0)
        month_df = month_df.drop(columns=["Wet Days", "Recs"])
        month_df.loc[:, "Low Temp"] = month_df.loc[:, "Low Temp"].apply(CtoF)
        month_df.loc[:, "High Temp"] = month_df.loc[:, "High Temp"].apply(CtoF)
        month_df.loc[:, "Month"] = month
        month_df.loc[:, "Town"] = month_df.loc[:, "Town"].apply(convert_town)
        travel_df = travel_df.append(month_df)

    travel_df = travel_df.reset_index(drop=True)
    return travel_df

def CtoF(celsius):
    return round((int(celsius) * 9 / 5) + 32, 1)

def parenthetic_contents(string):
    """Generate parenthesized contents in string as pairs (level, contents)."""
    stack = []
    for i, c in enumerate(string):
        if c == '(':
            stack.append(i)
        elif c == ')' and stack:
            start = stack.pop()
            yield (len(stack), string[start + 1: i])

def convert_town(in_town):
    """Make town go from `County (City)` to `City, Country`"""
    contents = parenthetic_contents(f"{in_town}")
    city = in_town
    for level, str in contents:
        if level == 0:
            city = str

    country = in_town[:in_town.find(city) - 1]
    city += f", {country}"

    return city


if __name__ == "__main__":
    main()
