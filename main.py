import argparse
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

# Locks for parallel execution
_results_lock = asyncio.Lock()
_completed_lock = asyncio.Lock()
_completed_emails: set[str] = set()
_proxy_index = 0
_proxy_lock = asyncio.Lock()


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
        return [
            AccountData(
                email=row["email"].strip(),
                username=row["username"].strip(),
                password=row["password"].strip(),
                birthdate=row["birthdate"].strip(),
            )
            for row in csv.DictReader(f)
        ]


def load_completed_emails(results_path: str) -> set[str]:
    if not Path(results_path).exists():
        return set()
    with open(results_path, newline="", encoding="utf-8") as f:
        return {row["email"].strip().lower() for row in csv.DictReader(f)}


async def write_result(results_path: str, account: AccountData):
    async with _results_lock:
        file_exists = Path(results_path).exists()
        with open(results_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "email", "username", "password"])
            writer.writerow(
                [
                    datetime.now().isoformat(),
                    account.email,
                    account.username,
                    account.password,
                ]
            )


async def get_next_proxy(proxies: list[str]) -> str | None:
    global _proxy_index
    if not proxies:
        return None
    async with _proxy_lock:
        proxy = proxies[_proxy_index]
        _proxy_index = (_proxy_index + 1) % len(proxies)
        return proxy


async def mark_completed(email: str):
    async with _completed_lock:
        _completed_emails.add(email.lower())


async def is_completed(email: str) -> bool:
    async with _completed_lock:
        return email.lower() in _completed_emails


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


async def process_account(
    account: AccountData,
    email_client: EmailClient,
    headless: bool,
    results_path: str,
    debug_cursor: bool = False,
    speed: float = 1.0,
    proxy: str | None = None,
    window_index: int = 0,
) -> bool:
    print(f"\n{'=' * 60}")
    print(f"[Window {window_index}] Creating account: {account.email}")
    print(f"Username: {account.username}")
    print(f"{'=' * 60}")

    creator = RiotAccountCreator(
        headless=headless,
        debug_cursor=debug_cursor,
        speed=speed,
        proxy=proxy,
        window_index=window_index,
    )

    async def get_existing_codes(email: str) -> set[str]:
        return await email_client.get_existing_codes(email)

    async def get_otp(email: str, existing_codes: set[str]) -> str | None:
        return await email_client.wait_for_verification_code_with_timeout(
            email, existing_codes, timeout=20
        )

    try:
        await creator.start()
        success, message = await creator.create_account(
            account, get_otp, get_existing_codes, max_otp_retries=1
        )
        if success:
            print(f"[Window {window_index}] SUCCESS: {message}")
            await write_result(results_path, account)
            await mark_completed(account.email)
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


async def main(max_concurrent: int = 3):
    load_dotenv()
    gmail_email, gmail_app_password = (
        os.getenv("GMAIL_EMAIL"),
        os.getenv("GMAIL_APP_PASSWORD"),
    )

    if not gmail_email or not gmail_app_password:
        print("ERROR: Missing GMAIL_EMAIL or GMAIL_APP_PASSWORD in .env file")
        print("Please create a .env file with:")
        print("  GMAIL_EMAIL=your-gmail@gmail.com")
        print("  GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx")
        return

    accounts_path, results_path = "accounts.csv", "results.csv"

    if not Path(accounts_path).exists():
        print(f"ERROR: {accounts_path} not found")
        print(
            "Please create accounts.csv with columns: email,username,password,birthdate"
        )
        print("Example:")
        print("  email,username,password,birthdate")
        print("  user@example.com,myusername,SecurePass123!,01/25/1998")
        return

    all_accounts = load_accounts(accounts_path)
    if not all_accounts:
        print("ERROR: No accounts found in accounts.csv")
        return

    global _completed_emails
    completed_emails = load_completed_emails(results_path)
    _completed_emails = completed_emails.copy()
    accounts = [a for a in all_accounts if a.email.lower() not in completed_emails]
    proxies = load_proxies()

    print(f"Loaded {len(all_accounts)} account(s) from CSV")
    if completed_emails:
        print(
            f"Skipping {len(all_accounts) - len(accounts)} already completed account(s)"
        )
    if not accounts:
        print("All accounts already completed!")
        return
    print(f"Remaining: {len(accounts)} account(s) to create")
    print(
        f"Loaded {len(proxies)} proxy(ies)"
        if proxies
        else "No proxies loaded, running without proxy"
    )

    print(f"Running with {max_concurrent} parallel browser(s)")

    email_client = EmailClient(gmail_email, gmail_app_password)
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_semaphore(account: AccountData, task_index: int) -> bool:
        if shutdown_requested or await is_completed(account.email):
            return False
        # Stagger initial browser starts by 3 seconds each
        if task_index < max_concurrent:
            await asyncio.sleep(task_index * 3)
        async with semaphore:
            if shutdown_requested:
                return False
            window_index = task_index % max_concurrent
            proxy = await get_next_proxy(proxies)
            print(f"\n[Task {task_index + 1}/{len(accounts)}] Starting...")
            if proxy:
                print(f"Using proxy: {proxy.split('@')[1]}")
            return await process_account(
                account=account,
                email_client=email_client,
                headless=False,
                results_path=results_path,
                debug_cursor=True,
                speed=2.0,
                proxy=proxy,
                window_index=window_index,
            )

    tasks = [process_with_semaphore(acc, i) for i, acc in enumerate(accounts)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is False or isinstance(r, Exception))

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total accounts: {len(accounts)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Results saved to: {results_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Riot account generator")
    parser.add_argument("parallel", type=int, nargs="?", default=3, help="Number of parallel browsers (default: 3)")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    loop = uc.loop()
    loop.set_exception_handler(suppress_connection_errors)
    try:
        loop.run_until_complete(main(max_concurrent=args.parallel))
    except KeyboardInterrupt:
        print("\nExiting...")
