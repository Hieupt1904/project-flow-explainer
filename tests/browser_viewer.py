"""Optional Chromium E2E: python3 tests/browser_viewer.py.

Requires Python Playwright and its Chromium, or set PFE_BROWSER to a system binary.
Set PFE_SCREENSHOTS to a directory to save desktop and mobile captures.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class ViewerBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        cls.demo = cls.work / 'demo.html'
        subprocess.run([sys.executable, ROOT / 'scripts/render_flow.py',
                        ROOT / 'assets/example_workflow.json', '--out', cls.demo, '--viewer', 'classic'], check=True)
        repo = cls.work / 'shop-app'
        shutil.copytree(ROOT / 'tests/fixtures/shop-app', repo, ignore=shutil.ignore_patterns('artifacts'))
        subprocess.run(['git', 'init', '-q', repo], check=True)
        subprocess.run([sys.executable, ROOT / 'scripts/build_flow.py', '--repo', repo,
                        '--request', 'Giải thích luồng xuất báo cáo', '--slug', 'evidence-demo'], check=True)
        cls.evidence = repo / 'artifacts/flows/evidence-demo/flow.html'
        subprocess.run([sys.executable, ROOT / 'scripts/render_flow.py', cls.evidence.with_suffix('.json'),
                        '--out', cls.evidence, '--viewer', 'classic'], check=True)
        playwright = sync_playwright().start()
        cls.addClassCleanup(playwright.stop)
        cls.browser = playwright.chromium.launch(executable_path=os.getenv('PFE_BROWSER'))
        cls.addClassCleanup(cls.browser.close)

    def open(self, path, width=1440, height=900):
        context = self.browser.new_context(viewport={'width': width, 'height': height}, color_scheme='light', offline=True)
        self.addCleanup(context.close)
        page = context.new_page()
        page.set_default_timeout(4000)
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        page.on('request', lambda request: requests.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
        self.addCleanup(lambda: self.assertEqual(errors, []))
        self.addCleanup(lambda: self.assertEqual(requests, []))
        page.goto(path.as_uri())
        return page

    def shot(self, page, file):
        if out := os.getenv('PFE_SCREENSHOTS'):
            Path(out).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=Path(out) / file)

    def test_map_fit_zoom_and_label_positions(self):
        page = self.open(self.demo)
        expect(page.get_by_role('heading', name='Tổng quan luồng')).to_be_visible()
        expect(page.locator('.node-card')).to_have_count(8)
        expect(page.locator('.edge-path[marker-end]')).to_have_count(8)
        expect(page.locator('.mini-node')).to_have_count(8)
        # Compare in world coordinates, independent of the viewport transform.
        overlaps = page.evaluate('''() => {
          const boxes = [...document.querySelectorAll('.edge-label-rect, .node-card')];
          return boxes.flatMap((a,i) => !a.matches('.edge-label-rect') ? [] : boxes.slice(i+1).filter(b => {
            const r=a.getBoundingClientRect(), s=b.getBoundingClientRect();
            return r.left<s.right && r.right>s.left && r.top<s.bottom && r.bottom>s.top;
          })).length;
        }''')
        self.assertEqual(overlaps, 0)
        zoom = page.locator('#zoom-level')
        fit = zoom.inner_text()
        page.get_by_role('button', name='Phóng to', exact=True).click()
        self.assertGreater(int(zoom.inner_text().strip('%')), int(fit.strip('%')))
        page.get_by_role('button', name='Vừa khung').click()
        expect(zoom).to_have_text(fit)
        self.shot(page, 'flow-desktop.png')

    def test_search_guide_branch_loop_back_and_finish(self):
        page = self.open(self.demo)
        page.keyboard.press('/')
        search = page.get_by_role('searchbox')
        expect(search).to_be_focused()
        search.fill('kiem tra tinh hop le')
        search.press('ArrowDown')
        page.keyboard.press('Enter')
        expect(page.get_by_role('heading', name='Kiểm tra tính hợp lệ', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='Kiểm tra tính hợp lệ', exact=True)).to_have_attribute('aria-pressed', 'true')
        search.fill('query matches nothing')
        expect(page.get_by_text('Không có bước nào khớp.', exact=True)).to_be_visible()
        search.press('Escape')
        expect(page.locator('#search-results')).to_be_hidden()
        page.get_by_role('button', name='Dẫn qua luồng').click()
        guide = page.locator('#guide')
        guide.get_by_role('button', name='Kích hoạt bảo hành').click()
        guide.get_by_role('button', name='Đã gửi biểu mẫu').click()
        guide.get_by_role('button', name='Cần bổ sung').click()
        guide.get_by_role('button', name='Người dùng sửa lại').click()
        expect(guide.get_by_role('heading', name='Gửi thông tin kích hoạt')).to_be_visible()
        guide.get_by_role('button', name='Quay lại').click()
        expect(guide.get_by_role('heading', name='Yêu cầu bổ sung thông tin')).to_be_visible()
        guide.get_by_role('button', name='Quay lại').click()
        guide.get_by_role('button', name='Dữ liệu hợp lệ').click()
        guide.get_by_role('button', name='Kết thúc hướng dẫn').click()
        expect(guide).to_be_hidden()
        expect(page.get_by_role('heading', name='Thông báo kích hoạt thành công')).to_be_visible()

    def test_evidence_filters_and_source_details(self):
        page = self.open(self.evidence)
        page.get_by_role('button', name='Căn cứ', exact=True).click()
        panel = page.locator('#inspection-content')
        expect(panel.get_by_role('heading', name='Căn cứ và giới hạn')).to_be_visible()
        expect(panel.get_by_text('Các tệp này không nằm trên đường nối của sơ đồ.')).to_be_visible()
        expect(panel.get_by_text('routes/preview.js', exact=True)).to_be_visible()
        panel.get_by_role('button', name='Có căn cứ tĩnh').click()
        expect(page.get_by_role('button', name='Từng bước')).to_have_attribute('aria-pressed', 'true')
        self.assertGreater(page.locator('.step-row').count(), 0)
        expect(page.locator('.step-row .label:not(.verified)')).to_have_count(0)
        page.get_by_role('button', name='Bỏ lọc').click()
        panel.locator('.ref-links button').first.click()
        expect(panel.get_by_role('heading', name='Căn cứ trong mã nguồn')).to_be_visible()
        self.shot(page, 'flow-evidence.png')

    def test_dark_theme_panel_and_downloaded_copy(self):
        page = self.open(self.demo)
        theme = page.locator('#theme-toggle')
        theme.click()
        theme.click()
        expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
        page.reload()
        expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
        toggle = page.get_by_role('button', name='Ẩn hoặc hiện bảng chi tiết')
        toggle.click()
        expect(page.locator('#inspector')).to_be_hidden()
        toggle.click()
        expect(page.locator('#inspector')).to_be_visible()
        self.shot(page, 'flow-dark.png')
        with page.expect_download() as download:
            page.get_by_role('button', name='Tải bản đồ HTML').click()
        self.assertEqual(download.value.suggested_filename, 'demo-warranty-chatbot.html')
        copy = self.work / 'share.html'
        download.value.save_as(copy)
        self.assertNotIn('class="node-card', copy.read_text(encoding='utf-8'))
        reopened = self.open(copy)
        expect(reopened.locator('.node-card')).to_have_count(8)
        self.assertEqual(reopened.locator('#workflow-json').text_content(),
                         page.locator('#workflow-json').text_content())
        expect(reopened.get_by_role('heading', name='Tổng quan luồng')).to_be_visible()

    def test_mobile_navigation_has_no_horizontal_overflow(self):
        page = self.open(self.demo, 390, 844)
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.shot(page, 'flow-mobile.png')
        page.get_by_role('button', name='Từng bước').click()
        page.locator('.step-row').first.get_by_role('button').click()
        expect(page.locator('#inspection-content').get_by_role('heading', name='Chào mừng khách hàng')).to_be_visible()
        expect(page.get_by_role('button', name='Mở trên bản đồ')).to_be_visible()
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
