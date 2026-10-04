"""Public tools preserve report text and focus when clipboard access fails."""

import pytest
from playwright.sync_api import expect


@pytest.mark.parametrize("route", ["ti-rads-calculator", "fleischner-calculator", "adrenal-washout-calculator"])
@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("mode", ["modern", "legacy", "denied", "throws"])
def test_copy_paths(page, base_url, route, width, mode):
    page.set_viewport_size({"width": width, "height": 900})
    page.add_init_script("""(mode => {
        window.copiedText = null;
        Object.defineProperty(navigator, 'clipboard', {value: {
            writeText: async text => {
                if (mode !== 'modern') throw new Error('Synthetic clipboard denial');
                window.copiedText = text;
            }
        }});
        document.execCommand = () => {
            if (mode === 'throws') throw new Error('Synthetic legacy denial');
            if (mode === 'legacy') {
                window.copiedText = document.querySelector('textarea').value;
                return true;
            }
            return false;
        };
    })(""" + repr(mode) + ");")
    page.goto(f"{base_url}/{route}")
    expect(page.locator("#report-line")).not_to_have_text("")
    report = page.locator("#report-line").inner_text()
    page.locator("#btn-copy").press("Enter")
    status = page.locator("#status")
    expect(status).to_have_attribute("role", "status")
    expect(status).to_have_attribute("aria-live", "polite")
    if mode in ("modern", "legacy"):
        expect(status).to_have_text("Report line copied to clipboard.")
        assert page.evaluate("window.copiedText") == report
    else:
        expect(status).to_contain_text("The report line is selected.")
        expect(status).to_contain_text("On a phone, touch and hold the report line, then choose Copy.")
        assert page.evaluate("window.getSelection().toString()") == report
    expect(page.locator("#btn-copy")).to_be_focused()
    expect(page.locator("textarea")).to_have_count(0)
    expect(page.locator("#report-line")).to_have_text(report)


@pytest.mark.parametrize("width", [390, 1440])
def test_library_keyboard_and_unmatched_search(page, base_url, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{base_url}/report-templates")
    ct = page.locator('.library-filter[data-modality="ct"]')
    ct.press("Space")
    expect(ct).to_have_attribute("aria-pressed", "true")
    expect(ct).to_be_focused()
    expect(page.locator("#template-search-status")).to_contain_text("in CT")
    page.locator('.library-filter[data-modality="all"]').press("Enter")
    expect(page.locator('.library-filter[data-modality="all"]')).to_have_attribute("aria-pressed", "true")
    page.locator("#template-search").fill("zzzznonexistent")
    expect(page.locator("#template-search-status")).to_have_text("No match. Try a study name or clear the search.")
    expect(page.locator("#library-closest a")).to_have_count(0)
    page.locator("#library-empty-reset").press("Enter")
    expect(page.locator("#template-search")).to_be_focused()
    expect(page.locator(".template-card:visible")).to_have_count(39)
