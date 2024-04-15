import csv
import datetime
import pytz
import requests
import urllib
import uuid
import time

from flask import redirect, render_template, session
from functools import wraps


def apology(message, code=400):
    """Render message as an apology to user."""

    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [
            ("-", "--"),
            (" ", "-"),
            ("_", "__"),
            ("?", "~q"),
            ("%", "~p"),
            ("#", "~h"),
            ("/", "~s"),
            ('"', "''"),
        ]:
            s = s.replace(old, new)
        return s

    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def lookup(symbol):
    """Look up quote for symbol using Alpha Vantage API."""
    # API request preparation
    symbol = symbol.upper()
    api_key = 'MNFKXB2M6YSWS9KW'  # Replace with your actual API key
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={symbol}&interval=5min&apikey={api_key}"

    # Query API with retry logic
    attempts = 0
    while attempts < 3:
        try:
            response = requests.get(url)
            response.raise_for_status()

            # Parse JSON
            data = response.json()
            time_series = data.get("Time Series (5min)")
            if not time_series:
                return {"error": "No data available for this symbol"}

            # Get the latest data entry
            latest_datetime = max(time_series.keys())  # Finds the latest time entry
            latest_data = time_series[latest_datetime]

            # Extract the closing price and format it
            price = round(float(latest_data["4. close"]), 2)
            return {"price": price, "symbol": symbol}

        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:  # Rate limited
                time.sleep((2 ** attempts) * 1)  # Exponential back-off
            else:
                return {"error": "HTTP error", "message": str(e)}
        except (KeyError, ValueError) as e:
            return {"error": "Data parsing error", "message": str(e)}
        except requests.RequestException as e:
            return {"error": "Request failed", "message": str(e)}

        attempts += 1

    return {"error": "API request failed after retries"}


def usd(value):
    """Format value as USD."""
    return f"${value:,.2f}"
