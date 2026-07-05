import logging
import sys
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncLogger import SyncLogger

# ==============================================================================
# 設定區 (Configuration)
# ==============================================================================
# 請根據您的接收器設定修改 URI (預設可能是 radio://0/80/2M)
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


def wait_for_position_estimator(scf):
    """
    等待 EKF (Extended Kalman Filter) 收斂。
    這對於搭載 Flow Deck 的無人機極度重要，未收斂就起飛會導致嚴重的暴衝。
    """
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
    """
    重置 EKF 狀態。確保起飛前的估測器沒有累積之前的誤差。
    """
    print('[2/5] 重置 EKF 估測器狀態...')
    cf = scf.cf
    cf.param.set_value('kalman.resetEstimation', '1')
    time.sleep(0.1)
    cf.param.set_value('kalman.resetEstimation', '0')
    time.sleep(2.0)
    print('[2/5] EKF 重置完成。')


def main():
    # 初始化通訊底層
    cflib.crtp.init_drivers()
    print(f'[0/5] 正在連接至 Crazyflie (URI: {URI})...')

    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
        print('[0/5] 連線成功！')
        
        # 1. 啟用 High Level Commander (給予高層次自主飛行權限)
        scf.cf.param.set_value('commander.enHighLevel', '1')

        # 2. 重置並等待 EKF 收斂 (防止一起飛就迷失方向)
        reset_estimator(scf)
        wait_for_position_estimator(scf)

        print('[3/5] 準備起飛，按下 Ctrl+C 可隨時緊急降落！')
        # 解鎖電機 (Arming)
        print('      正在解鎖無人機電機 (Arming)...')
        scf.cf.supervisor.send_arming_request(True)
        time.sleep(2.0) # 給予操作者反應時間與讓狀態就緒
        
        # 計算起飛與降落所需的時間 (Duration = Distance / Velocity)
        takeoff_duration = TARGET_HEIGHT / TAKEOFF_VELOCITY
        landing_duration = TARGET_HEIGHT / LANDING_VELOCITY

        try:
            # 3. 緩慢平滑起飛
            print(f'[4/5] 正在起飛至高度 {TARGET_HEIGHT}m (需時 {takeoff_duration:.1f} 秒)...')
            scf.cf.high_level_commander.takeoff(TARGET_HEIGHT, takeoff_duration)
            time.sleep(takeoff_duration) # 等待到達目標高度

            # 4. 懸停
            print(f'[5/5] 已到達 {TARGET_HEIGHT}m！開始懸停 {HOVER_DURATION} 秒...')
            time.sleep(HOVER_DURATION)

        except KeyboardInterrupt:
            # 緊急防呆機制：攔截 Ctrl+C
            print('\n[警告] 偵測到 Ctrl+C！啟動緊急降落程序！')
        
        finally:
            # 5. 確保無論如何都能平滑降落
            print(f'[降落] 正在降落至地面 (需時 {landing_duration:.1f} 秒)...')
            scf.cf.high_level_commander.land(0.0, landing_duration)
            time.sleep(landing_duration)
            
            # 徹底關閉馬達指令，避免落地後持續旋轉 (發送 stop 停止所有動作)
            scf.cf.high_level_commander.stop()
            
            # 上鎖電機 (Disarm)
            print('      正在上鎖無人機電機 (Disarm)...')
            scf.cf.supervisor.send_arming_request(False)
            print('[完成] 飛機已著陸，馬達已停機。')

if __name__ == '__main__':
    main()
