# Flow Deck v2 診斷與測試工具 (`test_flowdeck_v2.py`)

本測試腳本專為 Bitcraze Crazyflie 平台設計，用於在無人機地面靜止狀態下全面診斷並驗證新安裝或維修後的 **Flow Deck v2** 擴充板硬體功能。

---

## 📋 功能特色

腳本會依序執行以下 6 大項測試與驗證：

1. **硬體識別偵測 (Hardware Detection)**
   - 透過 Crazyflie 參數系統讀取 `deck.bcFlow2`，驗證韌體是否已正確識別 Flow Deck v2。
2. **ToF 測距感測器測試 (VL53L1x Laser Ranging)**
   - 訂閱 `range.zrange` (mm)。
   - 驗證桌面靜止時的測距高度是否在合理範圍（30 ~ 500 mm）、測距標準差（小於 50 mm）與數據丟失/零值比例（小於 10%）。
3. **光流感測器測試 (PMW3901 Optical Flow)**
   - 訂閱 `motion.deltaX` 與 `motion.deltaY`。
   - 驗證靜止狀態下的位移雜訊、中心偏移（平均值接近 0）以及避免感測器死機/全零無響應情況。
4. **EKF 狀態估計融合驗證 (Position Estimate)**
   - 訂閱 `stateEstimate.x`, `stateEstimate.y`, `stateEstimate.z`。
   - 驗證擴展卡爾曼濾波器 (EKF) 在靜止時是否良好收斂，XY 水平漂移標準差是否在 5 cm 以內。
5. **輔助姿態與數據取樣率監控**
   - 監控 `stabilizer.roll`, `stabilizer.pitch` 確定放置平穩。
   - 檢查通訊封包取得率（需達預期封包數之 80% 以上）。
6. **即時終端顯示與 CSV 數據匯出**
   - 終端機即時刷新顯示目前樣本數、高度、光流變化及即時位置座標。
   - 測試結束後自動將所有原始數據儲存為 `flowdeck_test_YYYYMMDD_HHMMSS.csv`，方便後續繪圖或深入分析。

---

## 🛠️ 環境與前置需求

1. **硬體需求**：
   - Crazyflie 2.x 或 Crazyflie Bolt（已安裝 Flow Deck v2 並完成開機校準）。
   - Crazyradio PA USB 接收器（插上電腦）。
   - 請將飛行器放置於**有紋理、平坦且光線充足的桌面上**（避免完全反光或純白光滑桌面）。
2. **軟體環境**：
   - Python 3.8+
   - `cflib` 函式庫：
     ```bash
     pip install cflib
     ```
   - Linux 需確認已配置 Crazyradio USB udev 權限。

---

## 🚀 操作方式

### 1. 切換至腳本目錄
```bash
cd /home/bill/桌面/klwang/workspace/Bill/crazyflie-clients-python/test/deck
```

### 2. 基本執行
使用預設 Radio URI (`radio://0/79/2M/E7E7E7E7E7`) 進行 15 秒數據測試：
```bash
python test_flowdeck_v2.py
```

### 3. 指定參數執行
- **指定 Crazyflie Radio 頻道與通訊位址**（如 Channel 80）：
  ```bash
  python test_flowdeck_v2.py --uri radio://0/80/2M/E7E7E7E7E7
  ```
- **自訂測試取樣持續時間**（例如測試 30 秒）：
  ```bash
  python test_flowdeck_v2.py --duration 30
  ```
- **開啟詳細除錯日誌 (Verbose)**：
  ```bash
  python test_flowdeck_v2.py --verbose
  ```

---

## 📊 參數說明

| 參數 | 預設值 | 說明 |
| :--- | :---: | :--- |
| `--uri` | `radio://0/79/2M/E7E7E7E7E7` | Crazyflie 連線 URI，亦支援從環境變數讀取 |
| `--duration` | `15` | 數據收集秒數（單位：秒） |
| `--verbose` | 關閉 | 開啟 cflib 底層 DEBUG 訊息輸出 |

---

## 🔍 測試結果與排錯建議

測試結束後終端機會印出完整測試評估清單：
- 若出現 **`✔ PASS`**：代表 Flow Deck v2 各感測器與 EKF 融合皆正常運作。
- 若出現 **`✘ FAIL`**，請參考以下排查指南：
  - **硬體偵測 FAIL**：確認擴充座接腳是否有彎折、虛焊或接觸不良，檢查 OneWire EEPROM 讀取是否正常。
  - **ToF 測距 FAIL**：檢查 VL53L1x 保護膜是否未撕除、表面是否有灰塵，確認飛機離桌子高度是否在 30 ~ 500 mm 內。
  - **光流感測器 FAIL**：檢查 PMW3901 鏡頭是否髒污或被遮擋，確保測試桌面具有足夠表面紋理與對比度。
  - **位置估計融合 FAIL**：確認飛機在測試期間完全保持靜止，未受到人為震動或風力干擾。
