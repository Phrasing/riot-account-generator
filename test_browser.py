import nodriver as uc

async def test():
    print("Starting browser...")
    try:
        browser = await uc.start(sandbox=False, host="127.0.0.1",
                                  browser_args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        print(f"Browser started successfully!")
        print(f"Browser type: {type(browser)}")
        print(f"Tabs: {browser.tabs}")
        tab = await browser.get("https://google.com")
        print(f"Got tab: {tab}")
        print(f"Page title: {await tab.get_content()[:100]}")
        browser.stop()
        print("Test passed!")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    uc.loop().run_until_complete(test())
