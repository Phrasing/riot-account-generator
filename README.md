# Riot Account Generator

Automated Riot Games account creation with human-like browser behavior.

## Requirements

- Python 3.13+
- Gmail account with App Password
- Chrome browser

## Setup

```bash
uv sync
cp .env.example .env
cp accounts.csv.example accounts.csv
```

Edit `.env` with your Gmail credentials. Edit `accounts.csv` with accounts to create (or use the generator).

## Usage

Generate accounts:
```bash
uv run python generate_accounts.py example.com -n 10
```

Run the creator:
```bash
uv run python main.py
```

## Optional: Proxies

```bash
cp proxies.txt.example proxies.txt
```

Format: `host:port:username:password`
