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

# 前進距離設定 (公尺) - 50cm = 0.5m
MOVE_DISTANCE = 0.5

# 起飛、前進與降落的預期速度 (m/s)，5吋機建議非常緩慢
TAKEOFF_VELOCITY = 0.15
MOVE_VELOCITY = 0.15
LANDING_VELOCITY = 0.15

# 起飛後懸停穩定時間 (秒)
HOVER_DURATION = 5.0

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


def safe_sleep(seconds):
    """
    安全睡眠，將長睡眠拆解為小段睡眠，以確保 KeyboardInterrupt 能被即時偵測與反應。
    """
    start_time = time.time()
    while time.time() - start_time < seconds:
        time.sleep(0.05)


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

        print('[3/5] 準備起飛，按下 Ctrl+C 可隨時「緊急停止（立即斷電）」！')
        # 解鎖電機 (Arming)
        print('      正在解鎖無人機電機 (Arming)...')
        scf.cf.supervisor.send_arming_request(True)
        safe_sleep(2.0) # 給予操作者反應時間與讓狀態就緒
        
        # 計算起飛、前進與降落所需的時間 (Duration = Distance / Velocity)
        takeoff_duration = TARGET_HEIGHT / TAKEOFF_VELOCITY
        move_duration = MOVE_DISTANCE / MOVE_VELOCITY
        landing_duration = TARGET_HEIGHT / LANDING_VELOCITY

        # 定義正方形的絕對頂點 (相對於起飛點 0,0,TARGET_HEIGHT)
        p1 = (MOVE_DISTANCE, 0.0, TARGET_HEIGHT)             # 頂點 1: (+0.5, 0.0)
        p2 = (MOVE_DISTANCE, MOVE_DISTANCE, TARGET_HEIGHT)    # 頂點 2: (+0.5, +0.5)
        p3 = (0.0, MOVE_DISTANCE, TARGET_HEIGHT)             # 頂點 3: (0.0, +0.5)
        p4 = (0.0, 0.0, TARGET_HEIGHT)                       # 頂點 4 / 原點: (0.0, 0.0)

        is_interrupted = False

        try:
            # 3. 緩慢平滑起飛
            print(f'[4/5] 正在起飛至高度 {TARGET_HEIGHT}m (需時 {takeoff_duration:.1f} 秒)...')
            scf.cf.high_level_commander.takeoff(TARGET_HEIGHT, takeoff_duration)
            safe_sleep(takeoff_duration) # 等待到達目標高度

            # 4. 起飛後懸停穩定
            print(f'[5/5] 已到達 {TARGET_HEIGHT}m！開始懸停 {HOVER_DURATION} 秒穩定狀態...')
            safe_sleep(HOVER_DURATION)

            # 1. 前往頂點 1 (+X)
            print(f'[第一邊] 前往頂點 1 {p1} (需時 {move_duration:.1f} 秒)...')
            scf.cf.high_level_commander.go_to(p1[0], p1[1], p1[2], 0, move_duration, relative=False)
            safe_sleep(move_duration)
            print('      到達頂點 1，懸停穩定 2.0 秒...')
            safe_sleep(2.0)

            # 2. 前往頂點 2 (+Y)
            print(f'[第二邊] 前往頂點 2 {p2} (需時 {move_duration:.1f} 秒)...')
            scf.cf.high_level_commander.go_to(p2[0], p2[1], p2[2], 0, move_duration, relative=False)
            safe_sleep(move_duration)
            print('      到達頂點 2，懸停穩定 2.0 秒...')
            safe_sleep(2.0)

            # 3. 前往頂點 3 (-X)
            print(f'[第三邊] 前往頂點 3 {p3} (需時 {move_duration:.1f} 秒)...')
            scf.cf.high_level_commander.go_to(p3[0], p3[1], p3[2], 0, move_duration, relative=False)
            safe_sleep(move_duration)
            print('      到達頂點 3，懸停穩定 2.0 秒...')
            safe_sleep(2.0)

            # 4. 回到原點 (-Y)
            print(f'[第四邊] 回到原點 {p4} (需時 {move_duration:.1f} 秒)...')
            scf.cf.high_level_commander.go_to(p4[0], p4[1], p4[2], 0, move_duration, relative=False)
            safe_sleep(move_duration)
            print('      回到原點，懸停穩定 2.0 秒...')
            safe_sleep(2.0)

        except KeyboardInterrupt:
            print('\n[警告] 偵測到 Ctrl+C！執行緊急停止程序！')
            is_interrupted = True
            # 立即發送緊急停止與上鎖電機
            scf.cf.supervisor.send_emergency_stop()
            scf.cf.supervisor.send_arming_request(False)
            print('      [緊急] 電機已切斷電源並上鎖！')
        
        finally:
            if not is_interrupted:
                # 5. 確保無論如何都能平滑降落
                print(f'[降落] 正在降落至地面 (需時 {landing_duration:.1f} 秒)...')
                scf.cf.high_level_commander.land(0.0, landing_duration)
                safe_sleep(landing_duration)
                
                # 徹底關閉馬達指令，避免落地後持續旋轉 (發送 stop 停止所有動作)
                scf.cf.high_level_commander.stop()
                
                # 上鎖電機 (Disarm)
                print('      正在上鎖無人機電機 (Disarm)...')
                scf.cf.supervisor.send_arming_request(False)
                print('[完成] 飛機已著陸，馬達已停機。')
            else:
                print('[完成] 程序已由使用者緊急中止。')

if __name__ == '__main__':
    main()
