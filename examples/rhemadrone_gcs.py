"""
RhemaDrone GCS v2 — Tactical Ground Control Station
=====================================================
重新設計重點：
  1. 顯性飛行狀態機 (IDLE/ARMED/TAKEOFF/HOVER/LAND/EMERGENCY)，按鈕依狀態互斥啟停
  2. 資料新鮮度（staleness）偵測：telemetry 逾時未更新會顯示 LINK LOST
  3. Multi-ranger 改為自繪雷達環（QPainter），距離用顏色與長度雙重編碼
  4. FPV 影像疊加 HUD（十字準星、角落框、電量/模式浮水印）
  5. Kill 鍵二次確認；PID 滑桿改為「預覽 → 確認套用」而非即時寫入
  6. Console log 依嚴重度上色（INFO / WARN / CRIT）

⚠️ 目前 telemetry / video 仍是模擬資料。實接 cflib 時：
   - 把 SimTelemetrySource 換成真正的 cflib LogConfig callback
   - 把 VideoThread 的 cv2.VideoCapture(0) 換成 5.8G UVC 接收器的裝置索引
   - PID 套用按鈕呼叫 cf.param.set_value(...)（已標註 TODO 位置）
"""

import sys
import time
import random
import cv2
import numpy as np
from enum import Enum, auto

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QPointF
from PyQt6.QtGui import QImage, QPixmap, QFont, QPainter, QPen, QColor, QBrush, QPolygonF
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                              QHBoxLayout, QLabel, QPushButton, QSlider, QTextEdit,
                              QGridLayout, QFrame, QSizePolicy)
import pyqtgraph as pg

ACCENT = "#00FFCC"
WARN = "#FFB300"
CRIT = "#FF3B3B"
BG_DEEP = "#12121C"
BG_PANEL = "#1B1B2A"
BORDER = "#33334A"
TEXT_MUTED = "#7C84A8"


# ---------------------------------------------------------------------------
# 飛行狀態機
# ---------------------------------------------------------------------------
class FlightState(Enum):
    IDLE = auto()
    ARMED = auto()
    TAKEOFF = auto()
    HOVER = auto()
    LANDING = auto()
    EMERGENCY = auto()


STATE_LABEL = {
    FlightState.IDLE: ("IDLE", TEXT_MUTED),
    FlightState.ARMED: ("ARMED", WARN),
    FlightState.TAKEOFF: ("TAKEOFF", ACCENT),
    FlightState.HOVER: ("HOVER", ACCENT),
    FlightState.LANDING: ("LANDING", WARN),
    FlightState.EMERGENCY: ("EMERGENCY STOP", CRIT),
}


# ---------------------------------------------------------------------------
# FPV 視訊執行緒
# ---------------------------------------------------------------------------
class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)

    def run(self):
        # TODO: 換成 5.8G UVC 接收器的裝置索引
        cap = cv2.VideoCapture(0)
        while True:
            ret, frame = cap.read()
            if ret:
                self.change_pixmap_signal.emit(frame)
            else:
                fake = np.random.randint(0, 40, (480, 640, 3), dtype=np.uint8)
                self.change_pixmap_signal.emit(fake)
            self.msleep(33)


# ---------------------------------------------------------------------------
# 自繪 Multi-ranger 雷達環
# ---------------------------------------------------------------------------
class ObstacleRadar(QWidget):
    """以無人機為中心的四向距離雷達環。距離越近，光條越長且越紅。"""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(220)
        self.max_range = 2.0  # 顯示上限（公尺），multi-ranger 硬體上限約 4m
        self.dist = {"front": 2.0, "back": 2.0, "left": 2.0, "right": 2.0}

    def set_distances(self, front, back, left, right):
        self.dist = {"front": front, "back": back, "left": left, "right": right}
        self.update()

    def _color_for(self, d):
        if d < 0.4:
            return QColor(CRIT)
        if d < 0.8:
            return QColor(WARN)
        return QColor(ACCENT)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        radius = min(w, h) / 2 - 24

        # 距離刻度環
        p.setPen(QPen(QColor(BORDER), 1))
        for frac in (0.33, 0.66, 1.0):
            r = radius * frac
            p.drawEllipse(QPointF(cx, cy), r, r)

        # 無人機三角形（機頭朝上 = front）
        nose = QPointF(cx, cy - 14)
        left_wing = QPointF(cx - 10, cy + 8)
        right_wing = QPointF(cx + 10, cy + 8)
        p.setBrush(QBrush(QColor(ACCENT)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([nose, left_wing, right_wing]))

        # 四向距離條（越近越長，代表「威脅程度」而非實際距離）
        directions = {
            "front": (0, -1, "F"),
            "back": (0, 1, "B"),
            "left": (-1, 0, "L"),
            "right": (1, 0, "R"),
        }
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        for key, (dx, dy, label) in directions.items():
            d = max(0.05, min(self.dist[key], self.max_range))
            proximity = 1.0 - (d / self.max_range)  # 越近數值越大
            bar_len = 20 + proximity * (radius - 20)
            color = self._color_for(d)
            p.setPen(QPen(color, 5, cap=Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(cx, cy), QPointF(cx + dx * bar_len, cy + dy * bar_len))
            label_pt = QPointF(cx + dx * (radius + 10) - 5, cy + dy * (radius + 10) + 4)
            p.setPen(QPen(QColor(TEXT_MUTED)))
            p.drawText(label_pt, f"{label} {d:.2f}m")
        p.end()


# ---------------------------------------------------------------------------
# 主視窗
# ---------------------------------------------------------------------------
class TacticalGCS(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tactical Ground Control Station — RhemaDrone / Bee35 Edition")
        self.setGeometry(100, 100, 1400, 780)

        self.flight_state = FlightState.IDLE
        self.traj_x, self.traj_y = [0.0], [0.0]
        self.last_telemetry_ts = time.time()
        self.pending_p = 0.120  # 使用者正在調整、尚未套用的值
        self.applied_p = 0.120  # 實際已套用到飛控的值
        self._kill_armed_until = 0.0

        self.init_ui()
        self.init_threads_and_timers()
        self.apply_style()
        self._set_flight_state(FlightState.IDLE)

    # ------------------------------------------------------------------ UI
    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        main_layout.addWidget(self._build_left_panel(), stretch=28)
        main_layout.addWidget(self._build_center_panel(), stretch=46)
        main_layout.addWidget(self._build_right_panel(), stretch=26)

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("SectionLabel")
        return lbl

    def _build_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(self._section_label("MULTI-RANGER OBSTACLE RADAR"))
        self.radar = ObstacleRadar()
        layout.addWidget(self.radar)

        layout.addWidget(self._section_label("FLOW DECK POSITION TRAJECTORY (X/Y)"))
        self.traj_win = pg.GraphicsLayoutWidget()
        self.traj_win.setBackground(BG_PANEL)
        self.traj_plot = self.traj_win.addPlot()
        self.traj_plot.showGrid(x=True, y=True, alpha=0.25)
        self.traj_plot.setAspectLocked(True)
        self.traj_curve = self.traj_plot.plot(pen=pg.mkPen(ACCENT, width=2))
        self.traj_head = self.traj_plot.plot(
            [0], [0], pen=None, symbol="o", symbolSize=8, symbolBrush=WARN
        )
        layout.addWidget(self.traj_win, stretch=1)
        return panel

    def _build_center_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._section_label("LIVE FPV VIDEO FEED (5.8G ANALOG)"))
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet(
            f"background-color: {BG_DEEP}; border: 1px solid {BORDER};"
        )
        # 讓 pixmap 自動縮放貼合 label，並讓 label 尺寸完全交給 layout 決定，
        # 避免「setPixmap -> sizeHint 變大 -> layout 撐大 label -> 下一幀又用更大的
        # width() 去 scale -> 視窗持續放大」的迴授迴圈。
        self.image_label.setScaledContents(True)
        self.image_label.setMinimumSize(1, 1)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        layout.addWidget(self.image_label, stretch=1)
        return panel

    def _build_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # --- 連線/健康狀態列 ---
        layout.addWidget(self._section_label("LINK & ESTIMATOR HEALTH"))
        health = QFrame()
        health.setObjectName("Card")
        hl = QGridLayout(health)
        self.heartbeat_dot = QLabel("●")
        self.heartbeat_dot.setObjectName("HeartbeatDot")
        self.link_label = QLabel("LINK: OK")
        self.batt_label = QLabel("BATT: 16.4V (4S)")
        self.rssi_label = QLabel("RSSI: -42 dBm")
        self.ekf_label = QLabel("EKF: CONVERGED")
        hl.addWidget(self.heartbeat_dot, 0, 0)
        hl.addWidget(self.link_label, 0, 1)
        hl.addWidget(self.batt_label, 1, 0, 1, 2)
        hl.addWidget(self.rssi_label, 2, 0, 1, 2)
        hl.addWidget(self.ekf_label, 3, 0, 1, 2)
        layout.addWidget(health)

        # --- 飛行狀態機 ---
        layout.addWidget(self._section_label("FLIGHT STATE"))
        self.state_label = QLabel("IDLE")
        self.state_label.setObjectName("StateLabel")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.state_label)

        btn_layout = QHBoxLayout()
        self.btn_arm = QPushButton("ARM")
        self.btn_takeoff = QPushButton("TAKEOFF")
        self.btn_land = QPushButton("LAND")
        for b in (self.btn_arm, self.btn_takeoff, self.btn_land):
            btn_layout.addWidget(b)
        layout.addLayout(btn_layout)
        self.btn_arm.clicked.connect(self._on_arm)
        self.btn_takeoff.clicked.connect(self._on_takeoff)
        self.btn_land.clicked.connect(self._on_land)

        self.btn_kill = QPushButton("EMERGENCY KILL")
        self.btn_kill.setObjectName("KillButton")
        self.btn_kill.clicked.connect(self._on_kill)
        layout.addWidget(self.btn_kill)

        # --- PID 調整（預覽→套用）---
        layout.addWidget(self._section_label("RATE PID QUICK TUNING"))
        self.pid_label = QLabel("Rate P — applied: 0.120  |  preview: 0.120")
        layout.addWidget(self.pid_label)
        self.slider_p = QSlider(Qt.Orientation.Horizontal)
        self.slider_p.setRange(0, 200)
        self.slider_p.setValue(120)
        self.slider_p.valueChanged.connect(self._on_pid_preview)
        layout.addWidget(self.slider_p)
        self.btn_apply_pid = QPushButton("APPLY TO FLIGHT CONTROLLER")
        self.btn_apply_pid.setEnabled(False)
        self.btn_apply_pid.clicked.connect(self._on_pid_apply)
        layout.addWidget(self.btn_apply_pid)

        # --- Console ---
        layout.addWidget(self._section_label("FLIGHT LOG / ESTKALMAN CONSOLE"))
        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        layout.addWidget(self.console_text, stretch=1)
        self._log("INFO", "Ground Station initialized successfully.")
        self._log("INFO", "ExpressLRS CRSF link connected at 420000 bps.")

        return panel

    # ------------------------------------------------------------ 狀態機
    def _set_flight_state(self, state: FlightState):
        self.flight_state = state
        text, color = STATE_LABEL[state]
        self.state_label.setText(text)
        self.state_label.setStyleSheet(
            f"color: {color}; border: 1px solid {color}; font-size: 15px; padding: 6px;"
        )
        self.btn_arm.setEnabled(state == FlightState.IDLE)
        self.btn_takeoff.setEnabled(state == FlightState.ARMED)
        self.btn_land.setEnabled(state in (FlightState.HOVER, FlightState.TAKEOFF))

    def _on_arm(self):
        self._set_flight_state(FlightState.ARMED)
        self._log("WARN", "Vehicle ARMED. Propellers will spin on takeoff command.")

    def _on_takeoff(self):
        self._set_flight_state(FlightState.TAKEOFF)
        self._log("INFO", "Takeoff command sent (target 0.5m).")
        # TODO: cf.high_level_commander.takeoff(0.5, 2.0)
        QTimer.singleShot(1500, lambda: self._set_flight_state(FlightState.HOVER))

    def _on_land(self):
        self._set_flight_state(FlightState.LANDING)
        self._log("INFO", "Landing command sent.")
        # TODO: cf.high_level_commander.land(0.0, 2.0)
        QTimer.singleShot(1500, lambda: self._set_flight_state(FlightState.IDLE))

    def _on_kill(self):
        now = time.time()
        if now < self._kill_armed_until:
            # 第二次點擊：確實執行
            self._set_flight_state(FlightState.EMERGENCY)
            self.btn_kill.setText("EMERGENCY KILL")
            self._log("CRIT", "EMERGENCY STOP triggered — motors cut.")
            # TODO: cf.commander.send_stop_setpoint()
        else:
            # 第一次點擊：進入 1.5 秒確認視窗
            self._kill_armed_until = now + 1.5
            self.btn_kill.setText("CONFIRM KILL?")
            QTimer.singleShot(1500, self._reset_kill_button)

    def _reset_kill_button(self):
        if time.time() >= self._kill_armed_until:
            self.btn_kill.setText("EMERGENCY KILL")

    # --------------------------------------------------------------- PID
    def _on_pid_preview(self):
        self.pending_p = self.slider_p.value() / 1000.0
        self.pid_label.setText(
            f"Rate P — applied: {self.applied_p:.3f}  |  preview: {self.pending_p:.3f}"
        )
        self.btn_apply_pid.setEnabled(abs(self.pending_p - self.applied_p) > 1e-6)

    def _on_pid_apply(self):
        self.applied_p = self.pending_p
        self.btn_apply_pid.setEnabled(False)
        self._log("WARN", f"pid_rate.roll_p applied -> {self.applied_p:.3f}")
        # TODO: cf.param.set_value("pid_rate.roll_p", f"{self.applied_p}")

    # --------------------------------------------------------------- Log
    def _log(self, level, msg):
        color = {"INFO": ACCENT, "WARN": WARN, "CRIT": CRIT}[level]
        ts = time.strftime("%H:%M:%S")
        self.console_text.append(f'<span style="color:{color}">[{ts}] [{level}] {msg}</span>')

    # ---------------------------------------------------------- 執行緒/計時器
    def init_threads_and_timers(self):
        self.thread = VideoThread()
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.start()

        self.telemetry_timer = QTimer()
        self.telemetry_timer.timeout.connect(self.update_telemetry)
        self.telemetry_timer.start(100)  # 模擬 10Hz

        # 獨立的 watchdog：偵測 telemetry 是否斷流
        self.watchdog_timer = QTimer()
        self.watchdog_timer.timeout.connect(self._check_link_health)
        self.watchdog_timer.start(250)

    def update_image(self, cv_img):
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        # 不再手動 .scaled() 到 label 目前尺寸，改交給 setScaledContents 處理，
        # label 的顯示尺寸完全由 layout 決定，不會因為 pixmap 尺寸反過來被撐大。
        pix = QPixmap.fromImage(qimg)
        pix = self._draw_hud_overlay(pix)
        self.image_label.setPixmap(pix)

    def _draw_hud_overlay(self, pixmap: QPixmap) -> QPixmap:
        pix = QPixmap(pixmap)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = pix.width(), pix.height()

        # 角落框
        p.setPen(QPen(QColor(ACCENT), 2))
        L = 22
        for x, y, dx, dy in ((0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)):
            p.drawLine(x, y, x + dx * L, y)
            p.drawLine(x, y, x, y + dy * L)

        # 中央十字準星
        cx, cy = w // 2, h // 2
        p.setPen(QPen(QColor(ACCENT), 1))
        p.drawLine(cx - 12, cy, cx - 4, cy)
        p.drawLine(cx + 4, cy, cx + 12, cy)
        p.drawLine(cx, cy - 12, cx, cy - 4)
        p.drawLine(cx, cy + 4, cx, cy + 12)

        # 左下角浮水印：狀態 / 電量
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        text, color = STATE_LABEL[self.flight_state]
        p.setPen(QPen(QColor(color)))
        p.drawText(10, h - 12, f"{text}")
        p.end()
        return pix

    def update_telemetry(self):
        self.last_telemetry_ts = time.time()

        # Flow deck 軌跡（模擬漂移）
        nx = self.traj_x[-1] + random.uniform(-0.05, 0.05)
        ny = self.traj_y[-1] + random.uniform(-0.05, 0.05)
        self.traj_x.append(nx)
        self.traj_y.append(ny)
        if len(self.traj_x) > 150:
            self.traj_x.pop(0)
            self.traj_y.pop(0)
        self.traj_curve.setData(self.traj_x, self.traj_y)
        self.traj_head.setData([nx], [ny])

        # Multi-ranger
        front = random.uniform(0.4, 2.0)
        back = random.uniform(0.6, 2.0)
        left = random.uniform(0.2, 1.8)
        right = random.uniform(0.5, 2.0)
        self.radar.set_distances(front, back, left, right)
        if left < 0.4:
            self._log("WARN", "Left obstacle clearance low (<0.4m).")

        # 電量 / RSSI（模擬，附色階邏輯）
        batt_v = random.uniform(15.8, 16.6)
        self.batt_label.setText(f"BATT: {batt_v:.1f}V (4S)")
        self.batt_label.setStyleSheet(
            f"color:{CRIT if batt_v < 14.8 else WARN if batt_v < 15.4 else ACCENT}"
        )

    def _check_link_health(self):
        age = time.time() - self.last_telemetry_ts
        if age > 0.5:
            self.link_label.setText("LINK: LOST")
            self.link_label.setStyleSheet(f"color:{CRIT}")
            self.heartbeat_dot.setStyleSheet(f"color:{CRIT}")
        else:
            self.link_label.setText("LINK: OK")
            self.link_label.setStyleSheet(f"color:{ACCENT}")
            # 心跳閃爍：用 age 的奇偶造成明暗切換
            blink = int(time.time() * 2) % 2 == 0
            self.heartbeat_dot.setStyleSheet(f"color:{ACCENT if blink else BORDER}")

    # -------------------------------------------------------------- 樣式
    def apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {BG_DEEP}; }}
            QLabel {{ color: #C7CCE8; font-family: 'Consolas','Monospace'; font-size: 11px; }}
            #SectionLabel {{ color: {TEXT_MUTED}; font-weight: bold; font-size: 10px;
                              letter-spacing: 1px; margin-top: 4px; }}
            #StateLabel {{ background-color: {BG_PANEL}; border-radius: 4px; }}
            #Card {{ background-color: {BG_PANEL}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px; }}
            #HeartbeatDot {{ font-size: 14px; }}
            QPushButton {{ background-color: #2A2A40; color: #FFFFFF; border: 1px solid {BORDER};
                           padding: 8px; border-radius: 4px; font-family:'Consolas'; font-weight:bold; }}
            QPushButton:hover {{ background-color: {ACCENT}; color: {BG_DEEP}; border: 1px solid {ACCENT}; }}
            QPushButton:disabled {{ color: #555; border: 1px solid #2A2A3A; }}
            #KillButton {{ background-color: #4A0E0E; border: 1px solid {CRIT}; }}
            #KillButton:hover {{ background-color: {CRIT}; color: #FFFFFF; }}
            QSlider::groove:horizontal {{ border: 1px solid {BORDER}; height: 6px;
                                          background: {BG_PANEL}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {WARN}; width: 14px; margin: -4px 0; border-radius: 7px; }}
            QTextEdit {{ background-color: #0F0F18; color: {ACCENT}; font-family:'Consolas';
                        font-size: 11px; border: 1px solid {BORDER}; border-radius: 4px; }}
        """)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Consolas", 9))
    gcs = TacticalGCS()
    gcs.show()
    sys.exit(app.exec())
