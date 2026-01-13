import asyncio
import subprocess
import socket
import aiohttp

async def test_port(port):
    """Check if a port is open"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    except:
        return False

async def test_cdp(port):
    """Try to connect to Chrome DevTools Protocol"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'http://127.0.0.1:{port}/json/version', timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                print(f"  CDP response: {data.get('Browser', 'unknown')}")
                return True
    except Exception as e:
        print(f"  CDP connection failed: {e}")
        return False

async def main():
    print("=== Chrome CDP Connection Test ===\n")

    # Find Chrome
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    chrome_path = None
    for path in chrome_paths:
        try:
            if subprocess.run(["cmd", "/c", f'if exist "{path}" echo found'], capture_output=True, text=True).stdout.strip():
                chrome_path = path
                break
        except:
            pass

    if not chrome_path:
        print("Chrome not found in standard locations")
        print("Trying 'where chrome'...")
        result = subprocess.run(["where", "chrome"], capture_output=True, text=True)
        print(result.stdout or result.stderr)
        return

    print(f"Chrome found: {chrome_path}\n")

    port = 9222
    print(f"Starting Chrome with --remote-debugging-port={port}...")

    proc = subprocess.Popen([
        chrome_path,
        f"--remote-debugging-port={port}",
        "--no-sandbox",
        "--disable-gpu",
        "--user-data-dir=C:\\temp\\chrome-test",
        "about:blank"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    print(f"Chrome PID: {proc.pid}")
    print("Waiting 5 seconds for Chrome to start...")
    await asyncio.sleep(5)

    print(f"\nChecking if port {port} is open...")
    if await test_port(port):
        print(f"  Port {port} is OPEN")
        print("\nTrying CDP connection...")
        if await test_cdp(port):
            print("\n=== SUCCESS: Chrome DevTools is accessible! ===")
            print("The issue might be with nodriver's connection method.")
        else:
            print("\n=== FAIL: Port open but CDP not responding ===")
    else:
        print(f"  Port {port} is CLOSED")
        print("\n=== FAIL: Chrome is not listening on the debug port ===")
        print("This suggests Chrome can't bind to localhost in this VM.")

    print("\nTerminating Chrome...")
    proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
