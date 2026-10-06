"""Public blank report copying, with an explicit manual fallback."""
import pytest
from playwright.sync_api import expect


@pytest.mark.parametrize(
    'slug',
    ['ct-head-brain', 'ct-neck', 'ultrasound-doppler-venous', 'ct-pulmonary-angiogram', 'mri-hip', 'ultrasound-breast', 'hrct-thorax'],
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


@pytest.mark.parametrize('slug', ['ct-head-brain', 'ct-pulmonary-angiogram', 'hrct-thorax'])
def test_denied_copy_selects_text_without_false_success(page, base_url, slug):
    page.add_init_script("""Object.defineProperty(navigator, 'clipboard', {
        value: {writeText: async () => { throw new Error('denied'); }}
    });""")
    page.goto(f'{base_url}/report-templates/{slug}')
    page.get_by_role('button', name='Copy blank report').click()
    expect(page.locator('#copy-report-status')).to_contain_text('Automatic copy is unavailable')
    assert page.evaluate('window.getSelection().toString()') == page.locator('#report-format-text').text_content()


@pytest.mark.parametrize('width', [390, 1440])
def test_hrct_format_layout_and_onward_path(page, base_url, width):
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(f'{base_url}/report-templates/hrct-thorax')
    expect(page.locator('h1')).to_have_text('HRCT Chest (Thorax) report template')
    expect(page.locator('link[rel="canonical"]')).to_have_attribute(
        'href', 'https://radspeed.com.au/report-templates/hrct-thorax')
    report = page.locator('#report-format-text').text_content()
    assert 'SERIES ACQUIRED:' in report and 'if acquired' in report
    assert 'No pleural effusion.' not in report and 'Pattern is consistent' not in report
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.get_by_role('link', name='Reporting software', exact=True).first.click()
    expect(page).to_have_url(f'{base_url}/radiology-reporting-software')


def test_hrct_without_javascript_keeps_format_and_source(browser, base_url):
    context = browser.new_context(java_script_enabled=False)
    try:
        page = context.new_page()
        page.goto(f'{base_url}/report-templates/hrct-thorax')
        expect(page.locator('#report-format-text')).to_contain_text('EXAM: HRCT CHEST')
        expect(page.get_by_role('button', name='Copy blank report')).to_be_hidden()
        expect(page.get_by_role('link', name='2022 ATS/ERS/JRS/ALAT IPF and PPF guideline')).to_have_attribute(
            'href', 'https://pmc.ncbi.nlm.nih.gov/articles/PMC9851481/')
    finally:
        context.close()
