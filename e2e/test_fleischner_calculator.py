"""The Fleischner calculator derives the mean diameter and compares the prior."""

from playwright.sync_api import expect


def test_axes_derive_the_rounded_mean_and_lock_the_field(page, base_url):
    page.goto(f"{base_url}/fleischner-calculator")
    # 8 x 5 mm averages 6.5 mm, which must round up to 7 mm and land in the
    # 6-8 mm band rather than below 6 mm.
    page.fill("#long_axis_mm", "8")
    page.fill("#short_axis_mm", "5")
    page.wait_for_function("document.getElementById('size_mm').value === '7'")
    assert page.eval_on_selector("#size_mm", "el => el.readOnly") is True
    expect(page.locator("#measurement-note")).to_contain_text("reports as 7 mm")
    expect(page.locator("#size-band")).to_have_text("6–8 mm")

    # Clearing an axis hands the mean back to the radiologist.
    page.fill("#short_axis_mm", "")
    page.wait_for_function("document.getElementById('size_mm').readOnly === false")
    # The field unlocks immediately; the explanatory text awaits the API result.
    expect(page.locator("#measurement-note")).to_have_text("")


def test_prior_study_shows_growth_and_leaves_when_cleared(page, base_url):
    page.goto(f"{base_url}/fleischner-calculator")
    page.fill("#size_mm", "8")
    page.fill("#prior_size_mm", "5")
    page.fill("#interval_months", "12")
    page.wait_for_selector("#interval-change[data-status='growth']")
    expect(page.locator("#change-tag")).to_have_text("Growth")
    # Growth is already visible before the interval request returns.
    expect(page.locator("#change-summary")).to_contain_text("+3.0 mm over 12 months")
    expect(page.locator("#change-note")).to_contain_text("Reassess management")
    expect(page.locator("#report-line")).to_contain_text("Mean diameter 5 mm to 8 mm")

    # A 1 mm change sits inside measurement variability.
    page.fill("#prior_size_mm", "7")
    page.wait_for_selector("#interval-change[data-status='stable']")
    expect(page.locator("#change-tag")).to_have_text("Stable")
    expect(page.locator("#change-note")).to_have_text("")

    page.fill("#prior_size_mm", "")
    page.wait_for_selector("#interval-change", state="hidden")
