from playwright.sync_api import sync_playwright

def run_cuj(page):
    page.goto("http://localhost:8000")
    page.wait_for_timeout(3000) # Wait a bit longer to load DB

    # Click the "Contorni" category
    page.locator('button', has_text="contorni").first.click()
    page.wait_for_timeout(1000)

    # Click Patatine
    page.locator('.menu-item-title').first.click()
    page.wait_for_timeout(1000)

    # Click 'INVIA ORDINE'
    page.get_by_role("button", name="INVIA ORDINE").click()
    page.wait_for_timeout(1000)

    # Take screenshot of the payment modal showing the total
    page.screenshot(path="verification.png")
    page.wait_for_timeout(500)

    # Click Bancomat to trigger the spinner
    page.get_by_role("button", name="BANCOMAT").click()
    page.wait_for_timeout(500)

    # Click Conferma Pagamento
    page.get_by_role("button", name="Conferma Pagamento").click()
    page.wait_for_timeout(500)

    # Take another screenshot to show the spinner text "ATTENDI BANCOMAT..." or "Elaborazione..."
    page.screenshot(path="spinner.png")
    page.wait_for_timeout(1000)

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir="."
        )
        page = context.new_page()
        try:
            run_cuj(page)
        finally:
            context.close()
            browser.close()
