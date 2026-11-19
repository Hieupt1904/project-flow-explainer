// Fixture: lớp nghiệp vụ xuất báo cáo (Excel/CSV) cho test build_flow.
const path = require('node:path')
const { loadReportRows } = require('../db/report_repo')

async function exportReport(reportId, format = 'xlsx') {
  const rows = await loadReportRows(reportId)
  if (!rows.length) {
    throw new Error('report_empty')
  }
  const target = path.join('/tmp', `report-${reportId}.${format}`)
  return { path: target, name: `report-${reportId}.${format}` }
}

async function buildWorkbook(rows) {
  return rows.map((row, index) => ({ index, ...row }))
}

module.exports = { exportReport, buildWorkbook }
