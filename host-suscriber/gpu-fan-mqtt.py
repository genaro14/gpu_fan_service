[root@pve ~]$ cat /usr/local/bin/gpu-fan-mqtt.py
#!/usr/bin/env python3

import json
import time
import signal
import sys
import threading
import paho.mqtt.client as mqtt


# ============================================================
# MQTT CONFIGURATION
# ============================================================

BROKER = "192.168.10.133"
PORT = 1883

MQTT_USER = "mqtt"
MQTT_PASS = "Anana25"

TOPIC = "gpu/170hx/status"


# ============================================================
# PWM HARDWARE CONFIGURATION
# ============================================================

HWMON = "/sys/class/hwmon/hwmon3"

PWM = "pwm3"

PWM_ENABLE = f"{HWMON}/{PWM}_enable"
PWM_OUTPUT = f"{HWMON}/{PWM}"


# ============================================================
# FAN CURVE CONFIGURATION
#
# Temperature °C : PWM output 0-255
#
# Tune only this section
# ============================================================

FAN_CURVE = [
    (35, 60),      # idle
    (45, 90),
    (55, 130),
    (65, 180),
    (75, 230),
    (80, 255),     # maximum
]


# ============================================================
# FAN BEHAVIOR SETTINGS
# ============================================================

MQTT_TIMEOUT = 10

STARTUP_PWM = 125

# Temperature stability
HYSTERESIS_LIMIT = 55.0

TEMP_HYSTERESIS_LOW = 2.0
TEMP_HYSTERESIS_HIGH = 0.5

# Maximum PWM movement per update
PWM_STEP = 5


# ============================================================
# MQTT RECONNECT SETTINGS
#
# Fibonacci backoff:
#
# 1, 1, 2, 3, 5, 8, 13, 21, ...
#
# Capped at MQTT_RECONNECT_MAX seconds.
# ============================================================

MQTT_RECONNECT_MAX = 60


# ============================================================
# INTERNAL STATE
# ============================================================

last_message = 0

last_pwm = -1

last_temp = None

mqtt_connected = False

reconnect_lock = threading.Lock()


# ============================================================
# FAN CURVE INTERPOLATION
# ============================================================

def calculate_pwm(temp):

    if temp <= FAN_CURVE[0][0]:
        return FAN_CURVE[0][1]

    if temp >= FAN_CURVE[-1][0]:
        return FAN_CURVE[-1][1]

    for i in range(len(FAN_CURVE) - 1):

        t1, p1 = FAN_CURVE[i]
        t2, p2 = FAN_CURVE[i + 1]

        if t1 <= temp <= t2:

            pwm = p1 + (
                (temp - t1) *
                (p2 - p1) /
                (t2 - t1)
            )

            return int(pwm)

    return 255


# ============================================================
# TEMPERATURE HYSTERESIS
# ============================================================

def apply_temperature_hysteresis(temp, target_pwm):

    global last_temp

    if last_temp is None:

        last_temp = temp

        return target_pwm

    delta = abs(temp - last_temp)

    if temp < HYSTERESIS_LIMIT:

        if delta < TEMP_HYSTERESIS_LOW:

            return last_pwm

    else:

        if delta < TEMP_HYSTERESIS_HIGH:

            return last_pwm

    last_temp = temp

    return target_pwm


# ============================================================
# PWM SMOOTHING
# ============================================================

def smooth_pwm(target):

    global last_pwm

    if last_pwm < 0:

        return target

    if target > last_pwm:

        return min(
            last_pwm + PWM_STEP,
            target
        )

    if target < last_pwm:

        return max(
            last_pwm - PWM_STEP,
            target
        )

    return target


# ============================================================
# PWM CONTROL
# ============================================================

def set_pwm(value):

    global last_pwm

    value = max(
        0,
        min(
            255,
            int(value)
        )
    )

    if value == last_pwm:

        return

    try:

        # Manual mode

        with open(PWM_ENABLE, "w") as f:
            f.write("1")

        # Raw PWM value

        with open(PWM_OUTPUT, "w") as f:
            f.write(str(value))

        last_pwm = value

        print(
            f"PWM -> {value}",
            flush=True
        )

    except Exception as e:

        print(
            f"PWM ERROR: {e}",
            flush=True
        )


# ============================================================
# MQTT CALLBACKS
# ============================================================

def on_connect(client, userdata, flags, reason_code, properties):

    global mqtt_connected

    if reason_code == 0:

        mqtt_connected = True

        print(
            "MQTT connected",
            flush=True
        )

        result, mid = client.subscribe(TOPIC)

        if result != mqtt.MQTT_ERR_SUCCESS:

            print(
                f"MQTT subscribe failed: {result}",
                flush=True
            )

        else:

            print(
                f"MQTT subscribed: {TOPIC}",
                flush=True
            )

    else:

        mqtt_connected = False

        print(
            f"MQTT connection failed: {reason_code}",
            flush=True
        )


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):

    global mqtt_connected

    mqtt_connected = False

    print(
        f"MQTT disconnected: {reason_code}",
        flush=True
    )


def on_message(client, userdata, msg):

    global last_message

    try:

        data = json.loads(
            msg.payload.decode()
        )

        temp = float(
            data["temperature"]
        )

        last_message = time.time()

        pwm = calculate_pwm(temp)

        pwm = apply_temperature_hysteresis(
            temp,
            pwm
        )

        pwm = smooth_pwm(pwm)

        if pwm != last_pwm:

            print(
                f"GPU {temp:.1f}°C -> PWM {pwm}",
                flush=True
            )

        set_pwm(pwm)

    except Exception as e:

        print(
            f"MQTT message error: {e}",
            flush=True
        )


# ============================================================
# FIBONACCI RECONNECT
# ============================================================

def fibonacci_delays():

    """
    Generate Fibonacci reconnect delays:

        1, 1, 2, 3, 5, 8, 13, ...

    Values are capped at MQTT_RECONNECT_MAX.
    """

    previous = 0
    current = 1

    while True:

        delay = min(
            current,
            MQTT_RECONNECT_MAX
        )

        yield delay

        previous, current = current, previous + current


# ============================================================
# MQTT CONNECTION MANAGER
# ============================================================

def mqtt_connection_manager(client):

    """
    Keeps MQTT connected.

    Paho's network loop handles normal MQTT traffic.
    This thread handles persistent connection failures.
    """

    global mqtt_connected

    delays = fibonacci_delays()

    while True:

        if mqtt_connected:

            # Connection is healthy.
            # Reset Fibonacci sequence so the next failure
            # starts immediately with a 1 second retry.
            delays = fibonacci_delays()

            time.sleep(1)

            continue

        delay = next(delays)

        print(
            f"MQTT reconnect attempt in {delay}s",
            flush=True
        )

        time.sleep(delay)

        if mqtt_connected:

            continue

        with reconnect_lock:

            if mqtt_connected:

                continue

            try:

                print(
                    f"MQTT reconnecting to "
                    f"{BROKER}:{PORT}",
                    flush=True
                )

                result = client.reconnect()

                if result == mqtt.MQTT_ERR_SUCCESS:

                    print(
                        "MQTT reconnect successful",
                        flush=True
                    )

                else:

                    print(
                        f"MQTT reconnect failed: {result}",
                        flush=True
                    )

            except Exception as e:

                print(
                    f"MQTT reconnect error: {e}",
                    flush=True
                )


# ============================================================
# WATCHDOG
# ============================================================

def watchdog():

    global last_message

    while True:

        if last_message:

            age = time.time() - last_message

            if age > MQTT_TIMEOUT:

                print(
                    "MQTT timeout - forcing maximum fan",
                    flush=True
                )

                set_pwm(255)

        time.sleep(2)


# ============================================================
# SHUTDOWN
# ============================================================

def shutdown(sig, frame):

    print(
        "Shutdown - setting max fan",
        flush=True
    )

    set_pwm(255)

    sys.exit(0)


signal.signal(
    signal.SIGTERM,
    shutdown
)

signal.signal(
    signal.SIGINT,
    shutdown
)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "GPU MQTT Fan Controller",
        flush=True
    )

    # Safe startup

    set_pwm(
        STARTUP_PWM
    )

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    client.username_pw_set(
        MQTT_USER,
        MQTT_PASS
    )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    # Initial connection

    try:

        client.connect(
            BROKER,
            PORT,
            60
        )

    except Exception as e:

        print(
            f"Initial MQTT connection failed: {e}",
            flush=True
        )

    # Start Paho network loop

    client.loop_start()

    # Start reconnect manager

    reconnect_thread = threading.Thread(
        target=mqtt_connection_manager,
        args=(client,),
        daemon=True
    )

    reconnect_thread.start()

    try:

        watchdog()

    except KeyboardInterrupt:

        shutdown(
            None,
            None
        )
