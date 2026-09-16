"""Public discovery remains usable when the resource links grow."""

import pytest


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


@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("source,target", [
    ("mri-hip", "mri-ankle"),
    ("mri-shoulder", "mri-wrist"),
    ("ct-spine-lumbar", "mri-spine-lumbar"),
    ("mri-spine-thoracic", "ct-spine-thoracic"),
    ("cxr", "ct-chest"),
    ("ct-pulmonary-angiogram", "cxr"),
])
def test_related_template_navigation(page, base_url, width, source, target):
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{base_url}/report-templates/{source}")
    section = page.locator('.detail-related')
    section.scroll_into_view_if_needed()
    assert section.locator('h2').inner_text() == 'Related report templates'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    section.locator(f'a[href="/report-templates/{target}"]').click()
    assert page.url.endswith(f'/report-templates/{target}')
    assert page.locator('h1').is_visible()


@pytest.mark.parametrize("width", [390, 1440])
def test_software_to_public_template_paths(page, base_url, width):
    page.set_viewport_size({"width": width, "height": 844})
    for target in ['mri-spine-lumbar', '']:
        path = '/report-templates' + ('/' + target if target else '')
        page.goto(f"{base_url}/radiology-reporting-software")
        link = page.locator(f'#workflow a[href="{path}"]')
        link.scroll_into_view_if_needed()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        link.click()
        assert page.url.endswith(path)


@pytest.mark.parametrize("width", [390, 1440])
def test_library_finder_filters_and_routes_unmatched_studies(page, base_url, width):
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{base_url}/report-templates")
    search = page.locator('#template-search')
    status = page.locator('#template-search-status')
    cards = page.locator('.template-card:visible')
    assert cards.count() >= 39
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')

    search.fill('doppler report format')
    assert cards.count() == 2
    assert 'match “doppler report format”' in status.inner_text()
    assert page.locator('.library-group:visible').count() == 1
    assert '?q=doppler' in page.url

    page.locator('.library-filter[data-modality="ct"]').click()
    assert cards.count() == 0
    empty = page.locator('#library-empty')
    assert empty.is_visible()
    assert 'No match in CT' in status.inner_text()

    page.locator('.library-filter[data-modality="all"]').click()
    search.fill('wrist ultrasound')
    assert cards.count() == 0
    closest = empty.locator('#library-closest a')
    assert closest.first.get_attribute('href') == '/report-templates/mri-wrist'
    assert closest.count() == 4
    assert empty.locator('a[href="/impressions"]').is_visible()

    page.locator('#library-empty-reset').click()
    assert cards.count() >= 39
    assert not empty.is_visible()
    assert '?q=' not in page.url

    search.fill('wrist ultrasound')
    empty.locator('#library-closest a').first.click()
    assert page.url.endswith('/report-templates/mri-wrist')

    page.goto(f"{base_url}/report-templates?q=ctpa&modality=ct")
    assert cards.count() == 1
    assert page.locator('.library-filter.is-active').get_attribute('data-modality') == 'ct'
    cards.first.click()
    assert page.url.endswith('/report-templates/ct-pulmonary-angiogram')
