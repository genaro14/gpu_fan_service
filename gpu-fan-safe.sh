[root@pve ~]$ cat /usr/local/sbin/gpu-fan-safe.sh
#!/bin/sh

PWM_ENABLE="/sys/class/hwmon/hwmon3/pwm3_enable"
PWM_OUTPUT="/sys/class/hwmon/hwmon3/pwm3"

# Force manual mode first.
echo 1 > "$PWM_ENABLE"

# Maximum PWM = 255.
echo 255 > "$PWM_OUTPUT"
