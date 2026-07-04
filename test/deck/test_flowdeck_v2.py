#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Flow Deck v2 診斷與測試工具

此腳本用於驗證新安裝的 Flow Deck v2 是否正常運作，包括：
  1. 硬體偵測 — 確認 Flow Deck v2 已被 Crazyflie 正確識別
  2. ToF 感測器 (VL53L1x) — 測試雷射測距數據是否正常
  3. 光流感測器 (PMW3901) — 測試 X/Y 光流位移數據
  4. 融合後位置估計 — 驗證 EKF 狀態估計是否收斂
  5. 數據品質分析 — 統計各感測器的雜訊、穩定性與有效率

使用方式：
  python test_flowdeck_v2.py [--uri RADIO_URI] [--duration SECONDS]

需求：
  - cflib (pip install cflib)
  - Crazyflie 2.x 已安裝 Flow Deck v2 並開機
  - Crazyradio PA 已連接電腦
"""

import argparse
import logging
import math
import os
import signal
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime

# 強制 Windows 終端使用 UTF-8 編碼，確保中文正常顯示
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import cflib.crtp
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.mem import MemoryElement
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
    from cflib.crazyflie.syncLogger import SyncLogger
    from cflib.utils import uri_helper
except ImportError:
    print("錯誤：找不到 cflib 模組。請先安裝：pip install cflib")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 常數定義
# ---------------------------------------------------------------------------

# Flow Deck v2 硬體參數
TOF_MIN_RANGE_MM = 10       # VL53L1x 最小量測距離 (mm)
TOF_MAX_RANGE_MM = 4000     # VL53L1x 最大量測距離 (mm)
TOF_EXPECTED_DESK_MM = (30, 500)  # 桌面上預期的距離範圍 (mm)

FLOW_NOISE_THRESHOLD = 200  # 光流靜止時的雜訊容許值 (delta 絕對值)
FLOW_SATURATION_VALUE = 0   # 完全無數據時的飽和值

# 測試持續時間預設值
DEFAULT_DURATION_S = 15

# 日誌取樣頻率
LOG_PERIOD_MS = 50  # 20 Hz

# ANSI 顏色碼
class Color:
    RESET  = "\033[0m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"

# ---------------------------------------------------------------------------
# 工具函式
# ---------------------------------------------------------------------------

def _supports_ansi() -> bool:
    """檢查終端是否支援 ANSI 色彩"""
    if os.name == "nt":
        # Windows Terminal / ConEmu 等現代終端支援 ANSI
        return os.environ.get("WT_SESSION") is not None or "ANSICON" in os.environ
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

USE_COLOR = _supports_ansi()

def c(color_code: str, text: str) -> str:
    """包裝帶有色彩的文字"""
    if USE_COLOR:
        return f"{color_code}{text}{Color.RESET}"
    return text

def banner(title: str) -> None:
    """輸出區段標題"""
    width = 60
    print()
    print(c(Color.CYAN, "═" * width))
    print(c(Color.CYAN + Color.BOLD, f"  {title}"))
    print(c(Color.CYAN, "═" * width))

def status(label: str, ok: bool, detail: str = "") -> None:
    """輸出測試結果行"""
    icon = c(Color.GREEN, "✔ PASS") if ok else c(Color.RED, "✘ FAIL")
    detail_str = f"  {c(Color.DIM, detail)}" if detail else ""
    print(f"  {icon}  {label}{detail_str}")

def warn(msg: str) -> None:
    """輸出警告"""
    print(f"  {c(Color.YELLOW, '⚠')}  {msg}")

# ---------------------------------------------------------------------------
# 數據收集器
# ---------------------------------------------------------------------------

class FlowDeckDataCollector:
    """收集 Flow Deck v2 的所有相關感測器數據"""

    def __init__(self):
        self.data = defaultdict(list)
        self.timestamps = []
        self._start_time = None
        self._sample_count = 0
        self._last_print_time = 0

    def _log_tof_callback(self, timestamp, data, logconf):
        """ToF 測距數據回呼"""
        if self._start_time is None:
            self._start_time = timestamp
        self.timestamps.append(timestamp)
        for key, value in data.items():
            self.data[key].append(value)
        self._sample_count += 1
        self._print_live(timestamp, data)

    def _log_flow_callback(self, timestamp, data, logconf):
        """光流數據回呼"""
        for key, value in data.items():
            self.data[key].append(value)

    def _log_pose_callback(self, timestamp, data, logconf):
        """位姿估計數據回呼"""
        for key, value in data.items():
            self.data[key].append(value)

    def _print_live(self, timestamp, data):
        """即時顯示數據（限制刷新率）"""
        now = time.time()
        if now - self._last_print_time < 0.5:
            return
        self._last_print_time = now

        zrange = self.data.get("range.zrange", [0])[-1]
        dx = self.data.get("motion.deltaX", [0])[-1]
        dy = self.data.get("motion.deltaY", [0])[-1]
        x = self.data.get("stateEstimate.x", [0])[-1]
        y = self.data.get("stateEstimate.y", [0])[-1]
        z = self.data.get("stateEstimate.z", [0])[-1]

        line = (
            f"\r  📡 samples={self._sample_count:>5d}  "
            f"z={zrange:>5.0f}mm  "
            f"dX={dx:>+6.0f}  dY={dy:>+6.0f}  "
            f"pos=({x:>+6.3f}, {y:>+6.3f}, {z:>+6.3f})  "
        )
        print(line, end="", flush=True)

    @property
    def sample_count(self):
        return self._sample_count


# ---------------------------------------------------------------------------
# 測試流程
# ---------------------------------------------------------------------------

class FlowDeckV2Tester:
    """Flow Deck v2 完整測試流程"""

    def __init__(self, uri: str, duration: float):
        self.uri = uri
        self.duration = duration
        self.collector = FlowDeckDataCollector()
        self.results = {}  # 測試名稱 -> (pass/fail, detail)
        self._interrupted = False

    def run(self):
        """執行完整測試"""
        self._print_header()

        # 初始化驅動程式
        banner("初始化無線通訊")
        print("  正在初始化 CRTP 驅動程式...")
        cflib.crtp.init_drivers()
        print(f"  目標 URI: {c(Color.BOLD, self.uri)}")

        # 連接
        banner("連接 Crazyflie")
        try:
            with SyncCrazyflie(self.uri, cf=Crazyflie(rw_cache="./cache")) as scf:
                print(f"  {c(Color.GREEN, '已連接!')}  韌體版本取得中...")

                # 取得韌體版本
                self._check_firmware(scf)

                # 偵測 Flow Deck
                self._detect_deck(scf)

                # 收集感測器數據
                self._collect_data(scf)

        except Exception as e:
            print(f"\n  {c(Color.RED, '連接失敗：')}{e}")
            print()
            print("  故障排除建議：")
            print("    1. 確認 Crazyflie 已開機（LED 閃爍）")
            print("    2. 確認 Crazyradio PA 已插入 USB")
            print("    3. 嘗試更換 Radio 頻道或地址")
            print("    4. 在 cfclient 中確認可以連接")
            return False

        # 分析數據
        self._analyze_data()

        # 輸出報告
        self._print_report()

        return all(ok for ok, _ in self.results.values())

    def _print_header(self):
        """輸出測試程式標題"""
        print()
        print(c(Color.BOLD + Color.CYAN, "╔══════════════════════════════════════════════════════════╗"))
        print(c(Color.BOLD + Color.CYAN, "║       Flow Deck v2 診斷與測試工具                       ║"))
        print(c(Color.BOLD + Color.CYAN, "║       Bitcraze Crazyflie Flow Deck v2 Diagnostic        ║"))
        print(c(Color.BOLD + Color.CYAN, "╠══════════════════════════════════════════════════════════╣"))
        print(c(Color.BOLD + Color.CYAN, "║  測試項目：                                             ║"))
        print(c(Color.BOLD + Color.CYAN, "║    ① 硬體偵測              ② ToF 測距感測器             ║"))
        print(c(Color.BOLD + Color.CYAN, "║    ③ 光流感測器 (PMW3901)  ④ 位置估計融合               ║"))
        print(c(Color.BOLD + Color.CYAN, "║    ⑤ 數據品質統計          ⑥ 數據收集穩定性             ║"))
        print(c(Color.BOLD + Color.CYAN, "╚══════════════════════════════════════════════════════════╝"))
        print()
        print(f"  測試時長: {self.duration}s | 取樣率: {1000 / LOG_PERIOD_MS:.0f} Hz")
        print(f"  時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def _check_firmware(self, scf: SyncCrazyflie):
        """取得並顯示韌體版本"""
        cf = scf.cf
        try:
            # 讀取韌體修訂參數
            fw_rev0 = cf.param.get_value("firmware.revision0")
            fw_rev1 = cf.param.get_value("firmware.revision1")
            print(f"  韌體修訂: {fw_rev0}")
        except Exception:
            print(f"  {c(Color.DIM, '（無法讀取韌體版本資訊）')}")

    def _detect_deck(self, scf: SyncCrazyflie):
        """偵測 Flow Deck v2 是否被系統識別"""
        banner("偵測擴充板 (Deck)")

        cf = scf.cf
        deck_attached = False
        deck_name = "bcFlow2"

        # 方法 1：透過參數系統查詢 deck 資訊
        try:
            # 嘗試讀取 deck.bcFlow2 參數（若已安裝，值通常非 0）
            val = cf.param.get_value("deck.bcFlow2")
            deck_attached = int(val) != 0
            if deck_attached:
                print(f"  偵測到 Flow Deck v2 (deck.bcFlow2 = {val})")
            else:
                print(f"  {c(Color.YELLOW, 'deck.bcFlow2 = 0 — Flow Deck v2 未偵測到')}")
        except Exception as e:
            print(f"  {c(Color.YELLOW, f'無法讀取 deck.bcFlow2 參數: {e}')}")
            print("  嘗試透過感測器數據判斷...")

        self.results["硬體偵測"] = (
            deck_attached,
            "deck.bcFlow2 已識別" if deck_attached else "未偵測到 Flow Deck v2"
        )

        if not deck_attached:
            warn("Flow Deck v2 可能未正確安裝。以下測試仍將繼續，但結果可能異常。")
            warn("請檢查：")
            warn("  • Deck 接腳是否確實插入 Crazyflie 底部擴充座")
            warn("  • Deck 方向是否正確（元件面朝下）")
            warn("  • 接腳是否有髒污或彎折")

    def _collect_data(self, scf: SyncCrazyflie):
        """配置日誌並收集感測器數據"""
        banner(f"數據收集 ({self.duration}s)")
        print("  正在設定日誌配置...")
        print()
        print("  📌 請確保 Crazyflie 靜止放在平坦表面上")
        print("     （避免手持或放在不穩定的物體上）")
        print()

        cf = scf.cf

        # --- LogConfig 1: ToF + Flow (高優先數據) ---
        lg_sensor = LogConfig(name="FlowSensor", period_in_ms=LOG_PERIOD_MS)
        lg_sensor.add_variable("range.zrange", "uint16_t")      # ToF 距離 (mm)
        lg_sensor.add_variable("motion.deltaX", "int16_t")       # 光流 X 位移
        lg_sensor.add_variable("motion.deltaY", "int16_t")       # 光流 Y 位移

        # --- LogConfig 2: 位姿估計 ---
        lg_pose = LogConfig(name="PoseEstimate", period_in_ms=LOG_PERIOD_MS)
        lg_pose.add_variable("stateEstimate.x", "float")
        lg_pose.add_variable("stateEstimate.y", "float")
        lg_pose.add_variable("stateEstimate.z", "float")

        # --- LogConfig 3: 其他輔助數據 ---
        lg_aux = LogConfig(name="AuxData", period_in_ms=LOG_PERIOD_MS)
        lg_aux.add_variable("stabilizer.roll", "float")
        lg_aux.add_variable("stabilizer.pitch", "float")

        # 註冊回呼
        cf.log.add_config(lg_sensor)
        cf.log.add_config(lg_pose)
        cf.log.add_config(lg_aux)

        lg_sensor.data_received_cb.add_callback(self.collector._log_tof_callback)
        lg_pose.data_received_cb.add_callback(self.collector._log_pose_callback)
        lg_aux.data_received_cb.add_callback(self.collector._log_flow_callback)

        # 啟動日誌
        lg_sensor.start()
        lg_pose.start()
        lg_aux.start()

        print(f"  日誌已啟動，收集 {self.duration} 秒數據...")
        print()

        # 安裝中斷處理
        original_handler = signal.getsignal(signal.SIGINT)
        def _handler(signum, frame):
            self._interrupted = True
            print(f"\n\n  {c(Color.YELLOW, '收到中斷信號，提前停止收集...')}")
        signal.signal(signal.SIGINT, _handler)

        # 等待收集
        start = time.time()
        while (time.time() - start) < self.duration and not self._interrupted:
            time.sleep(0.1)

        # 停止日誌
        lg_sensor.stop()
        lg_pose.stop()
        lg_aux.stop()

        # 恢復原始信號處理
        signal.signal(signal.SIGINT, original_handler)

        elapsed = time.time() - start
        print(f"\n\n  收集完成！共 {self.collector.sample_count} 筆樣本 "
              f"({elapsed:.1f}s)")

    def _analyze_data(self):
        """分析收集到的數據"""
        banner("數據品質分析")
        data = self.collector.data

        # === 測試 1: 樣本數 ===
        expected_samples = int(self.duration * (1000 / LOG_PERIOD_MS))
        actual_samples = self.collector.sample_count
        sample_ratio = actual_samples / max(expected_samples, 1)
        sample_ok = sample_ratio >= 0.8  # 允許 20% 的損失

        self.results["數據收集穩定性"] = (
            sample_ok,
            f"預期 {expected_samples} 筆, 實際 {actual_samples} 筆 "
            f"({sample_ratio:.0%})"
        )
        status(
            "數據收集穩定性",
            sample_ok,
            f"取得率 {sample_ratio:.0%} ({actual_samples}/{expected_samples})"
        )

        # === 測試 2: ToF 測距 ===
        zrange = data.get("range.zrange", [])
        if zrange:
            z_mean = statistics.mean(zrange)
            z_std = statistics.stdev(zrange) if len(zrange) > 1 else 0
            z_min = min(zrange)
            z_max = max(zrange)
            z_zeros = sum(1 for v in zrange if v == 0)
            z_zero_ratio = z_zeros / len(zrange)

            # 驗證條件
            z_in_range = TOF_EXPECTED_DESK_MM[0] <= z_mean <= TOF_EXPECTED_DESK_MM[1]
            z_stable = z_std < 50  # 靜止在桌面上標準差應小於 50mm
            z_no_dropout = z_zero_ratio < 0.1  # 零值（掉數據）比例應小於 10%
            z_ok = z_in_range and z_stable and z_no_dropout

            self.results["ToF 測距 (VL53L1x)"] = (
                z_ok,
                f"均值={z_mean:.1f}mm σ={z_std:.1f}mm "
                f"範圍=[{z_min}-{z_max}]mm 零值率={z_zero_ratio:.1%}"
            )
            status("ToF 測距 (VL53L1x)", z_ok)
            print(f"       均值: {z_mean:.1f} mm")
            print(f"       標準差: {z_std:.1f} mm")
            print(f"       範圍: [{z_min} ~ {z_max}] mm")
            print(f"       零值比例: {z_zero_ratio:.1%} ({z_zeros}/{len(zrange)})")
            if not z_in_range:
                warn(f"均值 {z_mean:.0f}mm 不在預期桌面範圍 "
                     f"{TOF_EXPECTED_DESK_MM} 內")
            if not z_stable:
                warn(f"標準差 {z_std:.1f}mm 過大 (> 50mm)，可能有干擾或反射問題")
            if not z_no_dropout:
                warn(f"零值比例 {z_zero_ratio:.1%} 過高，感測器可能有問題")
        else:
            self.results["ToF 測距 (VL53L1x)"] = (False, "未收到任何 range.zrange 數據")
            status("ToF 測距 (VL53L1x)", False, "無數據")

        print()

        # === 測試 3: 光流感測器 ===
        dx = data.get("motion.deltaX", [])
        dy = data.get("motion.deltaY", [])
        if dx and dy:
            dx_mean = statistics.mean(dx)
            dy_mean = statistics.mean(dy)
            dx_std = statistics.stdev(dx) if len(dx) > 1 else 0
            dy_std = statistics.stdev(dy) if len(dy) > 1 else 0
            dx_abs_max = max(abs(v) for v in dx)
            dy_abs_max = max(abs(v) for v in dy)

            # 靜止狀態：均值應接近 0，無巨大跳動
            flow_centered = abs(dx_mean) < 20 and abs(dy_mean) < 20
            flow_not_noisy = dx_std < FLOW_NOISE_THRESHOLD and dy_std < FLOW_NOISE_THRESHOLD
            flow_has_variance = dx_std > 0 or dy_std > 0  # 全部為 0 也不正常

            # 檢查是否有全零的情況（感測器可能沒接好）
            all_zero_dx = all(v == 0 for v in dx)
            all_zero_dy = all(v == 0 for v in dy)
            flow_not_dead = not (all_zero_dx and all_zero_dy)

            flow_ok = flow_centered and flow_not_noisy and flow_not_dead

            self.results["光流感測器 (PMW3901)"] = (
                flow_ok,
                f"dX: μ={dx_mean:+.1f} σ={dx_std:.1f} | "
                f"dY: μ={dy_mean:+.1f} σ={dy_std:.1f}"
            )
            status("光流感測器 (PMW3901)", flow_ok)
            print(f"       deltaX — 均值: {dx_mean:+.2f}, 標準差: {dx_std:.2f}, "
                  f"最大絕對值: {dx_abs_max}")
            print(f"       deltaY — 均值: {dy_mean:+.2f}, 標準差: {dy_std:.2f}, "
                  f"最大絕對值: {dy_abs_max}")
            if all_zero_dx and all_zero_dy:
                warn("光流 X/Y 全部為 0 — 感測器可能未工作或遮蔽")
            if not flow_centered:
                warn(f"靜止狀態下光流均值偏大 (dX={dx_mean:+.1f}, dY={dy_mean:+.1f})")
            if not flow_not_noisy:
                warn("光流雜訊過大，可能表面紋理不足或高度過高")
        else:
            self.results["光流感測器 (PMW3901)"] = (False, "未收到光流數據")
            status("光流感測器 (PMW3901)", False, "無數據")

        print()

        # === 測試 4: 位置估計融合 ===
        est_x = data.get("stateEstimate.x", [])
        est_y = data.get("stateEstimate.y", [])
        est_z = data.get("stateEstimate.z", [])
        if est_x and est_y and est_z:
            ex_std = statistics.stdev(est_x) if len(est_x) > 1 else 0
            ey_std = statistics.stdev(est_y) if len(est_y) > 1 else 0
            ez_mean = statistics.mean(est_z)
            ez_std = statistics.stdev(est_z) if len(est_z) > 1 else 0

            # 靜止狀態下位置估計應穩定
            pose_xy_stable = ex_std < 0.05 and ey_std < 0.05  # 5cm 以內的漂移
            pose_z_reasonable = 0.01 < ez_mean < 0.6  # Z 高度應在合理範圍（公尺）
            pose_z_stable = ez_std < 0.05

            pose_ok = pose_xy_stable and pose_z_reasonable and pose_z_stable

            self.results["位置估計融合 (EKF)"] = (
                pose_ok,
                f"X σ={ex_std:.4f}m | Y σ={ey_std:.4f}m | "
                f"Z μ={ez_mean:.4f}m σ={ez_std:.4f}m"
            )
            status("位置估計融合 (EKF)", pose_ok)
            print(f"       X 標準差: {ex_std:.4f} m")
            print(f"       Y 標準差: {ey_std:.4f} m")
            print(f"       Z 均值: {ez_mean:.4f} m (標準差: {ez_std:.4f} m)")
            if not pose_xy_stable:
                warn("XY 位置漂移偏大，EKF 可能未完全收斂")
            if not pose_z_reasonable:
                warn(f"Z 均值 {ez_mean:.4f}m 不在合理範圍")
        else:
            self.results["位置估計融合 (EKF)"] = (False, "未收到位姿數據")
            status("位置估計融合 (EKF)", False, "無數據")

        print()

        # === 測試 5: 姿態數據 (輔助驗證) ===
        roll = data.get("stabilizer.roll", [])
        pitch = data.get("stabilizer.pitch", [])
        if roll and pitch:
            r_mean = statistics.mean(roll)
            p_mean = statistics.mean(pitch)
            r_std = statistics.stdev(roll) if len(roll) > 1 else 0
            p_std = statistics.stdev(pitch) if len(pitch) > 1 else 0

            attitude_ok = abs(r_mean) < 10 and abs(p_mean) < 10  # 靜止時 < 10 度
            self.results["姿態感測 (輔助)"] = (
                attitude_ok,
                f"Roll: {r_mean:+.2f}° ± {r_std:.2f}° | "
                f"Pitch: {p_mean:+.2f}° ± {p_std:.2f}°"
            )
            status("姿態感測 (輔助)", attitude_ok,
                   f"Roll={r_mean:+.1f}°  Pitch={p_mean:+.1f}°")

    def _print_report(self):
        """輸出最終測試報告"""
        banner("測試結果總覽")

        all_pass = True
        for name, (ok, detail) in self.results.items():
            status(name, ok, detail)
            if not ok:
                all_pass = False

        print()
        if all_pass:
            print(c(Color.GREEN + Color.BOLD,
                     "  ╔═══════════════════════════════════════╗"))
            print(c(Color.GREEN + Color.BOLD,
                     "  ║   ✔ 所有測試通過！Flow Deck v2 正常   ║"))
            print(c(Color.GREEN + Color.BOLD,
                     "  ╚═══════════════════════════════════════╝"))
        else:
            failed = [n for n, (ok, _) in self.results.items() if not ok]
            print(c(Color.RED + Color.BOLD,
                     "  ╔═══════════════════════════════════════╗"))
            print(c(Color.RED + Color.BOLD,
                     "  ║   ✘ 有測試項目未通過                  ║"))
            print(c(Color.RED + Color.BOLD,
                     "  ╚═══════════════════════════════════════╝"))
            print()
            print("  失敗項目：")
            for name in failed:
                _, detail = self.results[name]
                print(f"    • {name}: {detail}")
            print()
            print("  建議排查步驟：")
            print("    1. 確認 Flow Deck v2 安裝方向正確（光流元件朝下）")
            print("    2. 確認接腳牢固、無鬆動")
            print("    3. 將 Crazyflie 放在有紋理的平坦表面上（避免純色光滑面）")
            print("    4. 確認地面距離在 10mm ~ 4000mm 範圍內")
            print("    5. 更新韌體至最新穩定版本")
            print("    6. 在 cfclient 的 Console 標籤頁查看是否有錯誤訊息")

        # 匯出 CSV
        self._export_csv()

        print()

    def _export_csv(self):
        """將收集的原始數據匯出為 CSV"""
        data = self.collector.data
        if not data:
            return

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"flowdeck_test_{timestamp_str}.csv"

        # 取得所有變數名稱
        all_keys = sorted(data.keys())
        max_len = max(len(v) for v in data.values()) if data else 0

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(",".join(all_keys) + "\n")
                for i in range(max_len):
                    row = []
                    for key in all_keys:
                        vals = data[key]
                        row.append(str(vals[i]) if i < len(vals) else "")
                    f.write(",".join(row) + "\n")

            print()
            print(f"  📄 原始數據已匯出至: {c(Color.BOLD, filename)}")
            print(f"     共 {max_len} 筆記錄, {len(all_keys)} 個變數")
        except IOError as e:
            warn(f"匯出 CSV 失敗: {e}")


# ---------------------------------------------------------------------------
# 主程式
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Flow Deck v2 診斷與測試工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  python test_flowdeck_v2.py
  python test_flowdeck_v2.py --uri radio://0/79/2M/E7E7E7E7E7
  python test_flowdeck_v2.py --duration 30
  python test_flowdeck_v2.py --uri radio://0/100/2M/E7E7E7E7E7 --duration 20
        """
    )
    parser.add_argument(
        "--uri",
        default="radio://0/79/2M/E7E7E7E7E7",
        help="Crazyflie 的 Radio URI (預設: radio://0/79/2M/E7E7E7E7E7)"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION_S,
        help=f"數據收集持續時間（秒）(預設: {DEFAULT_DURATION_S})"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="顯示詳細的 cflib 除錯日誌"
    )

    args = parser.parse_args()

    # 設定日誌等級
    log_level = logging.DEBUG if args.verbose else logging.ERROR
    logging.basicConfig(level=log_level)

    uri = uri_helper.uri_from_env(default=args.uri)

    tester = FlowDeckV2Tester(uri=uri, duration=args.duration)
    success = tester.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
