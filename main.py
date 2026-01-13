import asyncio
import csv
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

import nodriver as uc
from dotenv import load_dotenv
from browser import AccountData, RiotAccountCreator
from email_client import EmailClient

logging.getLogger("nodriver").setLevel(logging.WARNING)
shutdown_requested = False

def suppress_connection_errors(loop, context):
    if isinstance(context.get("exception"), (ConnectionResetError, OSError)):
        return
    loop.default_exception_handler(context)

def signal_handler(signum, frame):
    global shutdown_requested
    if shutdown_requested:
        print("\n\nForce quitting...")
        sys.exit(1)
    shutdown_requested = True
    print("\n\nShutdown requested, finishing current operation...")

def load_accounts(csv_path: str) -> list[AccountData]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return [AccountData(email=row["email"].strip(), username=row["username"].strip(),
                           password=row["password"].strip(), birthdate=row["birthdate"].strip())
                for row in csv.DictReader(f)]

def load_completed_emails(results_path: str) -> set[str]:
    if not Path(results_path).exists():
        return set()
    with open(results_path, newline="", encoding="utf-8") as f:
        return {row["email"].strip().lower() for row in csv.DictReader(f)}

def write_result(results_path: str, account: AccountData):
    file_exists = Path(results_path).exists()
    with open(results_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "email", "username", "password"])
        writer.writerow([datetime.now().isoformat(), account.email, account.username, account.password])

def load_proxies(path: str = "proxies.txt") -> list[str]:
    if not Path(path).exists():
        return []
    proxies = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if len(parts) == 4:
                host, port, user, password = parts
                proxies.append(f"http://{user}:{password}@{host}:{port}")
    return proxies

async def process_account(account: AccountData, email_client: EmailClient, headless: bool, results_path: str,
                          debug_cursor: bool = False, speed: float = 1.0, proxy: str | None = None) -> bool:
    print(f"\n{'='*60}")
    print(f"Creating account: {account.email}")
    print(f"Username: {account.username}")
    print(f"{'='*60}")

    creator = RiotAccountCreator(headless=headless, debug_cursor=debug_cursor, speed=speed, proxy=proxy)

    async def get_existing_codes(email: str) -> set[str]:
        return await email_client.get_existing_codes(email)

    async def get_otp(email: str, existing_codes: set[str]) -> str | None:
        return await email_client.wait_for_verification_code_with_timeout(email, existing_codes, timeout=25)

    try:
        await creator.start()
        success, message = await creator.create_account(account, get_otp, get_existing_codes)
        if success:
            print(f"SUCCESS: {message}")
            write_result(results_path, account)
        else:
            print(f"FAILED: {message}")
        return success
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        return False
    finally:
        await creator.stop()

async def main():
    load_dotenv()
    gmail_email, gmail_app_password = os.getenv("GMAIL_EMAIL"), os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_email or not gmail_app_password:
        print("ERROR: Missing GMAIL_EMAIL or GMAIL_APP_PASSWORD in .env file")
        print("Please create a .env file with:")
        print("  GMAIL_EMAIL=your-gmail@gmail.com")
        print("  GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx")
        return

    accounts_path, results_path = "accounts.csv", "results.csv"

    if not Path(accounts_path).exists():
        print(f"ERROR: {accounts_path} not found")
        print("Please create accounts.csv with columns: email,username,password,birthdate")
        print("Example:")
        print("  email,username,password,birthdate")
        print("  user@example.com,myusername,SecurePass123!,01/25/1998")
        return

    all_accounts = load_accounts(accounts_path)
    if not all_accounts:
        print("ERROR: No accounts found in accounts.csv")
        return

    completed_emails = load_completed_emails(results_path)
    accounts = [a for a in all_accounts if a.email.lower() not in completed_emails]
    proxies = load_proxies()

    print(f"Loaded {len(all_accounts)} account(s) from CSV")
    if completed_emails:
        print(f"Skipping {len(all_accounts) - len(accounts)} already completed account(s)")
    if not accounts:
        print("All accounts already completed!")
        return
    print(f"Remaining: {len(accounts)} account(s) to create")
    print(f"Loaded {len(proxies)} proxy(ies)" if proxies else "No proxies loaded, running without proxy")

    email_client = EmailClient(gmail_email, gmail_app_password)
    successful, failed = 0, 0

    for i, account in enumerate(accounts, 1):
        if shutdown_requested:
            print("Shutdown requested, stopping...")
            break

        proxy = proxies[(i - 1) % len(proxies)] if proxies else None
        print(f"\n[{i}/{len(accounts)}] Processing account...")
        if proxy:
            print(f"Using proxy: {proxy.split('@')[1]}")

        success = await process_account(account=account, email_client=email_client, headless=False,
                                        results_path=results_path, debug_cursor=True, speed=2.0, proxy=proxy)
        if success:
            successful += 1
        else:
            failed += 1

        if i < len(accounts) and not shutdown_requested:
            print("Waiting 5 seconds before next account...")
            await asyncio.sleep(5)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total accounts: {len(accounts)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Results saved to: {results_path}")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    loop = uc.loop()
    loop.set_exception_handler(suppress_connection_errors)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\nExiting...")
