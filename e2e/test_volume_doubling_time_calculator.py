"""The volume doubling time calculator reads dates, volumes and diameters."""

import os

from playwright.sync_api import expect


def _capture(page, name):
    # Optional review screenshots; set RADSPEED_SCREENSHOT_DIR to keep them.
    folder = os.environ.get("RADSPEED_SCREENSHOT_DIR")
    if folder:
        page.screenshot(path=os.path.join(folder, name), full_page=True)


def test_default_volumes_show_growth_and_dates_set_the_interval(page, base_url):
    errors = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.goto(f"{base_url}/volume-doubling-time-calculator")
    # 120 -> 180 mm3 over 182 days: +50%, VDT 311 days.
    expect(page.locator("#vdt-val")).to_have_text("311")
    expect(page.locator("#change-val")).to_have_text("+50%")
    expect(page.locator("#headline")).to_have_text("Growing")
    expect(page.locator("#bts-text")).to_contain_text("under 400 days")
    expect(page.locator("#report-line")).to_contain_text("volume doubling time 311 days")
    _capture(page, "vdt-desktop.png")

    # Both scan dates replace the typed interval; a doubling equals the interval.
    page.fill("#prior", "100")
    page.fill("#current", "200")
    page.fill("#prior_date", "2025-01-01")
    page.fill("#current_date", "2026-01-01")
    expect(page.locator("#interval_days")).to_have_value("365")
    expect(page.locator("#vdt-val")).to_have_text("365")
    assert errors == []


def test_diameter_mode_relabels_and_warns(page, base_url):
    page.goto(f"{base_url}/volume-doubling-time-calculator")
    page.select_option("#method", "diameter")
    expect(page.locator("#prior-label")).to_have_text("Prior mean diameter (mm)")
    page.fill("#prior", "6")
    page.fill("#current", "7")
    page.fill("#interval_days", "365")
    expect(page.locator("#vdt-val")).to_have_text("547")
    # The 1 mm change is stable under the NLCSP diameter rule.
    expect(page.locator("#headline")).to_have_text("Stable")
    expect(page.locator("#warnings")).to_contain_text("cubes any measurement error")


def test_decrease_has_no_doubling_time_and_mobile_fits(page, base_url):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{base_url}/volume-doubling-time-calculator")
    page.fill("#current", "80")
    expect(page.locator("#vdt-val")).to_have_text("—")
    expect(page.locator("#vdt-note")).to_have_text("no volume increase")
    expect(page.locator("#headline")).to_have_text("Decreased")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    _capture(page, "vdt-mobile.png")


def test_location_is_added_in_the_browser_only(page, base_url):
    bodies = []
    page.on("request", lambda req: bodies.append(req.post_data or "") if "/api/nodule-growth/vdt" in req.url else None)
    page.goto(f"{base_url}/volume-doubling-time-calculator")
    page.fill("#location", "right upper lobe")
    expect(page.locator("#report-line")).to_contain_text("Right upper lobe pulmonary nodule: volume 180 mm³")
    page.fill("#prior_date", "2025-01-01")
    page.fill("#current_date", "2025-07-02")
    expect(page.locator("#interval_days")).to_have_value("182")
    assert bodies and not any("upper lobe" in b or "2025" in b for b in bodies)


def test_dates_across_a_leap_day_still_read_as_24_months(page, base_url):
    page.goto(f"{base_url}/volume-doubling-time-calculator")
    page.select_option("#method", "diameter")
    page.fill("#prior", "6")
    page.fill("#current", "8")
    page.fill("#prior_date", "2024-01-01")
    page.fill("#current_date", "2026-01-01")
    expect(page.locator("#interval_days")).to_have_value("731")
    expect(page.locator("#headline")).to_have_text("Growing")
    # Typing an interval clears the dates so they cannot disagree.
    page.fill("#interval_days", "800")
    expect(page.locator("#prior_date")).to_have_value("")
    expect(page.locator("#headline")).to_have_text("Slowly growing")


def test_slow_growth_pattern_headline_stays_open(page, base_url):
    page.goto(f"{base_url}/volume-doubling-time-calculator")
    page.fill("#prior", "100")
    page.fill("#current", "150")
    page.fill("#interval_days", "800")
    expect(page.locator("#headline")).to_have_text("Stable or slowly growing")


def test_switching_unit_loads_that_units_example(page, base_url):
    page.goto(f"{base_url}/volume-doubling-time-calculator")
    page.select_option("#method", "diameter")
    expect(page.locator("#prior")).to_have_value("6.0")
    expect(page.locator("#current")).to_have_value("7.6")
    expect(page.locator("#report-line")).to_contain_text("mean diameter change +1.6 mm")
    page.fill("#location", "right upper lobe")
    expect(page.locator("#report-line")).to_contain_text("Right upper lobe pulmonary nodule: mean diameter 7.6 mm")
