#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Flow Deck v2 診斷與測試工具 (圖形化介面版)
直觀顯示感測器即時數據與測試結果。
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import statistics
import datetime
from collections import defaultdict
import os
import sys

# 嘗試載入 cflib
try:
    import cflib.crtp
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
    CFLIB_AVAILABLE = True
except ImportError:
    CFLIB_AVAILABLE = False

# =============================================================================
# 參數與閾值設定
# =============================================================================
TOF_MIN_RANGE_MM = 10
TOF_MAX_RANGE_MM = 4000
TOF_EXPECTED_DESK_MM = (30, 500)
FLOW_NOISE_THRESHOLD = 200
LOG_PERIOD_MS = 50

# =============================================================================
# 背景測試執行緒 (避免凍結 UI)
# =============================================================================
class TesterThread(threading.Thread):
    def __init__(self, uri, duration, ui_callbacks):
        super().__init__()
        self.uri = uri
        self.duration = duration
        self.ui = ui_callbacks
        self.data = defaultdict(list)
        self.sample_count = 0
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def _log_data_cb(self, timestamp, data, logconf):
        """處理所有日誌數據"""
        for key, value in data.items():
            self.data[key].append(value)
        if "range.zrange" in data:  # 算作一個主要 sample
            self.sample_count += 1
            
            # 抽出即時數據更新 UI
            z = data.get("range.zrange", 0)
            dx = data.get("motion.deltaX", 0)
            dy = data.get("motion.deltaY", 0)
            self.ui['live_data'](z, dx, dy)

    def _log_pose_cb(self, timestamp, data, logconf):
        for key, value in data.items():
            self.data[key].append(value)
        
        x = data.get("stateEstimate.x", 0)
        y = data.get("stateEstimate.y", 0)
        z = data.get("stateEstimate.z", 0)
        self.ui['live_pose'](x, y, z)

    def run(self):
        self.ui['log']("開始初始化無線通訊...", "info")
        try:
            cflib.crtp.init_drivers()
        except Exception as e:
            self.ui['log'](f"驅動初始化失敗: {e}", "error")
            self.ui['done']()
            return

        self.ui['log'](f"嘗試連接至 {self.uri} ...", "info")
        try:
            with SyncCrazyflie(self.uri, cf=Crazyflie(rw_cache="./cache")) as scf:
                cf = scf.cf
                self.ui['log']("連線成功！正在檢查 Flow Deck 硬體...", "pass")
                time.sleep(1) # 確保參數同步
                
                # 1. 偵測硬體
                deck_attached = False
                try:
                    val = cf.param.get_value("deck.bcFlow2")
                    deck_attached = int(val) != 0
                except:
                    pass
                
                if deck_attached:
                    self.ui['result']("硬體偵測", True, "已正確識別 deck.bcFlow2")
                else:
                    self.ui['result']("硬體偵測", False, "未偵測到 Flow Deck v2")
                    self.ui['log']("警告：可能未安裝 Flow Deck，將繼續嘗試讀取數據", "warn")

                # 2. 設定日誌
                lg_sensor = LogConfig(name="FlowSensor", period_in_ms=LOG_PERIOD_MS)
                lg_sensor.add_variable("range.zrange", "uint16_t")
                lg_sensor.add_variable("motion.deltaX", "int16_t")
                lg_sensor.add_variable("motion.deltaY", "int16_t")
                
                lg_pose = LogConfig(name="PoseEstimate", period_in_ms=LOG_PERIOD_MS)
                lg_pose.add_variable("stateEstimate.x", "float")
                lg_pose.add_variable("stateEstimate.y", "float")
                lg_pose.add_variable("stateEstimate.z", "float")

                cf.log.add_config(lg_sensor)
                cf.log.add_config(lg_pose)
                
                lg_sensor.data_received_cb.add_callback(self._log_data_cb)
                lg_pose.data_received_cb.add_callback(self._log_pose_cb)

                self.ui['log'](f"開始收集數據，持續 {self.duration} 秒...", "info")
                lg_sensor.start()
                lg_pose.start()

                # 3. 收集迴圈
                start_time = time.time()
                while (time.time() - start_time) < self.duration and not self._stop_event.is_set():
                    elapsed = time.time() - start_time
                    progress = (elapsed / self.duration) * 100
                    self.ui['progress'](progress)
                    time.sleep(0.1)

                lg_sensor.stop()
                lg_pose.stop()
                
                if self._stop_event.is_set():
                    self.ui['log']("測試已被使用者中止。", "warn")
                else:
                    self.ui['progress'](100)
                    self.ui['log']("數據收集完成！開始分析...", "info")
                    self.analyze_data()
                    self.export_csv()
                    
        except Exception as e:
            self.ui['log'](f"連線或收集過程發生錯誤: {e}", "error")
        
        self.ui['done']()

    def analyze_data(self):
        # 分析取樣率
        expected = int(self.duration * (1000 / LOG_PERIOD_MS))
        ratio = self.sample_count / max(expected, 1)
        ok_sample = ratio >= 0.8
        self.ui['result']("數據穩定性", ok_sample, f"取得率 {ratio:.0%} ({self.sample_count}/{expected})")

        # 分析 ToF
        zr = self.data.get("range.zrange", [])
        if zr:
            z_mean, z_std = statistics.mean(zr), statistics.stdev(zr) if len(zr)>1 else 0
            z_zeros = sum(1 for v in zr if v == 0)
            z_zero_ratio = z_zeros / len(zr)
            ok_z = (TOF_EXPECTED_DESK_MM[0] <= z_mean <= TOF_EXPECTED_DESK_MM[1]) and (z_std < 50) and (z_zero_ratio < 0.1)
            self.ui['result']("ToF 雷射測距", ok_z, f"均值 {z_mean:.1f}mm | 標準差 {z_std:.1f}mm | 零值率 {z_zero_ratio:.1%}")
        else:
            self.ui['result']("ToF 雷射測距", False, "無數據")

        # 分析 Flow
        dx = self.data.get("motion.deltaX", [])
        dy = self.data.get("motion.deltaY", [])
        if dx and dy:
            dx_m, dx_s = statistics.mean(dx), statistics.stdev(dx) if len(dx)>1 else 0
            dy_m, dy_s = statistics.mean(dy), statistics.stdev(dy) if len(dy)>1 else 0
            all_zero = all(v == 0 for v in dx) and all(v == 0 for v in dy)
            ok_flow = (abs(dx_m) < 20 and abs(dy_m) < 20) and (dx_s < FLOW_NOISE_THRESHOLD and dy_s < FLOW_NOISE_THRESHOLD) and not all_zero
            self.ui['result']("光流感測 (PMW3901)", ok_flow, f"X 均值 {dx_m:+.1f} | Y 均值 {dy_m:+.1f} (全零: {all_zero})")
        else:
            self.ui['result']("光流感測 (PMW3901)", False, "無數據")

        # 分析 EKF
        ex = self.data.get("stateEstimate.x", [])
        ey = self.data.get("stateEstimate.y", [])
        ez = self.data.get("stateEstimate.z", [])
        if ex and ey and ez:
            ex_s = statistics.stdev(ex) if len(ex)>1 else 0
            ey_s = statistics.stdev(ey) if len(ey)>1 else 0
            ez_m, ez_s = statistics.mean(ez), statistics.stdev(ez) if len(ez)>1 else 0
            ok_ekf = (ex_s < 0.05 and ey_s < 0.05) and (0.01 < ez_m < 0.6) and (ez_s < 0.05)
            self.ui['result']("EKF 位置融合", ok_ekf, f"XY漂移 {max(ex_s, ey_s):.3f}m | Z均值 {ez_m:.3f}m")
        else:
            self.ui['result']("EKF 位置融合", False, "無數據")

    def export_csv(self):
        if not self.data: return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"flowdeck_test_{ts}.csv"
        keys = sorted(self.data.keys())
        max_len = max(len(v) for v in self.data.values())
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(",".join(keys) + "\n")
                for i in range(max_len):
                    row = [str(self.data[k][i]) if i < len(self.data[k]) else "" for k in keys]
                    f.write(",".join(row) + "\n")
            self.ui['log'](f"數據已匯出: {filename}", "pass")
        except Exception as e:
            self.ui['log'](f"CSV 匯出失敗: {e}", "error")

# =============================================================================
# 主視窗 GUI
# =============================================================================
class FlowDeckApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Flow Deck v2 診斷與測試工具")
        self.geometry("750x600")
        self.configure(padx=10, pady=10)
        self.thread = None

        self._setup_ui()
        self._check_dependencies()

    def _setup_ui(self):
        # 風格設定
        style = ttk.Style()
        style.configure("TButton", font=("Arial", 11))
        style.configure("TLabel", font=("Arial", 10))
        style.configure("Title.TLabel", font=("Arial", 14, "bold"))
        style.configure("Header.TLabel", font=("Arial", 11, "bold"))

        # --- 頂部設定區 ---
        frame_config = ttk.LabelFrame(self, text=" 系統設定 ", padding=10)
        frame_config.pack(fill=tk.X, pady=5)

        ttk.Label(frame_config, text="Radio URI:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.ent_uri = ttk.Entry(frame_config, width=30)
        self.ent_uri.insert(0, "radio://0/79/2M/E7E7E7E7E7")
        self.ent_uri.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        ttk.Label(frame_config, text="測試秒數:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.ent_dur = ttk.Entry(frame_config, width=10)
        self.ent_dur.insert(0, "15")
        self.ent_dur.grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)

        self.btn_start = ttk.Button(frame_config, text="開始測試", command=self.start_test)
        self.btn_start.grid(row=0, column=4, padx=15, pady=5)

        self.btn_stop = ttk.Button(frame_config, text="強制停止", command=self.stop_test, state=tk.DISABLED)
        self.btn_stop.grid(row=0, column=5, padx=5, pady=5)

        # --- 即時數據顯示區 ---
        frame_live = ttk.LabelFrame(self, text=" 即時感測器狀態 ", padding=10)
        frame_live.pack(fill=tk.X, pady=5)

        self.lbl_z = ttk.Label(frame_live, text="Z 高度: --- mm", font=("Arial", 12, "bold"), foreground="blue")
        self.lbl_z.grid(row=0, column=0, padx=20, pady=5)

        self.lbl_flow = ttk.Label(frame_live, text="光流 (dX, dY): ---, ---")
        self.lbl_flow.grid(row=0, column=1, padx=20, pady=5)

        self.lbl_pose = ttk.Label(frame_live, text="位置估計 (X, Y, Z): ---")
        self.lbl_pose.grid(row=0, column=2, padx=20, pady=5)

        self.progress = ttk.Progressbar(frame_live, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.grid(row=1, column=0, columnspan=3, sticky=tk.EW, pady=10, padx=5)
        frame_live.columnconfigure(2, weight=1)

        # --- 測試報告區 ---
        frame_log = ttk.LabelFrame(self, text=" 測試報告與日誌 ", padding=10)
        frame_log.pack(fill=tk.BOTH, expand=True, pady=5)

        self.txt_log = scrolledtext.ScrolledText(frame_log, wrap=tk.WORD, font=("Consolas", 10))
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        # 標籤顏色設定
        self.txt_log.tag_config('info', foreground='black')
        self.txt_log.tag_config('pass', foreground='green', font=("Consolas", 10, "bold"))
        self.txt_log.tag_config('error', foreground='red', font=("Consolas", 10, "bold"))
        self.txt_log.tag_config('warn', foreground='orange', font=("Consolas", 10, "bold"))

    def _check_dependencies(self):
        if not CFLIB_AVAILABLE:
            self.write_log("未檢測到 'cflib' 模組。請在終端機執行: pip install cflib", "error")
            self.btn_start.config(state=tk.DISABLED)

    def write_log(self, msg, tag="info"):
        self.txt_log.insert(tk.END, msg + "\n", tag)
        self.txt_log.see(tk.END)

    def update_live_data(self, z, dx, dy):
        self.lbl_z.config(text=f"Z 高度: {z} mm")
        self.lbl_flow.config(text=f"光流 (dX, dY): {dx:d}, {dy:d}")

    def update_live_pose(self, x, y, z):
        self.lbl_pose.config(text=f"位置 (X, Y, Z): {x:.2f}, {y:.2f}, {z:.2f}")

    def update_progress(self, val):
        self.progress['value'] = val

    def append_result(self, name, passed, detail):
        status = "✔ PASS" if passed else "✘ FAIL"
        tag = "pass" if passed else "error"
        self.write_log(f"[{status}] {name} - {detail}", tag)

    def thread_done(self):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.ent_uri.config(state=tk.NORMAL)
        self.ent_dur.config(state=tk.NORMAL)

    def start_test(self):
        uri = self.ent_uri.get().strip()
        try:
            dur = float(self.ent_dur.get())
        except ValueError:
            messagebox.showerror("錯誤", "測試秒數必須為數字")
            return

        self.txt_log.delete(1.0, tk.END)
        self.progress['value'] = 0
        self.write_log("=========================================", "info")
        self.write_log(" Flow Deck v2 診斷開始", "info")
        self.write_log(" 註: 請確保無人機平靜放置在有紋理的桌面上", "warn")
        self.write_log("=========================================\n", "info")

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.ent_uri.config(state=tk.DISABLED)
        self.ent_dur.config(state=tk.DISABLED)

        ui_callbacks = {
            'log': lambda msg, tag: self.after(0, self.write_log, msg, tag),
            'live_data': lambda z, dx, dy: self.after(0, self.update_live_data, z, dx, dy),
            'live_pose': lambda x, y, z: self.after(0, self.update_live_pose, x, y, z),
            'progress': lambda v: self.after(0, self.update_progress, v),
            'result': lambda n, p, d: self.after(0, self.append_result, n, p, d),
            'done': lambda: self.after(0, self.thread_done)
        }

        self.thread = TesterThread(uri, dur, ui_callbacks)
        self.thread.daemon = True
        self.thread.start()

    def stop_test(self):
        if self.thread and self.thread.is_alive():
            self.write_log("正在強制停止測試...", "warn")
            self.thread.stop()
            self.btn_stop.config(state=tk.DISABLED)

if __name__ == "__main__":
    app = FlowDeckApp()
    app.mainloop()
