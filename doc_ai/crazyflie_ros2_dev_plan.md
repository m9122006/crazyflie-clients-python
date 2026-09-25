# Crazyflie × ROS 2 完整開發計畫
## 平台：Ubuntu 22.04 + ROS 2 Humble

---

## 一、Crazyflie 支援 ROS 2 嗎？

**是的，官方與社群都支援。**

核心是 **Crazyswarm2**（原 Crazyswarm 的 ROS 2 移植版），由 TU Berlin 的 IMRCLab 維護，是
Bitcraze 官方推薦的 ROS 2 溝通中介層。ROS 1 已於 2025 年正式停止支援，Bitcraze 已將重心
轉移到 ROS 2 Humble / Jazzy。

主要的生態系元件：

| 元件 | 說明 | 連結 |
|---|---|---|
| **Crazyswarm2** | ROS 2 核心溝通 stack，支援單台到多台 | [IMRCLab/crazyswarm2](https://github.com/IMRCLab/crazyswarm2) |
| **CrazySim** | SITL 模擬器，ICRA 2024 論文成果，支援 Gazebo + MuJoCo | [gtfactslab/CrazySim](https://github.com/gtfactslab/CrazySim) |
| **ros_gz_crazyflie** | Gazebo Harmonic + ROS 2 橋接，已驗證 Humble/Jazzy/Ionic | [knmcguire/ros_gz_crazyflie](https://github.com/knmcguire/ros_gz_crazyflie) |
| **crazyflie_ros2_multiranger** | Multi-ranger 的 ROS 2 節點（含 SLAM、Nav2）| [knmcguire/crazyflie_ros2_multiranger](https://github.com/knmcguire/crazyflie_ros2_multiranger) |
| **sim_cf2** | 另一款 SITL，基於 FreeRTOS Linux Port | [CrazyflieTHI/sim_cf2](https://github.com/CrazyflieTHI/sim_cf2) |

---

## 二、整體架構圖

```
Ubuntu 22.04
└── ROS 2 Humble
    ├── Crazyswarm2          ← 溝通中介層（cflib backend）
    │   ├── crazyflie server（C++）
    │   └── Python wrapper
    ├── Gazebo Harmonic      ← 物理模擬
    │   └── CrazySim / ros_gz_crazyflie
    ├── slam_toolbox         ← SLAM（2D 建圖）
    ├── Nav2                 ← 自主導航
    └── RViz2               ← 可視化
```

---

## 三、開發環境安裝步驟

### 3.1 安裝 ROS 2 Humble

```bash
# 設定 locale
sudo apt update && sudo apt install locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

# 加入 ROS 2 apt repository
sudo apt install software-properties-common
sudo add-apt-repository universe
sudo apt update && sudo apt install curl -y
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# 安裝 ROS 2 Humble Desktop（含 RViz2、demo tool 等）
sudo apt update
sudo apt install ros-humble-desktop

# 安裝 build 工具
sudo apt install python3-colcon-common-extensions python3-rosdep
sudo rosdep init
rosdep update

# 加入 shell 啟動設定
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

> 官方文件：https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debians.html

---

### 3.2 安裝 Gazebo Harmonic（搭配 ROS 2 Humble 的模擬器）

```bash
# 安裝 Gazebo Harmonic
sudo apt-get install ros-humble-ros-gzharmonic

# 驗證安裝
gz sim --version
```

> Humble 預設配對 Gazebo Harmonic（gz-harmonic），不要裝 Gazebo Classic（gazebo11）。

---

### 3.3 安裝 Crazyswarm2 與 Crazyflie 相關工具

```bash
# 安裝系統依賴
sudo apt-get install libboost-program-options-dev libusb-1.0-0-dev
sudo apt-get install ros-humble-motion-capture-tracking
sudo apt-get install ros-humble-tf-transformations
sudo apt-get install ros-humble-teleop-twist-keyboard

# 安裝 Python 依賴
pip3 install cflib transform3D

# 建立 workspace
mkdir -p ~/crazyflie_ws/src
cd ~/crazyflie_ws/src

# clone 三個核心 repo
git clone https://github.com/IMRCLab/crazyswarm2 --recursive
git clone https://github.com/knmcguire/ros_gz_crazyflie
git clone https://github.com/knmcguire/crazyflie_ros2_multiranger

# clone Crazyflie 的 Gazebo 模型
mkdir -p ~/simulation_models
cd ~/simulation_models
git clone https://github.com/bitcraze/crazyflie-simulation.git
# ⚠️ 切換到 multiranger 分支（給 multiranger 用的模型）
git checkout gazebo-multiranger

# 設定 Gazebo 資源路徑（每次新開 terminal 都要 export，建議加到 .bashrc）
export GZ_SIM_RESOURCE_PATH="$HOME/simulation_models/crazyflie-simulation/simulator_files/gazebo/"
echo 'export GZ_SIM_RESOURCE_PATH="$HOME/simulation_models/crazyflie-simulation/simulator_files/gazebo/"' >> ~/.bashrc

# 安裝 rosdep 依賴並 build
cd ~/crazyflie_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --cmake-args -DBUILD_TESTING=ON
# build 會出現大量 warnings，只要沒有 'Failed' 就繼續

# 加入 workspace 設定
echo "source ~/crazyflie_ws/install/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

> 參考：https://www.bitcraze.io/2024/09/crazyflies-adventures-with-ros-2-and-gazebo/

---

### 3.4 安裝 SLAM Toolbox

```bash
sudo apt install ros-humble-slam-toolbox
```

---

### 3.5 安裝 Nav2（自主導航 stack）

```bash
sudo apt install ros-humble-navigation2 ros-humble-nav2-bringup
```

---

### 3.6 設定 Crazyradio 的 USB 權限（實機用）

```bash
# 讓一般使用者有權限存取 Crazyradio
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1915", ATTRS{idProduct}=="7777", MODE="0664", GROUP="plugdev"' \
  | sudo tee /etc/udev/rules.d/99-crazyradio.rules
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1915", ATTRS{idProduct}=="0101", MODE="0664", GROUP="plugdev"' \
  | sudo tee -a /etc/udev/rules.d/99-crazyradio.rules
sudo udevadm control --reload-rules
sudo usermod -aG plugdev $USER
# 登出再重新登入使生效
```

---

### 3.7 安裝 CrazySim（SITL 模擬器，選配但強烈建議）

CrazySim 讓你可以在不需要實體 Crazyflie 硬體的情況下，用完整的 crazyflie-firmware 跑 SITL。

```bash
# 安裝前置依賴
sudo apt install cmake build-essential

# clone CrazySim（包含 crazyflie-firmware 子模組）
cd ~
git clone https://github.com/gtfactslab/CrazySim.git --recursive
cd CrazySim/crazyflie-firmware

# 編譯 SITL firmware
mkdir -p sitl_make/build && cd sitl_make/build
cmake ../..
make all

# 安裝 cflib（source 版本，因為 pip 版本不支援 UDP driver）
cd ~
git clone https://github.com/bitcraze/crazyflie-lib-python.git
cd crazyflie-lib-python
pip install -e .
```

啟動單台 SITL 模擬：

```bash
# Terminal 1：啟動 Gazebo + SITL firmware
cd ~/CrazySim/crazyflie-firmware
bash tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh -m crazyflie -x 0 -y 0

# Terminal 2：用 cflib 連接（URI 改為 UDP）
# 把原本的 radio:// URI 改成 udp://127.0.0.1:19850
```

---

### 3.8 完整環境驗證

```bash
# 驗證 ROS 2 安裝
ros2 --version

# 驗證 Gazebo
gz sim shapes.sdf

# 驗證 Crazyswarm2 launch（模擬模式）
source ~/crazyflie_ws/install/setup.bash
ros2 launch crazyflie launch.py backend:=sim

# 在另一個 terminal 確認 topic 有出現
ros2 topic list
# 應看到 /cf1/odom、/tf、/cf1/cmd_vel_legacy 等
```

---

## 四、模擬工具比較

| 工具 | 特色 | 適合用途 |
|---|---|---|
| **Gazebo Harmonic + ros_gz_crazyflie** | 官方支援的 ROS 2 橋接，輕量，適合單機驗證 | 入門、sensor 測試 |
| **CrazySim（SITL）** | 跑真實 crazyflie-firmware，最貼近硬體行為，支援 Gazebo 和 MuJoCo | PID 調整、控制演算法、多機群飛 |
| **Crazyswarm2 內建 sim** | 純 Python 模擬，不需 Gazebo，快速但無物理模擬 | 快速邏輯驗證、swarm 行為測試 |
| **sim_cf2** | 基於 FreeRTOS Linux Port 的 SITL，支援 HITL | 研究室環境，深度韌體開發 |

**建議組合**：CrazySim（SITL）+ Gazebo Harmonic + Crazyswarm2（ROS 2 bridge）

---

## 五、可實做專案

以下依照由淺入深的順序排列，每個專案都可以先在模擬器（CrazySim/Gazebo）完成，再部署到實機。

---

### 專案 1：基本遙控 + ROS 2 Topic 監控（入門）

**目標**：熟悉 ROS 2 + Crazyswarm2 的基本操作流程

**所需硬體**：Crazyflie 2.1 + Crazyradio PA
**所需 deck**：Flow deck v2（光流定位，室內懸停用）

**步驟**：

```bash
# 1. 編輯 crazyflie 設定
nano ~/crazyflie_ws/src/crazyswarm2/crazyflie/config/crazyflies.yaml
# 設定你的 CF URI，例如 radio://0/80/2M/E7E7E7E7E7

# 2. 啟動 crazyflie server
ros2 launch crazyflie launch.py

# 3. 用鍵盤遙控
ros2 run teleop_twist_keyboard teleop_twist_keyboard \
  --ros-args --remap cmd_vel:=/cf1/cmd_vel

# 4. 監控 IMU 資料
ros2 topic echo /cf1/imu

# 5. 監控姿態（RPY）
ros2 topic echo /cf1/odom
```

**學習重點**：topic/service/action 的概念、tf 座標樹、RViz2 基本操作

---

### 專案 2：SLAM 建圖（核心目標）

**目標**：用 Multi-ranger deck 配合 slam_toolbox 建立 2D 地圖

**所需硬體**：Crazyflie 2.1 + Crazyradio PA
**所需 deck**：Multi-ranger deck + Flow deck v2

**架構**：

```
Crazyflie（Multi-ranger）
    ↓ /cf1/scan （LaserScan 格式）
slam_toolbox
    ↓ /map（OccupancyGrid）
RViz2
```

**模擬器測試**：

```bash
# Terminal 1：啟動 CrazySim SITL
cd ~/CrazySim/crazyflie-firmware
bash tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh -m crazyflie -x 0 -y 0

# Terminal 2：啟動 simple mapper（含 slam_toolbox）
source ~/crazyflie_ws/install/setup.bash
ros2 launch crazyflie_ros2_multiranger_bringup simple_mapper_simulation.launch.py

# Terminal 3：鍵盤遙控（按 't' 起飛）
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

**實機測試**：

```bash
# 修改 yaml 設定 URI 後 rebuild
ros2 launch crazyflie_ros2_multiranger_bringup simple_mapper_real.launch.py
```

**SLAM 參數調整（`slam_params.yaml`）**：

```yaml
slam_toolbox:
  ros__parameters:
    resolution: 0.05          # 地圖解析度（公尺），越小越細緻但越慢
    max_laser_range: 3.5      # Multi-ranger 最遠 4 m，設 3.5 保守
    map_update_interval: 0.2  # 更新頻率
    use_scan_matching: false  # Multi-ranger 點太稀疏，建議關閉 ray matching
```

**儲存地圖**：

```bash
ros2 run nav2_map_server map_saver_cli -f ~/my_map
# 產生 my_map.pgm + my_map.yaml
```

---

### 專案 3：Nav2 自主導航（SLAM + 導航）

**目標**：在已知地圖上讓 Crazyflie 自主規劃路徑並飛行到目標點

**前提**：專案 2 的地圖已建好（`my_map.yaml`）

**啟動步驟**：

```bash
# 啟動 Nav2（載入之前建的地圖）
ros2 launch crazyflie_examples multiranger_nav2_launch.py \
  map:=$HOME/my_map.yaml

# 在 RViz2 點選「Nav2 Goal」，設定目標點
# Crazyflie 會自動規劃路徑並繞開障礙物
```

**Nav2 關鍵參數（`nav2_params.yaml`）**：

```yaml
local_costmap:
  robot_radius: 0.1        # Crazyflie 機身半徑約 7cm，設 10cm 保守
  inflation_radius: 0.3    # 障礙物膨脹半徑

global_costmap:
  inflation_layer:
    inflation_radius: 0.4
```

---

### 專案 4：自主避障牆跟隨（Wall Following）

**目標**：實作自動沿牆壁飛行並建圖的行為

**架構**：Multi-ranger → 前後左右距離 → 控制決策 → cmd_vel

```bash
# 模擬器中啟動自動牆跟隨 + 建圖
ros2 launch crazyflie_ros2_multiranger_bringup wall_follower_mapper_simulation.launch.py

# 停止牆跟隨並降落
ros2 service call /crazyflie/stop_wall_following std_srvs/srv/Trigger
```

**可延伸方向**：

- 自己實作 wall following 邏輯（ROS 2 Python node）
- 加入動態障礙物閃避
- 結合 SLAM，做到「邊飛邊建圖」的完整 pipeline

---

### 專案 5：多機群飛協調（Swarm）

**目標**：同時控制 2〜4 台 Crazyflie，協調飛行隊形

**CrazySim 模擬 4 台**：

```bash
# 啟動 4 台 SITL
bash tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_multiagent_square.sh -n 4 -m crazyflie

# 設定 crazyflies.yaml 加入 4 台 URI（SITL 用 UDP port）
# cf1: udp://127.0.0.1:19850
# cf2: udp://127.0.0.1:19851
# cf3: udp://127.0.0.1:19852
# cf4: udp://127.0.0.1:19853

# 啟動 Crazyswarm2
ros2 launch crazyflie launch.py

# 執行群飛 GoTo 範例
ros2 run crazyflie_examples hello_world
```

**多機 SLAM 建圖**（進階）：

```bash
# 使用 mapMergeForMultiRobotMapping-ROS2 合併地圖
# 每台 CF 建自己的地圖，再 merge 成全局地圖
# 參考：https://github.com/hrnr/m-explore-ros2
```

---

### 專案 6：自訂 ROS 2 Node — EKF 狀態估計器橋接

**目標**：把 Crazyflie 的 IMU + Flow deck 資料接到 `robot_localization` 的 EKF 節點

**適合你的背景**（因為你已在做 H35 的 EKF/AKF 實作）

```bash
sudo apt install ros-humble-robot-localization
```

**節點架構**：

```
/cf1/imu  ──────────┐
/cf1/odom ──────────┼──→ ekf_node ──→ /odometry/filtered
/cf1/pose ──────────┘
```

**`ekf.yaml` 範例片段**：

```yaml
ekf_node:
  ros__parameters:
    frequency: 30.0
    sensor_timeout: 0.1
    two_d_mode: false
    odom0: /cf1/odom
    odom0_config: [true,true,true, false,false,false, true,true,true, false,false,false, false,false,false]
    imu0: /cf1/imu
    imu0_config: [false,false,false, true,true,true, false,false,false, true,true,true, false,false,false]
```

---

### 專案 7：PID 調整工具（CrazySim SITL 應用）

**目標**：用 CrazySim 在模擬中 live 調整 PID 參數，再部署到實機

因為你目前正在 debug H35 的 roll oscillation，這個工作流程可以直接用在 Crazyflie 的飛控調整上，
而且 CrazySim 支援完整的 crazyflie-firmware 參數系統。

```python
# 用 cflib 在模擬中 live 調整 PID
import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

URI = 'udp://127.0.0.1:19850'  # SITL

with SyncCrazyflie(URI) as scf:
    cf = scf.cf
    # 調整 roll PID
    cf.param.set_value('pid_attitude.roll_kp', 6.0)
    cf.param.set_value('pid_attitude.roll_ki', 3.0)
    cf.param.set_value('pid_attitude.roll_kd', 0.0)
```

---

## 六、學習資源與連結

| 資源 | 連結 |
|---|---|
| Crazyswarm2 官方文件 | https://imrclab.github.io/crazyswarm2/ |
| Crazyswarm2 ROS 2 Tutorial（SLAM + Nav2）| https://imrclab.github.io/crazyswarm2/tutorials.html |
| Bitcraze ROS 2 + Gazebo 完整教學 | https://www.bitcraze.io/2024/09/crazyflies-adventures-with-ros-2-and-gazebo/ |
| CrazySim GitHub | https://github.com/gtfactslab/CrazySim |
| CrazySim ICRA 2024 論文 | https://coogan.ece.gatech.edu/papers/pdf/llanes2024crazysim.pdf |
| crazyflie_ros2_multiranger | https://github.com/knmcguire/crazyflie_ros2_multiranger |
| ROS 2 Humble 安裝文件 | https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debians.html |
| Nav2 文件 | https://docs.nav2.org/ |
| slam_toolbox GitHub | https://github.com/SteveMacenski/slam_toolbox |

---

## 七、建議學習路徑

```
週 1-2：環境安裝 + ROS 2 基礎
  └─ 完成 3.1~3.8 的安裝
  └─ 跑通 Gazebo + Crazyswarm2 模擬
  └─ 完成 ROS 2 官方 beginner tutorial（pub/sub/service）

週 3-4：基本飛行控制（專案 1）
  └─ 模擬器中遙控起飛、移動
  └─ 熟悉 topic list/echo/hz 工具

週 5-6：SLAM 建圖（專案 2）
  └─ 先在 Gazebo 中完整跑通
  └─ 調整 slam_params.yaml
  └─ 儲存地圖

週 7-8：Nav2 自主導航（專案 3）
  └─ 載入地圖後設定導航目標
  └─ 調整 costmap 參數

週 9-10：實機部署
  └─ 設定 Crazyradio USB 權限
  └─ 把模擬中測試好的 config 移植到實機

週 11+：進階專案（依興趣選擇）
  └─ 多機群飛（專案 5）
  └─ 自訂 EKF 橋接（專案 6）
  └─ PID SITL 調整（專案 7）
```

---

## 八、注意事項與已知限制

- **Multi-ranger 的 SLAM 精度**：Multi-ranger 是 5 方向點雷射，不是旋轉雷達，SLAM 點雲稀疏，
  效果比傳統 LiDAR 差，需調整 `slam_toolbox` 的 `use_scan_matching: false`。

- **Gazebo 效能**：Gazebo Harmonic 較耗資源，同時模擬 4 台以上的 CF 需要中高端 CPU。
  若 GPU 支援 Vulkan，可加速渲染。

- **Crazyswarm2 的 warning**：build 時會有大量 std_err 輸出，這是已知問題，
  只要 build 沒有 `Failed` 就可以繼續，不影響功能。

- **CrazySim 使用 cflib source 版本**：不能直接 `pip install cflib`，必須從 source 安裝
  才能支援 UDP driver。

- **實機 SLAM + Nav2**：目前 Bitcraze 官方說明 SLAM + Nav2 在 Crazyflie 上「可行但不完美」，
  需要耐心調整參數，不要期待跟 TurtleBot3 一樣開箱即用的效果。
