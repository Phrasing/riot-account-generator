import asyncio
import random
from dataclasses import dataclass

import nodriver as uc
import nodriver.cdp.input_ as cdp_input
import nodriver.cdp.network as cdp_network
from human_mouse import HumanMouse, MouseConfig

@dataclass(frozen=True)
class AccountData:
    email: str
    username: str
    password: str
    birthdate: str  # MM/DD/YYYY

@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential: bool = True

DELAYS = {"micro": (0.05, 0.15), "short": (0.3, 0.8), "action": (0.8, 2.0), "thinking": (1.5, 3.5), "page": (2.5, 4.5)}
SPEED_PROFILES = {"fast": (0.03, 0.08), "normal": (0.05, 0.12), "slow": (0.08, 0.18)}

class RiotAccountCreator:
    RIOT_SIGNUP_URL = "https://account.riotgames.com/account"
    CURSOR_INJECT_JS = """(function(){if(document.getElementById('__debug_cursor__'))return;const c=document.createElement('div');c.id='__debug_cursor__';c.style.cssText='position:fixed;width:12px;height:12px;background:rgba(255,50,50,0.8);border:2px solid white;border-radius:50%;pointer-events:none;z-index:999999;transform:translate(-50%,-50%);box-shadow:0 0 4px rgba(0,0,0,0.5);transition:none';document.body.appendChild(c)})();"""
    CURSOR_MOVE_JS = "(function(x,y){const c=document.getElementById('__debug_cursor__');if(c){c.style.left=x+'px';c.style.top=y+'px'}})(%s,%s);"

    def __init__(self, headless: bool = False, retry_config: RetryConfig | None = None, mouse_config: MouseConfig | None = None,
                 debug_cursor: bool = False, speed: float = 2.0, proxy: str | None = None, window_index: int = 0):
        self.headless, self.speed, self.proxy, self.debug_cursor = headless, speed, proxy, debug_cursor
        self.window_index = window_index
        self.retry_config = retry_config or RetryConfig()
        mouse_cfg = mouse_config or MouseConfig()
        mouse_cfg = MouseConfig(speed_factor=mouse_cfg.speed_factor * (1 / speed), zigzag_probability=mouse_cfg.zigzag_probability,
                                min_nodes=mouse_cfg.min_nodes, max_nodes=mouse_cfg.max_nodes, variance_factor=mouse_cfg.variance_factor,
                                max_variance=mouse_cfg.max_variance, points_per_path=mouse_cfg.points_per_path)
        self.mouse = HumanMouse(mouse_cfg)
        self.cursor_x: float = 0
        self.cursor_y: float = 0
        self.browser: uc.Browser | None = None
        self.tab: uc.Tab | None = None

    async def start(self):
        x_offset, y_offset = 50 + (self.window_index * 50), 50 + (self.window_index * 50)
        browser_args = [
            f"--window-position={x_offset},{y_offset}",
            "--window-size=1200,800",
            # Bandwidth reduction
            "--disable-remote-fonts",
            "--disable-background-networking",
            "--disable-default-apps",
            "--no-pings",
        ]
        self.browser = await uc.start(headless=self.headless, browser_args=browser_args)
        self.cursor_x, self.cursor_y = random.uniform(100, 400), random.uniform(100, 300)

    async def stop(self):
        if not self.browser:
            return
        try:
            self.browser.stop()
        except Exception:
            pass
        await asyncio.sleep(1)
        self.browser, self.tab = None, None

    async def _retry(self, operation, description: str = "operation"):
        cfg, last_error = self.retry_config, None
        for attempt in range(cfg.max_retries + 1):
            try:
                return await operation()
            except Exception as e:
                last_error = e
                if attempt < cfg.max_retries:
                    delay = min(cfg.base_delay * (2**attempt), cfg.max_delay) if cfg.exponential else cfg.base_delay
                    print(f"      Retry {attempt + 1}/{cfg.max_retries} for {description}: {e}")
                    await asyncio.sleep(delay)
        raise last_error

    async def _select(self, selector: str, timeout: int = 10):
        async def select_with_timeout():
            return await asyncio.wait_for(self.tab.select(selector), timeout=timeout)
        return await self._retry(select_with_timeout, f"select '{selector}'")

    async def _find(self, text: str, best_match: bool = True, timeout: int = 10):
        async def find_with_timeout():
            return await asyncio.wait_for(self.tab.find(text, best_match=best_match), timeout=timeout)
        return await self._retry(find_with_timeout, f"find '{text}'")

    async def _click(self, element):
        await self._human_move_to(element)
        await self._retry(lambda: element.click(), "click")

    async def _apply(self, element, js: str):
        return await self._retry(lambda: element.apply(js), "apply JS")

    async def _inject_debug_cursor(self):
        if not (self.debug_cursor and self.tab):
            return
        try:
            await self.tab.evaluate(self.CURSOR_INJECT_JS)
            await self.tab.evaluate(self.CURSOR_MOVE_JS % (self.cursor_x, self.cursor_y))
        except Exception:
            pass

    async def _block_heavy_resources(self):
        """Block images, media, fonts, and tracking to save proxy bandwidth."""
        if not self.tab:
            return
        try:
            await self.tab.send(cdp_network.enable())
            await self.tab.send(cdp_network.set_blocked_ur_ls(urls=[
                # Images
                "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.svg", "*.ico",
                # Media
                "*.mp4", "*.webm", "*.mp3", "*.wav",
                # Fonts
                "*.woff", "*.woff2", "*.ttf", "*.eot",
                # Analytics & tracking
                "*google-analytics.com*", "*googletagmanager.com*",
                "*facebook.com/tr*", "*doubleclick.net*", "*hotjar.com*",
            ]))
        except Exception:
            pass

    async def _move_mouse(self, x: float, y: float):
        await self.tab.send(cdp_input.dispatch_mouse_event(type_="mouseMoved", x=x, y=y))
        if self.debug_cursor:
            await self.tab.evaluate(self.CURSOR_MOVE_JS % (x, y))

    async def _get_element_center(self, element) -> tuple[float, float]:
        box = await element.get_position()
        return (box.x + box.width / 2 + random.uniform(-box.width * 0.15, box.width * 0.15),
                box.y + box.height / 2 + random.uniform(-box.height * 0.15, box.height * 0.15))

    async def _human_move_to(self, element):
        target_x, target_y = await self._get_element_center(element)
        path = self.mouse.generate_path(self.cursor_x, self.cursor_y, target_x, target_y)
        delays = self.mouse.calculate_delays(path)
        for (x, y), delay in zip(path, delays):
            await self._move_mouse(x, y)
            await asyncio.sleep(delay / 1000)
        self.cursor_x, self.cursor_y = target_x, target_y

    async def random_delay(self, mode: str = "action"):
        min_d, max_d = DELAYS.get(mode, DELAYS["action"])
        if mode != "micro" and random.random() < 0.1:
            max_d += random.uniform(0.5, 1.5)
        await asyncio.sleep(random.uniform(min_d, max_d) / self.speed)

    async def human_type(self, element, text: str, speed: str = "normal"):
        base_min, base_max = SPEED_PROFILES.get(speed, SPEED_PROFILES["normal"])
        for i, char in enumerate(text):
            await element.send_keys(char)
            delay = random.uniform(base_min, base_max)
            if char in ".,@!?-_":
                delay += random.uniform(0.05, 0.15)
            if random.random() < 0.03:
                delay += random.uniform(0.2, 0.5)
            if i > 3 and random.random() < 0.3:
                delay *= 0.85
            await asyncio.sleep(delay / self.speed)

    async def navigate_to_signup(self):
        try:
            if self.proxy:
                if self.browser.tabs:
                    await self.browser.tabs[0].close()
                self.tab = await self.browser.create_context(
                    url=self.RIOT_SIGNUP_URL,
                    proxy_server=self.proxy
                )
            else:
                self.tab = await self.browser.get(self.RIOT_SIGNUP_URL)
        except Exception as e:
            raise Exception(f"Proxy connection failed: {e}")

        # Block heavy resources to save bandwidth
        await self._block_heavy_resources()
        await self.random_delay("page")

        # Check for proxy error responses
        current_url = self.tab.target.url.lower()
        if "403" in current_url or "forbidden" in current_url or "error" in current_url:
            raise Exception(f"403 Forbidden - proxy blocked at {self.tab.target.url}")

        await self._inject_debug_cursor()

        create_link = await self._find("Create account")
        await self.random_delay("action")
        await self._click(create_link)
        await self.random_delay("page")
        await self._inject_debug_cursor()

    async def enter_email(self, email: str):
        email_input = await self._select("[data-testid='riot-signup-email']")
        await self._click(email_input)
        await self.random_delay("short")
        await self.human_type(email_input, email)
        await self.random_delay("short")

    async def uncheck_marketing_boxes(self):
        # Marketing boxes are unchecked by default, skip this step
        pass

    async def submit_email(self):
        submit_btn = await self._select("[data-testid='btn-signup-submit']")
        await self.random_delay("action")
        await self._click(submit_btn)
        await self.random_delay("page")

    async def enter_otp(self, code: str):
        if len(code) != 6:
            raise ValueError(f"OTP code must be 6 digits, got: {code}")
        await self.random_delay("short")
        for i, digit in enumerate(code):
            input_field = await self._select(f"[data-testid='otp-input'] div:nth-of-type({i + 1}) > input")
            await input_field.send_keys(digit)
            delay = random.uniform(0.12, 0.28) + (random.uniform(0.05, 0.12) if i < 2 else 0)
            await asyncio.sleep(delay)
        await self.random_delay("short")

    async def submit_otp(self):
        submit_btn = await self._select("[data-testid='btn-otp-submit']")
        await self.random_delay("action")
        await self._click(submit_btn)
        await self.random_delay("page")

    async def click_resend_otp(self):
        resend_btn = await self._select("[data-testid='otp-resend']")
        await self.random_delay("action")
        await self._click(resend_btn)
        await self.random_delay("thinking")

    async def enter_birthdate(self, birthdate: str):
        parts = birthdate.split("/")
        if len(parts) != 3:
            raise ValueError(f"Birthdate must be MM/DD/YYYY format, got: {birthdate}")
        month, day, year = parts
        for testid, value in [("riot-signup-birthdate-month", month), ("riot-signup-birthdate-day", day), ("riot-signup-birthdate-year", year)]:
            inp = await self._select(f"[data-testid='{testid}']")
            await self.random_delay("short")
            await self.human_type(inp, value, speed="fast")
            await self.random_delay("short")

    async def submit_birthdate(self):
        submit_btn = await self._select("[data-testid='btn-signup-submit']")
        await self.random_delay("action")
        await self._click(submit_btn)
        await self.random_delay("page")

    async def enter_username(self, username: str):
        username_input = await self._select("[data-testid='riot-signup-username']")
        await self.random_delay("short")
        await self.human_type(username_input, username)
        await self.random_delay("short")

    async def submit_username(self):
        submit_btn = await self._select("[data-testid='btn-signup-submit']")
        await self.random_delay("action")
        await self._click(submit_btn)
        await self.random_delay("page")

    async def enter_password(self, password: str):
        for testid in ["input-password", "password-confirm"]:
            inp = await self._select(f"[data-testid='{testid}']")
            await self.random_delay("short")
            await self.human_type(inp, password, speed="slow")
            await self.random_delay("short")

    async def submit_password(self):
        submit_btn = await self._select("[data-testid='btn-signup-submit']")
        await self.random_delay("action")
        await self._click(submit_btn)
        await self.random_delay("page")

    async def accept_tos(self):
        tos_area = await self._select("#tos-scrollable-area")
        await self.random_delay("short")
        await self._click(tos_area)
        await self.random_delay("short")
        await self.random_delay("thinking")
        await self._apply(tos_area, "(el) => el.scrollTop = el.scrollHeight")
        await self.random_delay("short")
        tos_checkbox = await self._select("#tos-checkbox")
        await self.random_delay("action")
        await self._click(tos_checkbox)
        await self.random_delay("short")
        accept_btn = await self._select("[data-testid='btn-accept-tos']")
        await self.random_delay("action")
        await self._click(accept_btn)
        await self.random_delay("page")

    async def verify_account_created(self) -> bool:
        print("      Waiting 10 seconds for redirects...")
        await asyncio.sleep(10)
        return "account.riotgames.com" in self.tab.target.url

    async def take_screenshot(self, filename: str):
        if self.tab:
            await self.tab.save_screenshot(filename)

    async def create_account(self, account: AccountData, get_otp_callback, get_existing_codes_callback, max_otp_retries: int = 3) -> tuple[bool, str]:
        def step(n: int, name: str, status: str = ""):
            status_str = f" {status}" if status else ""
            print(f"  [{n}/8] {name}{status_str}")

        try:
            step(1, "Navigate")
            await self.navigate_to_signup()

            step(2, "Email")
            await self.enter_email(account.email)
            existing_codes = await get_existing_codes_callback(account.email)
            await self.submit_email()

            step(3, "OTP", "(waiting)")
            otp_code = None
            for attempt in range(max_otp_retries + 1):
                if attempt > 0:
                    print(f"         Resending ({attempt + 1}/{max_otp_retries + 1})...")
                    await self.click_resend_otp()
                otp_code = await get_otp_callback(account.email, existing_codes)
                if otp_code:
                    print(f"         Code: {otp_code}")
                    break
            if not otp_code:
                return False, f"OTP timeout after {max_otp_retries + 1} attempts"

            step(4, "Verify OTP")
            await self.enter_otp(otp_code)
            await self.submit_otp()

            step(5, "Birthdate")
            await self.enter_birthdate(account.birthdate)
            await self.submit_birthdate()

            step(6, "Username")
            await self.enter_username(account.username)
            await self.submit_username()

            step(7, "Password")
            await self.enter_password(account.password)
            await self.submit_password()

            step(8, "Terms")
            await self.accept_tos()

            if await self.verify_account_created():
                return True, "OK"
            return False, f"Verification failed: {self.tab.target.url}"
        except Exception as e:
            try:
                await self.take_screenshot(f"error_{account.username}.png")
            except Exception:
                pass
            return False, str(e)
