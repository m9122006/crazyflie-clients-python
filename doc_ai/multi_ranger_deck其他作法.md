# you asked

message time: 2026-07-17 09:45:36

https://store.bitcraze.io/products/multi-ranger-deck，搜尋此產品的核心晶片與作法，如果我要自己製作或是找其他的替代品，可行嗎？

---

# chatgpt response

如果你的目標是**把 Multi-ranger 整合到自己的飛控（例如 H35 或 Crazyflie 衍生版）**，我認為**完全可行，而且沒有想像中困難**。

## Multi-ranger 的核心架構

Bitcraze 的 Multi-ranger 並不是特殊的雷射模組，它本質上就是：

```
                STM32 (Crazyflie)
                      │
                    I2C
                      │
              PCA9534 IO Expander
         ┌────┬────┬────┬────┬────┐
         │    │    │    │    │
     XSHUT XSHUT XSHUT XSHUT XSHUT
         │    │    │    │    │
     VL53L1X VL53L1X VL53L1X VL53L1X VL53L1X
      Front  Left   Right  Rear    Up
```

官方規格也直接列出：

- **5 × ST VL53L1X ToF 感測器**
- **PCA9534 I²C GPIO Expander**
- **1-Wire EEPROM（Deck 自動辨識）** ([Bitcraze](https://www.bitcraze.io/documentation/hardware/multi_ranger_deck/multi_ranger_deck-datasheet.pdf?utm_source=chatgpt.com))

---

## 為什麼需要 PCA9534？

很多人第一次看都會疑惑：

> 五顆 VL53L1X 都是 I²C，不是可以直接接嗎？

問題在於：

所有 VL53L1X 開機後都是 **同一個預設 I²C 位址**。

因此流程必須是：

```
Power ON

↓

全部 XSHUT 拉低

↓

只開第一顆

↓

改 I2C Address = 0x31

↓

關掉

↓

開第二顆

↓

改成 0x32

↓

...

↓

五顆全部完成
```

所以官方利用 **PCA9534** 控制五個 XSHUT。Bitcraze 的論壇也說明了這個初始化方式，並指出 Crazyflie 韌體會逐一喚醒感測器、設定新的 I²C 位址。([Bitcraze 论坛](https://forum.bitcraze.io/viewtopic.php?t=4085&utm_source=chatgpt.com))

---

# 如果自己做，我會怎麼設計？

我反而不一定照抄 PCA9534。

### 方案一：直接 MCU GPIO（推薦 ⭐⭐⭐⭐⭐）

如果你的 STM32 還有 GPIO：

```
STM32

GPIO1 ---> Front XSHUT

GPIO2 ---> Left

GPIO3 ---> Right

GPIO4 ---> Rear

GPIO5 ---> Up
```

優點：

- 少一顆 IC
- 成本更低
- 韌體更簡單
- 初始化速度更快

這是我最推薦的方式。

---

### 方案二：TCA6408A / PCA9555

如果 GPIO 不夠：

```
STM32

↓

I2C

↓

TCA6408A

↓

五個 XSHUT
```

和官方差不多。

---

### 方案三：I²C Multiplexer（通常不建議）

例如：

```
TCA9548A
```

每顆 VL53L1X 放不同 Channel。

優點：

不用改 Address。

缺點：

成本增加

PCB 更大

速度稍慢

通常沒必要。

---

# 可否不用 VL53L1X？

可以。

其實很多替代方案。

## 方案 A：VL53L4CD（我最推薦）

ST 新一代。

優點：

- 更快
- 更新率更高
- 成本比 VL53L1X 更低
- Driver 幾乎相容

如果重新設計，我會直接選它。

---

## 方案 B：VL53L5CX

8×8 ToF。

一顆：

```
64 pixels
```

以前：

```
Front

Left

Right

```

三顆。

現在：

一顆就能得到完整視野。

缺點：

比較貴。

Driver 複雜。

需要 RAM。

---

## 方案 C：VL53L8CX

甚至：

```
8x8

或

4x4
```

真正的小型 LiDAR。

做避障很棒。

---

## 方案 D：Benewake TFmini

量測遠。

但是：

太大。

5 吋無人機不適合。

---

# 如果是你的 H35

你之前提過：

- STM32G4
- ArduPilot
- DroneCAN
- Vision Module

我反而會建議：

```
            STM32

              │

      I2C1 400kHz

              │

   VL53L4CD ×5
```

不用 PCA9534。

GPIO：

```
PB0

PB1

PB2

PB10

PB11
```

控制五個 XSHUT。

---

# 如果是 5 吋 FPV

甚至：

```
Front

Left

Right
```

三顆就夠。

因為：

```
Rear

通常不用。

Up

幾乎不用。
```

---

# 如果你要商品化

我甚至不會做成 Crazyflie Deck。

而會做：

```
      Multi ToF Module

VL53L4CD x5

↓

STM32G030

↓

DroneCAN

↓

CAN
```

變成一個獨立模組。

ArduPilot：

```
DroneCAN Node
```

即可使用。

完全不用修改飛控 PCB。

---

## 依你的背景，我最推薦的方案

考慮到你最近在開發 Crazyflie、ArduPilot 與 DroneCAN，也規劃將模組商品化，我會建議不要直接複製 Bitcraze 的 Deck，而是做一個**獨立的 DroneCAN 多方向 ToF 模組**：

- **MCU：** STM32G030 或 STM32G431
- **感測器：** 5 × VL53L4CD（或視需求改用 VL53L1X）
- **匯流排：** I²C + MCU GPIO 控制各 XSHUT（省去 PCA9534）
- **輸出：** DroneCAN（或 UART/MAVLink 視系統需求）

這樣可以直接用在 Crazyflie、ArduPilot、PX4，甚至其他機器人平台，不受 Deck 機構限制，也更容易發展成自己的產品。

---
Powered by [AI Exporter](https://saveai.net)