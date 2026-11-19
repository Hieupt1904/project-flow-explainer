// Fixture: truy vấn dữ liệu báo cáo cho test build_flow.
const { db } = require('./connection')

async function loadReportRows(reportId) {
  const sql = 'SELECT id, total, created_at FROM report_lines WHERE report_id = ?'
  return db.query(sql, [reportId])
}

module.exports = { loadReportRows }
