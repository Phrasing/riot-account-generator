import nodriver as uc

async def test_config(name, **kwargs):
    print(f"\n--- Testing: {name} ---")
    try:
        browser = await uc.start(**kwargs)
        print(f"SUCCESS: Browser started!")
        browser.stop()
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False

async def main():
    configs = [
        ("default", {}),
        ("sandbox=False", {"sandbox": False}),
        ("sandbox=False + port=9222", {"sandbox": False, "port": 9222}),
        ("headless", {"headless": True, "sandbox": False}),
        ("headless + port", {"headless": True, "sandbox": False, "port": 9223}),
    ]

    for name, kwargs in configs:
        if await test_config(name, **kwargs):
            print(f"\n=== WORKING CONFIG: {name} with {kwargs} ===")
            break

if __name__ == "__main__":
    uc.loop().run_until_complete(main())
