# serial_manager.py
# 这里放串口管理代码
# serial_manager.py
# 串口读线程（QThread 版本），向主线程发射接收到的原始 bytes

from PyQt5.QtCore import QThread, pyqtSignal
import serial
import serial.tools.list_ports
import time

class SerialThread(QThread):
    bytes_received = pyqtSignal(bytes)
    error = pyqtSignal(str)
    opened = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ser = None
        self._running = False
        self.port = None
        self.baud = 115200
        self.read_interval = 0.02  # 20ms

    @staticmethod
    def list_ports():
        """Return list of available port names"""
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]

    def open(self, port: str, baud: int = 115200):
        if self._ser and self._ser.is_open:
            self.close()
        try:
            self._ser = serial.Serial(port, baudrate=baud, timeout=0.1)
            self.port = port
            self.baud = baud
            self._running = True
            if not self.isRunning():
                self.start()
            self.opened.emit()
        except Exception as e:
            self.error.emit(str(e))

    def close(self):
        self._running = False
        try:
            if self._ser and self._ser.is_open:
                try:
                    self._ser.flush()
                except:
                    pass
                self._ser.close()
        except Exception as e:
            self.error.emit(str(e))
        self.closed.emit()

    def run(self):
        # thread main loop: read bytes and emit
        try:
            while self._running:
                try:
                    if self._ser and self._ser.is_open:
                        n = self._ser.in_waiting
                        if n:
                            data = self._ser.read(n)
                            if data:
                                self.bytes_received.emit(data)
                        else:
                            time.sleep(self.read_interval)
                    else:
                        time.sleep(0.1)
                except Exception as e:
                    self.error.emit(str(e))
                    time.sleep(0.5)
        finally:
            # ensure closed
            try:
                if self._ser and self._ser.is_open:
                    self._ser.close()
            except:
                pass
