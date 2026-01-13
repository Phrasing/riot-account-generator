import asyncio
import email
import imaplib
import re
from email.header import decode_header

class EmailClient:
    RIOT_SENDER = "noreply@umail.accounts.riotgames.com"
    CODE_PATTERN = re.compile(r"Login Code[:\s]*(\d{6})")

    def __init__(self, gmail_email: str, gmail_app_password: str, max_connections: int = 3):
        self.gmail_email, self.gmail_app_password = gmail_email, gmail_app_password
        self._semaphore = asyncio.Semaphore(max_connections)

    def _connect(self) -> imaplib.IMAP4_SSL:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=15)
        mail.login(self.gmail_email, self.gmail_app_password)
        return mail

    def _extract_code_from_subject(self, subject: str) -> str | None:
        match = self.CODE_PATTERN.search(subject)
        return match.group(1) if match else None

    def _decode_subject(self, msg: email.message.Message) -> str:
        decoded_parts = decode_header(msg.get("Subject", ""))
        return "".join(part.decode(enc or "utf-8", errors="ignore") if isinstance(part, bytes) else part
                       for part, enc in decoded_parts)

    def _get_all_codes(self, target_email: str, limit: int = 10) -> list[str]:
        mail = self._connect()
        codes: list[str] = []
        try:
            mail.select('"[Gmail]/All Mail"')
            _, message_numbers = mail.search(None, f'(FROM "{self.RIOT_SENDER}" TO "{target_email}")')
            if not message_numbers[0]:
                return codes
            all_nums = message_numbers[0].split()
            for num in reversed(all_nums[-limit:] if len(all_nums) > limit else all_nums):
                _, msg_data = mail.fetch(num, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        code = self._extract_code_from_subject(self._decode_subject(msg))
                        if code and code not in codes:
                            codes.append(code)
            return codes
        finally:
            mail.logout()

    def _get_latest_code(self, target_email: str) -> str | None:
        codes = self._get_all_codes(target_email, limit=5)
        return codes[0] if codes else None

    async def _fetch_codes(self, target_email: str, limit: int = 10, timeout: int = 30) -> list[str]:
        async with self._semaphore:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self._get_all_codes, target_email, limit),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                print(f"      IMAP timeout after {timeout}s")
                return []

    async def get_existing_codes(self, target_email: str) -> set[str]:
        return set(await self._fetch_codes(target_email, 10))

    async def wait_for_verification_code(self, target_email: str, timeout: int = 120, poll_interval: int = 5,
                                         existing_codes: set[str] | None = None) -> str:
        if existing_codes is None:
            existing_codes = await self.get_existing_codes(target_email)
        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            for code in await self._fetch_codes(target_email, 5):
                if code not in existing_codes:
                    return code
        raise TimeoutError(f"No verification code received for {target_email} within {timeout}s")

    async def wait_for_verification_code_with_timeout(self, target_email: str, existing_codes: set[str],
                                                      timeout: int = 25, poll_interval: int = 5) -> str | None:
        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            for code in await self._fetch_codes(target_email, 5):
                if code not in existing_codes:
                    return code
        return None

    async def get_verification_code_immediate(self, target_email: str) -> str | None:
        async with self._semaphore:
            return await asyncio.to_thread(self._get_latest_code, target_email)
