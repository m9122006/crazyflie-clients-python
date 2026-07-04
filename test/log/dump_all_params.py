#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dump_all_params.py
==================
匯出 Crazyflie 所有參數 (包含出廠預設值) 至純文字檔。
"""

import logging
import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

# ────────── 正確的連線設定 ──────────
URI = 'radio://0/79/2M'
# ────────────────────────────────────

# 只顯示 WARNING 以上的 cflib 內部日誌，保持終端機乾淨
logging.basicConfig(level=logging.WARNING)

def main() -> None:
    print('=' * 60)
    print('  Crazyflie 參數完整匯出腳本')
    print(f'  目標 URI : {URI}')
    print('=' * 60)
    print()

    # 初始化 cflib 底層驅動
    cflib.crtp.init_drivers(enable_debug_driver=False)
    print(f'[連線] 正在嘗試連線到 {URI} ...')

    # 加入 rw_cache='./cache'，大幅加快 TOC 與參數下載速度，避免連線卡死
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache='./cache')) as scf:
        cf = scf.cf
        print('[連線] 連線成功！參數已同步完成。\n')
        
        output_filename = "all_params_dump.txt"
        print(f'[執行] 正在匯出所有參數至 {output_filename} ...')

        try:
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(f"# Crazyflie 參數匯出表\n")
                f.write(f"# 連線來源: {URI}\n")
                f.write(f"{'='*50}\n\n")
                
                # 取得參數的 TOC (目錄) 結構
                p_toc = cf.param.toc.toc
                total_params = 0
                
                # 走訪所有的參數群組 (group) 與變數名稱 (name)
                for group in sorted(p_toc.keys()):
                    f.write(f"[{group}]\n")
                    for name in sorted(p_toc[group].keys()):
                        full_name = f"{group}.{name}"
                        
                        try:
                            # 取得快取中的最新數值 (包含預設值)
                            value = cf.param.get_value(full_name)
                            f.write(f"  {full_name} = {value}\n")
                            total_params += 1
                        except Exception as e:
                            f.write(f"  {full_name} = <讀取失敗: {e}>\n")
                            
                    f.write("\n")
                    
            print(f'[完成] ✅ 成功匯出 {total_params} 個參數！請查看 {output_filename}。')
            
        except Exception as e:
            print(f'[錯誤] 匯出過程中發生錯誤: {e}')

if __name__ == '__main__':
    main()
