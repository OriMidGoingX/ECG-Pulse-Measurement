# 将下面整个文件替换到你的 main.py
import sys
import csv
import time
import numpy as np
from collections import deque
from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QComboBox, QFileDialog,
    QSpinBox, QDoubleSpinBox, QSizePolicy, QDialog,
    QPlainTextEdit, QFrame
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
import pyqtgraph as pg

from serial_manager import SerialThread
from parser import Parser

from utils import crc16_ccitt  # 如果 utils.py 在同级目录

# default parameters
DEFAULT_SAMPLING_RATE = 120  # samples per second (editable)
DEFAULT_WINDOW_SECONDS = 5  # seconds
MAX_POINTS_LIMIT = 200000  # safety cap

# ----------------- 自定义底部刻度轴（只显示整秒或 1 位小数） -----------------
class TimeAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        strs = []
        for v in values:
            if abs(v - round(v)) < 1e-6:
                strs.append(f"{int(round(v))}")
            else:
                strs.append(f"{v:.1f}")
        return strs
# ----------------------------------------------------------------------


class RawDialog(QDialog):
    """弹窗显示原始串口数据（只做查看/复制）"""
    def __init__(self, parent=None, initial_text=""):
        super().__init__(parent)
        self.setWindowTitle("原始串口数据（最近）")
        self.resize(600, 400)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(initial_text)
        layout = QVBoxLayout()
        layout.addWidget(self.text)
        self.setLayout(layout)

    def set_text(self, txt: str):
        self.text.setPlainText(txt)

    def append_text(self, txt: str):
        current = self.text.toPlainText()
        self.text.setPlainText(current + "\n" + txt)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("心电脉搏测量-Designed by Orange")
        self.resize(1200, 720)

        # serial & parser
        self.serial_thread = SerialThread()
        self.parser = Parser()

        # parameters
        self.sampling_rate = DEFAULT_SAMPLING_RATE
        self.time_window = DEFAULT_WINDOW_SECONDS
        self.adc_bits = 8      # default ADC bits (10-bit -> 0..1023)
        self.vref = 5         # default reference voltage

        # 心率算法参数（可根据实际信号调整）
        self.r_threshold_ratio = 0.45  # R波检测阈值比例（0.5-0.8，无滤波时建议调大）
        self.min_r_interval = 0.45     # 最小R波间隔（秒，避免误检）

        # plotting buffers
        self._recreate_buffers()

        # timestamps queue for sample-rate calc
        self.sample_times = deque()

        # raw text buffer for popup (limited lines)
        self.raw_buffer = deque(maxlen=400)  # store recent raw lines / hex strings

        # CSV writer (None when not writing)
        self.csv_file = None
        self.csv_writer = None

        # vertical pan/zoom state (in volts)
        self.v_offset = 0.0           # vertical offset center shift (V)
        self.v_range_factor = 1.05    # multiplier for Vref to set half-range

        self.raw_dialog = None  # lazily created

        self._setup_ui()
        self._connect_signals()

        self.refresh_ports()

        # timer for UI/plot update (refresh drawing and sample rate)
        self.timer = QTimer()
        self.timer.setInterval(50)  # ms; 可以调大到 80-100 以降低 CPU
        self.timer.timeout.connect(self.on_timer)
        self.timer.start()

        # 初始化 BPM 显示
        self.update_bpm(None)

    def _recreate_buffers(self):
        """(Re)create plot buffers based on current time_window and sampling_rate"""
        pts = int(self.time_window * max(1, self.sampling_rate))
        if pts <= 0:
            pts = 1
        if pts > MAX_POINTS_LIMIT:
            pts = MAX_POINTS_LIMIT
        self.plot_x = deque(maxlen=pts)
        self.plot_y = deque(maxlen=pts)

    def _setup_ui(self):
        # Top controls (一行，整体放大)
        top_h = QHBoxLayout()

        self.port_combo = QComboBox()
        self.refresh_btn = QPushButton("刷新端口")
        self.baud_combo = QComboBox()
        for b in [9600, 19200, 38400, 57600, 115200, 230400, 460800]:
            self.baud_combo.addItem(str(b))
        # 合并的串口开关按钮（toggle）
        self.toggle_btn = QPushButton("打开串口")
        # 其他按钮
        self.clear_btn = QPushButton("清屏")
        self.save_btn = QPushButton("导出CSV")

        # display mode (hex/text)
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItems(["HEX", "TEXT"])

        # time window selection (s)
        self.window_combo = QComboBox()
        for t in range(2, 21):
            self.window_combo.addItem(str(t))
        self.window_combo.setCurrentText(str(DEFAULT_WINDOW_SECONDS))

        # sampling rate
        self.sampling_spin = QSpinBox()
        self.sampling_spin.setRange(1, 20000)
        self.sampling_spin.setValue(DEFAULT_SAMPLING_RATE)

        # ADC bits and Vref
        self.adc_bits_spin = QSpinBox()
        self.adc_bits_spin.setRange(1, 32)
        self.adc_bits_spin.setValue(self.adc_bits)
        self.vref_spin = QDoubleSpinBox()
        self.vref_spin.setRange(0.1, 10.0)
        self.vref_spin.setDecimals(3)
        self.vref_spin.setSingleStep(0.1)
        self.vref_spin.setValue(self.vref)

        # show raw popup button
        self.show_raw_btn = QPushButton("显示原始数据")

        # 把顶部所有控件放在列表里，统一放大样式（最小改动）
        top_widgets = [
            QLabel("串口:"), self.port_combo, self.refresh_btn,
            QLabel("波特率:"), self.baud_combo,
            self.toggle_btn, self.clear_btn, self.save_btn,
            QLabel("显示模式:"), self.display_mode_combo,
            QLabel("窗口(s):"), self.window_combo,
            QLabel("采样(Hz):"), self.sampling_spin,
            QLabel("ADC bits:"), self.adc_bits_spin,
            QLabel("Vref(V):"), self.vref_spin,
            self.show_raw_btn
        ]

        # 设置统一字体与高度（你可以改下面两个数值让控件更大/更小）
        top_font = QFont()
        top_font.setPointSize(12)  # 改这里调整顶部控件字体大小
        top_height = 50            # 改这里调整顶部控件高度（px）

        for w in top_widgets:
            if isinstance(w, QLabel):
                w.setFont(top_font)
            else:
                try:
                    w.setFont(top_font)
                    w.setFixedHeight(top_height)
                except Exception:
                    pass

        # initial toggle button style = 红色 (未打开)
        self.toggle_btn.setStyleSheet("background-color: #E57373; color: white; font-weight: bold;")
        self.toggle_btn.setToolTip("点击打开/关闭串口")

        # assemble top layout
        top_h.addWidget(top_widgets[0])
        top_h.addWidget(self.port_combo)
        top_h.addWidget(self.refresh_btn)
        top_h.addWidget(top_widgets[3])
        top_h.addWidget(self.baud_combo)
        top_h.addWidget(self.toggle_btn)
        top_h.addWidget(self.clear_btn)
        top_h.addWidget(self.save_btn)
        top_h.addStretch()
        top_h.addWidget(top_widgets[8])
        top_h.addWidget(self.display_mode_combo)
        top_h.addWidget(top_widgets[10])
        top_h.addWidget(self.window_combo)
        top_h.addWidget(top_widgets[12])
        top_h.addWidget(self.sampling_spin)
        top_h.addWidget(top_widgets[14])
        top_h.addWidget(self.adc_bits_spin)
        top_h.addWidget(top_widgets[16])
        top_h.addWidget(self.vref_spin)
        top_h.addWidget(self.show_raw_btn)

        # Right: plot area
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')

        bottom_axis = TimeAxis(orientation='bottom')
        self.plot_widget = pg.PlotWidget(title="实时心率/脉搏波形", axisItems={'bottom': bottom_axis})
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Voltage', units='V')
        self.plot_widget.setLabel('bottom', 'Time', units='s')

        # 原始波形曲线（线宽可在这里调）
        self.curve = self.plot_widget.plot([], [], pen=pg.mkPen(color=(200, 20, 20), width=4), antialias=False)
        # R波峰值标记曲线（绿色圆点）
        self.r_peak_curve = self.plot_widget.plot([], [], pen=None, symbol='o', symbolSize=8, symbolBrush='g')
        try:
            self.curve.setDownsampling(auto=True, method='mean')
        except Exception:
            pass

        self.plot_widget.enableAutoRange(False)

        # Controls under plot
        controls_v = QVBoxLayout()
        row1 = QHBoxLayout()
        self.btn_up = QPushButton("↑ 上移")
        self.btn_reset = QPushButton("● 居中")
        self.btn_down = QPushButton("↓ 下移")
        for btn in (self.btn_up, self.btn_reset, self.btn_down):
            btn.setFixedSize(140, 52)
        row1.addStretch()
        row1.addWidget(self.btn_up)
        row1.addSpacing(18)
        row1.addWidget(self.btn_reset)
        row1.addSpacing(18)
        row1.addWidget(self.btn_down)
        row1.addStretch()

        row2 = QHBoxLayout()
        self.btn_range_up = QPushButton("缩小▼")
        self.btn_range_down = QPushButton("放大▲")
        for btn in (self.btn_range_up, self.btn_range_down):
            btn.setFixedSize(140, 48)
        row2.addStretch()
        row2.addWidget(self.btn_range_up)
        row2.addSpacing(22)
        row2.addWidget(self.btn_range_down)
        row2.addStretch()

        controls_v.addLayout(row1)
        controls_v.addLayout(row2)

        # 左侧BPM显示（下面添加峰峰与周期显示）
        self.bpm_frame = QFrame()
        self.bpm_frame.setFixedWidth(300)
        self.bpm_frame.setStyleSheet("background-color: white; border: 1px solid #ddd;")
        bpm_layout = QVBoxLayout()
        bpm_layout.setContentsMargins(8, 12, 8, 12)

        # 顶部小标题（你之前希望加“数据监视”可在这改）
        self.top_title = QLabel("数据监视")
        self.top_title.setAlignment(Qt.AlignCenter)
        ft = QFont()
        ft.setPointSize(11)
        ft.setBold(True)
        self.top_title.setFont(ft)
        bpm_layout.addWidget(self.top_title)

        self.bpm_title = QLabel("心率")
        self.bpm_title.setAlignment(Qt.AlignCenter)
        font_title = QFont()
        font_title.setPointSize(10)
        font_title.setBold(True)
        self.bpm_title.setFont(font_title)
        bpm_layout.addWidget(self.bpm_title)

        self.bpm_label = QLabel("BPM: --")
        self.bpm_label.setAlignment(Qt.AlignCenter)
        font_bpm = QFont()
        font_bpm.setPointSize(26)  # 更大显示，改这里可以调节
        font_bpm.setBold(True)
        self.bpm_label.setFont(font_bpm)
        self.bpm_label.setStyleSheet("color: rgb(200,20,20); background-color: transparent;")
        bpm_layout.addWidget(self.bpm_label)

        # 新增：峰峰值 & 周期 显示
        self.peak_to_peak_label = QLabel("Pk-Pk: -- V")
        self.peak_to_peak_label.setAlignment(Qt.AlignCenter)
        self.peak_to_peak_label.setFont(QFont("", 10))
        bpm_layout.addWidget(self.peak_to_peak_label)

        self.period_label = QLabel("周期: -- s")
        self.period_label.setAlignment(Qt.AlignCenter)
        self.period_label.setFont(QFont("", 10))
        bpm_layout.addWidget(self.period_label)

        bpm_layout.addStretch()
        self.bpm_frame.setLayout(bpm_layout)

        # 主布局
        right_v = QVBoxLayout()
        right_v.addWidget(self.plot_widget, 1)
        right_v.addLayout(controls_v)

        mid_layout = QHBoxLayout()
        mid_layout.addWidget(self.bpm_frame, 0)
        mid_layout.addLayout(right_v, 1)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_h)
        main_layout.addLayout(mid_layout)

        self.status_label = QLabel("状态: 未连接    采样率: 0 sps")
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)

    def resizeEvent(self, event):
        total_h = self.height()
        target = max(200, int(total_h * 2 / 3))
        self.plot_widget.setMinimumHeight(target)
        super().resizeEvent(event)

    def _connect_signals(self):
        self.refresh_btn.clicked.connect(self.refresh_ports)
        # 合并按钮：toggle_btn 点击后根据当前状态 打开/关闭
        self.toggle_btn.clicked.connect(self.on_toggle_port)

        self.clear_btn.clicked.connect(self.clear_display)
        self.save_btn.clicked.connect(self.export_csv)
        self.show_raw_btn.clicked.connect(self.on_show_raw)

        self.window_combo.currentTextChanged.connect(self.on_window_changed)
        self.sampling_spin.valueChanged.connect(self.on_sampling_changed)
        self.adc_bits_spin.valueChanged.connect(self.on_adc_bits_changed)
        self.vref_spin.valueChanged.connect(self.on_vref_changed)

        self.btn_up.clicked.connect(lambda: self._pan_vertical(+1))
        self.btn_reset.clicked.connect(self._reset_pan)
        self.btn_down.clicked.connect(lambda: self._pan_vertical(-1))
        self.btn_range_up.clicked.connect(lambda: self._zoom_range(1.12))
        self.btn_range_down.clicked.connect(lambda: self._zoom_range(1/1.12))

        self.serial_thread.bytes_received.connect(self.on_bytes)
        self.serial_thread.error.connect(self.on_error)
        # 额外绑定打开/关闭信号以更新按钮颜色和状态
        self.serial_thread.opened.connect(self.on_port_opened)
        self.serial_thread.closed.connect(self.on_port_closed)
        # 仍然保持状态文本更新
        self.serial_thread.opened.connect(lambda: self.status_label.setText(f"状态: 已打开 {self.serial_thread.port} @ {self.serial_thread.baud}    采样率: 0 sps"))
        self.serial_thread.closed.connect(lambda: self.status_label.setText("状态: 已关闭    采样率: 0 sps"))

    # ------------------- 串口切换逻辑 -------------------
    def on_toggle_port(self):
        """单个按钮负责打开或关闭串口"""
        try:
            ser = getattr(self.serial_thread, "_ser", None)
            is_open = getattr(ser, "is_open", False)
        except Exception:
            is_open = False

        if is_open:
            # currently open -> close
            try:
                self.serial_thread.close()
            except Exception as e:
                self.status_label.setText("关闭串口失败: " + str(e))
        else:
            # currently closed -> open selected port
            port = self.port_combo.currentText()
            if not port:
                self.status_label.setText("状态: 未选择串口")
                return
            baud = int(self.baud_combo.currentText())
            try:
                self.serial_thread.open(port, baud)
            except Exception as e:
                self.status_label.setText("打开串口失败: " + str(e))

    def on_port_opened(self):
        """串口成功打开后：更新 toggle 按钮样式，禁用顶部选择控件"""
        self.toggle_btn.setText("关闭串口")
        self.toggle_btn.setStyleSheet("background-color: #66BB6A; color: white; font-weight: bold;")
        # 禁用顶部会导致误改参数
        for w in (self.port_combo, self.baud_combo, self.adc_bits_spin, self.sampling_spin):
            try:
                w.setEnabled(False)
            except Exception:
                pass

    def on_port_closed(self):
        """串口关闭后：更新样式，恢复顶部控件可用"""
        self.toggle_btn.setText("打开串口")
        self.toggle_btn.setStyleSheet("background-color: #E57373; color: white; font-weight: bold;")
        for w in (self.port_combo, self.baud_combo, self.adc_bits_spin, self.sampling_spin):
            try:
                w.setEnabled(True)
            except Exception:
                pass

    # ------------------- UI回调函数 -------------------
    def refresh_ports(self):
        ports = SerialThread.list_ports()
        self.port_combo.clear()
        self.port_combo.addItems(ports)

    # NOTE: open_port / close_port 不再公开使用，但保留以防你想单独调用
    def open_port(self):
        port = self.port_combo.currentText()
        if not port:
            self.status_label.setText("状态: 未选择串口")
            return
        baud = int(self.baud_combo.currentText())
        self.serial_thread.open(port, baud)

    def close_port(self):
        self.serial_thread.close()

    def on_error(self, msg):
        self.status_label.setText("错误: " + msg)

    def on_show_raw(self):
        txt = "\n".join(list(self.raw_buffer))
        if self.raw_dialog is None or not self.raw_dialog.isVisible():
            self.raw_dialog = RawDialog(self, initial_text=txt)
            self.raw_dialog.show()
        else:
            self.raw_dialog.set_text(txt)
            self.raw_dialog.raise_()
            self.raw_dialog.activateWindow()

    def on_window_changed(self, text):
        try:
            self.time_window = float(text)
        except:
            self.time_window = DEFAULT_WINDOW_SECONDS
        self._recreate_buffers()

    def on_sampling_changed(self, v):
        self.sampling_rate = int(v)
        self._recreate_buffers()

    def on_adc_bits_changed(self, v):
        self.adc_bits = int(v)

    def on_vref_changed(self, v):
        self.vref = float(v)

    # 绘图缩放/平移
    def _pan_vertical(self, direction: int):
        step = self.vref * 0.06
        self.v_offset += direction * step

    def _reset_pan(self):
        self.v_offset = 0.0

    def _zoom_range(self, factor: float):
        self.v_range_factor *= factor
        if self.v_range_factor < 0.4:
            self.v_range_factor = 0.4
        if self.v_range_factor > 4.0:
            self.v_range_factor = 4.0

    # 数据接收
    def on_bytes(self, b: bytes):
        if not b:
            return

        mode = self.display_mode_combo.currentText()
        if mode == "HEX":
            preview = ' '.join(f'{x:02X}' for x in b)[:200]
        else:
            try:
                txt = b.decode('utf-8', errors='ignore')
            except:
                txt = str(b)
            preview = txt.replace('\r', '').replace('\n', '\\n')[:200]
        self.raw_buffer.append(preview)

        now = time.time()
        n = len(b)

        if self.sampling_rate and self.sampling_rate > 0:
            dt = 1.0 / float(self.sampling_rate)
        else:
            dt = 0.0

        base_offset = (n - 1) * dt
        for i, byte in enumerate(b):
            ts = now - (base_offset - i * dt)
            adc = int(byte)
            self.plot_x.append(ts)
            self.plot_y.append(adc)
            self.sample_times.append(ts)
            if self.csv_writer:
                voltage = self._adc_to_voltage(adc)
                try:
                    self.csv_writer.writerow([f"{ts:.6f}", int(adc), f"{voltage:.6f}"])
                except Exception:
                    pass

    # ------------------- 心率算法核心（无滤波） -------------------
    def detect_r_peaks(self, raw_data, fs):
        r_peak_indices = []
        n = len(raw_data)
        if n < 3:
            return r_peak_indices

        if fs <= 0:
            fs = self.sampling_rate if self.sampling_rate > 0 else 120

        min_interval_points = max(1, int(round(self.min_r_interval * fs)))

        vmin = min(raw_data)
        vmax = max(raw_data)
        vmean = sum(raw_data) / n
        amp = vmax - vmin
        if amp <= 1e-9:
            return r_peak_indices

        thr = vmean + float(self.r_threshold_ratio) * (vmax - vmean)
        min_thr_offset = 0.005 * (self.vref if self.vref else 1.0)
        if thr - vmin < min_thr_offset:
            thr = vmin + min_thr_offset

        last_peak = -min_interval_points * 2
        for i in range(1, n - 1):
            val = raw_data[i]
            if val <= thr:
                continue
            if val > raw_data[i - 1] and val >= raw_data[i + 1]:
                if (i - last_peak) >= min_interval_points:
                    r_peak_indices.append(i)
                    last_peak = i

        return r_peak_indices

    def _estimate_bpm_from_wave(self, voltages, rel_xs):
        fs = self.sampling_rate
        n = len(voltages)
        if fs <= 0 or n < 3:
            return None

        peaks = self.detect_r_peaks(voltages, fs)
        if len(peaks) < 2:
            return None

        peak_times = [rel_xs[i] for i in peaks]
        intervals = [peak_times[i] - peak_times[i - 1] for i in range(1, len(peak_times))]
        if not intervals:
            return None

        avg = sum(intervals) / len(intervals)
        filtered = [it for it in intervals if 0.5 * avg <= it <= 1.5 * avg]
        if not filtered:
            return None

        mean_interval = sum(filtered) / len(filtered)
        if mean_interval <= 0:
            return None

        bpm = 60.0 / mean_interval
        if 30 <= bpm <= 220:
            return int(round(bpm))
        else:
            return None

    # 数据转换与绘图
    def _adc_to_voltage(self, adc_raw: int) -> float:
        max_code = (1 << self.adc_bits) - 1
        if max_code <= 0:
            return 0.0
        return float(adc_raw) / float(max_code) * float(self.vref)

    def on_timer(self):
        # 更新采样率显示
        now = time.time()
        cutoff = now - 1.0
        while self.sample_times and self.sample_times[0] < cutoff:
            self.sample_times.popleft()
        sample_rate = len(self.sample_times) / 1.0

        # 更新状态
        port_info = "未连接"
        try:
            if getattr(self.serial_thread, "_ser", None) and getattr(self.serial_thread._ser, "is_open", False):
                port_info = f"{self.serial_thread.port} @ {self.serial_thread.baud}"
        except:
            port_info = "未连接"
        base_status = f"状态: {'已打开 ' + port_info if port_info != '未连接' else '未连接'}"
        self.status_label.setText(f"{base_status}    采样率: {sample_rate:.1f} sps")

        if not self.plot_x:
            return

        # 提取窗口内数据
        latest_ts = self.plot_x[-1]
        start_ts = latest_ts - self.time_window
        abs_xs = []
        ys = []
        for ts, adc in zip(self.plot_x, self.plot_y):
            if ts >= start_ts:
                abs_xs.append(ts)
                ys.append(self._adc_to_voltage(int(adc)))

        if not abs_xs:
            return

        # 绘制原始波形
        rel_xs = [t - start_ts for t in abs_xs]
        self.curve.setData(rel_xs, ys)

        # 计算峰峰值
        try:
            p2p = max(ys) - min(ys)
            self.peak_to_peak_label.setText(f"Pk-Pk: {p2p:.2f} V")
        except Exception:
            self.peak_to_peak_label.setText("Pk-Pk: -- V")

        # 检测R波并计算心率与周期
        r_peak_bpm = None
        period_text = "--"
        if len(ys) > 0:
            # 估计 BPM
            r_peak_bpm = self._estimate_bpm_from_wave(ys, rel_xs)
            # 得到峰索引并计算平均周期
            r_peak_indices = self.detect_r_peaks(ys, self.sampling_rate)
            if r_peak_indices and len(r_peak_indices) >= 2:
                peak_times = [rel_xs[i] for i in r_peak_indices]
                intervals = [peak_times[i] - peak_times[i - 1] for i in range(1, len(peak_times))]
                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    period_text = f"{avg_interval:.2f} s"
            # 绘制绿点
            if r_peak_indices:
                r_peak_x = [rel_xs[i] for i in r_peak_indices]
                r_peak_y = [ys[i] for i in r_peak_indices]
                self.r_peak_curve.setData(r_peak_x, r_peak_y)
            else:
                self.r_peak_curve.setData([], [])

        # 更新 BPM / 周期 显示
        self.update_bpm(r_peak_bpm)
        self.period_label.setText(f"周期: {period_text}")

        # 固定X轴范围
        try:
            self.plot_widget.setXRange(0, self.time_window, padding=0)
        except Exception:
            pass

        # 固定Y轴范围
        mid = (self.vref / 2.0) + self.v_offset
        half_range = (self.vref / 2.0) * self.v_range_factor
        ymin = mid - half_range
        ymax = mid + half_range
        if ymin < -self.vref * 2:
            ymin = -self.vref * 2
        if ymax > self.vref * 3:
            ymax = self.vref * 3
        self.plot_widget.setYRange(ymin, ymax, padding=0.01)

    # 其他UI功能
    def clear_display(self):
        self.raw_buffer.clear()
        self.plot_x.clear()
        self.plot_y.clear()
        self.sample_times.clear()
        self.curve.setData([], [])
        self.r_peak_curve.setData([], [])
        self.peak_to_peak_label.setText("Pk-Pk: -- V")
        self.period_label.setText("周期: -- s")
        self.status_label.setText("状态: 已清屏    采样率: 0 sps")
        self.update_bpm(None)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存 CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['timestamp', 'adc_raw', 'voltage_V'])
                for ts, adc in zip(self.plot_x, self.plot_y):
                    voltage = self._adc_to_voltage(int(adc))
                    w.writerow([f"{ts:.6f}", int(adc), f"{voltage:.6f}"])
            self.status_label.setText("导出成功: " + path)
        except Exception as e:
            self.status_label.setText("导出失败: " + str(e))

    def closeEvent(self, event):
        self.serial_thread.close()
        try:
            if self.csv_file:
                self.csv_file.close()
        except:
            pass
        super().closeEvent(event)

    def update_bpm(self, bpm: int or None):
        if bpm is None:
            self.bpm_label.setText("BPM: --")
        else:
            # 固定宽度显示，不会“抖动”位置（尽量减少布局变化）
            self.bpm_label.setText(f"BPM: {int(bpm)}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
