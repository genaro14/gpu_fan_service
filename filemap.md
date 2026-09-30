# GPU Fan MQTT — File Map

## Proxmox Host — Fan Controller

| File                                       | Purpose                                |
| ------------------------------------------ | -------------------------------------- |
| `/usr/local/bin/gpu-fan-mqtt.py`           | MQTT subscriber and fan controller     |
| `/usr/local/sbin/gpu-fan-safe.sh`          | Forces the external GPU fan to maximum |
| `/etc/systemd/system/gpu-fan-mqtt.service` | systemd service definition             |

### Edit

```bash
vim /usr/local/bin/gpu-fan-mqtt.py
vim /usr/local/sbin/gpu-fan-safe.sh
vim /etc/systemd/system/gpu-fan-mqtt.service
```

### Reload and restart

```bash
systemctl daemon-reload
systemctl restart gpu-fan-mqtt.service
systemctl status gpu-fan-mqtt.service
```

### Logs

```bash
journalctl -u gpu-fan-mqtt.service -f
```

---

## AI Lab Guest VM — GPU Telemetry Publisher

| File                                   | Purpose                                      |
| -------------------------------------- | -------------------------------------------- |
| `/usr/local/bin/gpu-mqtt.sh`           | Reads GPU telemetry and publishes it to MQTT |
| `/etc/systemd/system/gpu-mqtt.service` | systemd publisher service                    |

### Edit

```bash
vim /usr/local/bin/gpu-mqtt.sh
vim /etc/systemd/system/gpu-mqtt.service
```

### Reload and restart

```bash
systemctl daemon-reload
systemctl restart gpu-mqtt.service
systemctl status gpu-mqtt.service
```

### Logs

```bash
journalctl -u gpu-mqtt.service -f
```

---

## MQTT Test

Subscribe to the GPU telemetry topic:

```bash
mosquitto_sub \
  -h 192.168.10.133 \
  -p 1883 \
  -u mqtt \
  -P 'Anana25' \
  -t 'gpu/170hx/status' \
  -v
```

Subscribe to everything:

```bash
mosquitto_sub \
  -h 192.168.10.133 \
  -p 1883 \
  -u mqtt \
  -P 'fake_password' \
  -t '#' \
  -v
```

---

## Quick Service Commands

### Proxmox Host

```bash
systemctl restart gpu-fan-mqtt.service
systemctl status gpu-fan-mqtt.service
```

### AI Lab Guest

```bash
systemctl restart gpu-mqtt.service
systemctl status gpu-mqtt.service
```

### After Editing a systemd Unit

```bash
systemctl daemon-reload
systemctl restart <service>
```

