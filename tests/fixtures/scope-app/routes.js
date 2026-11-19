// Fixture: route xuất báo cáo KHÔNG có try/catch; route xem chi tiết CÓ try/catch.
// Khi chọn route export, builder không được sinh decision từ try/catch của route kia.
const express = require('express')
const router = express.Router()

router.post('/api/reports/export', async (req, res) => {
  const target = buildReportFile(req.body.id)
  res.download(target)
})

router.get('/api/reports/:id', async (req, res) => {
  try {
    const rows = loadRows(req.params.id)
    res.json(rows)
  } catch (error) {
    res.status(500).json({ ok: false })
  }
})

function buildReportFile(id) {
  return 'report-' + id + '.xlsx'
}

function loadRows(id) {
  return []
}

module.exports = router
