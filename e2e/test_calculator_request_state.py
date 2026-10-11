"""Only current, successful calculator responses may be copied (synthetic data)."""
import os
import pytest
from playwright.sync_api import expect

TOOLS = [
    ("ti-rads-calculator", "/api/tirads/score", "location"),
    ("adrenal-washout-calculator", "/api/adrenal/washout", "location"),
    ("fleischner-calculator", "/api/fleischner/recommend", "location"),
]


@pytest.fixture(scope="session")
def base_url(radspeed_server):
    return os.environ.get("RADSPEED_QA_URL", radspeed_server)


@pytest.mark.parametrize("tool,api,field", TOOLS)
@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("case", ["pending", "race", "old_error", "http_error", "network_error", "recovery"])
def test_current_response_only(page, base_url, tool, api, field, width, case):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{base_url}/{tool}")
    expect(page.locator("#report-line")).not_to_have_text("")
    # Capture a genuine deterministic response for the default synthetic input.
    # Later responses change only the report-line marker, never the clinical values.
    response = page.evaluate("""async api => {
        const original = window.fetch;
        return await new Promise(resolve => {
            window.fetch = async (...args) => {
                const response = await original(...args);
                if (args[0] === api) resolve(await response.clone().json());
                return response;
            };
            const input = document.getElementById('location');
            input.dispatchEvent(new Event('input', {bubbles:true}));
        });
    }""", api)
    expect(page.locator("#report-line")).not_to_have_text("")
    page.evaluate("""({api, response}) => {
        window.qaPending = [];
        window.fetch = (url, options) => new Promise((resolve, reject) => {
            window.qaPending.push({resolve, reject});
        });
        window.qaResolve = (index, marker) => window.qaPending[index].resolve({
            ok:true, json:async () => ({...response, report_line:marker})
        });
    }""", {"api": api, "response": response})
    page.locator(f"#{field}").fill("Synthetic first")
    page.wait_for_function("window.qaPending.length === 1")
    if case == "pending":
        expect(page.locator("#btn-copy")).to_be_disabled()
        expect(page.locator("#report-line")).to_have_text("")
        return
    if case in ("race", "old_error"):
        page.locator(f"#{field}").fill("Synthetic latest")
        page.wait_for_function("window.qaPending.length === 2")
        page.evaluate("window.qaResolve(1, 'SYNTHETIC latest response')")
        expect(page.locator("#report-line")).to_have_text("SYNTHETIC latest response")
        if case == "race":
            page.evaluate("window.qaResolve(0, 'SYNTHETIC old response')")
        else:
            page.evaluate("window.qaPending[0].reject(new Error('Synthetic old failure'))")
        page.wait_for_timeout(100)
        expect(page.locator("#report-line")).to_have_text("SYNTHETIC latest response")
        expect(page.locator("#btn-copy")).to_be_enabled()
        expect(page.locator("#status")).to_have_text("")
    else:
        if case == "http_error":
            page.evaluate("window.qaPending[0].resolve({ok:false,status:503,statusText:'QA unavailable',json:async()=>({detail:'Synthetic failure'})})")
        else:
            page.evaluate("window.qaPending[0].reject(new Error('Synthetic network failure'))")
        expect(page.locator("#status")).to_contain_text("Error:")
        expect(page.locator("#report-line")).to_have_text("")
        expect(page.locator("#btn-copy")).to_be_disabled()
        if case == "recovery":
            page.locator(f"#{field}").fill("Synthetic recovered")
            page.wait_for_function("window.qaPending.length === 2")
            page.evaluate("window.qaResolve(1, 'SYNTHETIC recovered response')")
            expect(page.locator("#report-line")).to_have_text("SYNTHETIC recovered response")
            expect(page.locator("#btn-copy")).to_be_enabled()
            expect(page.locator("#status")).to_have_text("")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("tool,api,field", TOOLS[1:])
def test_empty_required_input_invalidates_pending_response(page, base_url, tool, api, field):
    page.goto(f"{base_url}/{tool}")
    expect(page.locator("#report-line")).not_to_have_text("")
    page.evaluate("""() => {
        window.qaPending = [];
        window.fetch = () => new Promise(resolve => window.qaPending.push(resolve));
    }""")
    page.locator("#location").fill("Synthetic pending")
    page.wait_for_function("window.qaPending.length === 1")
    required = "enhanced_hu" if tool == "adrenal-washout-calculator" else "size_mm"
    page.locator(f"#{required}").fill("")
    expect(page.locator("#report-line")).to_have_text("")
    expect(page.locator("#btn-copy")).to_be_disabled()
    # An obsolete failure cannot replace the useful missing-input instruction.
    page.evaluate("window.qaPending[0]({ok:false,status:503,statusText:'Old synthetic error',json:async()=>({})})")
    page.wait_for_timeout(100)
    expect(page.locator("#status")).to_contain_text("Enter")
    expect(page.locator("#btn-copy")).to_be_disabled()
