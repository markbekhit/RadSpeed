"""Public discovery remains usable when the resource links grow."""


def test_mobile_library_footer_and_tool_routes(page, base_url):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{base_url}/report-templates")
    page.locator('.site-footer').scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    for link in page.locator('.site-footer nav a').all():
        box = link.bounding_box()
        assert box and box['x'] >= 0 and box['x'] + box['width'] <= 391
    page.locator('.site-footer a[href="/adrenal-washout-calculator"]').click()
    assert page.url.endswith('/adrenal-washout-calculator')
    page.goto(f"{base_url}/impressions")
    page.locator('a[href="/powerscribe-companion"]').click()
    assert page.url.endswith('/powerscribe-companion')
