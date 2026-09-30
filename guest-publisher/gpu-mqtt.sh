#!/bin/bash

BROKER="192.168.10.133"
PORT=1883
USERNAME="mqtt"
PASSWORD="Anana25"

TOPIC="gpu/170hx/status"
HOSTNAME=$(hostname)

while true; do
    IFS=',' read -r temp util mem power <<< "$(
        nvidia-smi \
          --query-gpu=temperature.gpu,utilization.gpu,memory.used,power.draw \
          --format=csv,noheader,nounits
    )"

    payload=$(printf \
      '{"host":"%s","temperature":%s,"utilization":%s,"memory_used":%s,"power":%s,"timestamp":%s}' \
      "$HOSTNAME" \
      "${temp// /}" \
      "${util// /}" \
      "${mem// /}" \
      "${power// /}" \
      "$(date +%s)"
    )

    mosquitto_pub \
        -h "$BROKER" \
        -p "$PORT" \
        -u "$USERNAME" \
        -P "$PASSWORD" \
        -t "$TOPIC" \
        -m "$payload"

    sleep 1
done
