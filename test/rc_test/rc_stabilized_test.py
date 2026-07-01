#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual joystick control test program in self-stabilized mode (自穩模式).
Sends roll, pitch, yaw rate, and thrust setpoints to the Crazyflie stabilizer.
"""

import sys
import pygame
import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

# ================= 飛行與安全參數配置 =================
URI = 'radio://0/79/2M'

# 在自穩模式下：
# thrust: 0 ~ 65535 (16位元整數)。
# 依據 V2306 2550KV (4S 電池, 5寸槳) 與 500g 機身計算：
# 滿推約 4.8kg，懸停比約 10.4%。考慮非線性推力曲線，估計起飛懸停點約在 13000 ~ 26000 之間。
# 基於安全，將測試用最大推力上限限制為 35000 (約 53% 輸出)
MAX_THRUST = 26000       # 測試用最大推力上限限制
MAX_ROLL_PITCH = 25.0    # 最大傾角限制 (度)，限制姿態避免過度傾斜
MAX_YAW_RATE = 150.0     # 最大偏航角速度 (度/秒)
DEADBAND = 0.1           # 搖桿死區


# ─── 強制設定為 Xbox 手把的 Mode 1 (右油門) ───
AXIS_YAW = 0      # 左搖桿 左右
AXIS_PITCH = 1    # 左搖桿 上下
AXIS_ROLL = 3     # 右搖桿 左右
AXIS_THRUST = 4   # 右搖桿 上下

SCALE_YAW = 1.0
SCALE_PITCH = -1.0 # 推上去是負值，需反轉
SCALE_ROLL = 1.0
SCALE_THRUST = -1.0 # 推上去是負值，需反轉

BTN_ARM = 4       # 解鎖鍵 (Xbox 左肩鍵 LB)
BTN_EMG = 5       # 緊急停止鍵 (Xbox 右肩鍵 RB)
# ======================================================

# --- GUI 顏色定義 ---
BG_COLOR = (24, 28, 36)
PANEL_COLOR = (38, 44, 54)
TEXT_COLOR = (235, 240, 245)
GREEN = (46, 204, 113)
RED = (231, 76, 60)
DARK_RED = (150, 0, 0)
GRAY = (100, 110, 120)
CYAN = (52, 152, 219)
YELLOW = (241, 196, 15)


def apply_deadband(value, deadband):
    if abs(value) < deadband:
        return 0.0
    sign = 1 if value > 0 else -1
    return sign * ((abs(value) - deadband) / (1.0 - deadband))


def draw_joystick(surface, font, x, y, name, val_x, val_y, is_thrust=False):
    pygame.draw.rect(surface, PANEL_COLOR, (x, y, 200, 200), border_radius=10)
    pygame.draw.rect(surface, GRAY, (x, y, 200, 200), 2, border_radius=10)
    
    pygame.draw.line(surface, GRAY, (x+100, y), (x+100, y+200), 1)
    pygame.draw.line(surface, GRAY, (x, y+100), (x+200, y+100), 1)
    
    text = font.render(name, True, TEXT_COLOR)
    surface.blit(text, (x + 100 - text.get_width()//2, y - 30))
    
    cursor_x = x + 100 + int(val_x * 100)
    cursor_y = y + 100 - int(val_y * 100)
    
    if is_thrust:
        pygame.draw.circle(surface, CYAN, (cursor_x, cursor_y), 10)
        pygame.draw.line(surface, CYAN, (x+100, y+100), (cursor_x, cursor_y), 3)
    else:
        pygame.draw.circle(surface, GREEN, (cursor_x, cursor_y), 10)
        pygame.draw.line(surface, GREEN, (x+100, y+100), (cursor_x, cursor_y), 3)


def main():
    pygame.init()
    pygame.joystick.init()
    
    screen = pygame.display.set_mode((800, 500))
    pygame.display.set_caption("Rhema XBOX Control (Stabilized Mode - Mode 1)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 20, bold=True)
    big_font = pygame.font.SysFont("arial", 30, bold=True)
    
    if pygame.joystick.get_count() == 0:
        print("❌ 找不到 Gamepad！請確認 Xbox 手把已連接。")
        sys.exit()
        
    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(f"✅ 偵測到手把: {joystick.get_name()}")

    is_armed = False
    emg_stop = False

    btn_arm_rect = pygame.Rect(150, 380, 200, 80)
    btn_emg_rect = pygame.Rect(450, 380, 200, 80)

    print(f"連線至 {URI} ...")
    cflib.crtp.init_drivers()
    
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
        print("✅ 連線成功！")
        
        # 確保關閉 direct motor power set，以使用韌體的自穩與PID迴圈
        scf.cf.param.set_value('motorPowerSet.enable', '0')
        print("👉 按下 Xbox 手把 [LB 鍵] 解鎖")
        print("👉 按下 Xbox 手把 [RB 鍵] 緊急停止")
        
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if btn_arm_rect.collidepoint(event.pos) and not emg_stop:
                        is_armed = not is_armed
                        # 發送解鎖指令
                        scf.cf.supervisor.send_arming_request(is_armed)
                    elif btn_emg_rect.collidepoint(event.pos):
                        emg_stop = True
                        is_armed = False
                        scf.cf.commander.send_stop_setpoint()

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        emg_stop = True
                        is_armed = False
                        scf.cf.commander.send_stop_setpoint()

                elif event.type == pygame.JOYBUTTONDOWN:
                    if event.button == BTN_ARM and not emg_stop:
                        is_armed = not is_armed
                        scf.cf.supervisor.send_arming_request(is_armed)
                        print(f"🔓 馬達解鎖狀態: {is_armed}")
                    elif event.button == BTN_EMG:
                        emg_stop = True
                        is_armed = False
                        scf.cf.commander.send_stop_setpoint()
                        print("🚨 緊急停止！")

            # 讀取遙控手把數值
            yaw_scaled = joystick.get_axis(AXIS_YAW) * SCALE_YAW
            pitch_scaled = joystick.get_axis(AXIS_PITCH) * SCALE_PITCH
            roll_scaled = joystick.get_axis(AXIS_ROLL) * SCALE_ROLL
            thrust_scaled = joystick.get_axis(AXIS_THRUST) * SCALE_THRUST

            # 套用搖桿死區 (防止搖桿微幅偏移造成誤動作)
            yaw_in = apply_deadband(yaw_scaled, DEADBAND)
            pitch_in = apply_deadband(pitch_scaled, DEADBAND)
            roll_in = apply_deadband(roll_scaled, DEADBAND)
            thrust_in = apply_deadband(thrust_scaled, DEADBAND)

            # 將搖桿輸入映射到自穩控制量
            # roll/pitch 控制目標姿態傾角 (度)
            roll_cmd = roll_in * MAX_ROLL_PITCH
            pitch_cmd = pitch_in * MAX_ROLL_PITCH
            # yaw rate 控制偏航角速度 (度/秒)
            yaw_cmd = yaw_in * MAX_YAW_RATE

            thrust_ratio = thrust_in if thrust_in > 0 else 0.0
            
            # 推力與解鎖安全邏輯
            if emg_stop:
                final_thrust = 0
            elif is_armed:
                # 配合 all_params_dump.txt 中的 powerDist.idleThrust = 7000 設定怠速推力
                IDLE_THRUST = 5000
                thrust_range = MAX_THRUST - IDLE_THRUST
                final_thrust = IDLE_THRUST + int(thrust_ratio * thrust_range)
            else:
                final_thrust = 0
                
            # 自穩模式核心：透過 send_setpoint 向 Crazyflie 的 Stabilizer 任務 (優先級 5) 發送姿態指令。
            # 韌體會以 1000Hz 頻率運算 PID 自穩控制馬達。
            if is_armed and not emg_stop:
                scf.cf.commander.send_setpoint(roll_cmd, pitch_cmd, yaw_cmd, final_thrust)
            else:
                # 未解鎖或緊急停止時，發送 0 推力與 0 姿態
                scf.cf.commander.send_setpoint(0.0, 0.0, 0.0, 0)

            # --- GUI 繪製 ---
            screen.fill(BG_COLOR)
            
            # 繪製左右搖桿示意圖
            draw_joystick(screen, font, 100, 100, "LEFT (YAW / PITCH)", yaw_in, pitch_in)
            draw_joystick(screen, font, 500, 100, "RIGHT (ROLL / THRUST)", roll_in, thrust_in, is_thrust=True)

            # 繪製控制模式說明與參數狀態
            mode_surf = big_font.render("MODE: SELF-STABILIZED (ATTITUDE)", True, GREEN if is_armed else GRAY)
            screen.blit(mode_surf, (400 - mode_surf.get_width()//2, 320))

            arm_color = GREEN if is_armed else GRAY
            pygame.draw.rect(screen, arm_color, btn_arm_rect, border_radius=8)
            text_surf = big_font.render("ARMED" if is_armed else "DISARMED", True, (255, 255, 255))
            screen.blit(text_surf, (btn_arm_rect.centerx - text_surf.get_width()//2, btn_arm_rect.centery - text_surf.get_height()//2))

            emg_color = DARK_RED if emg_stop else RED
            pygame.draw.rect(screen, emg_color, btn_emg_rect, border_radius=8)
            text_surf = big_font.render("EMG. STOP", True, (255, 255, 255))
            screen.blit(text_surf, (btn_emg_rect.centerx - text_surf.get_width()//2, btn_emg_rect.centery - text_surf.get_height()//2))

            # 顯示當前發送的指令數值
            info_text = f"Thrust: {final_thrust:5d} | Roll: {roll_cmd:5.1f}° | Pitch: {pitch_cmd:5.1f}° | YawRate: {yaw_cmd:5.1f}°/s"
            info_surf = font.render(info_text, True, TEXT_COLOR)
            screen.blit(info_surf, (400 - info_surf.get_width()//2, 30))

            if emg_stop:
                warn_surf = big_font.render("🚨 EMERGENCY STOPPED! RESTART SCRIPT 🚨", True, RED)
                screen.blit(warn_surf, (400 - warn_surf.get_width()//2, 470))
            elif not is_armed:
                warn_surf = font.render("PRESS [LB] OR CLICK 'DISARMED' TO ARM MOTORS", True, YELLOW)
                screen.blit(warn_surf, (400 - warn_surf.get_width()//2, 470))
            else:
                warn_surf = font.render("FLYING ACTIVE. BE CAREFUL OF DRIFT WITHOUT DECK!", True, GREEN)
                screen.blit(warn_surf, (400 - warn_surf.get_width()//2, 470))

            pygame.display.flip()
            # 以 50Hz 頻率更新並發送 setpoint，防止飛控因超時停止馬達
            clock.tick(50)

        print("🛑 關閉連線...")
        scf.cf.commander.send_stop_setpoint()
        pygame.quit()


if __name__ == '__main__':
    main()
