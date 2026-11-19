window.__ModuleLoader__.load({
  id: "dsh-project-flow-explainer",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    const React = require("react");
    const h = React.createElement;

    const PACKAGE = "dsh-project-flow-explainer";
    const FIELDS = [
      {
        key: "allowedRoots",
        label: "Thư mục được đọc (allowedRoots)",
        hint: "Mỗi dòng một đường dẫn tuyệt đối. Để trống nghĩa là từ chối mọi repository.",
        kind: "lines",
      },
      {
        key: "pythonPath",
        label: "Interpreter Python",
        hint: "Lệnh dùng để gọi core, ví dụ python3.",
        kind: "text",
        placeholder: "python3",
      },
      {
        key: "coreRoot",
        label: "Thư mục core",
        hint: "Bỏ trống để tự dò vendor/core trong gói đã cài.",
        kind: "text",
        placeholder: "(tự dò)",
      },
      {
        key: "timeoutMs",
        label: "Timeout mỗi lần gọi (ms)",
        hint: "Ngân sách thời gian cho một lần chạy core.",
        kind: "number",
        placeholder: "180000",
      },
      {
        key: "maxOutputBytes",
        label: "Giới hạn output (byte)",
        hint: "Cắt stdout và stderr vượt ngưỡng này.",
        kind: "number",
        placeholder: "1048576",
      },
    ];

    const styles = {
      wrap: { display: "flex", flexDirection: "column", gap: 14 },
      row: { display: "flex", flexDirection: "column", gap: 4 },
      label: { fontSize: 13, fontWeight: 600, color: "var(--dsw-alias-label-primary)" },
      hint: { fontSize: 12, color: "var(--dsw-alias-label-secondary)" },
      input: {
        boxSizing: "border-box",
        width: "100%",
        padding: "6px 8px",
        borderRadius: "var(--dsw-radius-md, 8px)",
        border: "0.5px solid var(--dsw-alias-border-l1, #d0d0d0)",
        background: "var(--dsw-alias-card-fill, transparent)",
        color: "var(--dsw-alias-label-primary)",
        font: "inherit",
        fontSize: 13,
      },
      textarea: { minHeight: 84, resize: "vertical", fontFamily: "inherit" },
      footer: { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" },
      button: {
        padding: "6px 14px",
        borderRadius: "var(--dsw-radius-md, 8px)",
        border: "0.5px solid var(--dsw-alias-border-l1, #d0d0d0)",
        background: "var(--dsw-alias-card-fill-hover, #f2f2f2)",
        color: "var(--dsw-alias-label-primary)",
        font: "inherit",
        fontSize: 13,
        cursor: "pointer",
      },
      status: { fontSize: 12, color: "var(--dsw-alias-label-secondary)" },
      error: { fontSize: 12, color: "var(--dsw-alias-label-error, #c0392b)" },
    };

    function text(value) {
      if (Array.isArray(value)) return value.join("\n");
      if (value === undefined || value === null) return "";
      return String(value);
    }

    function readForm(form) {
      const state = (form && form.state) || {};
      const value = state.value || {};
      const next = {};
      for (const field of FIELDS) next[field.key] = text(value[field.key]);
      return { next, writable: state.writable !== false, status: state.status };
    }

    function ConfigCard(props) {
      const form = props.form;
      const initial = readForm(form);
      const [draft, setDraft] = React.useState(initial.next);
      const [message, setMessage] = React.useState("");
      const [busy, setBusy] = React.useState(false);

      React.useEffect(() => {
        setDraft(readForm(form).next);
      }, [form, form && form.state && form.state.revision]);

      if (props.view === "summary") {
        const roots = text(initial.next.allowedRoots).split("\n").filter(Boolean);
        return h("span", { style: styles.status },
          roots.length === 0
            ? "Chưa cấu hình thư mục nào, mọi lời gọi sẽ bị từ chối."
            : "Đọc được " + roots.length + " thư mục: " + roots.join(", "));
      }

      if (!form) {
        return h("div", { style: styles.wrap },
          h("p", { style: styles.hint },
            "Host chưa cung cấp form cấu hình cho bundle này. Cấu hình bằng patch layer: ",
            h("code", null, "- id: project-flow-explainer")),
          h("p", { style: styles.hint },
            "Xem dsh-plugin/README.md mục cấu hình để biết mẫu YAML."));
      }

      const update = (key, value) => {
        setDraft((current) => Object.assign({}, current, { [key]: value }));
        setMessage("");
      };

      const save = async () => {
        const ops = [];
        for (const field of FIELDS) {
          const raw = draft[field.key];
          if (field.kind === "lines") {
            const lines = text(raw).split("\n").map((line) => line.trim()).filter(Boolean);
            ops.push({ op: "set", path: [field.key], value: lines });
            continue;
          }
          if (field.kind === "number") {
            const trimmed = text(raw).trim();
            if (trimmed === "") continue;
            const parsed = Number(trimmed);
            if (!Number.isFinite(parsed) || parsed <= 0) {
              setMessage("Giá trị " + field.label + " phải là số dương.");
              return;
            }
            ops.push({ op: "set", path: [field.key], value: parsed });
            continue;
          }
          const trimmed = text(raw).trim();
          if (trimmed === "") ops.push({ op: "unset", path: [field.key] });
          else ops.push({ op: "set", path: [field.key], value: trimmed });
        }
        setBusy(true);
        try {
          const ok = await form.mutate(ops);
          setMessage(ok ? "Đã lưu. Lời gọi tiếp theo dùng cấu hình mới." : "Host từ chối thay đổi.");
        } catch (error) {
          setMessage("Lỗi khi lưu: " + String((error && error.message) || error));
        } finally {
          setBusy(false);
        }
      };

      return h("div", { style: styles.wrap },
        FIELDS.map((field) => h("div", { key: field.key, style: styles.row },
          h("label", { style: styles.label, htmlFor: "pfe-" + field.key }, field.label),
          h(field.kind === "lines" ? "textarea" : "input", {
            id: "pfe-" + field.key,
            style: field.kind === "lines"
              ? Object.assign({}, styles.input, styles.textarea)
              : styles.input,
            type: field.kind === "number" ? "number" : "text",
            min: field.kind === "number" ? 1 : undefined,
            placeholder: field.placeholder,
            value: draft[field.key],
            disabled: busy || !initial.writable,
            spellCheck: false,
            onChange: (event) => update(field.key, event.target.value),
          }),
          h("span", { style: styles.hint }, field.hint))),
        h("div", { style: styles.footer },
          h("button", {
            type: "button",
            style: Object.assign({}, styles.button, (busy || !initial.writable)
              ? { opacity: 0.6, cursor: "default" }
              : {}),
            disabled: busy || !initial.writable,
            onClick: save,
          }, busy ? "Đang lưu..." : "Lưu cấu hình"),
          h("span", { style: message.startsWith("Lỗi") ? styles.error : styles.status }, message)),
        h("p", { style: styles.hint },
          "Bundle đăng ký 7 tool: project_flow_explain, project_code_index, project_code_search, ",
          "project_context_pack, project_impact_analysis, project_verify_flow, project_knowledge_refresh."));
    }

    function apply(ctx) {
      ctx.slots.inject("plugins.bundle.config", () => ctx.slots.register(
        { name: "plugins.bundle.config", key: PACKAGE },
        ConfigCard,
      ));
    }

    exports.apply = apply;
    exports.inject = ["slots"];
    return module.exports;
  },
});
