# Ví dụ fact thật của ontology

Sinh từ fixture `tests/fixtures/shop-app` sau `pfe_cli.py index --mode full`.
Đây là dữ liệu thật trong index, không phải ví dụ tự nghĩ ra.

## 1. Mỗi quan hệ một ví dụ

```json
[
  {
    "subject": "repository:shop-app",
    "predicate": "contains",
    "object": "file:server.js",
    "evidence": { "kind": "structural", "path": "server.js", "start_line": 1 },
    "confidence": "structural"
  },
  {
    "subject": "file:db/report_repo.js",
    "predicate": "defines",
    "object": "function:db/report_repo.js#loadReportRows",
    "evidence": { "kind": "observed", "path": "db/report_repo.js", "start_line": 4, "symbol": "loadReportRows" },
    "confidence": "observed"
  },
  {
    "subject": "file:server.js",
    "predicate": "calls",
    "object": "symbol:services/report_service.js#exportReport",
    "evidence": {
      "kind": "call_site", "path": "server.js", "start_line": 9,
      "symbol": "exportReport",
      "detail": "call site; declaration tại services/report_service.js:5"
    },
    "confidence": "observed"
  },
  {
    "subject": "file:db/report_repo.js",
    "predicate": "exports",
    "object": "symbol:db/report_repo.js#loadReportRows",
    "evidence": { "kind": "observed", "path": "db/report_repo.js", "start_line": 4 },
    "confidence": "observed"
  },
  {
    "subject": "file:server.js",
    "predicate": "handles_route",
    "object": "route:GET /api/reports/:id",
    "evidence": { "kind": "observed", "path": "server.js", "start_line": 7 },
    "confidence": "observed"
  },
  {
    "subject": "file:server.js",
    "predicate": "reads_from",
    "object": "external_system:express",
    "evidence": { "kind": "structural", "path": "server.js", "start_line": 1 },
    "confidence": "structural"
  },
  {
    "subject": "file:server.js",
    "predicate": "catches",
    "object": "error_case:server.js#caught@8",
    "evidence": { "kind": "observed", "path": "server.js", "start_line": 8, "detail": "khối try" },
    "confidence": "observed"
  },
  {
    "subject": "file:jobs/export_worker.py",
    "predicate": "raises",
    "object": "error_case:jobs/export_worker.py#python-raise@9",
    "evidence": { "kind": "observed", "path": "jobs/export_worker.py", "start_line": 9 },
    "confidence": "observed"
  }
]
```

## 2. Vì sao mỗi fact "đứng vững"

| Fact | Bằng chứng |
|---|---|
| `calls` | dòng 9 của `server.js` thực sự gọi `exportReport`; khai báo ở `services/report_service.js:5` |
| `handles_route` | dòng 7 khai báo route, không phải suy từ tên file |
| `reads_from external_system` | `require('express')` ở dòng 1, xếp `structural` vì đó là import chứ không phải lời gọi |
| `catches` / `raises` | dòng cụ thể của `try` và `raise` |

## 3. Ba loại fact **không** được sinh

| Trường hợp | Lý do |
|---|---|
| `calls` khi chỉ có import | import không chứng minh lời gọi; flow cũng không gắn `evidence=call` |
| `returns` | cần type info; khai báo trong schema nhưng `emitted: false` |
| `belongs_to_flow` thành `observed` | thành viên luồng là suy luận, luôn `inferred` |

## 4. Khi hai fact trùng khoá

Fact yếu hơn không bị xoá âm thầm. Nó được ghi vào khoá `contradicted` của fact thắng:

```json
{
  "subject": "file:a.py",
  "predicate": "reads_from",
  "object": "data_model:rows",
  "confidence": "observed",
  "evidence": { "kind": "observed", "path": "a.py", "start_line": 3 },
  "contradicted": {
    "confidence": "structural",
    "evidence": { "kind": "structural", "path": "a.py", "start_line": 1 }
  }
}
```

Test khoá hành vi này: `test_structural_never_replaces_observed`.
