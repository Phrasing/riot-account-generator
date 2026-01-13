import asyncio
import subprocess
import socket
import os
import aiohttp

async def test_port(port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    except:
        return False

async def test_cdp(port):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'http://127.0.0.1:{port}/json/version', timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                print(f"  CDP response: {data.get('Browser', 'unknown')}")
                return True
    except Exception as e:
        print(f"  CDP connection failed: {e}")
        return False

def find_browser():
    paths = [
        # Chrome
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        # Edge (built into Windows 10)
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        # Chromium
        r"C:\Program Files\Chromium\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Chromium\Application\chrome.exe"),
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return None

async def main():
    print("=== Browser CDP Connection Test ===\n")

    browser_path = find_browser()
    if not browser_path:
        print("No Chromium-based browser found!")
        print("\nSearched locations:")
        print("  - Chrome (Program Files)")
        print("  - Chrome (AppData)")
        print("  - Edge (Program Files)")
        print("  - Chromium")
        print("\nPlease install Chrome or check where it's installed.")
        print("Run: dir /s /b C:\\chrome.exe 2>nul")
        return

    print(f"Browser found: {browser_path}\n")

    port = 9222
    print(f"Starting browser with --remote-debugging-port={port}...")

    proc = subprocess.Popen([
        browser_path,
        f"--remote-debugging-port={port}",
        "--no-sandbox",
        "--disable-gpu",
        "--user-data-dir=C:\\temp\\browser-test",
        "about:blank"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    print(f"Browser PID: {proc.pid}")
    print("Waiting 5 seconds...")
    await asyncio.sleep(5)

    print(f"\nChecking if port {port} is open...")
    if await test_port(port):
        print(f"  Port {port} is OPEN")
        print("\nTrying CDP connection...")
        if await test_cdp(port):
            print("\n=== SUCCESS: DevTools is accessible! ===")
        else:
            print("\n=== FAIL: Port open but CDP not responding ===")
    else:
        print(f"  Port {port} is CLOSED")
        print("\n=== FAIL: Browser not listening on debug port ===")

    print("\nTerminating browser...")
    proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
