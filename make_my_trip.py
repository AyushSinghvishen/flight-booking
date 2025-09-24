import json, asyncio, re
from datetime import datetime, timedelta
from transformers import pipeline
from playwright.async_api import async_playwright

# ----------------------------
# Hugging Face: generate passenger info
# ----------------------------
generator = pipeline("text-generation", model="gpt2")

def passenger_info():
    text = generator("Passenger name and contact", max_length=20)[0]['generated_text'].split()
    name = " ".join(text[:2])
    contact_raw = "".join([str(ord(c) % 10) for c in " ".join(text[:10])])
    contact = contact_raw[:10]
    if contact[0] not in "6789":
        contact = "9" + contact[1:]
    return name, contact

# ----------------------------
# Main async function
# ----------------------------
async def main():
    name, contact = passenger_info()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        page = await browser.new_page()
        await page.goto("https://www.makemytrip.com/")

        # --------------------------
        # Close popup if exists
        # --------------------------
        try:
            await page.wait_for_selector("span.commonModal__close", timeout=3000)
            await page.click("span.commonModal__close")
            print("Closed login popup")
        except:
            print("No login popup")

        # --------------------------
        # Enter FROM city
        # --------------------------
        await page.click("#fromCity")
        await page.fill("//input[@placeholder='From']", "Delhi")
        await page.click("//p[contains(text(),'Delhi, India')]")
        print("Selected FROM = Delhi")

        # --------------------------
        # Enter TO city
        # --------------------------
        await page.click("#toCity")
        await page.fill("//input[@placeholder='To']", "Mumbai")
        await page.click("//p[contains(text(),'Mumbai, India')]")
        print("Selected TO = Mumbai")

        # --------------------------
        # Select departure DATE safely
        # --------------------------
        await page.evaluate("document.querySelector('input[id=departure]').click()")
        await page.wait_for_selector("div.DayPicker", timeout=5000)

        date_str = (datetime.now() + timedelta(days=1)).strftime("%a %b %d %Y")
        date_cell = page.locator(f"div[aria-label='{date_str}']")
        if await date_cell.count() > 0:
            await date_cell.click()
            print("Selected travel date:", date_str)
        else:
            first_enabled = page.locator("div.DayPicker-Day:not(.disabled):not(.outside)").first
            await first_enabled.click()
            print("Selected first available date as fallback")


        await page.click("//a[text()='Search']")
        flight_frame = page
        for f in page.frames:
            if "listingCard" in await f.content():
                flight_frame = f
                print(f"Using iframe: {f.url}")
                break

        # --------------------------
        # Wait for flight cards
        # --------------------------
        flights_locator = flight_frame.locator("//div[contains(@class,'listingCard')]")
        try:
            await flights_locator.first.wait_for(timeout=90000)  # wait up to 90s
            print("Flights loaded")
        except:
            print("Flights did not load within 90s")
            await browser.close()
            return

        # --------------------------
        # Extract flight details
        # --------------------------
        flights_elements = await flight_frame.query_selector_all("//div[contains(@class,'listingCard')]")
        flights = []

        for el in flights_elements:
            airline_el = await el.query_selector(".//span[@class='boldFont blackText airlineName']")
            airline_text = await airline_el.inner_text() if airline_el else ""
            time_el = await el.query_selector(".//div[@class='flexOne timeInfoLeft']")
            time_text = await time_el.inner_text() if time_el else ""
            price_el = await el.query_selector(".//p[@class='blackText fontSize18 blackFont white-space-no-wrap']")
            price_text = await price_el.inner_text() if price_el else ""
            flights.append({"airline": airline_text, "time": time_text, "price": price_text})

        # Convert price to numeric for sorting
        for f in flights:
            price_str = re.sub(r'\D', '', f["price"])
            f["price_numeric"] = int(price_str) if price_str else float('inf')

        # Sort by lowest price
        flights_sorted = sorted(flights, key=lambda x: x["price_numeric"])
        cheapest_flight = flights_sorted[0] if flights_sorted else {}

        # --------------------------
        # Save JSON output
        # --------------------------
        with open("booking.json", "w") as f:
            json.dump({
                "passenger": {"name": name, "contact": contact},
                "selected_flight": cheapest_flight,
                "all_flights": flights_sorted
            }, f, indent=2)

        print("Saved booking.json with cheapest flight")
        await browser.close()

# ----------------------------
# Run the script
# ----------------------------
asyncio.run(main())
