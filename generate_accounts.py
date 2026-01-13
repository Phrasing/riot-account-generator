import argparse
import csv
import random
import secrets
import string
from pathlib import Path

from faker import Faker

fake = Faker()
DAYS_IN_MONTH = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

def generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in password) and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password) and any(c in "!@#$%" for c in password)):
            return password

def generate_birthdate() -> str:
    month = random.randint(1, 12)
    return f"{month:02d}/{random.randint(1, DAYS_IN_MONTH[month]):02d}/2000"

def generate_account(catchall_domain: str) -> dict:
    base_name = f"{fake.first_name()}{fake.last_name()}{random.randint(1000, 9999)}"
    return {"email": f"{base_name}@{catchall_domain}", "username": base_name.lower(),
            "password": generate_password(), "birthdate": generate_birthdate()}

def main():
    parser = argparse.ArgumentParser(description="Generate accounts for Riot account creation")
    parser.add_argument("catchall", help="Catchall email domain (e.g., example.com)")
    parser.add_argument("-n", "--count", type=int, default=10, help="Number of accounts to generate (default: 10)")
    parser.add_argument("-o", "--output", default="accounts.csv", help="Output file path (default: accounts.csv)")
    parser.add_argument("-a", "--append", action="store_true", help="Append to existing file instead of overwriting")
    args = parser.parse_args()

    accounts = [generate_account(args.catchall) for _ in range(args.count)]
    file_exists = Path(args.output).exists()
    mode = "a" if args.append and file_exists else "w"

    with open(args.output, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "username", "password", "birthdate"])
        if mode == "w" or not file_exists:
            writer.writeheader()
        writer.writerows(accounts)

    print(f"Generated {args.count} account(s) to {args.output}")
    for acc in accounts:
        print(f"  {acc['email']} / {acc['username']}")

if __name__ == "__main__":
    main()
