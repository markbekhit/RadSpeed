"""The Fleischner calculator derives the mean diameter and compares the prior."""


def test_axes_derive_the_rounded_mean_and_lock_the_field(page, base_url):
    page.goto(f"{base_url}/fleischner-calculator")
    # 8 x 5 mm averages 6.5 mm, which must round up to 7 mm and land in the
    # 6-8 mm band rather than below 6 mm.
    page.fill("#long_axis_mm", "8")
    page.fill("#short_axis_mm", "5")
    page.wait_for_function("document.getElementById('size_mm').value === '7'")
    assert page.eval_on_selector("#size_mm", "el => el.readOnly") is True
    assert "reports as 7 mm" in page.text_content("#measurement-note")
    assert page.text_content("#size-band").strip() == "6–8 mm"

    # Clearing an axis hands the mean back to the radiologist.
    page.fill("#short_axis_mm", "")
    page.wait_for_function("document.getElementById('size_mm').readOnly === false")
    assert page.text_content("#measurement-note").strip() == ""


def test_prior_study_shows_growth_and_leaves_when_cleared(page, base_url):
    page.goto(f"{base_url}/fleischner-calculator")
    page.fill("#size_mm", "8")
    page.fill("#prior_size_mm", "5")
    page.fill("#interval_months", "12")
    page.wait_for_selector("#interval-change[data-status='growth']")
    assert page.text_content("#change-tag").strip() == "Growth"
    assert "+3.0 mm over 12 months" in page.text_content("#change-summary")
    assert "Reassess management" in page.text_content("#change-note")
    assert "Mean diameter 5 mm to 8 mm" in page.text_content("#report-line")

    # A 1 mm change sits inside measurement variability.
    page.fill("#prior_size_mm", "7")
    page.wait_for_selector("#interval-change[data-status='stable']")
    assert page.text_content("#change-tag").strip() == "Stable"
    assert page.text_content("#change-note").strip() == ""

    page.fill("#prior_size_mm", "")
    page.wait_for_selector("#interval-change", state="hidden")
