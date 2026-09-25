# you asked

message time: 2026-07-17 10:37:57

我要自己設計一塊擴充板，需要安裝flow deck v2(I2C), multi-ranger(I2C), 2個uart，至少4個free 的gpio腳位，還有5V，請根據此電路圖，列出目前沒用到的腳位，根據我的需求整理成一個表格

---

# gemini response

為了幫您設計這塊 Crazyflie Bolt 1.1 的自製擴充板，我們需要深入分析原理圖中的 **Expansion Port (P11 與 P6)** 腳位 ，比對哪些腳位已經被板載晶片（STM32F405RG  與 NRF51822 ）佔用，哪些是完全獨立且可自由分配的 **Free GPIO / I2C / UART 腳位**。

---

### 🔍 一、 擴充插槽腳位（P11 & P6）定義與佔用分析

Crazyflie 透過兩個 10-Pin 的插槽（**P11** 與 **P6**）引出擴充訊號 ：

#### 1. 左側 P11 插槽分析 
* **1 (`E_TX2`):** 連接到 STM32 的 **PA2** 。此腳位可用於 **USART2_TX** 。
* **2 (`E_RX2`):** 連接到 STM32 的 **PA3** 。此腳位可用於 **USART2_RX** 。
* **3 (`E_SCK`):** 連接到 STM32 的 **PA5**  (SPI1_SCK)。
* **4 (`E_MISO`):** 連接到 STM32 的 **PA6**  (SPI1_MISO)。
* **5 (`E_MOSI`):** 連接到 STM32 的 **PA7**  (SPI1_MOSI)。
* **6 (`E_NRF_IO2`):** 連接到 NRF51 的 **P0.16**  (屬於 nRF 晶片端，不適合作為 STM32 的直接 GPIO 控制，但可作為中斷/設定線)。
* **7 (`E_NRF_IO1`):** 連接到 NRF51 的 **P0.15**  (屬於 nRF 端，同上)。
* **8 (`E_OW/WKUP`):** 單總線（One-Wire）與喚醒腳，連接到 **PA0** 。此腳位可用作一個通用 **GPIO (PA0)**。
* **9 (`VCOM_EXP`):** 電池/USB 未經穩壓的原始電源輸出（4.5V ~ 5.5V 或 3.7V ~ 4.2V） 。
* **10 (`VUSB`):** USB 直連電源 。

#### 2. 右側 P6 插槽分析 
* **1 (`E_RX1`):** 連接到 STM32 的 **PA10** 。此腳位可用於 **USART1_RX** 。
* **2 (`E_TX1`):** 連接到 STM32 的 **PA9** 。此腳位可用於 **USART1_TX** 。
* **3 (`E_SDA`):** 連接到 STM32 的 **PB7** / **PB9**（透過 $2.8\text{V}$ 系統的 I2C 總線 `E_SDA`） 。此腳位可用作 **I2C1_SDA** 。
* **4 (`E_SCL`):** 連接到 STM32 的 **PB6** / **PB8**（透過 `E_SCL`） 。此腳位可用作 **I2C1_SCL** 。
* **5 (`E_CS3`):** 連接到 STM32 的 **PB5**  (可用作自由 GPIO / SPI CS)。
* **6 (`E_CS2`):** 連接到 STM32 的 **PA4**  (可用作自由 GPIO / SPI CS)。
* **7 (`E_CS1`):** 連接到 STM32 的 **PB4**  (可用作自由 GPIO / SPI CS)。
* **8 (`E_CS0`):** 連接到 STM32 的 **PC12**  (可用作自由 GPIO / SPI CS)。
* **9 (`VCC`):** 穩壓 $2.8\text{V}$ 電源輸出 。
* **10 (`GND`):** 系統地 。

---

### 📋 二、 擴充板設計腳位分配與規劃表

根據您的需求：
1.  **Flow Deck v2** 與 **Multi-ranger** 共享同一組 **I2C 總線** 。
2.  需要 **2 組獨立的 UART 通訊** 。
3.  需要至少 **4 個 Free GPIO**（用於片選 CS、中斷 INT、或開關） 。
4.  需要 **5V 電源** 。

以下為您規劃完美的腳位分配表：

| 功能需求 | 分配實體腳位名稱 | 實體插槽與 Pin 腳  | STM32 內部硬體映射  | 說明與備註 |
| :--- | :--- | :--- | :--- | :--- |
| **I2C_SCL** (共用) | `E_SCL` | **P6 - Pin 4**  | `I2C1_SCL` / `PB6`  | 連接至 Flow Deck 與 Multi-ranger  |
| **I2C_SDA** (共用) | `E_SDA` | **P6 - Pin 3**  | `I2C1_SDA` / `PB7`  | 連接至 Flow Deck 與 Multi-ranger  |
| **UART 1_TX** | `E_TX1` | **P6 - Pin 2**  | `USART1_TX` / `PA9`  | 第一組 UART 發送端  |
| **UART 1_RX** | `E_RX1` | **P6 - Pin 1**  | `USART1_RX` / `PA10`  | 第一組 UART 接收端  |
| **UART 2_TX** | `E_TX2` | **P11 - Pin 1**  | `USART2_TX` / `PA2`  | 第二組 UART 發送端  |
| **UART 2_RX** | `E_RX2` | **P11 - Pin 2**  | `USART2_RX` / `PA3`  | 第二組 UART 接收端  |
| **Free GPIO 1** | `E_CS0` | **P6 - Pin 8**  | `PC12`  | 完全自由定義，可用於中斷/致能  |
| **Free GPIO 2** | `E_CS1` | **P6 - Pin 7**  | `PB4`  | 完全自由定義，可用於中斷/致能  |
| **Free GPIO 3** | `E_CS2` | **P6 - Pin 6**  | `PA4`  | 完全自由定義，可用於中斷/致能  |
| **Free GPIO 4** | `E_CS3` | **P6 - Pin 5**  | `PB5`  | 完全自由定義，可用於中斷/致能  |
| **5V 電源輸入/輸出** | `VCOM_EXP` | **P11 - Pin 9**  | `VCOM`  | 當連線 USB 或裝上電池時，此處提供 5V 級未穩壓電源  |
| **3.3V / 2.8V 電源** | `VCC` | **P6 - Pin 9**  | `VCC_Regulated`  | Crazyflie 系統供電，額定 2.8V  |
| **系統地** | `GND` | **P6 - Pin 10**  | `GND`  | 訊號與供電共用參考地  |

---

### 💡 擴充板設計注意要點（避坑指南）

1.  **I2C 邏輯電平（2.8V 限制）：**
    Crazyflie Bolt 1.1 系統的 `VCC` 輸出是 **2.8V** 。Flow Deck 與 Multi-ranger 原廠設計皆可完美相容 2.8V I2C 邏輯。但若您的自製板需要介接其他標準 3.3V 甚至 5V 的 I2C 設備，請務必在 `E_SDA`/`E_SCL` 線路上加上**雙向電平轉換晶片（Level Shifter）**，避免損壞主板上的 STM32 晶片 。
2.  **5V 電源使用（VCOM）：**
    `VCOM_EXP` 的電壓取決於您的供電方式 。在插上 USB 時，它能穩定輸出約 **5.0V** 的電壓 ；但若僅使用鋰電池供電，此處電壓會直接下降到電池電壓（約 **3.7V ~ 4.2V**） 。若您的擴充模組必須有極穩定的 5V 運作（例如某些雷達或光敏傳感器），建議在擴充板上加裝一個微型 **5V 升降壓（Buck-Boost）DC-DC 晶片**接自 `VCOM`。

---
Powered by [AI Exporter](https://saveai.net)