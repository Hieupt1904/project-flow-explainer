// Fixture: lớp đọc hóa đơn, có bắt lỗi riêng và ghi xuống DB.
const { db } = require('../db/connection')

async function readInvoice(id) {
  try {
    const sql = 'SELECT id, total FROM invoices WHERE id = ?'
    const rows = await db.query(sql, [id])
    return rows[0]
  } catch (error) {
    throw new Error('invoice_query_failed')
  }
}

module.exports = { readInvoice }
