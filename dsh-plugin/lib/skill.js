/**
 * Model-facing DSH skill for Project Flow Explainer.
 *
 * DSH discovers filesystem skills only under `.dsh/skills/<name>/SKILL.md`
 * (and the other roots in dsh-skill-filesystem). A published plugin does not
 * live in the workspace being explained, so `apply` also registers the same
 * instructions with `ctx.skills.register`. The catalog shows `description`;
 * `content` is what `skill({ name })` returns. Keep `description` within the
 * default catalog bound of 500 characters.
 */

export const SKILL_NAME = 'project-flow-explainer'

export const SKILL_DESCRIPTION = 'Dựng sơ đồ luồng hoặc bản đồ kho từ mã nguồn. '
  + 'Dùng khi cần hiểu một luồng, tìm hàm hoặc route, hoặc biết file nào cần đọc trước khi sửa. '
  + 'Không chạy ứng dụng và không trả source thô.'

const BODY = `
# Project Flow Explainer

Plugin này phân tích tĩnh. Nó không chạy ứng dụng, không gọi mạng, và không trả nội dung source.

## Chọn công cụ

- Câu mô tả một luồng nghiệp vụ: \`project_flow_explain\`. Kết quả nằm trong \`artifacts/flows/<slug>/\` (\`flow.html\`, \`flow.json\`, \`overview.md\`).
- Lần đầu vào kho, hoặc sau khi đổi nhiều file: \`project_code_index\` với \`mode=full\`.
- Biết tên hàm, route hoặc từ khóa: \`project_code_search\`.
- Sắp sửa một việc và cần file, điểm vào, test: \`project_context_pack\`.
- Vừa sửa file và cần biết chỗ nào bị ảnh hưởng: \`project_impact_analysis\`.
- Vừa pull hoặc sửa ít file: \`project_knowledge_refresh\`.
- Cần biết sơ đồ và artifact có đủ căn cứ không: \`project_verify_flow\`. Đây là kiểm tĩnh, không chạy test của ứng dụng.

Người dùng cũng có thể gõ \`/project-flow-explainer\`. \`--map\` dựng bản đồ toàn kho, \`--refresh-map\` dựng lại, \`--blueprint\` đọc \`project-flow-explainer/plan.json\` đã có.

## Phạm vi đọc

Mặc định plugin đọc thư mục mà DSH đã cấp cho phiên. \`allowedRoots\` chỉ thêm kho nằm ngoài thư mục đó. Đường dẫn phải tuyệt đối. Không đọc file secret và không đưa đường dẫn tuyệt đối của máy vào kết quả trả cho mô hình.

## Cách đọc kết quả

\`verified\` nghĩa là có vị trí trong mã, không phải là đã chạy. Phân biệt quan hệ tĩnh với hành vi lúc chạy. Sau khi có sơ đồ, gọi \`project_context_pack\` trước khi sửa file trong luồng.
`.trim()

export const SKILL_BODY = BODY

/** Registration accepted by `ctx.skills.register`. */
export function skillRegistration() {
  return {
    name: SKILL_NAME,
    description: SKILL_DESCRIPTION,
    whenToUse: 'Người dùng muốn hiểu một luồng, một bản đồ kho, hoặc vị trí mã trước khi sửa.',
    source: 'runtime',
    content: SKILL_BODY,
    invocation: { modelInvocable: true, userInvocable: true },
  }
}

/** Filesystem skill. The local provider reads this frontmatter itself. */
export function skillMarkdown() {
  return [
    '---',
    `name: ${SKILL_NAME}`,
    `description: ${SKILL_DESCRIPTION}`,
    '---',
    '',
    SKILL_BODY,
    '',
  ].join('\n')
}
