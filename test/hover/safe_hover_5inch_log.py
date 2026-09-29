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
# 請根據您的接收器設定修改 URI
URI = 'radio://0/79/2M/E7E7E7E7E7'

# 飛行高度設定 (公尺)
TARGET_HEIGHT = 0.4

# 起飛與降落的預期速度 (m/s)，5吋機建議非常緩慢
TAKEOFF_VELOCITY = 0.15
LANDING_VELOCITY = 0.15

# 懸停時間 (秒)
HOVER_DURATION = 10.0

# EKF 收斂判定閾值 (變異數變化量低於此值代表穩定)
EKF_THRESHOLD = 0.05
# ==============================================================================

logging.basicConfig(level=logging.ERROR)

# 用來儲存飛行日誌的列表
flight_log_data = []
start_time_ms = 0
current_data = {
    'thrust': 0, 'roll_act': 0, 'pitch_act': 0,
    'roll_I_term': 0, 'pitch_I_term': 0,
    'z_target': 0, 'z_actual': 0
}

def log_callback_1(timestamp, data, logconf):
    """
    Log 區塊 1 的回呼函式 (姿態與推力)。我們以此作為儲存資料的時間基準。
    """
    global start_time_ms, current_data
    if start_time_ms == 0:
        start_time_ms = timestamp
    
    # 更新狀態
    if 'stabilizer.thrust' in data: current_data['thrust'] = data['stabilizer.thrust']
    if 'stabilizer.roll' in data: current_data['roll_act'] = data['stabilizer.roll']
    if 'stabilizer.pitch' in data: current_data['pitch_act'] = data['stabilizer.pitch']
    if 'stateEstimate.z' in data: current_data['z_actual'] = data['stateEstimate.z']
    
    # 計算相對時間 (秒)並儲存當下所有數值
    time_s = (timestamp - start_time_ms) / 1000.0
    row = {'time_s': time_s, **current_data}
    flight_log_data.append(row)

def log_callback_2(timestamp, data, logconf):
    """
    Log 區塊 2 的回呼函式 (控制器與 PID 積分項)。
    """
    global current_data
    if 'pid_attitude.roll_outI' in data: current_data['roll_I_term'] = data['pid_attitude.roll_outI']
    if 'pid_attitude.pitch_outI' in data: current_data['pitch_I_term'] = data['pid_attitude.pitch_outI']
    if 'ctrltarget.z' in data: current_data['z_target'] = data['ctrltarget.z']


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

            min_x, max_x = min(var_x_history), max(var_x_history)
            min_y, max_y = min(var_y_history), max(var_y_history)
            min_z, max_z = min(var_z_history), max(var_z_history)

            diff_x = max_x - min_x
            diff_y = max_y - min_y
            diff_z = max_z - min_z

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
        # 關鍵參數覆寫區 (避免 yaml 沒改到或 DSHOT 安全機制鎖死)
        # ========================================================
        # 1. 啟用 High Level Commander
        scf.cf.param.set_value('commander.enHighLevel', '1')
        
        # 2. 繞過 DSHOT 怠速超速保護 (極度重要，否則解鎖 2 秒後會強制熄火)
        # 降低飛控內建的起飛怠速門檻，確保大馬達轉速低於 3500 RPM 檢查上限
        scf.cf.param.set_value('powerDist.idleThrust', '3200')
        
        # 3. 針對 600g 重型無人機設定前饋推力 (Hover Thrust)
        # 若推力給太低，飛機會在地上掙扎累積 I-term 導致起飛歪斜！
        # (請根據您實際的懸停推力修改此數值)
        scf.cf.param.set_value('posCtlPid.thrustBase', '28000') 
        scf.cf.param.set_value('posCtlPid.thrustMin', '15000')
        # ========================================================

        reset_estimator(scf)
        wait_for_position_estimator(scf)

        # ========================================================
        # 設定非同步 Logger (Method B)
        # ========================================================
        print('[設定日誌] 正在初始化非同步 PC 端日誌紀錄...')
        
        # 由於 Crazyflie 單個 Log 區塊的最大負載為 26 bytes (大約 6 個 float)
        # 為了避免超出大小限制 (AttributeError: The log configuration is too large)，
        # 我們將變數分拆為兩個 LogConfig 同時紀錄
        
        dyn_log_config1 = LogConfig(name='FlightDynamics1', period_in_ms=20) 
        dyn_log_config1.add_variable('stabilizer.thrust', 'float') 
        dyn_log_config1.add_variable('stabilizer.roll', 'float')   
        dyn_log_config1.add_variable('stabilizer.pitch', 'float')  
        dyn_log_config1.add_variable('stateEstimate.z', 'float')   

        dyn_log_config2 = LogConfig(name='FlightDynamics2', period_in_ms=20)
        dyn_log_config2.add_variable('pid_attitude.roll_outI', 'float') 
        dyn_log_config2.add_variable('pid_attitude.pitch_outI', 'float')
        dyn_log_config2.add_variable('ctrltarget.z', 'float')      

        scf.cf.log.add_config(dyn_log_config1)
        dyn_log_config1.data_received_cb.add_callback(log_callback_1)
        
        scf.cf.log.add_config(dyn_log_config2)
        dyn_log_config2.data_received_cb.add_callback(log_callback_2)
        
        dyn_log_config1.start()
        dyn_log_config2.start()
        print('[設定日誌] 日誌開始紀錄！')

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
            # 緊急切斷：發送停機指令並立刻 Disarm
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
            
            # 停止日誌紀錄 (無論正常或緊急都會執行，保全墜機前的數據)
            dyn_log_config1.stop()
            dyn_log_config2.stop()
            print('[日誌] 日誌紀錄已停止。')
            
            # 將紀錄寫入 CSV 檔案
            timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"flight_log_{timestamp_str}.csv"
            
            if flight_log_data:
                fieldnames = ['time_s', 'thrust', 'roll_act', 'pitch_act', 'roll_I_term', 'pitch_I_term', 'z_target', 'z_actual']
                try:
                    with open(csv_filename, mode='w', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(flight_log_data)
                    print(f'✅ [成功] 飛行數據已儲存至: {csv_filename}')
                except Exception as e:
                    print(f'❌ [錯誤] 寫入 CSV 檔案失敗: {e}')

            if emergency:
                print('💀 [緊急結束] 飛機已強制停機墜落，日誌已保全。')
            else:
                print('[完成] 飛機已著陸，馬達已停機。')

if __name__ == '__main__':
    main()
