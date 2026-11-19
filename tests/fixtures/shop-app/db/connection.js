// Fixture: kết nối giả lập; không kết nối mạng thật.
const db = {
  async query(sql, params) {
    return []
  },
}

module.exports = { db }
