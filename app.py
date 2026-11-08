"""A small Windows GUI for ClamAV on-demand scans."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "ClamAV Tarama Aracı"


class ClamAVScanApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("700x520")
        self.root.minsize(620, 450)
        self.selected_path: Path | None = None
        self.clamscan = tk.StringVar(value=self._find_program("clamscan.exe") or "")
        self.freshclam = tk.StringVar(value=self._find_program("freshclam.exe") or "")
        self.status = tk.StringVar(value="Başlamak için ClamAV kurulumunu seçin veya bulunan yolu kontrol edin.")
        self._busy = False
        self._build_ui()

    @staticmethod
    def _find_program(name: str) -> str:
        found = shutil.which(name)
        if found:
            return found
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ClamAV" / name,
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "ClamAV" / name,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return ""

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

        actions = ttk.Frame(outer)
        actions.pack(anchor="w")
        self.update_button = ttk.Button(actions, text="İmzaları güncelle", command=self._start_update)
        self.update_button.pack(side="left", padx=(0, 8))
        self.scan_button = ttk.Button(actions, text="Taramayı başlat", command=self._start_scan, state="disabled")
        self.scan_button.pack(side="left")

        ttk.Label(outer, textvariable=self.status, wraplength=640).pack(anchor="w", pady=(14, 6))
        result_frame = ttk.LabelFrame(outer, text="Tarama çıktısı", padding=6)
        result_frame.pack(fill="both", expand=True, pady=(4, 8))
        self.output = tk.Text(result_frame, height=8, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True)
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

    def _set_path(self, path: Path) -> None:
        self.selected_path = path
        self.path_text.set(str(path))
        self.scan_button.configure(state="normal")

    def _set_output(self, value: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", value or "Komut tamamlandı; ek çıktı yok.")
        self.output.configure(state="disabled")

    def _busy_state(self, busy: bool) -> None:
        self._busy = busy
        self.update_button.configure(state="disabled" if busy else "normal")
        can_scan = self.selected_path is not None and not busy
        self.scan_button.configure(state="normal" if can_scan else "disabled")

    def _start_update(self) -> None:
        executable = Path(self.freshclam.get().strip())
        if not executable.is_file():
            messagebox.showerror(APP_TITLE, "freshclam.exe bulunamadı. ClamAV kurulum klasöründen seçin.")
            return
        self._busy_state(True)
        self.status.set("ClamAV imza veritabanları güncelleniyor...")
        threading.Thread(target=self._run_command, args=("update", [str(executable)]), daemon=True).start()

    def _start_scan(self) -> None:
        if self.selected_path is None or not self.selected_path.exists():
            messagebox.showerror(APP_TITLE, "Lütfen mevcut bir dosya veya klasör seçin.")
            return
        executable = Path(self.clamscan.get().strip())
        if not executable.is_file():
            messagebox.showerror(APP_TITLE, "clamscan.exe bulunamadı. ClamAV kurulum klasöründen seçin.")
            return
        self._busy_state(True)
        self.status.set("Tarama çalışıyor. Büyük klasörler uzun sürebilir...")
        args = [str(executable), "--recursive", "--infected", "--no-summary", str(self.selected_path)]
        threading.Thread(target=self._run_command, args=("scan", args), daemon=True).start()

    def _run_command(self, action: str, args: list[str]) -> None:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            self.root.after(0, lambda: self._command_finished(action, result.returncode, result.stdout, result.stderr))
        except OSError as exc:
            detail = str(exc)
            self.root.after(0, lambda: self._command_error(detail))

    def _command_finished(self, action: str, code: int, stdout: str, stderr: str) -> None:
        self._busy_state(False)
        output = "\n".join(part.strip() for part in (stdout, stderr) if part.strip())
        self._set_output(output)
        if action == "update":
            self.status.set("İmza güncelleme tamamlandı." if code == 0 else f"İmza güncelleme başarısız oldu (kod {code}).")
        elif code == 0:
            self.status.set("ClamAV taramasında tespit edilen tehdit olmadı.")
        elif code == 1:
            self.status.set("ClamAV en az bir tehdit tespit etti. Ayrıntılar yukarıdaki çıktıda.")
        else:
            self.status.set(f"Tarama yapılamadı veya hata oluştu (kod {code}). Çıktıda hata ayrıntısı olabilir.")

    def _command_error(self, detail: str) -> None:
        self._busy_state(False)
        self.status.set("ClamAV komutu çalıştırılamadı.")
        self._set_output(detail)


def main() -> None:
    root = tk.Tk()
    ClamAVScanApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
