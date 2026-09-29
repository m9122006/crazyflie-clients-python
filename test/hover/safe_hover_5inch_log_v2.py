"""
safe_hover_5inch_log.py — v2
==============================================================
在原本的懸停測試基礎上，依照先前 PID/EKF 分析建議，補齊以下驗證用 log：

  1. Yaw 對稱性驗證（原本只 log roll/pitch，yaw 完全沒有）
     -> 用來確認 yaw_ki/yaw_kd 尚未跟著 roll/pitch 一起下修，
        是否造成 yaw 低頻擺動或回正過慢

  2. 懸停推力驗證（motor 實際輸出 + 電池電壓）
     -> 用來確認 posCtlPid.thrustBase=28000 是否貼近實際懸停推力，
        而不是猜測值

  3. 原始 Gyro（未濾波）
     -> 給事後 FFT 分析找震動主頻，是校正 filter cutoff frequency
        與評估 RPM notch filter 可行性的前置工作
        ⚠️ 見下方 VIBRATION 區塊註解，這裡有一個重要的頻寬限制说明

架構重點：
  - 所有 log 變數集中在 LOG_BLOCKS 宣告區定義，之後要加減變數只改這裡
  - 每個變數在加入前都會先檢查 TOC（韌體是否真的有這個 log 項目），
    沒有就跳過並印警告，不會讓整支程式因為一個變數名稱不存在而中斷
  - 每個 LogConfig 依然遵守 26 bytes 的封包大小上限（已在區塊設計時算好）
"""

import logging
import sys
import time
import csv
import datetime

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncLogger import SyncLogger

# ==============================================================================
# 設定區 (Configuration)
# ==============================================================================
URI = 'radio://0/79/2M/E7E7E7E7E7'

TARGET_HEIGHT = 0.4          # 公尺
TAKEOFF_VELOCITY = 0.15      # m/s，5吋機建議非常緩慢
LANDING_VELOCITY = 0.15      # m/s
HOVER_DURATION = 10.0        # 秒

EKF_THRESHOLD = 0.05         # EKF 收斂判定閾值

# ------------------------------------------------------------------------
# Log 區塊宣告區：要加減 log 變數只改這裡，不用動下面的邏輯
# 每個區塊的 bytes 總和必須 <= 26（float=4 bytes, uint16_t=2 bytes）
# ------------------------------------------------------------------------
LOG_BLOCKS = [
    {
        "name": "AttitudeAndAltitude",
        "period_ms": 20,          # 50Hz
        "purpose": "姿態與高度：驗證 rate loop 阻尼與高度控制",
        "variables": [
            ("stabilizer.thrust", "float"),
            ("stabilizer.roll", "float"),
            ("stabilizer.pitch", "float"),
            ("stateEstimate.z", "float"),
        ],
    },
    {
        "name": "YawSymmetryAndIntegral",
        "period_ms": 20,          # 50Hz
        "purpose": (
            "新增：yaw 對稱性驗證 + roll/pitch 積分項。"
            "之前分析指出 yaw_ki/yaw_kd 尚未跟著 roll/pitch 一起下修，"
            "這裡加入 stabilizer.yaw 觀察是否有低頻擺動或回正過慢"
        ),
        "variables": [
            ("stabilizer.yaw", "float"),
            ("pid_attitude.roll_outI", "float"),
            ("pid_attitude.pitch_outI", "float"),
            ("ctrltarget.z", "float"),
        ],
    },
    {
        "name": "HoverThrustValidation",
        "period_ms": 100,          # 10Hz，馬達輸出用來看平均值即可，不需要高頻
        "purpose": (
            "新增：驗證 posCtlPid.thrustBase=28000 是否貼近實際懸停推力。"
            "懸停穩定時把這裡的 m1~m4 平均值跟 thrustBase 比對，"
            "差距太大代表前饋沒抓準，高度控制會需要更多積分項去補償"
        ),
        "variables": [
            ("motor.m1", "uint16_t"),
            ("motor.m2", "uint16_t"),
            ("motor.m3", "uint16_t"),
            ("motor.m4", "uint16_t"),
            ("pm.vbat", "float"),
        ],
    },
    {
        "name": "VibrationRawGyro",
        "period_ms": 10,           # 100Hz，radio 頻寬能負擔的上限
        "purpose": (
            "新增：原始（未濾波）gyro，事後做 FFT 找震動主頻，"
            "是校正 filter cutoff 與評估 RPM notch filter 可行性的前置工作。"
            "⚠️ 100Hz 取樣的 Nyquist 上限只有 50Hz，"
            "如果大槳的震動主頻落在 80–150Hz（前面分析的推測範圍），"
            "這個取樣率會有 aliasing、抓不到真正的主頻。"
            "這裡先用 radio log 做「有沒有明顯震動」的粗略判斷；"
            "如果需要精確頻譜分析，建議改用 SD-card deck 做機載高頻錄製。"
        ),
        "variables": [
            ("gyro.x", "float"),
            ("gyro.y", "float"),
            ("gyro.z", "float"),
        ],
    },
]

# ⚠️ 頻寬提醒：以上 4 個區塊同時開啟時，粗估資料流量約在 3KB/s 上下，
# 已經接近 Crazyradio 穩定回傳的合理上限。如果實測時常看到 log 掉包、
# 數值出現跳空，建議：
#   (a) 先關掉 VibrationRawGyro 這個區塊單獨測，或
#   (b) 把 VibrationRawGyro 的 period_ms 從 10 調高到 20（50Hz）

logging.basicConfig(level=logging.ERROR)

# 飛行日誌資料（每一行對應一個時間點的完整快照）
flight_log_data = []
start_time_ms = 0

# 所有可能出現的欄位，先給預設值 0，避免某個區塊還沒收到第一筆資料時 CSV 缺欄位
current_data = {}
for block in LOG_BLOCKS:
    for var_name, _ in block["variables"]:
        current_data[var_name.replace('.', '_')] = 0


def _make_log_callback(is_master_clock):
    """
    產生對應每個 LogConfig 的 callback。
    is_master_clock=True 的那個區塊負責推進時間軸並寫入一筆完整快照，
    其餘區塊只負責更新 current_data，不重複寫入 row（避免同一時間點被寫成好幾行）。
    """
    def callback(timestamp, data, logconf):
        global start_time_ms
        for key, value in data.items():
            current_data[key.replace('.', '_')] = value

        if is_master_clock:
            if start_time_ms == 0:
                start_time_ms = timestamp
            time_s = (timestamp - start_time_ms) / 1000.0
            row = {'time_s': time_s, **current_data}
            flight_log_data.append(row)

    return callback


def variable_exists(toc, full_name):
    """檢查韌體 TOC 裡是否真的有這個 log 變數，避免加入不存在的變數導致連線失敗。"""
    if '.' not in full_name:
        return False
    group, name = full_name.split('.', 1)
    return group in toc.toc and name in toc.toc[group]


def build_log_configs(scf):
    """
    依照 LOG_BLOCKS 的宣告，逐一建立 LogConfig。
    每個變數加入前都先檢查 TOC，不存在就跳過並印警告，不會讓整支程式中斷。
    回傳已成功建立、且至少有一個有效變數的 LogConfig 清單。
    """
    toc = scf.cf.log.toc
    configs = []

    for i, block in enumerate(LOG_BLOCKS):
        log_config = LogConfig(name=block["name"], period_in_ms=block["period_ms"])
        added_any = False

        print(f'[Log 設定] 區塊「{block["name"]}」— {block["purpose"]}')
        for var_name, var_type in block["variables"]:
            if variable_exists(toc, var_name):
                log_config.add_variable(var_name, var_type)
                added_any = True
            else:
                print(f'      ⚠️ 略過不存在的 log 變數: {var_name}（可能是韌體版本沒有這個項目）')

        if added_any:
            scf.cf.log.add_config(log_config)
            # 第一個成功建立的區塊當作時間軸主時鐘
            is_master = (len(configs) == 0)
            log_config.data_received_cb.add_callback(_make_log_callback(is_master))
            configs.append(log_config)
        else:
            print(f'      ❌ 區塊「{block["name"]}」沒有任何有效變數，已跳過整個區塊。')

    return configs


def wait_for_position_estimator(scf):
    print('[1/5] 等待 EKF 定位估測器收斂...')
    log_config = LogConfig(name='Kalman Variance', period_in_ms=500)
    log_config.add_variable('kalman.varPX', 'float')
    log_config.add_variable('kalman.varPY', 'float')
    log_config.add_variable('kalman.varPZ', 'float')

    var_x_history = [1000] * 10
    var_y_history = [1000] * 10
    var_z_history = [1000] * 10

    with SyncLogger(scf, log_config) as logger:
        for log_entry in logger:
            data = log_entry[1]
            var_x_history.append(data['kalman.varPX'])
            var_x_history.pop(0)
            var_y_history.append(data['kalman.varPY'])
            var_y_history.pop(0)
            var_z_history.append(data['kalman.varPZ'])
            var_z_history.pop(0)

            diff_x = max(var_x_history) - min(var_x_history)
            diff_y = max(var_y_history) - min(var_y_history)
            diff_z = max(var_z_history) - min(var_z_history)

            print(f"      EKF 變異數跳動 -> X: {diff_x:.5f}, Y: {diff_y:.5f}, Z: {diff_z:.5f}")

            if diff_x < EKF_THRESHOLD and diff_y < EKF_THRESHOLD and diff_z < EKF_THRESHOLD:
                print('[1/5] EKF 已收斂！定位系統準備就緒。')
                break


def reset_estimator(scf):
    print('[2/5] 重置 EKF 估測器狀態...')
    cf = scf.cf
    cf.param.set_value('kalman.resetEstimation', '1')
    time.sleep(0.1)
    cf.param.set_value('kalman.resetEstimation', '0')
    time.sleep(2.0)
    print('[2/5] EKF 重置完成。')


def main():
    cflib.crtp.init_drivers()
    print(f'[0/5] 正在連接至 Crazyflie (URI: {URI})...')

    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
        print('[0/5] 連線成功！')

        # ========================================================
        # 關鍵參數覆寫區
        # ========================================================
        scf.cf.param.set_value('commander.enHighLevel', '1')
        scf.cf.param.set_value('powerDist.idleThrust', '3200')
        scf.cf.param.set_value('posCtlPid.thrustBase', '28000')
        scf.cf.param.set_value('posCtlPid.thrustMin', '15000')
        # ========================================================

        reset_estimator(scf)
        wait_for_position_estimator(scf)

        # ========================================================
        # 建立並啟動所有 log 區塊
        # ========================================================
        print('[設定日誌] 正在初始化非同步 PC 端日誌紀錄...')
        active_configs = build_log_configs(scf)
        if not active_configs:
            print('❌ [錯誤] 沒有任何 log 區塊成功建立，中止測試。')
            return

        for cfg in active_configs:
            cfg.start()
        print(f'[設定日誌] 共 {len(active_configs)} 個 log 區塊已開始紀錄！')

        print('[3/5] 準備起飛，按下 Ctrl+C 可隨時緊急降落！')
        print('      正在解鎖無人機電機 (Arming)...')
        scf.cf.supervisor.send_arming_request(True)
        time.sleep(2.0)

        takeoff_duration = TARGET_HEIGHT / TAKEOFF_VELOCITY
        landing_duration = TARGET_HEIGHT / LANDING_VELOCITY

        emergency = False
        try:
            print(f'[4/5] 正在起飛至高度 {TARGET_HEIGHT}m (需時 {takeoff_duration:.1f} 秒)...')
            scf.cf.high_level_commander.takeoff(TARGET_HEIGHT, takeoff_duration)
            time.sleep(takeoff_duration)

            print(f'[5/5] 已到達 {TARGET_HEIGHT}m！開始懸停 {HOVER_DURATION} 秒...')
            time.sleep(HOVER_DURATION)

        except KeyboardInterrupt:
            emergency = True
            print('\n🚨 [緊急停止] 偵測到 Ctrl+C！立即切斷所有動力並強制上鎖！')
            scf.cf.high_level_commander.stop()
            scf.cf.commander.send_stop_setpoint()
            scf.cf.supervisor.send_arming_request(False)

        finally:
            if not emergency:
                print(f'[降落] 正在降落至地面 (需時 {landing_duration:.1f} 秒)...')
                scf.cf.high_level_commander.land(0.0, landing_duration)
                time.sleep(landing_duration)

                scf.cf.high_level_commander.stop()
                print('      正在上鎖無人機電機 (Disarm)...')
                scf.cf.supervisor.send_arming_request(False)

            for cfg in active_configs:
                cfg.stop()
            print('[日誌] 日誌紀錄已停止。')

            timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"flight_log_{timestamp_str}.csv"

            if flight_log_data:
                fieldnames = ['time_s'] + list(current_data.keys())
                try:
                    with open(csv_filename, mode='w', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(flight_log_data)
                    print(f'✅ [成功] 飛行數據已儲存至: {csv_filename}')
                    print(f'      共 {len(fieldnames) - 1} 個 log 欄位: {", ".join(fieldnames[1:])}')
                except Exception as e:
                    print(f'❌ [錯誤] 寫入 CSV 檔案失敗: {e}')

            if emergency:
                print('💀 [緊急結束] 飛機已強制停機墜落，日誌已保全。')
            else:
                print('[完成] 飛機已著陸，馬達已停機。')


if __name__ == '__main__':
    main()
