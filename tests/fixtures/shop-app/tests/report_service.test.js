// Fixture: test nhắc tới exportReport để kiểm tra quan hệ tested_by.
const { exportReport } = require('../services/report_service')

describe('exportReport', () => {
  it('trả về file báo cáo', async () => {
    const file = await exportReport('r-1', 'xlsx')
    expect(file.name).toContain('r-1')
  })
})
