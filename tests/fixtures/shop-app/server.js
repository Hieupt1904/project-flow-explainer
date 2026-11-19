// Fixture: điểm vào HTTP của ứng dụng mẫu dùng cho test build_flow.
const express = require('express')
const { exportReport } = require('./services/report_service')

const app = express()

app.get('/api/reports/:id', async (req, res) => {
  try {
    const rows = await exportReport(req.params.id, req.query.format)
    res.json({ ok: true, rows: rows.length })
  } catch (error) {
    res.status(500).json({ ok: false, message: 'export_failed' })
  }
})

app.post('/api/reports/export', async (req, res) => {
  const file = await exportReport(req.body.reportId, req.body.format)
  res.download(file.path, file.name)
})

module.exports = app
