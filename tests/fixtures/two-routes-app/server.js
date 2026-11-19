// Fixture: hai route trong cùng file, mỗi route có khối bắt lỗi riêng.
// Dùng để chứng minh decision/error node chỉ lấy từ vùng code của route được chọn.
const express = require('express')
const { readInvoice } = require('./services/invoice')

const app = express()

app.get('/api/invoices/:id', async (req, res) => {
  try {
    const invoice = await readInvoice(req.params.id)
    res.json(invoice)
  } catch (error) {
    res.status(404).json({ ok: false, message: 'invoice_not_found' })
  }
})

app.post('/api/invoices/void', async (req, res) => {
  const invoice = await readInvoice(req.body.id)
  res.json({ ok: true, invoice })
})

module.exports = app
