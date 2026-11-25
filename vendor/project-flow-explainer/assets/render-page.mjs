import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {scriptJson,scriptCode,withPolicy} from './page-safety.mjs';
const HERE=path.dirname(fileURLToPath(import.meta.url));
const template = fs.readFileSync(path.join(HERE, 'viewer.html'), 'utf8');
// The layout engine (elkjs 0.9.3) and fonts (Inter, JetBrains Mono) are bundled in assets/vendor/ and
// inlined, so the map makes no outside requests and works offline.
const vendor = path.join(HERE, 'vendor');
const elkTag = `<script>${scriptCode(fs.readFileSync(path.join(vendor, 'elk.bundled.js'), 'utf8'))}</script>`;
const FONT_RANGES = {
  latin: 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD',
  'latin-ext': 'U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF',
};
const fontCss = [['Inter', 'inter'], ['JetBrains Mono', 'jetbrains-mono']].flatMap(([family, file]) => Object.entries(FONT_RANGES).map(([subset, range]) =>
  `@font-face{font-family:"${family}";font-style:normal;font-display:swap;font-weight:100 900;unicode-range:${range};src:url(data:font/woff2;base64,${fs.readFileSync(path.join(vendor, 'fonts', `${file}-${subset}-wght-normal.woff2`)).toString('base64')}) format("woff2")}`)).join('\n');
const graphQuery = fs.readFileSync(path.join(HERE, 'graph-query.js'), 'utf8');
// Code goes in through scriptCode and the map's data through scriptJson (assets/page-safety.mjs), and the data
// goes in last, so nothing in it can be taken for one of the page's own placeholders.
const projectMark = 'data:image/svg+xml;base64,' + fs.readFileSync(path.join(HERE, 'project-mark.svg')).toString('base64');
const page = (g) => template
  .replace('/*__GRAPH_QUERY__*/', () => scriptCode(graphQuery))
  .replace('<!--__ELK_SCRIPT__-->', () => elkTag)
  .replace('/*__FONTS__*/', () => fontCss)
  .replace(/__PROJECT_FLOW_TITLE__/g, () => escapeHtml(g.project.name === 'Project Flow Explainer' ? g.project.name : g.project.name + ' · Project Flow Explainer'))
  .replace(/__PROJECT_FLOW_MARK__/g, () => projectMark)
  .replace('<!--__UI_EXTENSIONS__-->', () => uiScripts)
  .replace(/<!--__PFE_DATA__-->|\/\*__PROJECT_FLOW_DATA__\*\/null/g, slot => slot === '<!--__PFE_DATA__-->'
    ? g.pfeFlow ? '<script id="workflow-json" type="application/json">'+scriptJson(g.pfeFlow)+'</script>' : ''
    : scriptJson(g));
const uiDir = path.join(HERE, 'ui');
const uiScripts = fs.existsSync(uiDir) ? fs.readdirSync(uiDir).filter((n) => n.endsWith('.js') && n !== '50-cloud.js').sort().map((n) => `<script>/* ui/${n} */\n${scriptCode(fs.readFileSync(path.join(uiDir, n), 'utf8'))}</script>`).join('\n') : '';

// Keep the generated title as text, not markup.
function escapeHtml(s) { return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]); }


export function renderPage(graph, policy='local') {
  return withPolicy(page(graph),policy);
}
