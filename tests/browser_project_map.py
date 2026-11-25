"""Real Chromium checks for the integrated Project Flow Explainer, including local Ask."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class ProjectFlowBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.workspace = Path(temp.name)
        cls.repo = cls.workspace / 'shop-app'
        shutil.copytree(ROOT / 'tests/fixtures/shop-app', cls.repo, ignore=shutil.ignore_patterns('artifacts'))
        subprocess.run(['git', 'init', '-q', cls.repo], check=True)
        subprocess.run([sys.executable, ROOT / 'scripts/build_flow.py', '--repo', cls.repo,
                        '--request', 'Giải thích luồng xuất báo cáo', '--slug', 'bao-cao'], check=True)
        cls.map_dir = cls.repo / 'project-flow-explainer'
        cli = ROOT / 'scripts/project_map.mjs'
        subprocess.run(['node', cli, 'build', cls.repo], check=True)
        with (cls.repo / 'server.js').open('a') as source:
            source.write('\n// fixture update\n')
        subprocess.run(['node', cli, 'refresh', cls.repo], check=True)
        cls.demo = cls.workspace / 'flow.html'
        subprocess.run([sys.executable, ROOT / 'scripts/render_flow.py', ROOT / 'assets/example_workflow.json',
                        '--out', cls.demo, '--viewer', 'project-flow-explainer'], check=True)
        cls.url = cls.start_server(cls.addClassCleanup)
        playwright = sync_playwright().start()
        cls.addClassCleanup(playwright.stop)
        cls.browser = playwright.chromium.launch(executable_path=os.getenv('PFE_BROWSER'))
        cls.addClassCleanup(cls.browser.close)

    @classmethod
    def start_server(cls, add_cleanup, *args, env=None):
        server = subprocess.Popen(['node', cls.map_dir / 'serve.mjs', '--no-open', '--port', '0', *args],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                  cwd=cls.repo, env=env)
        def cleanup():
            server.terminate()
            try:
                server.wait(timeout=5)
            finally:
                if server.poll() is None:
                    server.kill()
                    server.wait(timeout=5)
                server.stdout.close()
        add_cleanup(cleanup)
        import selectors
        with selectors.DefaultSelector() as selector:
            selector.register(server.stdout, selectors.EVENT_READ)
            if not selector.select(timeout=10):
                raise RuntimeError('Project Flow Explainer server startup timed out')
            line = server.stdout.readline()
            if not (match := re.search(r'http://127[.]0[.]0[.]1:[0-9]+', line)):
                raise RuntimeError(line)
            return match.group()

    def open(self, url, width=1440, height=900):
        context = self.browser.new_context(viewport={'width': width, 'height': height}, color_scheme='light',
                                           reduced_motion='reduce', offline=url.startswith('file:'))
        self.addCleanup(context.close)
        page = context.new_page()
        page.set_default_timeout(5000)
        errors, outside = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        from urllib.parse import urlsplit
        origin = urlsplit(url).netloc
        page.on('request', lambda request: outside.append(request.url) if request.url.startswith(('http:', 'https:')) and urlsplit(request.url).netloc != origin else None)
        self.addCleanup(lambda: self.assertEqual(errors, []))
        self.addCleanup(lambda: self.assertEqual(outside, []))
        page.goto(url+'#tour=0')
        page.wait_for_function('window.ProjectFlow?.state.layout')
        return page

    def shot(self, page, name):
        if directory := os.getenv('PFE_SCREENSHOTS'):
            target = Path(directory)
            target.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=target / name)

    def test_full_map_navigation_and_native_panels(self):
        page = self.open(self.url+'/')
        expect(page.locator('#proj-name')).to_have_text('shop-app')
        expect(page).to_have_title('shop-app · Project Flow Explainer')
        expect(page.locator('.brand .mark')).to_have_attribute('alt', 'Project Flow Explainer')
        self.shot(page,'project-flow-explainer-desktop.png')
        page.locator('#btn-health').click()
        expect(page.locator('#panel')).to_contain_text('Đã kiểm tra những gì')
        page.get_by_role('button',name='Việc gần đây', exact=True).click()
        expect(page.locator('#panel')).to_contain_text('Thay đổi từ lần dựng trước')
        page.locator('#search-btn').click()
        page.locator('#search').fill('report_service')
        page.locator('#search').press('Enter')
        expect(page.locator('#panel')).to_contain_text('services/report_service.js')
        page.locator('#theme-toggle').click()
        expect(page.locator('html')).to_have_attribute('data-theme','light')
        page.locator('#theme-toggle').click()
        expect(page.locator('html')).to_have_attribute('data-theme','dark')
        page.locator('#theme-toggle').click()
        page.locator('#flows-btn').click()
        expect(page.locator('#flowmenu')).to_contain_text('Giải thích luồng xuất báo cáo')

    def test_offline_map_explains_how_to_enable_dsh_ask(self):
        page = self.open((self.map_dir / 'index.html').as_uri())
        warning = page.locator('#ask-warn')
        expect(warning).to_contain_text('DeepSeek Harness')
        expect(warning).not_to_contain_text(re.compile('Claude|Codex'))
        expect(warning.locator('code').first).to_have_text('node project-flow-explainer/serve.mjs --no-open')
        expect(warning.locator('code').last).to_have_text('node project-flow-explainer/serve.mjs --no-open --agent')
        expect(page.locator('#ask-input')).to_be_disabled()

    def test_agent_ask_calls_dsh_headless_with_map_context(self):
        stub = self.workspace / 'fake-dsh.mjs'
        stub.write_text("""import fs from 'node:fs';
const args = process.argv.slice(2);
if (args[0] === '--version') { console.log('test-dsh'); process.exit(); }
const prompt = fs.readFileSync(0, 'utf8');
if (!args.includes('headless') || !args.includes('read-only') || !prompt.includes('report_service')) process.exit(2);
console.log(JSON.stringify({type:'final',text:JSON.stringify({title:'Kết quả thử',answer:'Đã nhận ngữ cảnh bản đồ.',items:[]})}));
""", encoding='utf-8')
        url = self.start_server(self.addCleanup, '--agent', env={**os.environ, 'PROJECT_FLOW_DSH': str(stub)})
        page = self.open(url + '/')
        expect(page.locator('#ask-engine')).to_have_text('DeepSeek Harness')
        page.locator('#ask-input').fill('report_service')
        page.locator('#ask-input').press('Enter')
        expect(page.locator('#ask-sheet')).to_contain_text('Đã nhận ngữ cảnh bản đồ.')

    def test_model_picker_uses_profile_routes_and_applies_temporary_overlay(self):
        stub = self.workspace / 'catalog-dsh.mjs'
        stub.write_text("""import fs from 'node:fs';
const args=process.argv.slice(2);
if (args.includes('--version')) { console.log('test-dsh'); process.exit(); }
if (args.includes('--dump-config')) {
  if (args[args.indexOf('--profile')+1]!=='web') process.exit(2);
  console.log(JSON.stringify([
    {id:'agent-default-model',config:{provider:'test-route',model:'shared/model'}},
    {id:'llm-pi-ai',config:{providers:{'test-route':{baseURL:'https://example.invalid/v1',apiKeyEnv:'FIXTURE_REF',headers:{Authorization:'PRIVATE_HEADER'},models:[{id:'shared/model',name:'Mô hình chung'}]},'other-route':{models:[{id:'shared/model',name:'Mô hình chung'}]}}}}
  ]));
  process.exit();
}
fs.readFileSync(0,'utf8');
if (args.includes('--model') || args[args.indexOf('--profile')+1]!=='headless') process.exit(3);
const patch=JSON.parse(fs.readFileSync(args[args.indexOf('--patch')+1],'utf8'));
const choice=patch.find(row=>row.id==='agent-default-model').config;
if (choice.provider!=='other-route'||choice.model!=='shared/model'||!patch.some(row=>row.id==='credentials'&&row.disabled===false)) process.exit(4);
console.log(JSON.stringify({type:'final',text:JSON.stringify({answer:'Đã dùng đúng tuyến.',items:[]})}));
""", encoding='utf-8')
        url = self.start_server(self.addCleanup, '--agent', env={**os.environ, 'PROJECT_FLOW_DSH':str(stub)})
        page = self.open(url + '/')
        picker = page.get_by_label('Mô hình DSH')
        expect(picker.locator('option')).to_have_count(2)
        self.assertEqual(page.request.get(url + '/api/models').status,403)
        self.assertFalse('PRIVATE_HEADER' in picker.inner_text())
        picker.select_option(label='Mô hình chung · other-route')
        page.locator('#ask-input').fill('report_service')
        page.locator('#ask-input').press('Enter')
        expect(page.locator('#ask-sheet')).to_contain_text('Đã dùng đúng tuyến.')

    def test_agent_missing_credential_has_local_lookup(self):
        stub = self.workspace / 'missing-credential-dsh.mjs'
        stub.write_text("""if (process.argv.includes('--version')) { console.log('test-dsh'); process.exit(); }
console.log(JSON.stringify({type:'final',reason:{kind:'error',error:{code:'MISSING_CREDENTIAL',message:'PRIVATE_PROVIDER_DIAGNOSTIC'}}}));
process.exitCode = 1;
""", encoding='utf-8')
        url = self.start_server(self.addCleanup, '--agent', env={**os.environ, 'PROJECT_FLOW_DSH': str(stub)})
        page = self.open(url + '/')
        page.locator('#ask-input').fill('report_service')
        page.locator('#ask-input').press('Enter')
        sheet = page.locator('#ask-sheet')
        expect(sheet).to_contain_text('MISSING_CREDENTIAL')
        expect(sheet).not_to_contain_text('PRIVATE_PROVIDER_DIAGNOSTIC')
        sheet.get_by_role('button',name='Tra cứu bản đồ cục bộ').click()
        expect(sheet).to_contain_text('Các mục sau khớp dữ liệu tĩnh')
        expect(sheet).to_contain_text('services/report_service.js')

    def test_agent_missing_dsh_explains_local_fallback(self):
        missing = self.workspace / 'missing-dsh'
        url = self.start_server(self.addCleanup, '--agent', env={**os.environ, 'PROJECT_FLOW_DSH': str(missing)})
        page = self.open(url + '/')
        expect(page.locator('#ask-engine')).to_have_text('Thiếu DSH')
        expect(page.locator('#ask-warn')).to_contain_text('dsh --version')
        expect(page.locator('#ask-warn')).not_to_contain_text(re.compile('Claude|Codex'))

    def test_local_ask_and_share(self):
        page = self.open(self.url+'/')
        expect(page.locator('#ask-engine')).to_contain_text('Bản đồ cục bộ')
        page.locator('#ask-input').fill('report_service')
        page.locator('#ask-input').press('Enter')
        expect(page.locator('#ask-sheet')).to_contain_text('Các mục sau khớp dữ liệu tĩnh')
        expect(page.locator('#ask-sheet')).to_contain_text('services/report_service.js')
        self.assertEqual(page.request.get(self.url+'/graph.json').status,404)
        self.assertEqual(page.request.get(self.url+'/api/health').status,403)
        page.locator('#btn-export').click()
        with page.expect_download() as request:
            page.get_by_role('button',name='Tải xuống',exact=True).click()
        artifact=self.workspace/'shared.html'
        request.value.save_as(artifact)
        shared=self.open(artifact.as_uri())
        expect(shared.locator('#ask')).to_be_hidden()
        expect(shared.locator('#proj-name')).to_have_text('shop-app')
        expect(shared.locator('#madewith')).to_contain_text('Project Flow Explainer')
        expect(shared.locator('#madewith')).to_have_attribute('href', 'https://github.com/Hieupt1904/project-flow-explainer')

    def test_business_flow_branch_retry_and_evidence(self):
        page=self.open(self.demo.as_uri())
        expect(page.locator('#pfe-guide')).to_be_visible()
        self.shot(page,'project-flow-explainer-flow.png')
        page.locator('#pfe-guide').click()
        panel=page.locator('#panel')
        for branch in ['Kích hoạt bảo hành','Đã gửi biểu mẫu','Cần bổ sung','Người dùng sửa lại']:
            panel.get_by_role('button',name=re.compile(branch)).click()
        expect(panel.locator('h2')).to_have_text('Gửi thông tin kích hoạt')
        panel.get_by_role('button',name='Quay lại').click()
        expect(panel.locator('h2')).to_have_text('Yêu cầu bổ sung thông tin')
        page.locator('#pfe-evidence').click()
        expect(panel.get_by_role('heading',name='Căn cứ và giới hạn')).to_be_visible()
        self.assertEqual(page.locator('#workflow-json').count(),1)

    def test_mobile_map_opens_offline(self):
        page=self.open((self.map_dir/'index.html').as_uri(),390,844)
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        page.locator('#btn-panel').click()
        expect(page.locator('#panel h2')).to_have_text('shop-app')
        self.shot(page,'project-flow-explainer-mobile.png')


if __name__ == '__main__':
    unittest.main(verbosity=2)
