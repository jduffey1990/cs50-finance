# C$50 Finance: A playful portfolio Web Application

# The Site is going to take a long time to load with the free server, please wait [at least a minute at this link](https://duffeyfinance.onrender.com/) if the load symbol is still spinning up.

Embark on a financial journey with C$50 Finance, my capstone project for Harvard's CS50 course during week 9. This interactive web application gamifies stock trading, enabling users to manage a virtual stock portfolio using simulated funds.

## Built With
- Python and Flask for backend logic, incorporating session-based authentication.
- SQL for database management.
- Front-end development with HTML and styled using Bootstrap.

## Overview
This is an innovative web app designed to simulate stock market trading. Users can engage in buying and selling shares with fictitious currency while accessing stock prices (previous market close) via the [Massive](https://massive.com/) (formerly Polygon.io) API. It also offers a comprehensive view of one's investment portfolio and transaction history, adding an educational and entertaining twist to learning about the stock market.

## Getting Started
Embark on your journey with "C$50 Finance" by following these straightforward steps to set up and launch the application:
1. **Clone the Repository**: Begin by cloning the repository to your local machine. Navigate to your desired directory in the terminal and use the command `git clone <repository-url>`. This is still in my class folder, if I haven't changed the markdown yet after making it's own repo, replace <repository-url> with the actual repo url.

2. **Environment Setup**: Once inside the directory, create a virtual environment for Python by executing `python3 -m venv .venv`. Activate this environment with `source .venv/bin/activate` on Unix/macOS or `.venv\Scripts\activate` on Windows.

3. **Dependency Installation**: With the virtual environment active, install the project's dependencies by running `pip install -r requirements.txt`. This command ensures all necessary Python packages, including Flask and CS50's SQL library, are available.

4. **API Key**: Grab a free API key from [Massive](https://massive.com/dashboard/keys), then copy `.env.example` to `.env` and paste your key in. The free tier (5 requests/minute) is plenty — the app caches quotes for 15 minutes.

5. **Create the Database**: Two options. For quick offline development, create a local SQLite file with `sqlite3 finance.db < schema.sql` — the app uses it automatically when `DATABASE_URL` is unset. For a persistent database (and what production uses), create a free Postgres database at [Neon](https://neon.tech), apply `schema.pg.sql` to it, and put its connection string in `.env` as `DATABASE_URL`.

6. **Launch the Application**: With everything in place, start the Flask application by executing `flask run` in your terminal. This command initiates a local web server. Navigate to the URL outputted by Flask (typically `http://127.0.0.1:5000/`) in your web browser to view the application.

7. **Create an Account**: To fully engage with "C$50 Finance," register for an account through the website's registration page. This allows you to simulate stock transactions and manage a virtual portfolio.  **please do not use any information on here that you use in other locations.  I used a password encryption tool, but this is still an unmonitored web application.**

By following these steps, you'll have "C$50 Finance" up and running, ready for you to explore the functionalities of stock trading within a controlled, simulated environment.

## Deployment (Render + Neon)

The live site runs as a [Render](https://render.com) web service with its data in a [Neon](https://neon.tech) Postgres database, so user accounts and trades survive deploys and free-tier spin-downs (a plain SQLite file on Render's ephemeral disk would be reset to its build-time state every time the service restarts).

- **Build command**: `pip install -r requirements.txt`
- **Start command**: `gunicorn app:app`
- **Environment variables**: `DATABASE_URL` (the Neon connection string) and `MASSIVE_API_KEY`

To migrate an existing local `finance.db` into a fresh Neon database, run `python scripts/migrate_sqlite_to_pg.py` once — it applies `schema.pg.sql`, copies every table with original ids, and verifies row counts.

## Application Features

### Register Page
Enables new users to create an account. Displays an error for incomplete submissions or duplicate usernames.

### Home/Index Page
Presents a detailed table of the user's stock portfolio, including the number of shares owned, current stock prices, total holding values, unrealized gain/loss per position (in dollars and percent), available cash balance, and combined net worth. Each visit also records a daily net-worth snapshot, charted over time at the bottom of the page.

### Quote Page
Facilitates stock price checks (previous market close) by querying the Massive (formerly Polygon.io) API, with error handling for invalid stock symbols.

### Buy Page
Allows users to purchase stocks by specifying the symbol and desired share quantity, ensuring transactions are viable based on current market prices and user funds.

### Sell Page
Enables the sale of stocks currently held in the user's portfolio, updating the database accordingly.

### History Page
Chronicles all user transactions, listing the nature of the transaction (buy/sell), stock symbol, transaction price, share quantity, and the date/time of execution.

### Time Machine Page
Answers "what if I had invested $X in Y back then?" — pick a stock, a dollar amount, and any date up to two years ago, and see the investment's value charted day by day through today, with the total gain or loss. A hands-on lesson in compound returns, powered by Massive's historical daily bars.

### Leaderboard Page
Ranks all users by net worth (cash plus holdings at last-known prices). Everyone starts with the same $10,000, so the ranking reflects pure investing performance.
