"""A small Windows GUI for ClamAV on-demand scans."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from scanner import (
    ACTION_SCAN,
    ACTION_UPDATE,
    CommandResult,
    CommandRunner,
    build_scan_command,
    build_update_command,
    can_start_scan,
    default_quarantine_dir,
    find_program,
    summarize_exit_code,
)

APP_TITLE = "ClamAV Tarama Aracı"
POLL_INTERVAL_MS = 100


class ClamAVScanApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("700x600")
        self.root.minsize(620, 540)
        self.selected_path: Path | None = None
        self.clamscan = tk.StringVar(value=find_program("clamscan.exe"))
        self.freshclam = tk.StringVar(value=find_program("freshclam.exe"))
        self.quarantine_enabled = tk.BooleanVar(value=False)
        self.quarantine_dir = tk.StringVar(value=str(default_quarantine_dir()))
        self.status = tk.StringVar(value="Başlamak için ClamAV kurulumunu seçin veya bulunan yolu kontrol edin.")
        self._busy = False
        self._runner = CommandRunner()
        self._events: queue.Queue[tuple] = queue.Queue()
        self._had_output = False
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(POLL_INTERVAL_MS, self._poll_events)

    # ------------------------------------------------------------------ arayüz

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="ClamAV Tarama", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Bu arayüz, bilgisayarınızda kurulu ClamAV komut satırı motorunu kullanır.",
            wraplength=640,
        ).pack(anchor="w", pady=(6, 16))

        self._program_picker(outer, "clamscan.exe", self.clamscan)
        self._program_picker(outer, "freshclam.exe (imza güncelleme)", self.freshclam)

        select_row = ttk.Frame(outer)
        select_row.pack(anchor="w", pady=(12, 6))
        ttk.Button(select_row, text="Dosya seç", command=self._choose_file).pack(side="left", padx=(0, 8))
        ttk.Button(select_row, text="Klasör seç", command=self._choose_folder).pack(side="left")
        self.path_text = tk.StringVar(value="Taranacak konum seçilmedi")
        ttk.Label(outer, textvariable=self.path_text, wraplength=640).pack(anchor="w", pady=(0, 10))

        quarantine_row = ttk.Frame(outer)
        quarantine_row.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(
            quarantine_row,
            text="Tespit edilen dosyaları karantina klasörüne taşı",
            variable=self.quarantine_enabled,
        ).pack(side="left")
        ttk.Entry(quarantine_row, textvariable=self.quarantine_dir).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(quarantine_row, text="Gözat", command=self._choose_quarantine_dir).pack(side="left")

        actions = ttk.Frame(outer)
        actions.pack(anchor="w")
        self.update_button = ttk.Button(actions, text="İmzaları güncelle", command=self._start_update)
        self.update_button.pack(side="left", padx=(0, 8))
        self.scan_button = ttk.Button(actions, text="Taramayı başlat", command=self._start_scan, state="disabled")
        self.scan_button.pack(side="left", padx=(0, 8))
        self.cancel_button = ttk.Button(actions, text="İptal", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left")

        ttk.Label(outer, textvariable=self.status, wraplength=640).pack(anchor="w", pady=(14, 6))
        result_frame = ttk.LabelFrame(outer, text="Tarama çıktısı", padding=6)
        result_frame.pack(fill="both", expand=True, pady=(4, 8))
        scrollbar = ttk.Scrollbar(result_frame, orient="vertical")
        self.output = tk.Text(
            result_frame,
            height=8,
            wrap="word",
            state="disabled",
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=self.output.yview)
        scrollbar.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)
        ttk.Label(
            outer,
            text="Sınırlama: ClamAV tüm zararlıları tespit etmeyi garanti etmez. İmzalar güncel olmalıdır; bu araç gerçek zamanlı koruma sağlamaz.",
            wraplength=640,
            foreground="#555555",
        ).pack(anchor="w")

    def _program_picker(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=31).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Gözat", command=lambda: self._choose_program(variable)).pack(side="left")

    # ------------------------------------------------------------ seçim işlemleri

    def _choose_program(self, variable: tk.StringVar) -> None:
        chosen = filedialog.askopenfilename(
            title="ClamAV programını seçin",
            filetypes=[("Windows uygulaması", "*.exe"), ("Tüm dosyalar", "*.*")],
        )
        if chosen:
            variable.set(chosen)

    def _choose_file(self) -> None:
        chosen = filedialog.askopenfilename(title="Taranacak dosyayı seçin")
        if chosen:
            self._set_path(Path(chosen))

    def _choose_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Taranacak klasörü seçin", mustexist=True)
        if chosen:
            self._set_path(Path(chosen))

    def _choose_quarantine_dir(self) -> None:
        chosen = filedialog.askdirectory(title="Karantina klasörünü seçin")
        if chosen:
            self.quarantine_dir.set(chosen)

    def _set_path(self, path: Path) -> None:
        self.selected_path = path
        self.path_text.set(str(path))
        self._refresh_buttons()

    # ----------------------------------------------------------- düğme ve çıktı

    def _refresh_buttons(self) -> None:
        self.update_button.configure(state="disabled" if self._busy else "normal")
        scan_allowed = can_start_scan(self.selected_path is not None, self._busy)
        self.scan_button.configure(state="normal" if scan_allowed else "disabled")
        self.cancel_button.configure(state="normal" if self._busy else "disabled")

    def _busy_state(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_buttons()

    def _clear_output(self) -> None:
        self._had_output = False
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")

    def _append_output(self, text: str) -> None:
        if not text:
            return
        self._had_output = True
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _set_output(self, value: str) -> None:
        self._clear_output()
        self._append_output(value)

    # ------------------------------------------------------------- komut akışı

    def _start_update(self) -> None:
        if self._busy:
            return
        executable = Path(self.freshclam.get().strip())
        if not executable.is_file():
            messagebox.showerror(APP_TITLE, "freshclam.exe bulunamadı. ClamAV kurulum klasöründen seçin.")
            return
        self._begin(ACTION_UPDATE, build_update_command(executable), "ClamAV imza veritabanları güncelleniyor...")

    def _start_scan(self) -> None:
        if self._busy:
            return
        if self.selected_path is None or not self.selected_path.exists():
            messagebox.showerror(APP_TITLE, "Lütfen mevcut bir dosya veya klasör seçin.")
            return
        executable = Path(self.clamscan.get().strip())
        if not executable.is_file():
            messagebox.showerror(APP_TITLE, "clamscan.exe bulunamadı. ClamAV kurulum klasöründen seçin.")
            return

        quarantine: Path | None = None
        if self.quarantine_enabled.get():
            raw = self.quarantine_dir.get().strip()
            if not raw:
                messagebox.showerror(APP_TITLE, "Karantina klasörü boş. Bir klasör seçin veya karantinayı kapatın.")
                return
            quarantine = Path(raw)
            try:
                quarantine.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror(APP_TITLE, f"Karantina klasörü oluşturulamadı:\n{exc}")
                return

        args = build_scan_command(executable, self.selected_path, quarantine)
        self._begin(ACTION_SCAN, args, "Tarama çalışıyor. Büyük klasörler uzun sürebilir...")

    def _begin(self, action: str, args: list[str], message: str) -> None:
        self._clear_output()
        self._busy_state(True)
        self.status.set(message)
        threading.Thread(target=self._worker, args=(action, args), daemon=True).start()

    def _worker(self, action: str, args: list[str]) -> None:
        """Ayrı thread'de çalışır; arayüze yalnızca kuyruk üzerinden bilgi verir."""
        try:
            result = self._runner.run(args, lambda line: self._events.put(("line", line)))
        except OSError as exc:
            self._events.put(("error", str(exc)))
            return
        self._events.put(("done", action, result))

    def _poll_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                kind = event[0]
                if kind == "line":
                    self._append_output(event[1])
                elif kind == "done":
                    self._command_finished(event[1], event[2])
                elif kind == "error":
                    self._command_error(event[1])
        except queue.Empty:
            pass
        self.root.after(POLL_INTERVAL_MS, self._poll_events)

    def _cancel(self) -> None:
        if self._busy:
            self.cancel_button.configure(state="disabled")
            self.status.set("İptal ediliyor...")
            self._runner.cancel()

    def _command_finished(self, action: str, result: CommandResult) -> None:
        self._busy_state(False)
        if not self._had_output:
            self._append_output("Komut tamamlandı; ek çıktı yok.")
        self.status.set(summarize_exit_code(action, result.returncode, result.cancelled))

    def _command_error(self, detail: str) -> None:
        self._busy_state(False)
        self.status.set("ClamAV komutu çalıştırılamadı.")
        self._set_output(detail)

    def _on_close(self) -> None:
        if self._busy:
            if not messagebox.askyesno(APP_TITLE, "Bir işlem sürüyor. İptal edip çıkmak istiyor musunuz?"):
                return
            self._runner.cancel()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ClamAVScanApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
