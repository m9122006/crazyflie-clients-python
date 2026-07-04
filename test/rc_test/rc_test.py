#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import pygame
import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

# ================= 飛行與安全參數配置 =================
URI = 'radio://0/79/2M'

MAX_THRUST = 60000       # 測試期安全推力上限 (調高以確保足夠推力)
MAX_ROLL_PITCH = 20.0    # 最大姿態傾角 (度)
MAX_YAW_RATE = 100.0     # 最大偏航角速度 (度/秒)
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
BG_COLOR = (30, 30, 30)
PANEL_COLOR = (50, 50, 50)
TEXT_COLOR = (220, 220, 220)
GREEN = (46, 204, 113)
RED = (231, 76, 60)
DARK_RED = (150, 0, 0)
GRAY = (127, 140, 141)
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

def main():
    pygame.init()
    pygame.joystick.init()
    
    screen = pygame.display.set_mode((800, 500))
    pygame.display.set_caption("Rhema XBOX Control (Mode 1 - Right Thrust)")
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
        # 啟用 direct motor power control
        scf.cf.param.set_value('motorPowerSet.enable', '1')
        print("👉 按下 Xbox 手把 [LB 鍵] 解鎖")
        print("👉 按下 Xbox 手把 [RB 鍵] 緊急停止")
        
        prev_powers = (-1, -1, -1, -1)
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if btn_arm_rect.collidepoint(event.pos) and not emg_stop:
                        is_armed = not is_armed
                    elif btn_emg_rect.collidepoint(event.pos):
                        emg_stop = True
                        is_armed = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        emg_stop = True
                        is_armed = False

                elif event.type == pygame.JOYBUTTONDOWN:
                    if event.button == BTN_ARM and not emg_stop:
                        is_armed = not is_armed
                    elif event.button == BTN_EMG:
                        emg_stop = True
                        is_armed = False

            # 讀取數據
            yaw_scaled = joystick.get_axis(AXIS_YAW) * SCALE_YAW
            pitch_scaled = joystick.get_axis(AXIS_PITCH) * SCALE_PITCH
            roll_scaled = joystick.get_axis(AXIS_ROLL) * SCALE_ROLL
            thrust_scaled = joystick.get_axis(AXIS_THRUST) * SCALE_THRUST

            # 套用死區
            yaw_in = apply_deadband(yaw_scaled, DEADBAND)
            pitch_in = apply_deadband(pitch_scaled, DEADBAND)
            roll_in = apply_deadband(roll_scaled, DEADBAND)
            thrust_in = apply_deadband(thrust_scaled, DEADBAND)

            # 指令轉換
            roll_cmd = roll_in * MAX_ROLL_PITCH
            pitch_cmd = pitch_in * MAX_ROLL_PITCH
            yaw_cmd = yaw_in * MAX_YAW_RATE

            thrust_ratio = thrust_in if thrust_in > 0 else 0.0
            
            # 輸出邏輯
            if emg_stop:
                final_thrust = 0
            elif is_armed:
                IDLE_THRUST = 3000
                thrust_range = MAX_THRUST - IDLE_THRUST
                final_thrust = IDLE_THRUST + int(thrust_ratio * thrust_range)
            else:
                final_thrust = 0
                
            # 參考 test_motors_single.py 使用 motorPowerSet 直接驅動
            roll_mix = int(roll_in * 15000)
            pitch_mix = int(pitch_in * 15000)
            yaw_mix = int(yaw_in * 15000)
            
            def limit_thrust(v):
                return max(0, min(65535, int(v)))

            if final_thrust > 0:
                m1 = limit_thrust(final_thrust - pitch_mix + roll_mix + yaw_mix)
                m2 = limit_thrust(final_thrust - pitch_mix - roll_mix - yaw_mix)
                m3 = limit_thrust(final_thrust + pitch_mix - roll_mix + yaw_mix)
                m4 = limit_thrust(final_thrust + pitch_mix + roll_mix - yaw_mix)
            else:
                m1 = m2 = m3 = m4 = 0

            if (m1, m2, m3, m4) != prev_powers:
                scf.cf.param.set_value('motorPowerSet.m1', str(m1))
                scf.cf.param.set_value('motorPowerSet.m2', str(m2))
                scf.cf.param.set_value('motorPowerSet.m3', str(m3))
                scf.cf.param.set_value('motorPowerSet.m4', str(m4))
                prev_powers = (m1, m2, m3, m4)

            # --- GUI 繪製 ---
            screen.fill(BG_COLOR)
            
            # GUI 面板文字也根據 Mode 1 更新
            draw_joystick(screen, font, 100, 100, "LEFT (YAW / PITCH)", yaw_in, pitch_in)
            draw_joystick(screen, font, 500, 100, "RIGHT (ROLL / THRUST)", roll_in, thrust_in, is_thrust=True)

            # 繪製無人機馬達狀態示意圖 (X 型)
            pygame.draw.line(screen, GRAY, (360, 160), (440, 240), 4) # M4 <-> M2
            pygame.draw.line(screen, GRAY, (440, 160), (360, 240), 4) # M1 <-> M3
            pygame.draw.circle(screen, PANEL_COLOR, (400, 200), 12)
            pygame.draw.circle(screen, GRAY, (400, 200), 12, 2)
            
            # 顯示 M1~M4 當下的推力數值
            m4_surf = font.render(f"M4: {m4}", True, CYAN if m4 > 0 else GRAY)
            m1_surf = font.render(f"M1: {m1}", True, CYAN if m1 > 0 else GRAY)
            m3_surf = font.render(f"M3: {m3}", True, CYAN if m3 > 0 else GRAY)
            m2_surf = font.render(f"M2: {m2}", True, CYAN if m2 > 0 else GRAY)
            
            screen.blit(m4_surf, (330 - m4_surf.get_width()//2, 130))
            screen.blit(m1_surf, (470 - m1_surf.get_width()//2, 130))
            screen.blit(m3_surf, (330 - m3_surf.get_width()//2, 250))
            screen.blit(m2_surf, (470 - m2_surf.get_width()//2, 250))

            arm_color = GREEN if is_armed else GRAY
            pygame.draw.rect(screen, arm_color, btn_arm_rect, border_radius=8)
            text_surf = big_font.render("ARMED" if is_armed else "DISARMED", True, (255, 255, 255))
            screen.blit(text_surf, (btn_arm_rect.centerx - text_surf.get_width()//2, btn_arm_rect.centery - text_surf.get_height()//2))

            emg_color = DARK_RED if emg_stop else RED
            pygame.draw.rect(screen, emg_color, btn_emg_rect, border_radius=8)
            text_surf = big_font.render("EMG. STOP", True, (255, 255, 255))
            screen.blit(text_surf, (btn_emg_rect.centerx - text_surf.get_width()//2, btn_emg_rect.centery - text_surf.get_height()//2))

            info_text = f"Thrust: {final_thrust} | Roll: {roll_cmd:5.1f} | Pitch: {pitch_cmd:5.1f} | Yaw: {yaw_cmd:5.1f}"
            info_surf = font.render(info_text, True, TEXT_COLOR)
            screen.blit(info_surf, (400 - info_surf.get_width()//2, 30))

            if emg_stop:
                warn_surf = big_font.render("SYSTEM LOCKED. RESTART SCRIPT.", True, RED)
                screen.blit(warn_surf, (400 - warn_surf.get_width()//2, 470))
            elif not is_armed:
                warn_surf = font.render("PRESS LB TO ARM MOTORS", True, YELLOW)
                screen.blit(warn_surf, (400 - warn_surf.get_width()//2, 470))

            pygame.display.flip()
            clock.tick(50)

        print("🛑 關閉連線...")
        scf.cf.param.set_value('motorPowerSet.m1', '0')
        scf.cf.param.set_value('motorPowerSet.m2', '0')
        scf.cf.param.set_value('motorPowerSet.m3', '0')
        scf.cf.param.set_value('motorPowerSet.m4', '0')
        scf.cf.param.set_value('motorPowerSet.enable', '0')
        pygame.quit()

if __name__ == '__main__':
    main()
