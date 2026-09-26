# Crazyflie 測試腳本總覽與執行指南 (Test Directory Overview)

本文件整理了 `test/` 資料夾下所有測試腳本的功能與執行方法，以供未來參考。

## 1. 遙控與飛行測試 (RC & Flight Tests)

### `test/rc_test/rc_stabilized_test.py`
- **功能**：測試「自穩模式」(Self-stabilized mode) 下的手動搖桿控制。腳本使用 `pygame` 讀取 Xbox 手把 (預設 Mode 1：右手油門)，並將搖桿輸入轉換為 `roll`、`pitch`、`yaw rate` 與 `thrust` (推力) 的設定點 (setpoints)，然後傳送給 Crazyflie 的姿態穩定器。同時包含 ARM (解鎖) 與 EMG STOP (緊急停止) 安全機制。
- **執行環境要求**：需安裝 `pygame` 且電腦須接上 Xbox 手把。
- **執行方法**：
  ```bash
  python3 test/rc_test/rc_stabilized_test.py
  ```

### `test/rc_test/rc_test.py`
- **功能**：測試「無姿態穩定」(Bypass stabilizer) 的純手動直接馬達驅動。與自穩模式不同，此腳本讀取 Xbox 手把輸入後，會**直接計算出 M1~M4 的原始 PWM/推力比例**，並利用 `motorPowerSet` 參數強制驅動馬達。畫面中會透過 Pygame 顯示各馬達當下被分配的推力數值，主要用於驗證底層混控與馬達響應。
- **執行環境要求**：需安裝 `pygame` 且電腦須接上 Xbox 手把。
- **執行方法**：
  ```bash
  python3 test/rc_test/rc_test.py
  ```

---

## 2. 馬達硬體測試 (Motor Hardware Tests)

### `test/motor/test_motors_single.py`
- **功能**：提供一個基於 PyQt 的 GUI (圖形使用者介面) 工具，用於**單獨測試各個馬達 (M1~M4)** 的轉向與運作是否正常。使用者可以在介面上輸入指定的推力數值，點擊對應馬達的按鈕進行單獨啟動，內部利用 `motorPowerSet` 參數覆寫飛行控制器的輸出。
- **執行環境要求**：需安裝 `PyQt6` (或 PyQt5) 以及 `cflib`。
- **執行方法**：
  ```bash
  python3 test/motor/test_motors_single.py
  ```

### `test/motor/test_motors_interactive.py` ★ (推薦)
- **功能**：**互動式圖片點擊馬達測試工具**。移除了原本的 M1~M4 按鍵，改為將控制直接映射至左側 `motor.png` 俯視圖中的實體位置。
  - **點擊測試**：直接點擊圖中的 M1 (右前)、M2 (右後)、M3 (左後)、M4 (左前) 或對應的 ESC 方塊即可啟動該馬達。
  - **切換與急停**：再次點擊運轉中的馬達即可停止；支援按下 **ESC** 或**空白鍵**快速停止所有馬達。
  - **視覺回饋**：滑鼠懸停顯示藍色光環與文字導引；運轉中顯示綠色光環與推力即時狀態徽章。
  - **推力設定**：保留自訂推力數值輸入框，並新增 3000 / 5000 / 8000 / 12000 等快捷切換按鈕。
- **執行環境要求**：需安裝 `PyQt6` 以及 `cflib` (建議使用 `cf_env` 環境)。
- **執行方法**：
  ```bash
  python3 test/motor/test_motors_interactive.py
  ```

---

## 3. 擴充板檢測 (Deck Diagnostics)

### `test/deck/test_flowdeck_v2.py`
- **功能**：Flow Deck v2 (光流與測距擴充板) 的全自動診斷與測試工具。執行後會自動收集指定時間內的感測器數據：包含 VL53L1x (高度)、PMW3901 (光流) 及 EKF (位置估計融合)。收集完成後會進行合理性驗證 (如：雜訊大小、是否卡在 0、Z軸高度是否合理)，輸出彩色的終端機診斷報告，最後自動將收集的**原始數據匯出成 CSV 檔案**。
- **執行方法**：
  ```bash
  # 預設執行 (連線 radio://0/79/2M 並測試)
  python3 test/deck/test_flowdeck_v2.py
  
  # 指定 URI 與收集持續時間(秒)
  python3 test/deck/test_flowdeck_v2.py --uri radio://0/79/2M --duration 15
  ```

---

## 4. 系統與日誌 (System & Logging)

### `test/log/dump_all_params.py`
- **功能**：連接到 Crazyflie 後，從參數系統 (Parameter System) 中讀取並匯出所有的系統變數與參數 (包含出廠預設值)。適合用於確認韌體版本更新後的參數差異，或是備份當前飛機的配置狀態。
- **執行方法**：
  ```bash
  python3 test/log/dump_all_params.py
  ```
