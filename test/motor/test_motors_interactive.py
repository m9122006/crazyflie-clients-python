#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_motors_interactive.py
==========================
Crazyflie 互動式馬達轉向測試工具 (點擊圖片直接測試)
- 將 M1 ~ M4 按鈕整合至圖片對應位置，直接在圖中點擊馬達圓圈即可測試
- 保留推力設定與快速調整選項
- 支援懸停亮起、運轉中視覺特效、再次點擊停止與 ESC/空白鍵急停
"""

import sys
import os
import logging
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QTextEdit, QGroupBox, QGridLayout, QFrame)
from PyQt6.QtCore import pyqtSignal, QObject, Qt, QRectF, QPointF
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QPen, QBrush, QCursor

# 預設連線與推力設定
DEFAULT_URI = 'radio://0/79/2M'
DEFAULT_POWER = '5000'

logging.basicConfig(level=logging.WARNING)

# 圖片原始解析度與馬達圓圈中心座標 (基於 motor.png 844x774)
IMG_ORIG_W = 844
IMG_ORIG_H = 774

MOTOR_CENTERS = {
    1: (705, 96),   # M1: 右前 (Front Right)
    2: (705, 572),  # M2: 右後 (Rear Right)
    3: (141, 572),  # M3: 左後 (Rear Left)
    4: (141, 96),   # M4: 左前 (Front Left)
}

MOTOR_NAMES = {
    1: 'M1 (右前)',
    2: 'M2 (右後)',
    3: 'M3 (左後)',
    4: 'M4 (左前)',
}

# ESC 方塊範圍 (x1, y1, x2, y2)，點擊 ESC 方塊亦可觸發
ESC_BOXES = {
    1: (480, 70, 610, 170),
    2: (480, 500, 610, 600),
    3: (230, 500, 360, 600),
    4: (230, 70, 360, 170),
}


class EmittingStream(QObject):
    """將 stdout 輸出重導向至 GUI 的 Console 文字框"""
    textWritten = pyqtSignal(str)

    def write(self, text):
        self.textWritten.emit(str(text))

    def flush(self):
        pass


class CfSignalManager(QObject):
    """Crazyflie 回呼轉 Qt Signal 轉發器"""
    connected = pyqtSignal(str)
    disconnected = pyqtSignal(str)
    connection_failed = pyqtSignal(str, str)


class InteractiveMotorCanvas(QWidget):
    """
    可互動的馬達視圖元件：
    - 繪製 motor.png
    - 偵測滑鼠懸停 (Hover) 與點擊 (Click)
    - 視覺化標記正在運轉的馬達與推力狀態
    """
    motorClicked = pyqtSignal(int)  # 傳遞馬達編號 (1 ~ 4)

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.pixmap = None
        if os.path.exists(image_path):
            self.pixmap = QPixmap(image_path)
        
        self.is_connected = False
        self.hovered_motor = None
        self.running_motor = None
        self.running_power = 0
        
        self.setMinimumSize(360, 360)

    def set_connected(self, connected: bool):
        self.is_connected = connected
        if not connected:
            self.running_motor = None
        self.update()

    def set_running_motor(self, motor_num: int, power: int):
        self.running_motor = motor_num
        self.running_power = power
        self.update()

    def stop_motor(self):
        self.running_motor = None
        self.running_power = 0
        self.update()

    def _get_render_geometry(self):
        """計算保持原長寬比時的繪製尺寸與位移"""
        if not self.pixmap or self.pixmap.isNull():
            return 1.0, 0, 0, self.width(), self.height()
        
        w_widget = self.width()
        h_widget = self.height()
        scale = min(w_widget / IMG_ORIG_W, h_widget / IMG_ORIG_H)
        render_w = IMG_ORIG_W * scale
        render_h = IMG_ORIG_H * scale
        offset_x = (w_widget - render_w) / 2.0
        offset_y = (h_widget - render_h) / 2.0
        return scale, offset_x, offset_y, render_w, render_h

    def _pos_to_motor(self, pos):
        """判斷點擊/滑鼠位置屬於哪顆馬達 (1~4)，若無則傳回 None"""
        scale, offset_x, offset_y, render_w, render_h = self._get_render_geometry()
        x = pos.x()
        y = pos.y()

        # 檢查是否在繪製區內
        if not (offset_x <= x <= offset_x + render_w and offset_y <= y <= offset_y + render_h):
            return None

        # 映射回原圖座標系
        img_x = (x - offset_x) / scale
        img_y = (y - offset_y) / scale

        # 1. 檢查是否在馬達圓圈內 (半徑約 110 px)
        for m_id, (cx, cy) in MOTOR_CENTERS.items():
            dist = ((img_x - cx)**2 + (img_y - cy)**2)**0.5
            if dist <= 110:
                return m_id

        # 2. 檢查是否在對應 ESC 區塊內
        for m_id, (x1, y1, x2, y2) in ESC_BOXES.items():
            if x1 <= img_x <= x2 and y1 <= img_y <= y2:
                return m_id

        return None

    def mouseMoveEvent(self, event):
        motor = self._pos_to_motor(event.position())
        if motor != self.hovered_motor:
            self.hovered_motor = motor
            if motor and self.is_connected:
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                self.setToolTip(f"點擊測試 {MOTOR_NAMES[motor]}")
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
                if motor and not self.is_connected:
                    self.setToolTip("請先點擊「連線」以啟用馬達測試")
                else:
                    self.setToolTip("")
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.hovered_motor is not None:
            self.hovered_motor = None
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            motor = self._pos_to_motor(event.position())
            if motor:
                self.motorClicked.emit(motor)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 背景填充深灰柔和底色
        painter.fillRect(self.rect(), QColor("#f5f6f8"))

        scale, offset_x, offset_y, render_w, render_h = self._get_render_geometry()

        # 繪製 motor.png 原圖
        if self.pixmap and not self.pixmap.isNull():
            target_rect = QRectF(offset_x, offset_y, render_w, render_h)
            painter.drawPixmap(target_rect, self.pixmap, QRectF(self.pixmap.rect()))
        else:
            painter.setPen(QColor("#f44336"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "找不到 motor.png 圖片")
            return

        # 繪製各馬達標記或狀態效果
        for m_id, (cx, cy) in MOTOR_CENTERS.items():
            wx = offset_x + cx * scale
            wy = offset_y + cy * scale
            wr = 88 * scale

            # 運轉中的馬達：強烈綠光外圈與徽章
            if self.running_motor == m_id:
                # 呼吸/光暈光環
                painter.setBrush(QBrush(QColor(76, 175, 80, 80)))
                painter.setPen(QPen(QColor(46, 125, 50, 240), max(3.0, 4.0 * scale)))
                painter.drawEllipse(QPointF(wx, wy), wr, wr)

                # 閃爍外環
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(129, 199, 132, 220), max(2.0, 2.5 * scale), Qt.PenStyle.DashLine))
                painter.drawEllipse(QPointF(wx, wy), wr + 8 * scale, wr + 8 * scale)

                # 繪製運轉資訊浮動標籤
                badge_text = f"⚡ 運轉中 ({self.running_power})"
                badge_font = QFont("Noto Sans TC", max(8, int(11 * scale)), QFont.Weight.Bold)
                painter.setFont(badge_font)
                
                # 標籤位置：M1/M4 在上方，M2/M3 在下方
                badge_y = wy - wr - 14 * scale if m_id in (1, 4) else wy + wr + 14 * scale
                badge_w = 120 * scale
                badge_h = 24 * scale
                badge_rect = QRectF(wx - badge_w / 2.0, badge_y - badge_h / 2.0, badge_w, badge_h)

                painter.setBrush(QBrush(QColor("#2e7d32")))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(badge_rect, 6, 6)

                painter.setPen(QColor("white"))
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

            # 滑鼠懸停中的馬達：柔和藍光外環
            elif self.hovered_motor == m_id and self.is_connected:
                painter.setBrush(QBrush(QColor(33, 150, 243, 60)))
                painter.setPen(QPen(QColor(25, 118, 210, 220), max(2.0, 3.0 * scale)))
                painter.drawEllipse(QPointF(wx, wy), wr, wr)

                # 提示文字
                badge_text = f"點擊啟動 {MOTOR_NAMES[m_id]}"
                badge_font = QFont("Noto Sans TC", max(8, int(10 * scale)), QFont.Weight.Bold)
                painter.setFont(badge_font)

                badge_y = wy - wr - 14 * scale if m_id in (1, 4) else wy + wr + 14 * scale
                badge_w = 110 * scale
                badge_h = 22 * scale
                badge_rect = QRectF(wx - badge_w / 2.0, badge_y - badge_h / 2.0, badge_w, badge_h)

                painter.setBrush(QBrush(QColor("#1976d2")))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(badge_rect, 5, 5)

                painter.setPen(QColor("white"))
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

            # 連線時若為空閒：繪製淡藍色可點擊小引導框
            elif self.is_connected:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(100, 181, 246, 120), max(1.0, 1.5 * scale), Qt.PenStyle.DotLine))
                painter.drawEllipse(QPointF(wx, wy), wr, wr)

        # 頂部狀態橫條
        if not self.is_connected:
            banner_rect = QRectF(offset_x, offset_y, render_w, 26 * scale)
            painter.fillRect(banner_rect, QColor(60, 64, 67, 180))
            painter.setPen(QColor("white"))
            painter.setFont(QFont("Noto Sans TC", max(8, int(10 * scale)), QFont.Weight.Bold))
            painter.drawText(banner_rect, Qt.AlignmentFlag.AlignCenter, "未連線 — 請先點擊右側「連線」按鈕")


class InteractiveMotorGUI(QMainWindow):
    """主視窗"""
    def __init__(self):
        super().__init__()
        self.cf = Crazyflie(rw_cache='./cache')
        self.signals = CfSignalManager()
        
        self.signals.connected.connect(self.on_connected)
        self.signals.disconnected.connect(self.on_disconnected)
        self.signals.connection_failed.connect(self.on_connection_failed)
        
        self.current_motor = None
        
        self.init_ui()
        self.init_cf()

    def init_ui(self):
        self.setWindowTitle('Crazyflie 互動式馬達測試 (點選圖片直接測試)')
        self.resize(1020, 680)
        self.setFont(QFont('Noto Sans TC', 10))

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # ── 上方區域：左側圖片互動區 + 右側設定面板 ──
        upper_layout = QHBoxLayout()
        upper_layout.setSpacing(14)

        # 左側：互動式馬達圖畫布
        script_dir = os.path.dirname(os.path.abspath(__file__))
        image_path = os.path.join(script_dir, 'motor.png')

        self.canvas = InteractiveMotorCanvas(image_path, self)
        self.canvas.motorClicked.connect(self.handle_motor_clicked)
        upper_layout.addWidget(self.canvas, stretch=5)

        # 右側：控制與設定面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # 1. 連線設定卡片
        conn_group = QGroupBox("連線設定")
        conn_layout = QVBoxLayout(conn_group)
        
        uri_row = QHBoxLayout()
        uri_row.addWidget(QLabel("連線 URI:"))
        self.uri_input = QLineEdit(DEFAULT_URI)
        uri_row.addWidget(self.uri_input)
        conn_layout.addLayout(uri_row)

        self.btn_connect = QPushButton("連線至 Crazyflie")
        self.btn_connect.setMinimumHeight(42)
        self.btn_connect.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
        """)
        self.btn_connect.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.btn_connect)
        right_layout.addWidget(conn_group)

        # 2. 推力控制卡片 (保留推力選項)
        power_group = QGroupBox("推力設定 (Thrust Power)")
        power_layout = QVBoxLayout(power_group)

        power_row = QHBoxLayout()
        power_row.addWidget(QLabel("測試推力 (1 ~ 65535):"))
        self.power_input = QLineEdit(DEFAULT_POWER)
        self.power_input.setFixedWidth(90)
        self.power_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.power_input.setStyleSheet("font-size: 13px; font-weight: bold;")
        power_row.addWidget(self.power_input)
        power_layout.addLayout(power_row)

        # 推力快捷選擇按鈕
        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel("快捷調整:"))
        for p in [3000, 5000, 8000, 12000]:
            btn = QPushButton(str(p))
            btn.setFixedHeight(28)
            btn.setStyleSheet("padding: 2px 6px; font-size: 12px;")
            btn.clicked.connect(lambda checked, val=p: self.set_quick_power(val))
            quick_row.addWidget(btn)
        power_layout.addLayout(quick_row)
        right_layout.addWidget(power_group)

        # 3. 馬達狀態指示卡片
        status_group = QGroupBox("當前狀態")
        status_layout = QVBoxLayout(status_group)
        self.status_label = QLabel("🛑 狀態：尚未連線")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #555;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.status_label)
        right_layout.addWidget(status_group)

        # 4. 操作說明
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #e8f0fe; border-radius: 6px; padding: 6px;")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(8, 8, 8, 8)
        lbl_hint = QLabel("💡 <b>操作說明：</b><br>"
                          "1. 點擊「連線」按鈕<br>"
                          "2. 直接<b>點選左圖中的 M1 ~ M4</b> 即可啟動測試<br>"
                          "3. 再次點選運轉中馬達或按 <b>ESC / 空白鍵</b> 立即停止")
        lbl_hint.setStyleSheet("color: #1a73e8; font-size: 12px; line-height: 140%;")
        info_layout.addWidget(lbl_hint)
        right_layout.addWidget(info_frame)

        # 5. 緊急停止大按鈕
        self.btn_stop = QPushButton("🛑 停止所有馬達 (ESC / 空白鍵)")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                font-size: 15px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #e0e0e0;
                color: #9e9e9e;
            }
        """)
        self.btn_stop.setMinimumHeight(55)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_all_motors)
        right_layout.addWidget(self.btn_stop)

        right_layout.addStretch()
        upper_layout.addWidget(right_panel, stretch=4)
        main_layout.addLayout(upper_layout, stretch=4)

        # ── 下方區域：日誌輸出終端 ──
        log_group = QGroupBox("輸出日誌 (Console Log)")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 6, 6, 6)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #a9b7c6;
                font-family: 'Noto Sans Mono', 'Consolas', 'Monospace';
                font-size: 12px;
                border-radius: 4px;
            }
        """)
        self.console.setMaximumHeight(160)
        log_layout.addWidget(self.console)
        main_layout.addWidget(log_group, stretch=2)

        # 重新導向 stdout
        sys.stdout = EmittingStream()
        sys.stdout.textWritten.connect(self.append_log)

        print(f'[系統] 歡迎使用互動式馬達測試工具，預設連線字串：{DEFAULT_URI}')
        print('[系統] 點擊左側圖片對應馬達位置即可直接驅動測試。')

    def set_quick_power(self, val):
        self.power_input.setText(str(val))
        print(f'[推力] 快捷設定測試推力為：{val}')

    def append_log(self, text):
        self.console.insertPlainText(text)
        self.console.ensureCursorVisible()

    def init_cf(self):
        cflib.crtp.init_drivers(enable_debug_driver=False)
        self.cf.connected.add_callback(lambda uri: self.signals.connected.emit(uri))
        self.cf.disconnected.add_callback(lambda uri: self.signals.disconnected.emit(uri))
        self.cf.connection_failed.add_callback(lambda uri, msg: self.signals.connection_failed.emit(uri, msg))
        self.cf.connection_lost.add_callback(lambda uri, msg: self.signals.connection_failed.emit(uri, msg))

    def toggle_connection(self):
        if self.cf.is_connected():
            self.stop_all_motors()
            self.release_motor_control()
            self.cf.close_link()
        else:
            uri = self.uri_input.text().strip()
            print(f'[連線] 正在嘗試連線至 {uri} ...')
            self.cf.open_link(uri)

    def on_connected(self, link_uri):
        print(f'[連線] ✅ 成功連線到 {link_uri}')
        self.btn_connect.setText('斷開連線')
        self.btn_connect.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        self.btn_stop.setEnabled(True)
        self.canvas.set_connected(True)
        self.status_label.setText("🟢 狀態：已連線 (請點選左圖馬達進行測試)")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #2e7d32;")
        
        # 啟用 direct motor power control
        self.cf.param.set_value('motorPowerSet.enable', '1')
        self.stop_all_motors()

    def on_disconnected(self, link_uri):
        print(f'[連線] 🛑 已斷開連線')
        self.reset_ui_state()

    def on_connection_failed(self, link_uri, msg):
        print(f'[錯誤] ❌ 連線失敗: {msg}')
        self.reset_ui_state()

    def reset_ui_state(self):
        self.btn_connect.setText('連線至 Crazyflie')
        self.btn_connect.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
        """)
        self.btn_stop.setEnabled(False)
        self.canvas.set_connected(False)
        self.current_motor = None
        self.status_label.setText("🛑 狀態：尚未連線")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #555;")

    def set_motor_power(self, m1, m2, m3, m4):
        self.cf.param.set_value('motorPowerSet.m1', str(m1))
        self.cf.param.set_value('motorPowerSet.m2', str(m2))
        self.cf.param.set_value('motorPowerSet.m3', str(m3))
        self.cf.param.set_value('motorPowerSet.m4', str(m4))

    def stop_all_motors(self):
        self.current_motor = None
        self.canvas.stop_motor()
        if self.cf.is_connected():
            self.set_motor_power(0, 0, 0, 0)
            print('[安全] 🛑 已停止所有馬達。')
            self.status_label.setText("🟢 狀態：已連線 (所有馬達已停止)")
            self.status_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #2e7d32;")

    def release_motor_control(self):
        if self.cf.is_connected():
            self.cf.param.set_value('motorPowerSet.enable', '0')

    def handle_motor_clicked(self, num: int):
        """處理點擊圖片上的馬達"""
        if not self.cf.is_connected():
            print(f'[提醒] ⚠️ 尚未連線！請先點擊「連線」後再測試 {MOTOR_NAMES.get(num, f"M{num}")}。')
            return

        # 若點選的是當前正在轉動的馬達，則切換為停止 (Toggle 機制)
        if self.current_motor == num:
            print(f'[停止] 再次點擊 {MOTOR_NAMES[num]}，停止運轉。')
            self.stop_all_motors()
            return

        self.run_motor(num)

    def run_motor(self, num: int):
        try:
            power = int(self.power_input.text().strip())
            if power < 0 or power > 65535:
                raise ValueError()
        except ValueError:
            print('[警告] ⚠️ 推力數值格式錯誤！請輸入 0 ~ 65535 之間的整數。')
            return

        # 先全部歸零
        self.set_motor_power(0, 0, 0, 0)
        time.sleep(0.04)

        powers = [0, 0, 0, 0]
        powers[num - 1] = power
        self.set_motor_power(*powers)

        self.current_motor = num
        self.canvas.set_running_motor(num, power)

        name = MOTOR_NAMES.get(num, f'M{num}')
        self.status_label.setText(f"⚡ 運轉中：{name} | 推力: {power}")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #d32f2f;")
        print(f'[驅動] ⚡ 馬達 {name} 正以功率 {power} 運轉中...')

    def keyPressEvent(self, event):
        # ESC 或 空白鍵快速急停
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Space):
            self.stop_all_motors()
        # 數字鍵 1 ~ 4 亦可直接觸發對應馬達
        elif event.key() == Qt.Key.Key_1:
            self.handle_motor_clicked(1)
        elif event.key() == Qt.Key.Key_2:
            self.handle_motor_clicked(2)
        elif event.key() == Qt.Key.Key_3:
            self.handle_motor_clicked(3)
        elif event.key() == Qt.Key.Key_4:
            self.handle_motor_clicked(4)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.cf.is_connected():
            self.stop_all_motors()
            self.release_motor_control()
            self.cf.close_link()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    gui = InteractiveMotorGUI()
    gui.show()
    sys.exit(app.exec())
