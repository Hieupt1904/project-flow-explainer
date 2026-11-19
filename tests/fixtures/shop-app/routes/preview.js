// Fixture: route "mồi" — khớp từ khoá xuất báo cáo nhưng KHÔNG được nối vào luồng,
// vì server.js không import file này. Dùng để test rằng builder không dựng chuỗi giả.
const express = require('express')

const router = express.Router()

router.get('/api/legacy/preview', (req, res) => {
  // Bản cũ: trả CSV trực tiếp, không đi qua report_service.
  res.setHeader('Content-Type', 'text/csv')
  res.send('id,total\n1,2\n')
})

module.exports = router
