"""Fixture: desktop UI (tkinter) — entry point là binding, không phải tên hàm."""
import tkinter as tk


class MainWindow(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.export_button = tk.Button(self, text="Xuất Excel", command=self.on_update)
        self.export_button.pack()
        self.entry = tk.Entry(self)
        self.entry.bind("<Return>", self.on_submit)
        self.after(500, self.poll_status)

    def on_update(self):
        data = load_rows()
        return write_excel(data)

    def on_submit(self, event=None):
        return self.on_update()

    def poll_status(self):
        return "idle"


def load_rows():
    return []


def write_excel(rows):
    return {"rows": len(rows)}
