import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("postgres://koesqktgatmdcd:c4f3c132af0e9739adf8c81cfa8392e85e1e36fa23f970ccdd8711281095c2fb@ec2-52-202-146-43.compute-1.amazonaws.com:5432/d2t25rtf3u0bae")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Get user's cash balance
    users = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    cash = users[0]["cash"]

    # Add cash balance to portfolio value
    portfolio_value = cash

    # Get user's owned stocks
    stocks = db.execute("SELECT symbol, SUM(shares) AS share_count FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING share_count > 0",
                        user_id=session["user_id"])

    # Get updated quotes for each stock in the user's portfolio
    quotes = {}
    for stock in stocks:
        symbol = stock["symbol"]
        quotes[symbol] = lookup(symbol)

        # Add value of all holdings of each stock to the portfolio value
        portfolio_value += quotes[symbol]["price"] * stock["share_count"]

    return render_template("portfolio.html", cash=cash, stocks=stocks, quotes=quotes, portfolio_value=portfolio_value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # Request method is "GET"
    if request.method == "GET":
        return render_template("buy.html")

    # Request method is "POST"
    else:
        # Lookup the stock symbol provided
        quote = lookup(request.form.get("symbol"))

        # Check that a non-null value was returned
        if not quote:
            return apology("must provide valid stock symbol", 400)

        price = quote["price"]

        shares = request.form.get("shares")

        # Attempt to convert shares to int, dropping any fractional value
        try:
            shares = int(float(shares) // 1)
        except:
            return apology("must provide an integer greater than 0 for shares", 400)

        # Check that the user is buying at least 1 share
        if shares < 1:
            return apology("minimum number of shares than can be bought is 1", 400)

        # Calculate total price of transaction
        total_price = price * shares

        # Get cash remaining in user's account
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        cash = rows[0]["cash"]

        # Make sure user has enough cash for the transaction
        if total_price > cash:
            return apology("insufficient cash balance", 403)

        # Calculate cash post-transaction
        cash -= total_price

        # Update user's cash balance and transactions
        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=cash, user_id=session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"], symbol=quote["symbol"], shares=shares, price=price)

        flash("Purchase successful")
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    transactions = db.execute("SELECT symbol, shares, price, date_time FROM transactions WHERE user_id = :user_id",
                              user_id=session["user_id"])
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # Request method is "GET"
    if request.method == "GET":
        return render_template("quote.html")

    # Request method is "POST"
    else:
        # Lookup the stock symbol provided
        quote = lookup(request.form.get("symbol"))

        # Check that a non-null value was returned
        if not quote:
            return apology("must provide valid stock symbol", 400)

        return render_template("quoted.html", quote=quote)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Request method is "GET"
    if request.method == "GET":
        return render_template("register.html")

    # Request method is "POST"
    else:
        # Check that username is not blank
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Check that password is not blank
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Check if username already exists or not
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)
        # If rows does not have a length of 0, then the username is taken
        if len(rows) != 0:
            return apology("username is already taken", 403)

        # Check that passwords match
        if password != confirmation:
            return apology("passwords did not match", 403)

        # Hash the password
        pw_hash = generate_password_hash(password)

        db.execute("INSERT INTO users (username, hash) VALUES (:username, :pw_hash)", username=username, pw_hash=pw_hash)
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Request method is "GET"
    if request.method == "GET":
        return render_template("sell.html")

    # Request method is "POST"
    else:
        # Lookup the stock symbol provided
        quote = lookup(request.form.get("symbol"))

        # Check that a non-null value was returned
        if not quote:
            return apology("must provide valid stock symbol", 400)

        price = quote["price"]

        shares = request.form.get("shares")

        # Attempt to convert shares to int, dropping any fractional value
        try:
            shares = int(float(shares) // 1)
        except:
            return apology("must provide an integer greater than 0 for shares", 400)

        # Check that the user is selling at least 1 share
        if shares < 1:
            return apology("minimum number of shares than can be bought is 1", 400)

        # Get shares remaining in user's account
        rows = db.execute("SELECT SUM(shares) AS share_count FROM transactions WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol",
                          user_id=session["user_id"], symbol=quote["symbol"])
        owned = rows[0]["share_count"]

        # Make sure user has enough shares for the transaction
        if shares > owned:
            return apology("insufficient shares", 403)

        # Calculate total price of transaction
        total_price = price * shares

        # Get cash remaining in user's account
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        cash = rows[0]["cash"]

        # Calculate cash post-transaction
        cash += total_price

        # Update user's cash balance and transactions
        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=cash, user_id=session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"], symbol=quote["symbol"], shares=-shares, price=price)

        flash("Sale successful")
        return redirect("/")


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """Deposit money into account"""
    if request.method == "GET":
        return render_template("deposit.html")
    else:
        try:
            deposit = float(request.form.get("deposit_amount"))
        except:
            return apology("must enter a valid dollar amount", 400)

        # Make sure the amount entered is not zero or less
        if deposit <= 0:
            return apology("must deposit more than $0", 400)

        # Get cash remaining in user's account
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        cash = rows[0]["cash"]

        # Add deposit to cash
        cash += deposit

        # Update user's cash balance
        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=cash, user_id=session["user_id"])

        flash("Deposit successful")
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
