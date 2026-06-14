#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_motors_gui.py (修正版)
========================
已根據硬體現況修正 URI 為 radio://0/79/2M。
"""

import sys
import logging
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QTextEdit, QGridLayout)
from PyQt6.QtCore import pyqtSignal, QObject
from PyQt6.QtGui import QFont

# 根據 cfclient 截圖修正的預設連線設定
DEFAULT_URI = 'radio://0/79/2M'
DEFAULT_POWER = '5000'

logging.basicConfig(level=logging.WARNING)

class EmittingStream(QObject):
    textWritten = pyqtSignal(str)
    def write(self, text):
        self.textWritten.emit(str(text))
    def flush(self):
        pass

class CfSignalManager(QObject):
    connected = pyqtSignal(str)
    disconnected = pyqtSignal(str)
    connection_failed = pyqtSignal(str, str)

class MotorTestGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cf = Crazyflie(rw_cache='./cache')
        self.signals = CfSignalManager()
        
        self.signals.connected.connect(self.on_connected)
        self.signals.disconnected.connect(self.on_disconnected)
        self.signals.connection_failed.connect(self.on_connection_failed)
        
        self.init_ui()
        self.init_cf()
        
    def init_ui(self):
        self.setWindowTitle('Crazyflie 馬達轉向測試 (自製飛控專用)')
        self.resize(700, 500)
        
        # 優先套用 Noto Sans TC
        self.setFont(QFont('Noto Sans TC', 10))
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # ── 頂部設定欄 ──
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel('連線 URI:'))
        self.uri_input = QLineEdit(DEFAULT_URI)
        config_layout.addWidget(self.uri_input)
        
        config_layout.addWidget(QLabel('測試推力:'))
        self.power_input = QLineEdit(DEFAULT_POWER)
        self.power_input.setFixedWidth(80)
        config_layout.addWidget(self.power_input)
        
        self.btn_connect = QPushButton('連線')
        self.btn_connect.setStyleSheet('font-weight: bold;')
        self.btn_connect.clicked.connect(self.toggle_connection)
        config_layout.addWidget(self.btn_connect)
        layout.addLayout(config_layout)
        
        # ── 中央馬達控制網格 ──
        # 照標準四旋翼位置佈置：M3 (左前) | M4 (右前)
        #                     M2 (左後) | M1 (右後)
        grid = QGridLayout()
        self.btn_m1 = QPushButton('M1 (右後)')
        self.btn_m2 = QPushButton('M2 (左後)')
        self.btn_m3 = QPushButton('M3 (左前)')
        self.btn_m4 = QPushButton('M4 (右前)')
        
        self.motor_btns = [self.btn_m1, self.btn_m2, self.btn_m3, self.btn_m4]
        for btn in self.motor_btns:
            btn.setEnabled(False)
            btn.setMinimumHeight(80)
            btn.setStyleSheet('font-size: 14px; font-weight: bold;')
            
        self.btn_m1.clicked.connect(lambda: self.run_motor(1))
        self.btn_m2.clicked.connect(lambda: self.run_motor(2))
        self.btn_m3.clicked.connect(lambda: self.run_motor(3))
        self.btn_m4.clicked.connect(lambda: self.run_motor(4))
        
        grid.addWidget(self.btn_m3, 0, 0)
        grid.addWidget(self.btn_m4, 0, 1)
        grid.addWidget(self.btn_m2, 1, 0)
        grid.addWidget(self.btn_m1, 1, 1)
        layout.addLayout(grid)
        
        # ── 緊急停止按鈕 ──
        self.btn_stop = QPushButton('停止所有馬達 (ESC)')
        self.btn_stop.setStyleSheet('background-color: #f44336; color: white; font-weight: bold; font-size: 16px;')
        self.btn_stop.setMinimumHeight(60)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_all_motors)
        layout.addWidget(self.btn_stop)
        
        # ── 底部日誌輸出區 ──
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet('background-color: #2b2b2b; color: #a9b7c6; font-family: "Noto Sans Mono", "Monospace";')
        layout.addWidget(self.console)
        
        sys.stdout = EmittingStream()
        sys.stdout.textWritten.connect(self.append_log)
        
        print(f'已將預設頻道更新為 100，連線字串：{DEFAULT_URI}')
        print('請確保 cf_env 已啟動，並點擊「連線」開始測試。')

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
            self.cf.open_link(uri)

    def on_connected(self, link_uri):
        print(f'[連線] 成功連線到 {link_uri}')
        self.btn_connect.setText('斷開連線')
        for btn in self.motor_btns:
            btn.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.cf.param.set_value('motorPowerSet.enable', '1')
        self.stop_all_motors()

    def on_disconnected(self, link_uri):
        print(f'[連線] 已斷開連線')
        self.reset_ui_state()

    def on_connection_failed(self, link_uri, msg):
        print(f'[錯誤] 連線失敗: {msg}')
        self.reset_ui_state()

    def reset_ui_state(self):
        self.btn_connect.setText('連線')
        for btn in self.motor_btns:
            btn.setEnabled(False)
        self.btn_stop.setEnabled(False)

    def set_motor_power(self, m1, m2, m3, m4):
        self.cf.param.set_value('motorPowerSet.m1', str(m1))
        self.cf.param.set_value('motorPowerSet.m2', str(m2))
        self.cf.param.set_value('motorPowerSet.m3', str(m3))
        self.cf.param.set_value('motorPowerSet.m4', str(m4))

    def stop_all_motors(self):
        if self.cf.is_connected():
            self.set_motor_power(0, 0, 0, 0)
            print('[安全] 🛑 已停止所有馬達。')

    def release_motor_control(self):
        if self.cf.is_connected():
            self.cf.param.set_value('motorPowerSet.enable', '0')

    def run_motor(self, num):
        try:
            power = int(self.power_input.text().strip())
        except ValueError:
            print('[警告] 推力數值格式錯誤！')
            return
            
        # 先全停
        self.set_motor_power(0, 0, 0, 0)
        time.sleep(0.05)
        
        powers = [0, 0, 0, 0]
        powers[num-1] = power
        self.set_motor_power(*powers)
        print(f'[驅動] ⚡ 馬達 M{num} 正以功率 {power} 運轉')

    def keyPressEvent(self, event):
        # 增加空白鍵或 ESC 快速停止功能
        if event.key() == 16777216: # ESC
            self.stop_all_motors()

    def closeEvent(self, event):
        if self.cf.is_connected():
            self.stop_all_motors()
            self.release_motor_control()
            self.cf.close_link()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    gui = MotorTestGUI()
    gui.show()
    sys.exit(app.exec())