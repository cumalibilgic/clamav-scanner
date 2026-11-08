"""ClamAV komutlarını çalıştıran, arayüzden bağımsız yardımcılar.

Bu modül Tkinter'a bağlı değildir; böylece testlerde Tkinter olmadan kullanılabilir.
"""

from __future__ import annotations

import locale
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

ACTION_UPDATE = "update"
ACTION_SCAN = "scan"


def find_program(name: str, env: Optional[Mapping[str, str]] = None) -> str:
    """ClamAV programını PATH ve standart kurulum klasörlerinde arar.

    Çalışma klasörü ve göreli PATH girdileri bilerek atlanır; böylece uygulama
    güvenilmeyen bir klasörden çalıştırıldığında oradaki bir dosya seçilmez.
    """
    env = os.environ if env is None else env

    for entry in env.get("PATH", "").split(os.pathsep):
        entry = entry.strip().strip('"')
        if not entry:
            continue
        directory = Path(entry)
        if not directory.is_absolute():
            continue
        candidate = directory / name
        if candidate.is_file():
            return str(candidate)

    for variable, default in (
        ("ProgramFiles", r"C:\Program Files"),
        ("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ):
        candidate = Path(env.get(variable, default)) / "ClamAV" / name
        if candidate.is_file():
            return str(candidate)
    return ""


def default_quarantine_dir() -> Path:
    """Karantina klasörü için varsayılan konum (kullanıcının ev klasörü altında)."""
    return Path.home() / "ClamAV-Karantina"


def build_update_command(executable: str | Path) -> list[str]:
    return [str(executable)]


def build_scan_command(
    executable: str | Path,
    target: str | Path,
    quarantine_dir: str | Path | None = None,
) -> list[str]:
    """clamscan komut satırını oluşturur. Karantina yalnızca istenirse eklenir."""
    args = [str(executable), "--recursive", "--infected", "--no-summary"]
    if quarantine_dir:
        args.append(f"--move={quarantine_dir}")
    args.append(str(target))
    return args


def can_start_scan(has_path: bool, busy: bool) -> bool:
    """Tarama düğmesi yalnızca konum seçiliyken ve başka işlem yokken etkin olmalıdır."""
    return has_path and not busy


def summarize_exit_code(action: str, code: int, cancelled: bool = False) -> str:
    """ClamAV çıkış kodunu kullanıcıya gösterilecek mesaja çevirir."""
    if cancelled:
        if action == ACTION_UPDATE:
            return "İmza güncelleme iptal edildi."
        return "Tarama iptal edildi. Çıktı yalnızca iptal edilene kadarki sonuçları içerir."
    if action == ACTION_UPDATE:
        if code == 0:
            return "İmza güncelleme tamamlandı."
        return f"İmza güncelleme başarısız oldu (kod {code})."
    if code == 0:
        return "ClamAV taramasında tespit edilen tehdit olmadı."
    if code == 1:
        return "ClamAV en az bir tehdit tespit etti. Ayrıntılar yukarıdaki çıktıda."
    return f"Tarama yapılamadı veya hata oluştu (kod {code}). Çıktıda hata ayrıntısı olabilir."


def decode_output(raw: bytes) -> str:
    """Komut çıktısını çözer: önce UTF-8, olmazsa sistemin kodlaması, son çare değiştirerek."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    fallback = locale.getpreferredencoding(False) or "utf-8"
    try:
        return raw.decode(fallback)
    except (UnicodeDecodeError, LookupError):
        return raw.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    cancelled: bool


class CommandRunner:
    """Bir komutu çalıştırır, çıktısını satır satır iletir ve iptal edilebilir."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._cancelled = False

    def run(self, args: Sequence[str], on_line: Callable[[str], None]) -> CommandResult:
        """Komutu bitene kadar çalıştırır. Başlatılamazsa OSError fırlatır.

        İptal bayrağı çalıştırmanın sonunda sıfırlanır; böylece komut başlamadan
        hemen önce gelen bir iptal de kaybolmaz.
        """
        try:
            process = subprocess.Popen(
                list(args),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            with self._lock:
                self._cancelled = False
            raise
        with self._lock:
            self._process = process
            if self._cancelled:
                self._terminate(process)
        try:
            assert process.stdout is not None
            for raw in process.stdout:
                on_line(decode_output(raw))
            returncode = process.wait()
        finally:
            if process.stdout is not None:
                process.stdout.close()
            with self._lock:
                self._process = None
                cancelled = self._cancelled
                self._cancelled = False
        return CommandResult(returncode=returncode, cancelled=cancelled)

    def cancel(self) -> None:
        """Çalışan komutu durdurur. Süreç başlatılırken gelen iptal de yakalanır."""
        with self._lock:
            self._cancelled = True
            if self._process is not None:
                self._terminate(self._process)

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
