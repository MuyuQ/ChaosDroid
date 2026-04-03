"""Mock 设备执行器."""
import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from app.executors.base import (
    BaseDeviceExecutor,
    ExecutorMode,
    MockScenario,
    StorageInfo,
    BatteryInfo,
    ShellResult,
    MonkeyResult
)


class MockDeviceState:
    """Mock 设备状态管理"""

    def __init__(self, serial: str, scenario: MockScenario = MockScenario.normal):
        self.serial = serial
        self.scenario = scenario
        self.online = True
        self.battery_level = 100
        self.storage_total = 32 * 1024 * 1024 * 1024  # 32GB
        self.storage_available = 10 * 1024 * 1024 * 1024  # 10GB
        self.boot_completed = True
        self.network_connected = True
        self.stress_processes: List[str] = []
        self.properties: Dict[str, str] = {
            "ro.product.model": "Mock Device",
            "ro.product.brand": "MockBrand",
            "ro.build.version.release": "14",
            "ro.build.version.sdk": "34",
        }

        # 根据场景初始化状态
        self._apply_scenario(scenario)

    def _apply_scenario(self, scenario: MockScenario):
        """根据场景设置初始状态"""
        if scenario == MockScenario.offline:
            self.online = False
        elif scenario == MockScenario.low_battery:
            self.battery_level = 15
        elif scenario == MockScenario.storage_full:
            self.storage_available = 50 * 1024 * 1024  # 50MB
        elif scenario == MockScenario.boot_timeout:
            self.boot_completed = False
        elif scenario == MockScenario.network_error:
            self.network_connected = False

    def apply_injection(self, fault_type: str, params: Dict[str, Any]):
        """应用故障注入"""
        if fault_type == "storage_pressure":
            pressure_mb = params.get("pressure_mb", 1000)
            pressure_bytes = pressure_mb * 1024 * 1024
            self.storage_available = max(0, self.storage_available - pressure_bytes)
        elif fault_type == "low_battery":
            self.battery_level = params.get("level", 10)
        elif fault_type == "network_jitter":
            self.network_connected = False
        elif fault_type == "reboot_timeout":
            self.boot_completed = False
        elif fault_type == "cpu_io_stress":
            self.stress_processes.append(f"stress_process_{len(self.stress_processes)}")

    def apply_recovery(self, step: str, params: Dict[str, Any] = None):
        """应用恢复操作"""
        if step == "cleanup_storage":
            pressure_mb = (params or {}).get("pressure_mb", 1000)
            self.storage_available += pressure_mb * 1024 * 1024
        elif step == "reset_battery":
            self.battery_level = 100
        elif step == "reset_network":
            self.network_connected = True
        elif step == "wait_boot":
            self.boot_completed = True
        elif step == "stop_stress":
            self.stress_processes.clear()

    def reset(self):
        """重置到初始状态"""
        self.online = True
        self.battery_level = 100
        self.storage_available = 10 * 1024 * 1024 * 1024
        self.boot_completed = True
        self.network_connected = True
        self.stress_processes.clear()


class MockDeviceExecutor(BaseDeviceExecutor):
    """Mock 设备执行器"""

    mode = ExecutorMode.mock

    def __init__(self, serial: str, scenario: MockScenario = MockScenario.normal):
        self.device_serial = serial
        self.state = MockDeviceState(serial, scenario)

    async def _simulate_delay(self, min_ms: int = 100, max_ms: int = 500):
        """模拟操作延迟"""
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        await asyncio.sleep(delay)

    async def is_online(self) -> bool:
        """检查设备是否在线"""
        await self._simulate_delay(50, 100)
        return self.state.online

    async def get_properties(self) -> Dict[str, str]:
        """获取设备属性"""
        await self._simulate_delay()
        if not self.state.online:
            return {}
        return self.state.properties.copy()

    async def get_storage_info(self) -> StorageInfo:
        """获取存储信息"""
        await self._simulate_delay()
        return StorageInfo(
            total=self.state.storage_total,
            available=self.state.storage_available,
            used=self.state.storage_total - self.state.storage_available,
            path="/"
        )

    async def get_battery_info(self) -> BatteryInfo:
        """获取电池信息"""
        await self._simulate_delay()
        return BatteryInfo(
            level=self.state.battery_level,
            status="discharging",
            temperature=25,
            health="good"
        )

    async def execute_shell(self, cmd: str, timeout: int = 30) -> ShellResult:
        """执行 Shell 命令"""
        await self._simulate_delay()

        if not self.state.online:
            return ShellResult(
                success=False,
                stdout="",
                stderr="Device offline",
                exit_code=-1
            )

        # 处理特殊命令
        if cmd.startswith("getprop"):
            prop = cmd.split()[-1] if len(cmd.split()) > 1 else ""
            if prop == "sys.boot_completed":
                return ShellResult(
                    success=True,
                    stdout="1" if self.state.boot_completed else "0",
                    stderr="",
                    exit_code=0
                )
            return ShellResult(
                success=True,
                stdout=self.state.properties.get(prop, ""),
                stderr="",
                exit_code=0
            )

        if cmd.startswith("dumpsys battery"):
            return ShellResult(
                success=True,
                stdout=f"level: {self.state.battery_level}",
                stderr="",
                exit_code=0
            )

        # 默认成功执行
        return ShellResult(
            success=True,
            stdout="mock_output",
            stderr="",
            exit_code=0
        )

    async def push_file(self, local_path: str, remote_path: str) -> bool:
        """推送文件"""
        await self._simulate_delay(200, 500)
        return self.state.online

    async def pull_file(self, remote_path: str, local_path: str) -> bool:
        """拉取文件"""
        await self._simulate_delay(200, 500)
        return self.state.online

    async def run_monkey(self, package: str, count: int, options: Dict[str, Any] = None) -> MonkeyResult:
        """运行 Monkey 测试"""
        await self._simulate_delay(1000, 3000)

        if not self.state.online:
            return MonkeyResult(
                success=False,
                total_events=0,
                crash_count=0,
                anr_count=0,
                output="Device offline"
            )

        # 根据场景生成不同结果
        crash_count = 0
        anr_count = 0

        if self.state.scenario == MockScenario.network_error:
            crash_count = random.randint(1, 3)

        return MonkeyResult(
            success=True,
            total_events=count,
            crash_count=crash_count,
            anr_count=anr_count,
            output=f"Monkey completed with {count} events",
            duration_ms=random.randint(1000, 5000)
        )

    async def reboot(self, wait_timeout: int = 120) -> bool:
        """重启设备"""
        await self._simulate_delay(500, 1000)

        if not self.state.online:
            return False

        # 模拟重启过程
        self.state.boot_completed = False
        await asyncio.sleep(2)  # 模拟重启时间

        # 根据场景决定是否成功启动
        if self.state.scenario == MockScenario.boot_timeout:
            return False

        self.state.boot_completed = True
        return True

    async def wait_for_boot(self, timeout: int = 60) -> bool:
        """等待设备启动完成"""
        await asyncio.sleep(1)

        if self.state.scenario == MockScenario.boot_timeout:
            return False

        return self.state.boot_completed

    async def check_boot_completed(self) -> bool:
        """检查 boot 是否完成"""
        return self.state.boot_completed

    async def get_logcat(self, lines: int = 1000, filter_tag: Optional[str] = None, filter_level: Optional[str] = None) -> str:
        """获取 logcat 日志.

        Args:
            lines: 返回的日志行数，默认 1000 行
            filter_tag: 可选的日志标签过滤
            filter_level: 可选的日志级别过滤 (V/D/I/W/E/F)

        Returns:
            str: logcat 日志内容，使用标准 Android 日志格式
        """
        await self._simulate_delay(200, 500)

        if not self.state.online:
            return ""

        # 生成模拟日志
        log_lines = []

        # 更真实的 Android 日志组件和进程
        components = [
            # 系统服务
            ("ActivityManager", "I", "system_server", 1000),
            ("ActivityTaskManager", "I", "system_server", 1000),
            ("PackageManager", "I", "system_server", 1000),
            ("WindowManager", "I", "system_server", 1000),
            ("DisplayManager", "I", "system_server", 1000),
            ("PowerManager", "I", "system_server", 1000),
            ("PowerManagerService", "I", "system_server", 1000),
            ("BatteryService", "I", "system_server", 1000),
            ("BatteryStatsImpl", "D", "system_server", 1000),
            ("AlarmManager", "I", "system_server", 1000),
            ("LocationManager", "I", "system_server", 1000),
            ("ConnectivityManager", "I", "system_server", 1000),
            ("WifiTracker", "I", "system_server", 1000),
            ("TelephonyManager", "I", "system_server", 1000),
            ("SensorService", "I", "system_server", 1000),
            ("InputManager", "I", "system_server", 1000),
            ("InputMethodManager", "I", "system_server", 1000),
            ("ClipboardService", "I", "system_server", 1000),
            ("NotificationManager", "I", "system_server", 1000),
            ("AudioService", "I", "system_server", 1000),
            ("AudioFlinger", "I", "audioserver", 1023),
            ("MediaCodec", "I", "media.codec", 1038),
            ("MediaPlayer", "I", "media.player", 1039),
            ("CameraService", "I", "cameraserver", 1041),
            ("SurfaceFlinger", "I", "surfaceflinger", 1002),
            ("Choreographer", "I", "system_server", 1000),
            ("HardwareRenderer", "I", "system_server", 1000),
            # 网络和连接
            ("NetworkMonitor", "I", "network_service", 1051),
            ("DnsProxy", "I", "netd", 1015),
            ("Nat464Config", "I", "netd", 1015),
            ("WifiNl80211Manager", "I", "wifi", 1010),
            ("WifiStateMachine", "I", "wifi", 1010),
            ("BluetoothManager", "I", "bluetooth", 1002),
            # 应用相关
            ("Choreographer", "I", "com.android.systemui", 2345),
            ("Choreographer", "I", "com.mock.app", 12345),
            ("OpenGLRenderer", "I", "com.mock.app", 12345),
            ("dalvikvm", "I", "com.mock.app", 12345),
            ("AndroidRuntime", "E", "com.mock.app", 12345),
            ("System.err", "W", "com.mock.app", 12345),
            # 存储相关
            ("Vold", "I", "vold", 1014),
            ("StorageManager", "I", "system_server", 1000),
            ("DefaultContainerEngine", "I", "system_server", 1000),
            # 安全相关
            ("KeyguardService", "I", "system_server", 1000),
            ("FingerprintService", "I", "system_server", 1000),
            ("BiometricService", "I", "system_server", 1000),
        ]

        # 更详细的日志消息库
        log_messages = {
            "ActivityManager": [
                "START u0 {act=android.intent.action.MAIN cat=[android.intent.category.LAUNCHER] flg=0x10200000 cmp=com.mock.app/.MainActivity bidx=123} from uid 10123 from (from uid 10123) displayed in 156ms",
                "Displayed com.mock.app/.MainActivity: +234ms",
                "Stopping service: ComponentInfo{com.mock.app/com.mock.app.BackgroundService}",
                "Killing com.mock.app:adj=906 score=0 process:12345, reason: trim empty home",
                "Background start concurrent mark sweep GC freed 15234K, 42% free 12MB/21MB, paused 2ms",
                "Process com.mock.app (pid=12345) has died: fore TOP",
                "Force stopping com.mock.app appid=10123 user=0: from pid 1000",
            ],
            "ActivityTaskManager": [
                "START ActivityRecord{abc123 u0 com.mock.app/.MainActivity t123} from uid 10123",
                "Moving to front: ActivityRecord{abc123 u0 com.mock.app/.MainActivity t123}",
                "Override config changes for {1.0 320dpi}",
            ],
            "PackageManager": [
                "Scanning /data/app/com.mock.app-1/base.apk",
                "Package com.mock.app codePath changed; retaining data",
                "Successfully installed package com.mock.app",
                "Package com.mock.app already installed, skipping",
                "Updating external storage state for package com.mock.app",
                "Dexopt: Package com.mock.app code path: /data/app/com.mock.app-1/",
            ],
            "DisplayManager": [
                "Display device changed state: \"Built-in Screen\", ON",
                "Display 0 resolution: 1080x2400, density: 420dpi, refresh: 60.0fps",
                "Setting display mode: 0",
                "DisplayManagerService: Found display DisplayInfo{\"Built-in Screen\"}",
            ],
            "WindowManager": [
                "Adding window Window{abc123 u0 com.mock.app/com.mock.app.MainActivity}",
                "Removing window Window{abc123 u0 com.mock.app/com.mock.app.MainActivity}",
                "Relayout Window{abc123 u0 com.mock.app/com.mock.app.MainActivity}: oldVis=0 newVis=0",
                "Focus moving from Window{old123} to Window{abc123}",
            ],
            "PowerManager": [
                "Screen on duration: 123456 ms",
                "Going to sleep due to power button",
                "Waking up from sleep due to double tap",
                "User activity: 1234567890 ms ago, type=1",
            ],
            "PowerManagerService": [
                "updatePowerStateLocked: dirty=0x1a",
                "Wake lock: PowerManager.WakeLock{0x12345678 \"CpuWakeLock\"}",
                "Acquiring wake lock: 0x12345678",
                "Releasing wake lock: 0x12345678",
            ],
            "BatteryService": [
                "Battery level changed: 85%",
                "Charging status: DISCHARGING",
                "Battery temperature: 28.5C",
                "Battery voltage: 3850mV",
                "Battery health: GOOD",
                "Battery present: true",
            ],
            "BatteryStatsImpl": [
                "Recording battery state: level=85, plugged=0",
                "Started tracking wakelock: *job_scheduler_job_123",
                "Stop tracking wakelock: *job_scheduler_job_123, time=1234ms",
            ],
            "AlarmManager": [
                "Setting inexact repeating alarm: type=2, triggerAt=1234567890, window=5000ms",
                "Alarm triggered: type=2, listener={com.mock.app}",
                "Canceling alarm: listener={com.mock.app}",
            ],
            "LocationManager": [
                "Requesting location updates: provider=gps, interval=10000ms",
                "Removing location updates: listener={com.mock.app}",
                "Location changed: lat=37.123456, lng=-122.123456",
            ],
            "ConnectivityManager": [
                "Network available: WIFI, networkId=123, ssid=\"HomeWiFi\"",
                "Network connection validated: network=123",
                "Network connection lost: network=123",
                "ConnectivityService: NetworkAgent status changed to VALIDATED",
            ],
            "WifiTracker": [
                "Signal strength changed: networkId=123, level=4, rssi=-45",
                "Access point added: HomeWiFi",
                "Scan results updated, found 15 networks",
            ],
            "NetworkMonitor": [
                "Network 123 validated by CaptivePortalMonitor",
                "Switching to network 123 for internet",
                "Keeping DNS server 8.8.8.8 for network 123",
            ],
            "DnsProxy": [
                "DNS query: example.com -> 93.184.216.34",
                "Resolver query: www.google.com",
            ],
            "WifiNl80211Manager": [
                "Wifi lock acquired: WifiLock{com.mock.app}",
                "Wifi lock released: WifiLock{com.mock.app}",
                "Connection to HomeWiFi successful, rssi=-45",
            ],
            "WifiStateMachine": [
                "Connected to: HomeWiFi, freq=5180MHz",
                "Disconnecting from network",
                "Scanning for networks...",
            ],
            "BluetoothManager": [
                "Bluetooth enabled",
                "Bonding with device: 00:11:22:33:44:55",
                "Connection state changed: connected",
            ],
            "SensorService": [
                "Sensor enabled: type=1 (accelerometer), delay=16667us",
                "Sensor batch: type=4 (gyroscope), rate=50Hz",
                "Flush request for sensor: type=1",
            ],
            "InputManager": [
                "Input event: KeyEvent {action=0, keyCode=KEYCODE_HOME}",
                "Input event: MotionEvent {action=ACTION_DOWN, x=540.0, y=1200.0}",
                "Input event: MotionEvent {action=ACTION_UP, x=540.0, y=1200.0}",
            ],
            "InputMethodManager": [
                "Starting input: view=com.mock.app.EditText, inputType=none",
                "hideSoftInput: reason=FOCUS_CHANGED, window=Window{abc123}",
                "showSoftInput: reason=USER_REQUEST, flags=0",
            ],
            "ClipboardService": [
                "Clipboard set text: size=123 bytes",
                "Clipboard has text: true",
            ],
            "NotificationManager": [
                "Posting notification: id=123, pkg=com.mock.app",
                "Canceling notification: id=123",
                "Enqueuing notification: id=456, tag=null",
            ],
            "AudioService": [
                "Audio route changed: route=2 (speaker)",
                "Stream volume: stream=3 (music), volume=8",
                "Audio focus request: granted for com.mock.app",
                "Audio focus abandoned: com.mock.app",
            ],
            "AudioFlinger": [
                "AudioTrack created: sampleRate=44100, format=0x1, channelMask=0x3",
                "AudioBuffer overflow: 1234 frames",
                "Audio track started",
            ],
            "MediaCodec": [
                "MediaCodec created: mime=video/avc",
                "Configuring decoder: width=1920, height=1080",
                "MediaCodec state changed: 1 -> 2",
            ],
            "MediaPlayer": [
                "MediaPlayer created: path=/data/media/video.mp4",
                "prepareAsync: start",
                "onPrepared: width=1920, height=1080, duration=120000ms",
            ],
            "CameraService": [
                "Camera opened: cameraId=0, clientUid=10123",
                "Camera closed: cameraId=0",
                "Camera parameters updated: preview-size=1920x1080",
            ],
            "SurfaceFlinger": [
                "Layer created: com.mock.app/com.mock.app.MainActivity",
                "BufferQueue: max_buffer_count=3, consumer: SurfaceView",
                "VSync: 60Hz, phase=0.000000",
                "Composition type: GPU",
            ],
            "Choreographer": [
                "Skipped 45 frames! The application may be doing too much work on its main thread.",
                "Skipped 12 frames, next VSync in 8.33ms",
                "Frame rate: 60 fps",
                "doFrame: frameTimeNanos=123456789012345",
            ],
            "OpenGLRenderer": [
                "Initialized EGL, context: 0x12345678",
                "SwapBuffers: 16ms, frameTime=16.67ms",
                "Texture cache size: 32MB, limit=256MB",
                "Allocated texture: id=123, width=512, height=512",
            ],
            "HardwareRenderer": [
                "Creating hardware renderer",
                "Destroying hardware renderer",
                "EGL configuration: red=8, green=8, blue=8, alpha=8, depth=16",
            ],
            "Vold": [
                "Volume created: path=/storage/emulated/0",
                "Mounting volume: path=/storage/emulated/0",
                "Volume mounted: path=/storage/emulated/0",
            ],
            "StorageManager": [
                "External storage state changed: MOUNTED",
                "Primary physical volume: /data",
            ],
            "DefaultContainerEngine": [
                "Installing APK: /data/app/com.mock.app-1/base.apk",
                "Package installed: com.mock.app",
            ],
            "KeyguardService": [
                "Keyguard visibility changed: visible=false",
                "Keyguard hiding due to window: Window{abc123}",
            ],
            "FingerprintService": [
                "Fingerprint acquired: partial",
                "Fingerprint enrolled: id=1",
            ],
            "BiometricService": [
                "Biometric prompt shown: title=Authentication required",
                "Biometric authentication succeeded",
            ],
            "TelephonyManager": [
                "Signal strength changed: LTE, level=4, rssi=-85",
                "Data activity: direction=INOUT, bytes=1234567",
                "Call state changed: state=IDLE",
            ],
            "dalvikvm": [
                "GC_CONCURRENT freed 5678K, 50% free 12MB/24MB, paused 2ms+3ms, total time=15ms",
                "GC_FOR_ALLOC freed 1234K, 45% free 8MB/16MB, paused 5ms, total time=12ms",
                "GC_EXPLICIT freed 234K, 40% free 6MB/10MB, paused 3ms, total time=8ms",
                "Heap trim: 1024KB, 256KB, 128KB",
            ],
            "AndroidRuntime": [
                "FATAL EXCEPTION: main",
                "java.lang.NullPointerException: Attempt to invoke virtual method 'void com.mock.app.MainActivity.update()' on a null object reference",
                "    at com.mock.app.MainActivity$1.onClick(MainActivity.java:42)",
                "    at android.view.View.performClick(View.java:7500)",
                "    at android.view.View.performClickInternal(View.java:7469)",
                "    at android.view.View.access$3600(View.java:812)",
                "    at android.view.View$PerformClick.run(View.java:28536)",
                "    at android.os.Handler.handleCallback(Handler.java:938)",
                "Shutting down VM",
            ],
            "System.err": [
                "java.io.IOException: Connection refused",
                "    at com.mock.app.NetworkHelper.connect(NetworkHelper.java:123)",
                "    at com.mock.app.DataSync.sync(DataSync.java:45)",
                "java.lang.IllegalStateException: Not connected to service",
                "    at com.mock.app.ServiceHelper.getService(ServiceHelper.java:45)",
                "    at com.mock.app.App.init(App.java:23)",
                "java.net.SocketTimeoutException: timeout",
                "    at okhttp3.internal.http.HttpMethod.canRetryBody(HttpMethod.java:54)",
            ],
        }

        # 根据场景调整错误日志比例
        error_probability = 0.05  # 默认错误概率
        warn_probability = 0.10
        if self.state.scenario == MockScenario.network_error:
            error_probability = 0.15
            warn_probability = 0.20
        elif self.state.scenario == MockScenario.low_battery:
            warn_probability = 0.25
        elif self.state.scenario == MockScenario.storage_full:
            error_probability = 0.10
            warn_probability = 0.20

        # 定义日志级别过滤
        level_filter_map = {
            "V": 0,  # VERBOSE
            "D": 1,  # DEBUG
            "I": 2,  # INFO
            "W": 3,  # WARN
            "E": 4,  # ERROR
            "F": 5,  # FATAL
        }

        min_level = level_filter_map.get(filter_level, 0) if filter_level else 0

        # 生成时间戳基准
        now = datetime.now()
        base_time = now - timedelta(seconds=max(lines // 2, 300))  # 至少从 5 分钟前开始

        # 添加日志头部（logcat 标准输出格式）
        log_lines.append("--------- beginning of main")
        log_lines.append("--------- beginning of system")
        log_lines.append("--------- beginning of crash")
        log_lines.append("")

        generated_lines = 0
        tid_counter = 1000  # 线程 ID 计数器

        while generated_lines < lines:
            # 随机选择组件
            component_name, default_level, process, pid = random.choice(components)

            # 根据场景和概率选择日志级别
            rand = random.random()
            if component_name == "AndroidRuntime" or rand < error_probability * 0.5:
                level = "E"
            elif component_name == "System.err" or rand < error_probability:
                level = "W"
            elif rand < error_probability * 3:
                level = "D"
            elif rand < error_probability * 4:
                level = "V"
            else:
                level = "I"

            # 应用日志级别过滤
            if level_filter_map.get(level, 0) < min_level:
                continue

            # 应用标签过滤
            if filter_tag and filter_tag.lower() not in component_name.lower():
                continue

            # 生成时间戳（递增）
            timestamp = base_time + timedelta(milliseconds=generated_lines * random.randint(10, 100))
            time_str = timestamp.strftime("%m-%d %H:%M:%S.%f")[:-3]

            # 获取日志消息
            messages = log_messages.get(component_name, [
                f"[{component_name}] Generic log message {generated_lines}",
            ])
            message = random.choice(messages)

            # 生成线程 ID（同一组件的日志尽量使用相同线程）
            if random.random() < 0.7:
                tid = random.randint(1000, 9999)
            else:
                tid = tid_counter % 10000
                tid_counter += 1

            # 生成更真实的 logcat 格式
            # 格式：<date> <time> <pid> <tid> <level> <tag>: <message>
            log_line = f"{time_str} {pid:6d} {tid:6d} {level} {component_name}: {message}"
            log_lines.append(log_line)

            generated_lines += 1

            # 偶尔插入堆栈跟踪
            if level == "E" and random.random() < 0.3:
                stack_lines = [
                    f"    at com.mock.app.{component_name}.method1({component_name}.java:{random.randint(10, 500)})",
                    f"    at com.mock.app.{component_name}.method2({component_name}.java:{random.randint(10, 500)})",
                    f"    at android.app.ActivityThread.main(ActivityThread.java:{random.randint(5000, 10000)})",
                    f"    at java.lang.reflect.Method.invoke(Native method)",
                ]
                log_lines.extend(random.sample(stack_lines, random.randint(1, len(stack_lines))))

        return "\n".join(log_lines)

    def get_state(self) -> MockDeviceState:
        """获取设备状态对象（用于注入器操作）"""
        return self.state

    async def pull_directory(self, device_path: str, local_path: str) -> bool:
        """从设备拉取目录到本地（Mock 实现）."""
        await self._simulate_delay(300, 800)
        # Mock 设备返回成功
        return self.state.online
