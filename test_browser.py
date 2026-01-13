import os
import nodriver as uc

def find_chrome():
    paths = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

async def main():
    chrome = find_chrome()
    print(f"Chrome path: {chrome}\n")

    print("Test 1: nodriver with explicit path...")
    try:
        browser = await uc.start(browser_executable_path=chrome, sandbox=False,
                                  browser_args=["--no-sandbox", "--disable-gpu"])
        print("SUCCESS!")
        browser.stop()
        return
    except Exception as e:
        print(f"FAILED: {e}\n")

    print("Test 2: nodriver with path + port...")
    try:
        browser = await uc.start(browser_executable_path=chrome, sandbox=False, port=9555,
                                  browser_args=["--no-sandbox", "--disable-gpu"])
        print("SUCCESS!")
        browser.stop()
        return
    except Exception as e:
        print(f"FAILED: {e}\n")

    print("Test 3: nodriver with path + user_data_dir...")
    try:
        browser = await uc.start(browser_executable_path=chrome, sandbox=False,
                                  user_data_dir="C:\\temp\\nodriver-test",
                                  browser_args=["--no-sandbox", "--disable-gpu"])
        print("SUCCESS!")
        browser.stop()
        return
    except Exception as e:
        print(f"FAILED: {e}\n")

    print("Test 4: nodriver with all options...")
    try:
        browser = await uc.start(browser_executable_path=chrome, sandbox=False, port=9556,
                                  user_data_dir="C:\\temp\\nodriver-test2",
                                  browser_args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
        print("SUCCESS!")
        browser.stop()
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    uc.loop().run_until_complete(main())
