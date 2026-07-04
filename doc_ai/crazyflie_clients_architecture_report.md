# crazyflie-clients-python 深度源碼架構分析報告

> **專案版本**: cfclient (cflib~=0.1.32, PyQt6~=6.7.1)  
> **分析日期**: 2026-04-19  
> **分析範圍**: 完整 src/cfclient/ 源碼樹

---

## 目錄

- [系統功能圖譜](#系統功能圖譜)
- [第一部分：功能模組對應 (Feature-to-Code Mapping)](#第一部分功能模組對應)
- [第二部分：系統測試功能與機制](#第二部分系統測試功能與機制)
- [第三部分：開發者除錯工具](#第三部分開發者除錯工具)
- [自定義建議：油箱液面顯示功能](#自定義建議油箱液面顯示功能)

---

## 系統功能圖譜

```
crazyflie-clients-python
│
├── 入口點 (Entry Points)
│   ├── cfclient    → src/cfclient/gui.py:main()           [GUI 主程式]
│   ├── cfheadless  → src/cfclient/headless.py:main()      [無頭模式]
│   ├── cfloader    → cfloader:main()                      [韌體燒錄]
│   └── cfzmq       → cfzmq:main()                        [ZMQ 服務]
│
├── 核心 UI 層 (src/cfclient/ui/)
│   ├── main.py          [MainUI - 主視窗，管理連線/電池/標籤]
│   ├── tab_toolbox.py   [TabToolbox - 所有分頁的超類別]
│   ├── connectivity_manager.py  [連線狀態機管理]
│   ├── pose_logger.py   [即時飛行姿態記錄]
│   ├── pluginhelper.py  [跨分頁依賴注入容器]
│   │
│   ├── tabs/ ─────────────────────────────────────────────
│   │   ├── FlightTab.py         [飛行控制 / 馬達監控]
│   │   ├── ConsoleTab.py        [韌體 printf 輸出 / 硬體測試]
│   │   ├── ParamTab.py          [參數讀寫 / 持久化]
│   │   ├── LogTab.py            [Log TOC 瀏覽器]
│   │   ├── LogBlockTab.py       [Log 區塊啟停 / 寫檔]
│   │   ├── PlotTab.py           [即時波形繪圖]
│   │   ├── TuningTab.py         [PID 滑桿調參]
│   │   ├── LEDRingTab.py        [LED 燈環控制]
│   │   ├── ColorLEDTab.py       [RGB LED 控制]
│   │   ├── CrtpSharkToolbox.py  [CRTP 封包嗅探器 ★開發者工具]
│   │   ├── locopositioning_tab.py [Loco 定位系統]
│   │   ├── lighthouse_tab.py    [Lighthouse 定位系統]
│   │   └── LogClientTab.py      [LogClient 設定]
│   │
│   ├── dialogs/
│   │   ├── bootloader.py        [韌體 OTA 燒錄對話框]
│   │   ├── logconfigdialogue.py [Log 組態配置]
│   │   ├── inputconfigdialogue.py [搖桿映射配置]
│   │   └── cf2config.py         [EEPROM 組態讀寫]
│   │
│   └── widgets/
│       ├── ai.py             [AttitudeIndicator - 人工地平線姿態儀]
│       ├── plotwidget.py     [PyQtGraph 波形顯示元件]
│       └── super_slider.py   [精密滑桿元件 (TuningTab 用)]
│
├── 工具層 (src/cfclient/utils/)
│   ├── config.py            [全域設定檔讀寫 (Singleton)]
│   ├── config_manager.py    [輸入映射設定管理]
│   ├── logconfigreader.py   [Log 配置檔讀寫 (JSON格式)]
│   ├── logdatawriter.py     [Log 資料寫入 CSV 檔]
│   ├── ui.py                [UI 工具 / 主題樣式系統]
│   ├── zmq_param.py         [ZMQ 外部參數存取介面]
│   ├── zmq_led_driver.py    [ZMQ LED 驅動]
│   └── input/               [搖桿/手柄輸入系統]
│       └── JoystickReader   [輸入設備讀取器]
│
└── 外部依賴 (cflib)
    ├── Crazyflie            [飛機物件 - CRTP 連線核心]
    ├── crazyflie.log        [Log 系統 (TOC + LogConfig)]
    ├── crazyflie.param      [Param 系統 (TOC + 讀寫)]
    ├── crazyflie.commander  [指令發送 (Setpoint)]
    └── crtp                 [CRTP 協議驅動層]
```

---

## 第一部分：功能模組對應

### 1.1 UI 分頁完整對應表

| 分頁名稱 | Python 檔案 | UI 檔案 | 核心功能 |
|---------|------------|---------|---------|
| **Console** | `ConsoleTab.py` | `consoleTab.ui` | 接收韌體 printf 輸出；含螺旋槳測試、電池測試、Assert Dump 按鈕 |
| **Flight Control** | `FlightTab.py` | `flightTab.ui` | 飛行模式切換、PID 微調、馬達 M1~M4 PWM 監控、Arm/Disarm、AttitudeIndicator |
| **Parameters** | `ParamTab.py` | `paramTab.ui` | 完整 Param TOC 樹狀瀏覽、讀寫、持久化存取、YAML 匯入匯出 |
| **Log TOC** | `LogTab.py` | `logTab.ui` | 顯示 Log TOC 中所有可記錄變數清單 |
| **Log Blocks** | `LogBlockTab.py` | `logBlockTab.ui` | Log 區塊啟停控制、CSV 寫檔開關 |
| **Plotter** | `PlotTab.py` | `plotTab.ui` | 選擇 LogConfig 並即時繪製波形圖 |
| **Tuning** | `TuningTab.py` | `tuningTab.ui` | Rate/Attitude/Position/Velocity PID 滑桿，支援持久化存儲 |
| **LED Ring** | `LEDRingTab.py` | `ledRingTab.ui` | LED 燈環效果控制 |
| **ColorLED** | `ColorLEDTab.py` | `colorLEDTab.ui` | RGB LED 個別顏色控制 |
| **Loco Positioning** | `locopositioning_tab.py` | `locopositioning_tab.ui` | UWB Loco 定位系統視覺化 |
| **Lighthouse** | `lighthouse_tab.py` | `lighthouse_tab.ui` | SteamVR Lighthouse 基站幾何校準 |
| **LogClient** | `LogClientTab.py` | `logClientTab.ui` | Log 用戶端組態 |
| **CRTP Sniffer** ★ | `CrtpSharkToolbox.py` | `crtpSharkToolbox.ui` | **開發者工具**：即時顯示全部 CRTP 封包收發 |

> ★ CrtpSharkToolbox 雖在 `tabs/` 目錄，但設計為 **Toolbox** (浮動停靠窗)，透過 `View → Toolboxes` 選單啟用。

---

### 1.2 CRTP 協議封包收發整合機制

CRTP 通訊的所有邏輯都封裝在 **cflib** 裡，cfclient 透過 **callback 機制** 與之整合，絕不直接操作封包。

#### 連線建立流程

```
用戶點擊 Connect
  → MainUI._connect()
    → cf.open_link(uri)          # cflib 內部
      → CRTP 驅動層 (RadioDriver/USBDriver)
        → cf.connected.emit(uri) # 連線成功
          → 所有分頁的 connected() 回呼
```

#### cflib 整合進 UI 更新迴圈的關鍵機制

cflib 的回呼函數在**背景執行緒**執行，直接更新 Qt 元件會崩潰。解決方案是 **cflib callback → PyQt Signal → Qt slot** 的橋接模式：

```python
# 正確模式（每個分頁都如此設計）：
class FlightTab(TabToolbox):
    _log_data_signal = pyqtSignal(int, object, object)  # ① 定義 Signal

    def connected(self, linkURI):
        lg = LogConfig("Motors", 100)
        lg.add_variable("motor.m1")
        self._helper.cf.log.add_config(lg)
        lg.data_received_cb.add_callback(
            self._log_data_signal.emit)   # ② cflib執行緒 → Signal發送
        lg.start()

    def _log_data_received(self, ts, data, logconf):  # ③ Qt主執行緒接收
        self.actualM1.setValue(data["motor.m1"])       # ④ 安全更新UI
```

**這個模式確保**：cflib 的 Log/Param 回呼（在 radio 接收執行緒中）透過 Qt 的執行緒安全 Signal/Slot 機制，切換到 UI 主執行緒再更新介面。

#### Log 系統的完整資料流

```
韌體 → CRTP Port 5 → cflib Log subsystem
  → LogConfig.data_received_cb.call(ts, data_dict, conf)
    → tab._log_data_signal.emit(ts, data, conf)    [背景執行緒]
      → tab._log_data_received(ts, data, conf)     [Qt主執行緒]
        → 更新 UI 元件显示值
```

#### Param 系統的回呼流程

```
連線完成後，cflib 自動讀取 Param TOC
  → cf.param.all_updated.add_callback(cb)   [所有 param 讀取完畢]
  → cf.param.add_update_callback(group, name, cb)  [特定 param 更新]
    → ParamChildItem.updated(name, value)   [更新模型資料]
      → model.proxy.dataChanged.emit(...)   [通知 Qt View 重繪]
```

---

### 1.3 參數系統 (Param) 與日誌系統 (Log) 的訂閱機制與快取邏輯

#### Param 系統

| 機制 | 實作位置 | 說明 |
|------|---------|------|
| **TOC 快取** | `cfclient.config_path/cache/` | 連線後從 cflib 讀取 Param TOC，快取到本地，下次連線免重讀 |
| **訂閱個別參數** | `cf.param.add_update_callback(group, name, cb)` | ParamChildItem 在 `set_toc()` 時對每個 Param 節點都訂閱更新 |
| **全部更新完畢** | `cf.param.all_updated.add_callback(cb)` | FlightTab 用此時機才啟用 Commander 面板（確保 deck param 已讀）|
| **持久化查詢** | `cf.param.persistent_get_state(name, cb)` | ParamTab 顯示 EEPROM 中的儲存值 |
| **批次請求更新** | `cf.param.request_update_of_all_params()` | ParamTab 在 `_connected()` 中主動觸發全部 Param 重新讀取 |

**GUI 端 Param 快取邏輯（ParamBlockModel）**：
```
set_toc() 時
  → 建立 ParamGroupItem / ParamChildItem 樹狀結構
  → 每個 ParamChildItem 訂閱對應 param 的更新回呼
  → 回呼觸發時更新 node.value，標記 is_updating=False
  → 觸發 proxy.dataChanged 讓 QTreeView 重繪
```

#### Log 系統

| 機制 | 實作位置 | 說明 |
|------|---------|------|
| **TOC 快取** | `cfclient.config_path/cache/` | 同 Param，Log TOC 也快取在本地 |
| **LogConfig 訂閱** | `cf.log.add_config(lg)` + `lg.start()` | 以 100~1000ms 週期從韌體串流指定變數 |
| **Block 事件通知** | `cf.log.block_added_cb.add_callback(cb)` | LogBlockTab / PlotTab 監聽新區塊加入 |
| **配置檔管理** | `LogConfigReader._connected()` | 連線後讀取 `config_path/log/*.json`，自動呼叫 `cf.log.add_config()` |
| **CSV 儲存** | `LogWriter` (logdatawriter.py) | LogBlockTab 中每個 LogBlockItem 都持有一個 LogWriter 物件 |

**LogConfigReader 的 JSON 格式**：
```json
{
  "logconfig": {
    "logblock": {
      "name": "MyConfig",
      "period": 100,
      "variables": [
        {"type": "TOC", "name": "pm.vbat", "fetch_as": "float", "stored_as": "float"}
      ]
    }
  }
}
```

---

## 第二部分：系統測試功能與機制

### 2.1 單元測試現況

> [!IMPORTANT]
> 經過完整搜尋，**crazyflie-clients-python 專案本身不包含任何單元測試檔案**（`tests/` 目錄不存在）。所有 `*test*` 命名的 `.py` 檔案都來自已安裝的第三方套件（vispy、zmq 等）。

**專案無測試的可能原因**：
- 大部分邏輯依賴 PyQt6 GUI 執行環境，難以做純單元測試
- 實際測試靠 cflib 的整合測試套件（位於 cflib 專案）
- UI 驗證依賴手動測試或硬體在迴路測試

#### 如果要執行 pytest（若日後加入測試）

```bash
# 安裝開發依賴
pip install pytest pytest-qt

# 執行所有測試（目前無任何測試，結果為空）
pytest

# 執行特定目錄
pytest tests/

# 以 verbose 模式
pytest -v

# 排除第三方套件目錄（若有衝突）
pytest --ignore=venv/
```

---

### 2.2 硬體測試功能：螺旋槳測試 (Propeller Test)

> [!IMPORTANT]
> cfclient 中的「馬達測試」並非透過 DShot/PWM 直接驅動馬達，而是透過 **Param 系統** 發送一個觸發旗標給韌體，讓韌體的健康管理模組執行測試。

#### 馬達/螺旋槳測試實作位置

**檔案**: `src/cfclient/ui/tabs/ConsoleTab.py` (第 81~86 行)

```python
# 螺旋槳測試 —— 設定 health.startPropTest = 1
self._propellerTestButton.clicked.connect(
    lambda enabled:
    self._helper.cf.param.set_value("health.startPropTest", '1'))

# 電池測試 —— 設定 health.startBatTest = 1
self._batteryTestButton.clicked.connect(
    lambda enabled:
    self._helper.cf.param.set_value("health.startBatTest", '1'))
```

#### 馬達測試的完整指令鏈

```
用戶點擊 ConsoleTab "Propeller Test"
  → cf.param.set_value("health.startPropTest", "1")
    → CRTP Port 2 (Param Write)
      → 韌體 health.c 中的 startPropTest 參數處理器
        → 韌體依序驅動 M1~M4 馬達
          → 結果透過 CRTP Console Port 0 輸出文字
            → ConsoleTab 顯示 "PASS" / "FAIL"
```

#### FlightTab 中的馬達監控（非測試）

`FlightTab.py` 透過 Log 系統**監控**馬達電流值（非直接驅動）：
```python
LOG_NAME_MOTOR_1 = 'motor.m1'
LOG_NAME_MOTOR_2 = 'motor.m2'
LOG_NAME_MOTOR_3 = 'motor.m3'
LOG_NAME_MOTOR_4 = 'motor.m4'
```
這些值透過 `LogConfig("Motors", period)` 以固定週期串流，顯示在 FlightTab 的四個 ProgressBar 上。

#### 其他硬體健康測試（ConsoleTab）

| 按鈕 | Param 指令 | 作用 |
|------|-----------|------|
| Propeller Test | `health.startPropTest = 1` | 依序測試 M1~M4 |
| Battery Test | `health.startBatTest = 1` | 測試電池輸出特性 |
| Task Dump | `system.taskDump = 1` | 輸出全部 RTOS 任務堆疊使用量 |
| Assert Info | `system.assertInfo` raw | 讀取最後一次 assert 記錄 |
| Storage Stats | `system.storageStats = 1` | 顯示 Flash 儲存統計 |

---

### 2.3 模擬與 Mock 機制

#### cfheadless — 無頭模式 (Headless Client)

**檔案**: `src/cfclient/headless.py`

`cfheadless` 是一個**不需要 GUI 視窗**的控制客戶端，透過指令列啟動：
```bash
cfheadless -u radio://0/10/250K -i PS3_Mode_1
```

它使用真實的 `Crazyflie` 物件和 `JoystickReader`，但沒有任何 PyQt6 元件。**適合在 CI 環境或 SSH 會話中測試通訊邏輯**。

#### ZMQ 外部控制服務 (cfzmq)

**檔案**: `examples/zmqsrvtest.py`

`cfzmq` 提供了一個 ZMQ 服務器介面，讓外部程式（包括測試腳本）可以不啟動 GUI 就控制 Crazyflie：

| ZMQ Port | 方向 | 功能 |
|----------|------|------|
| 2000 | REQ/REP | 控制指令 (scan/connect/disconnect/log/param) |
| 2001 | PUB/SUB | Log 資料訂閱 |
| 2002 | PUB/SUB | Param 更新通知 |
| 2003 | PUB/SUB | 連線狀態事件 |
| 2004 | PUSH | 傳送控制指令 (roll/pitch/yaw/thrust) |
| 1213 (ZMQ_PULL_PORT) | PULL | ZMQParamAccess 接收外部 param 設定 |

**如何用 zmqsrvtest.py 在「沒有硬體」時測試 GUI 反應**：

```bash
# 終端機 1：啟動 cfzmq 服務
cfzmq

# 終端機 2：執行測試腳本（可模擬送出各種 Log/Param 事件）
python examples/zmqsrvtest.py
```

#### 無 Mock 飛機機制的說明

> [!WARNING]
> cfclient 本身**沒有內建的虛擬飛機模擬器 (Simulator)**。但有以下替代方案：
> 1. **cflib 的 simlink driver**：cflib 支援 `sim://` URI，可連接到外部模擬器（如 Gazebo）
> 2. **cfzmq + 外部腳本**：用 Python 腳本透過 ZMQ 介面假裝送出 Log 資料
> 3. **cfheadless 模式**：可以測試所有非 GUI 的通訊邏輯

---

## 第三部分：開發者除錯工具

### 3.1 隱藏/顯性開發者工具清單

#### CRTP Sniffer (CrtpSharkToolbox) ★ 最重要的開發者工具

**位置**: `src/cfclient/ui/tabs/CrtpSharkToolbox.py`  
**開啟方式**: `View 選單 → Toolboxes → CRTP Sniffer`

這是專門為**通訊協議除錯**設計的 Toolbox，以表格形式顯示所有 CRTP 封包：

```
| ms     | Direction | Port/Chan | Data (hex)      |
|--------|-----------|-----------|-----------------|
| 1234   | IN        | 5/1       | 0a3c...         |
| 1235   | OUT       | 2/1       | 0102...         |
```

實作細節：
- 透過 `cf.packet_received.add_callback()` 和 `cf.packet_sent.add_callback()` 掛鉤
- **只在顯示時才啟用**（`enable()`/`disable()` 方法），避免效能開銷
- 可以將嗅探資料儲存為 CSV 到 `config_path/logdata/shark_data.csv`
- 過濾設定：排除 Port=15/Chan=3 的心跳封包（`masterCheck` 勾選框）

#### LogBlockDebugTab (已停用)

`LogBlockDebugTab.py` 存在但未在 `__init__.py` 的 `available` 清單中，是一個被停用的除錯分頁。

#### menuView → Tabs / Toolboxes 動態選單

任何分頁都可以在 **Tab 模式**（嵌入在主 TabBar）或 **Toolbox 模式**（可停靠浮動面板）之間切換，透過 `View` 選單操作。

#### Console Tab 中的特殊開發者功能

| 按鈕 | 功能 | 說明 |
|------|------|------|
| `Dump system load` | `system.taskDump = 1` | 輸出各 RTOS 任務的 CPU 使用率和堆疊統計 |
| `Dump assert information` | `system.assertInfo` (raw) | **在連線建立的第一個封包後就啟用**，即使韌體 assert 崩潰也能讀取 |
| `Storage stats` | `system.storageStats = 1` | 顯示 kVélocité Flash 區塊使用情況 |

---

### 3.2 日誌記錄與異常處理機制

#### Python logging 架構

每個模組都使用標準的 Python logging：
```python
import logging
logger = logging.getLogger(__name__)
```

應用程式允許透過 `cfheadless -d` 或 `cfclient` 視窗選單切換 DEBUG/INFO 層級。

#### 通訊中斷的錯誤捕捉流程

```
CRTP 鏈路中斷發生
  → cflib 內部偵測到連線逾時或封包錯誤
    → cf.connection_lost.add_callback(cb) 觸發
      → MainUI.connectionLostSignal.emit(linkURI, msg)    [cflib執行緒]
        → MainUI._connection_lost(linkURI, msg)           [Qt主執行緒]
          → QMessageBox.critical("Communication failure")  [顯示錯誤對話框]
          → uiState = UIState.DISCONNECTED
          → _update_ui_state()                             [重置所有UI元件狀態]
```

#### 三種連線終止路徑

| 事件 | cflib 回呼 | UI 處理 | 使用者反應 |
|------|-----------|---------|-----------|
| 正常斷線 | `cf.disconnected` | `_disconnected()` | 靜默切換到 Disconnected 狀態 |
| 連線中斷 | `cf.connection_lost` | `_connection_lost()` | **彈出錯誤對話框**，告知原因 |
| 連線失敗 | `cf.connection_failed` | `_connection_failed()` | **彈出錯誤對話框**，如 "Timeout" |

#### Log 子系統的錯誤處理

```python
# 每個分頁在啟動 LogConfig 時都有錯誤處理
lg.error_cb.add_callback(self._log_error_signal.emit)
# ...
def _logging_error(self, log_conf, msg):
    QMessageBox.about(self, "Log error",
        "Error when starting log config [%s]: %s" % (log_conf.name, msg))
```

常見 Log 錯誤原因：
- `KeyError`: 要訂閱的變數名不在 TOC 中（固件版本不匹配）
- `AttributeError`: TOC 尚未載入就嘗試訂閱

#### Config 系統的例外處理慣例

```python
# 典型模式 — 設定值不存在時靜默略過
try:
    value = Config().get("some_key")
except KeyError:
    value = default_value
```

`Config()` 是 Singleton，使用 JSON 格式儲存在 `~/.config/cfclient/config.json`（Windows: `%APPDATA%\cfclient\config.json`）。

---

## 自定義建議：油箱液面顯示功能

> [!TIP]
> 如果你的目標是在 GUI 中添加一個「油箱（電池/燃料）液面顯示」元件，以下是最佳修改路徑。

### 方案 A：擴展現有 FlightTab（最快）

**修改位置**: `src/cfclient/ui/tabs/FlightTab.py` + `src/cfclient/ui/tabs/flightTab.ui`

**步驟**：
1. 在 `flightTab.ui` 中新增一個 `QProgressBar`（縱向）或自定義 `QLabel`
2. 在 `FlightTab.connected()` 中擴展 LogConfig，加入你的液面感測器變數：
   ```python
   lg.add_variable("fuel.level", "float")   # 假設韌體有此 log 變數
   ```
3. 在 `_log_data_received()` 中更新顯示：
   ```python
   def _log_data_received(self, timestamp, data, logconf):
       # ...現有程式碼...
       if "fuel.level" in data:
           self.fuelBar.setValue(int(data["fuel.level"] * 100))
   ```

### 方案 B：建立獨立 FuelTab（最乾淨）

**新增步驟**：
1. 複製 `ExampleTab.py` → `FuelTab.py`
2. 設計 `fuelTab.ui`（在 Qt Designer 中）
3. 在 `__init__.py` 的 `available` 清單中加入 `FuelTab`
4. 系統會自動掃描並在 `View → Tabs` 選單中顯示

**參考 ExampleTab.py 的最小實作框架**：
```python
class FuelTab(TabToolbox, fuel_tab_class):
    _log_data_signal = pyqtSignal(int, object, object)

    def __init__(self, helper):
        super().__init__(helper, 'Fuel Level')
        self.setupUi(self)
        self._helper.cf.connected.add_callback(
            self.connectionFinishedSignal.emit)
        self._log_data_signal.connect(self._log_data_received)

    def connected(self, linkURI):
        lg = LogConfig("Fuel", 500)
        lg.add_variable("fuel.level", "float")
        self._helper.cf.log.add_config(lg)
        lg.data_received_cb.add_callback(self._log_data_signal.emit)
        lg.start()

    def _log_data_received(self, ts, data, logconf):
        if self.isVisible():
            self.fuelGauge.setValue(int(data["fuel.level"] * 100))
```

### 方案 C：在 MainUI 頂部狀態列添加（最顯眼）

**修改位置**: `src/cfclient/ui/main.py` + `src/cfclient/ui/main.ui`

主視窗頂部的 `batteryBar` (`QProgressBar`) 就是電池電量顯示的實作參考：

```python
# main.py _connected() 方法中：
lg = LogConfig("Battery", 1000)
lg.add_variable("pm.vbat", "float")
lg.add_variable("pm.state", "int8_t")
# 新增液面感測器
lg.add_variable("fuel.level", "float")      # ← 加在這裡
```

```python
# main.py _update_battery() 方法中：
def _update_battery(self, timestamp, data, logconf):
    self.batteryBar.setValue(int(data["pm.vbat"] * 1000))
    if "fuel.level" in data:
        self.fuelBar.setValue(int(data["fuel.level"] * 100))  # ← 加在這裡
```

### 建議修改的 UI 元件位置總結

| 優先級 | 位置 | 檔案 | 適合場景 |
|--------|------|------|---------|
| ⭐⭐⭐ | FlightTab 中 | `FlightTab.py` + `flightTab.ui` | 飛行時即時監視，與其他飛行數據同頁 |
| ⭐⭐ | 獨立 FuelTab | 新建 `FuelTab.py` + `fuelTab.ui` | 詳細分析、歷史記錄、獨立顯示 |
| ⭐ | MainUI 狀態列 | `main.py` + `main.ui` | 類似電池電量的全域顯示 |

---

## 測試執行指南

### 目前可用的測試工具

#### 1. ZMQ 測試腳本（不需要硬體）

```bash
# 視窗 1：啟動 cfzmq 服務
cfzmq

# 視窗 2：執行 ZMQ 測試腳本
python examples/zmqsrvtest.py
```

#### 2. 無頭模式測試

```bash
# 列出可用控制器
cfheadless --controllers

# 連線到模擬器（cflib 的 sim 驅動）
cfheadless -u sim://  -i PS3_Mode_1
```

#### 3. CRTP Sniffer 連線除錯

1. 啟動 cfclient
2. `View → Toolboxes → CRTP Sniffer`
3. 選取 `Master Check`
4. 連線到 Crazyflie
5. 即時查看所有封包交換

#### 4. Console Tab 硬體測試

連線後在 Console Tab 點擊：
- **Propeller Test**：測試馬達是否正常旋轉（需安全環境，螺旋槳會轉）
- **Battery Test**：測試電池容量特性
- **Task Dump**：查看韌體 RTOS 任務狀態

#### 5. 直接 pytest（目前無測試）

```bash
# 安裝pytest
pip install pytest pytest-qt

# 若日後加入測試，執行方式
cd e:\workspace\crazyflie-clients-python
pytest tests/ -v --tb=short
```

---

*報告由 Antigravity 深度源碼分析生成 | 2026-04-19*
