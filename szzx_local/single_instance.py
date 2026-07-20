from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


# This name is deliberately independent of the executable name, install path, and
# application version.  Do not change it between releases: that is what lets a new
# build replace an older build.
INSTANCE_CHANNEL = "com.szzx.localdesk.instance"
_REPLACE_COMMAND = b"REPLACE\n"
_GRACEFUL_EXIT_SECONDS = 3.0


class SingleInstanceController(QObject):
    """Own the app-wide local endpoint and ask an existing owner to exit."""

    replacement_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept_connections)
        self._clients: list[QLocalSocket] = []
        self._buffers: dict[QLocalSocket, bytes] = {}

    def take_over(self, timeout_ms: int = 8000) -> bool:
        """Replace an existing instance and become the endpoint owner."""
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if self._server.listen(INSTANCE_CHANNEL):
                self._replace_legacy_instances()
                return True

            connected, owner_pid = self._request_replacement()
            if connected:
                if owner_pid and owner_pid != os.getpid():
                    self._wait_for_exit(owner_pid, _GRACEFUL_EXIT_SECONDS)
                    if self._process_exists(owner_pid):
                        self._terminate_process(owner_pid)
                        self._wait_for_exit(owner_pid, 2.0)
                        self._force_kill_process(owner_pid)
            else:
                # A crashed Unix process can leave its socket path behind.  Only
                # remove it after proving that nothing is accepting connections.
                QLocalServer.removeServer(INSTANCE_CHANNEL)
            time.sleep(0.08)
        return False

    def close(self) -> None:
        self._server.close()
        for client in self._clients:
            client.abort()
        self._clients.clear()
        self._buffers.clear()

    def _request_replacement(self) -> tuple[bool, int | None]:
        socket = QLocalSocket()
        socket.connectToServer(INSTANCE_CHANNEL)
        if not socket.waitForConnected(250):
            return False, None
        owner_pid = self._windows_pipe_owner_pid(socket)
        socket.write(_REPLACE_COMMAND)
        socket.flush()
        socket.waitForBytesWritten(250)
        if socket.waitForReadyRead(750):
            response = bytes(socket.readAll()).strip()
            if response.startswith(b"PID "):
                try:
                    owner_pid = int(response[4:])
                except ValueError:
                    pass
        socket.disconnectFromServer()
        return True, owner_pid

    def _accept_connections(self) -> None:
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            if client is None:
                continue
            self._clients.append(client)
            self._buffers[client] = b""
            client.readyRead.connect(lambda current=client: self._read_command(current))
            client.disconnected.connect(lambda current=client: self._forget_client(current))
            self._read_command(client)

    def _read_command(self, client: QLocalSocket) -> None:
        received = self._buffers.get(client, b"") + bytes(client.readAll())
        self._buffers[client] = received
        if _REPLACE_COMMAND.strip() not in received:
            return
        client.write(f"PID {os.getpid()}\n".encode("ascii"))
        client.flush()
        # Release the name first, so the new process cannot continue until this
        # instance has accepted the shutdown request.
        self._server.close()
        self.replacement_requested.emit()

    def _forget_client(self, client: QLocalSocket) -> None:
        if client in self._clients:
            self._clients.remove(client)
        self._buffers.pop(client, None)

    @staticmethod
    def _windows_pipe_owner_pid(socket: QLocalSocket) -> int | None:
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            owner_pid = ctypes.c_ulong()
            handle = wintypes.HANDLE(int(socket.socketDescriptor()))
            get_owner = ctypes.WinDLL("kernel32", use_last_error=True).GetNamedPipeServerProcessId
            get_owner.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG))
            get_owner.restype = wintypes.BOOL
            if get_owner(handle, ctypes.byref(owner_pid)):
                return int(owner_pid.value)
        except (AttributeError, OSError, TypeError, ValueError):
            pass
        return None

    @staticmethod
    def _process_exists(pid: int) -> bool:
        if pid <= 0:
            return False
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                synchronize = 0x00100000
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
                kernel32.OpenProcess.restype = wintypes.HANDLE
                kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
                kernel32.WaitForSingleObject.restype = wintypes.DWORD
                kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
                kernel32.CloseHandle.restype = wintypes.BOOL
                handle = kernel32.OpenProcess(synchronize, False, pid)
                if not handle:
                    return False
                wait_result = kernel32.WaitForSingleObject(handle, 0)
                kernel32.CloseHandle(handle)
                return wait_result == 0x00000102  # WAIT_TIMEOUT
            except (AttributeError, OSError):
                return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @classmethod
    def _wait_for_exit(cls, pid: int, timeout_seconds: float) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline and cls._process_exists(pid):
            time.sleep(0.05)

    @staticmethod
    def _terminate_process(pid: int) -> None:
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                process_terminate = 0x0001
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
                kernel32.OpenProcess.restype = wintypes.HANDLE
                kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
                kernel32.TerminateProcess.restype = wintypes.BOOL
                kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
                kernel32.CloseHandle.restype = wintypes.BOOL
                handle = kernel32.OpenProcess(process_terminate, False, pid)
                if handle:
                    kernel32.TerminateProcess(handle, 0)
                    kernel32.CloseHandle(handle)
            except (AttributeError, OSError):
                pass
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return

    @staticmethod
    def _force_kill_process(pid: int) -> None:
        if sys.platform == "win32" or not SingleInstanceController._process_exists(pid):
            return
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    @classmethod
    def _replace_legacy_instances(cls) -> None:
        """Stop packaged builds released before the IPC channel existed."""
        if not getattr(sys, "frozen", False):
            return
        current_pid = os.getpid()
        # PIDs normally increase with launch order.  Restricting this fallback to
        # lower PIDs prevents an older simultaneous launch from killing a newer one.
        for pid in cls._same_executable_pids():
            if 0 < pid < current_pid:
                cls._terminate_process(pid)
                cls._wait_for_exit(pid, 2.0)
                cls._force_kill_process(pid)

    @staticmethod
    def _same_executable_pids() -> list[int]:
        executable_name = Path(sys.executable).name
        if sys.platform == "win32":
            return SingleInstanceController._windows_processes_named(executable_name)
        try:
            result = subprocess.run(
                ["/usr/bin/pgrep", "-x", executable_name],
                capture_output=True,
                check=False,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        return [int(line) for line in result.stdout.splitlines() if line.strip().isdigit()]

    @staticmethod
    def _windows_processes_named(executable_name: str) -> list[int]:
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessEntry32W(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
            kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
            snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
            if not snapshot or int(snapshot) == ctypes.c_void_p(-1).value:
                return []
            kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W))
            kernel32.Process32FirstW.restype = wintypes.BOOL
            kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W))
            kernel32.Process32NextW.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            entry = ProcessEntry32W()
            entry.dwSize = ctypes.sizeof(entry)
            pids: list[int] = []
            found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while found:
                if entry.szExeFile.casefold() == executable_name.casefold():
                    pids.append(int(entry.th32ProcessID))
                found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            kernel32.CloseHandle(snapshot)
            return pids
        except (AttributeError, OSError, TypeError, ValueError):
            return []
