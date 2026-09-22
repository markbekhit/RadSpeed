"""Public blank report copying, with an explicit manual fallback."""
import pytest
from playwright.sync_api import expect


@pytest.mark.parametrize(
    'slug',
    ['ct-head-brain', 'ct-neck', 'ultrasound-doppler-venous', 'ct-pulmonary-angiogram'],
)
def test_blank_report_copy_preserves_placeholders(page, base_url, slug):
    page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
    page.goto(f'{base_url}/report-templates/{slug}')
    page.get_by_role('link', name='Get the blank report format').click()
    expected = page.locator('#report-format-text').text_content()
    assert '[Indication' in expected and 'IMPRESSION:' in expected
    page.get_by_role('button', name='Copy blank report').click()
    expect(page.locator('#copy-report-status')).to_contain_text('Blank report copied')
    assert page.evaluate('navigator.clipboard.readText()') == expected


@pytest.mark.parametrize('slug', ['ct-head-brain', 'ct-pulmonary-angiogram'])
def test_denied_copy_selects_text_without_false_success(page, base_url, slug):
    page.add_init_script("""Object.defineProperty(navigator, 'clipboard', {
        value: {writeText: async () => { throw new Error('denied'); }}
    });""")
    page.goto(f'{base_url}/report-templates/{slug}')
    page.get_by_role('button', name='Copy blank report').click()
    expect(page.locator('#copy-report-status')).to_contain_text('Automatic copy is unavailable')
    assert page.evaluate('window.getSelection().toString()') == page.locator('#report-format-text').text_content()
