window.__ModuleLoader__.load({
  id: "dsh-project-flow-explainer",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    const React = require("react");
    const h = React.createElement;

    const PACKAGE = "dsh-project-flow-explainer";
    const ROW_ID = "project-flow-explainer";
    const TOOLS = [
      "project_flow_explain", "project_code_index", "project_code_search",
      "project_context_pack", "project_impact_analysis", "project_verify_flow",
      "project_knowledge_refresh",
    ];

    const FIELDS = [
      {
        key: "allowedRoots", kind: "lines", label: "Thư mục được đọc",
        hint: "Mỗi dòng một đường dẫn tuyệt đối. Để trống nghĩa là từ chối mọi repository.",
      },
      {
        key: "pythonPath", kind: "text", label: "Interpreter Python",
        hint: "Lệnh hoặc đường dẫn tuyệt đối, ví dụ python3.", placeholder: "python3",
      },
      {
        key: "coreRoot", kind: "text", label: "Thư mục core",
        hint: "Bỏ trống để tự dò vendor/core trong gói đã cài.", placeholder: "(tự dò)",
      },
      {
        key: "timeoutMs", kind: "number", label: "Timeout mỗi lần gọi (ms)",
        hint: "Ngân sách thời gian cho một lần chạy core.", placeholder: "180000",
      },
      {
        key: "maxOutputBytes", kind: "number", label: "Giới hạn output (byte)",
        hint: "Cắt stdout và stderr vượt ngưỡng này.", placeholder: "1048576",
      },
    ];

    const css = {
      page: { display: "flex", flexDirection: "column", gap: 18, width: "100%", maxWidth: 720 },
      section: { display: "flex", flexDirection: "column", gap: 10 },
      sectionHead: { display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 },
      h2: { margin: 0, fontSize: 14, fontWeight: 600, color: "var(--dsw-alias-label-primary)" },
      meta: { fontSize: 12, color: "var(--dsw-alias-label-secondary)" },
      row: { display: "flex", flexDirection: "column", gap: 4 },
      label: { fontSize: 13, fontWeight: 600, color: "var(--dsw-alias-label-primary)" },
      hint: { fontSize: 12, color: "var(--dsw-alias-label-secondary)", lineHeight: 1.5 },
      input: {
        boxSizing: "border-box", width: "100%", padding: "6px 8px",
        borderRadius: "var(--dsw-radius-md, 8px)",
        border: "0.5px solid var(--dsw-alias-border-l1, #d0d0d0)",
        background: "var(--dsw-alias-card-fill, transparent)",
        color: "var(--dsw-alias-label-primary)", font: "inherit", fontSize: 13,
      },
      textarea: { minHeight: 96, resize: "vertical", fontFamily: "inherit" },
      grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 },
      error: { fontSize: 12, color: "var(--dsw-alias-label-error, #c0392b)" },
      actions: { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" },
      button: {
        padding: "6px 14px", borderRadius: "var(--dsw-radius-md, 8px)",
        border: "0.5px solid var(--dsw-alias-border-l1, #d0d0d0)",
        background: "var(--dsw-alias-card-fill-hover, #f2f2f2)",
        color: "var(--dsw-alias-label-primary)", font: "inherit", fontSize: 13, cursor: "pointer",
      },
      callout: {
        padding: "8px 10px", borderRadius: "var(--dsw-radius-md, 8px)",
        border: "0.5px solid var(--dsw-alias-border-l1, #d0d0d0)",
        background: "var(--dsw-alias-card-fill, transparent)",
        fontSize: 12, lineHeight: 1.6, color: "var(--dsw-alias-label-secondary)",
      },
      list: { display: "flex", flexWrap: "wrap", gap: 6 },
      chip: {
        padding: "2px 8px", borderRadius: 999,
        border: "0.5px solid var(--dsw-alias-border-l1, #d0d0d0)",
        fontSize: 12, color: "var(--dsw-alias-label-secondary)",
      },
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
      return {
        next,
        writable: state.writable !== false,
        status: state.status || "loading",
        revision: state.revision,
      };
    }

    /** @returns {{ops: object[], errors: Record<string, string>}} */
    function validate(draft) {
      const errors = {};
      const ops = [];
      for (const field of FIELDS) {
        const raw = draft[field.key];
        if (field.kind === "lines") {
          const lines = text(raw).split("\n").map((line) => line.trim()).filter(Boolean);
          const bad = lines.filter((line) => line.charAt(0) !== "/");
          if (bad.length > 0) errors[field.key] = "Phải là đường dẫn tuyệt đối: " + bad.join(", ");
          else if (lines.includes("/")) errors[field.key] = "Root \"/\" quá rộng, hãy chọn thư mục cụ thể.";
          if (!errors[field.key]) ops.push({ op: "set", path: [field.key], value: lines });
          continue;
        }
        if (field.kind === "number") {
          const trimmed = text(raw).trim();
          if (trimmed === "") continue;
          const parsed = Number(trimmed);
          if (!Number.isInteger(parsed) || parsed <= 0) {
            errors[field.key] = "Phải là số nguyên dương.";
            continue;
          }
          ops.push({ op: "set", path: [field.key], value: parsed });
          continue;
        }
        const trimmed = text(raw).trim();
        if (field.key === "pythonPath" && trimmed === "") {
          errors[field.key] = "Không được để trống.";
          continue;
        }
        if (trimmed === "") ops.push({ op: "unset", path: [field.key] });
        else ops.push({ op: "set", path: [field.key], value: trimmed });
      }
      return { ops, errors };
    }

    function SettingsPage(props) {
      const form = props.form;
      const initial = readForm(form);
      const [draft, setDraft] = React.useState(initial.next);
      const [errors, setErrors] = React.useState({});
      const [note, setNote] = React.useState("");
      const [busy, setBusy] = React.useState(false);
      const [savedAt, setSavedAt] = React.useState("");

      React.useEffect(() => {
        setDraft(readForm(form).next);
      }, [form, form && form.state && form.state.revision]);

      if (props.view === "summary") {
        const roots = text(initial.next.allowedRoots).split("\n").filter(Boolean);
        return h("span", { style: css.meta }, roots.length === 0
          ? "Chưa cấu hình thư mục nào, mọi lời gọi sẽ bị từ chối."
          : roots.length + " thư mục: " + roots.join(", "));
      }

      if (!form) {
        return h("div", { style: css.page },
          h("div", { style: css.callout },
            "Trang này không nhận được form cấu hình. Mở ",
            h("strong", null, "Configure"), " ở dòng ", h("code", null, ROW_ID),
            " bên dưới để sửa cấu hình, hoặc dùng patch layer ",
            h("code", null, "- id: " + ROW_ID), " (xem dsh-plugin/README.md)."));
      }

      const update = (key, value) => {
        setDraft((current) => Object.assign({}, current, { [key]: value }));
        setErrors((current) => Object.assign({}, current, { [key]: "" }));
        setNote("");
      };

      const save = async () => {
        const checked = validate(draft);
        if (Object.keys(checked.errors).length > 0) {
          setErrors(checked.errors);
          setNote("Chưa lưu: còn trường sai.");
          return;
        }
        setBusy(true);
        setNote("");
        try {
          const ok = await form.mutate(checked.ops);
          setNote(ok ? "Đã lưu." : "Host từ chối thay đổi.");
          if (ok) setSavedAt(new Date().toLocaleTimeString());
        } catch (error) {
          setNote("Lỗi khi lưu: " + String((error && error.message) || error));
        } finally {
          setBusy(false);
        }
      };

      const restore = async () => {
        setBusy(true);
        setNote("");
        try {
          const ok = await form.mutate(FIELDS.map((field) => ({ op: "unset", path: [field.key] })));
          setNote(ok ? "Đã khôi phục mặc định của schema." : "Host từ chối thay đổi.");
          if (ok) setDraft(readForm(form).next);
        } catch (error) {
          setNote("Lỗi khi khôi phục: " + String((error && error.message) || error));
        } finally {
          setBusy(false);
        }
      };

      const rootsCount = text(draft.allowedRoots).split("\n").map((line) => line.trim())
        .filter(Boolean).length;
      const disabled = busy || !initial.writable;

      const field = (item) => h("div", { key: item.key, style: css.row },
        h("label", { style: css.label, htmlFor: "pfe-" + item.key }, item.label),
        h(item.kind === "lines" ? "textarea" : "input", {
          id: "pfe-" + item.key,
          style: item.kind === "lines" ? Object.assign({}, css.input, css.textarea) : css.input,
          type: item.kind === "number" ? "number" : "text",
          min: item.kind === "number" ? 1 : undefined,
          placeholder: item.placeholder,
          value: draft[item.key],
          disabled,
          spellCheck: false,
          onChange: (event) => update(item.key, event.target.value),
        }),
        errors[item.key]
          ? h("span", { style: css.error }, errors[item.key])
          : h("span", { style: css.hint }, item.hint));

      return h("div", { style: css.page },
        h("div", { style: css.section },
          h("div", { style: css.sectionHead },
            h("span", { style: css.meta }, rootsCount + " root đang được đọc")),
          field(FIELDS[0])),
        h("div", { style: css.section },
          h("div", { style: css.sectionHead }, h("h2", { style: css.h2 }, "Runtime")),
          h("div", { style: css.grid }, FIELDS.slice(1).map(field))),
        h("div", { style: css.actions },
          h("button", {
            type: "button", disabled,
            style: Object.assign({}, css.button, disabled ? { opacity: 0.6, cursor: "default" } : {}),
            onClick: save,
          }, busy ? "Đang lưu..." : "Lưu cấu hình"),
          h("button", {
            type: "button", disabled,
            style: Object.assign({}, css.button, disabled ? { opacity: 0.6, cursor: "default" } : {}),
            onClick: restore,
          }, "Khôi phục mặc định"),
          h("span", { style: note.startsWith("Lỗi") || note.startsWith("Chưa lưu") ? css.error : css.meta },
            note || (savedAt ? "Lưu lúc " + savedAt : ""))),
        h("div", { style: css.callout },
          "Deny-by-default: ", h("code", null, "allowedRoots"), " rỗng thì mọi lời gọi trả ",
          h("code", null, "allowed_roots_unconfigured"), ". Đường dẫn được so sánh sau ",
          h("code", null, "realpath"), "; symlink trỏ ra ngoài bị loại. File chứa secret ",
          "không vào index, và tool không trả source thô."),
        h("div", { style: css.section },
          h("div", { style: css.sectionHead },
            h("h2", { style: css.h2 }, "Tool đã đăng ký"),
            h("span", { style: css.meta }, TOOLS.length + " tool")),
          h("div", { style: css.list }, TOOLS.map((tool) => h("code", { key: tool, style: css.chip }, tool)))),
        h("div", { style: css.meta },
          "Gói ", h("code", null, PACKAGE), " · row ", h("code", null, ROW_ID),
          initial.writable ? "" : " · Host đang chặn ghi cấu hình"));
    }

    function apply(ctx) {
      const options = { name: "plugins.bundle.config", key: PACKAGE };
      ctx.slots.inject("plugins.bundle.config", () => ctx.slots.register(options, SettingsPage));
      ctx.slots.inject("plugins.row.config", () => ctx.slots.register(
        { name: "plugins.row.config", key: PACKAGE + "#" + ROW_ID }, SettingsPage));
    }

    exports.apply = apply;
    exports.inject = ["slots"];
    return module.exports;
  },
});