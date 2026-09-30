# GPU Fan MQTT Service

MQTT-based GPU fan controller for a **NVIDIA CMP 170HX** used as a passthrough GPU in an AI lab.

## Overview

This service was created to solve a specific problem with GPU passthrough.

The CMP 170HX is physically installed in the Proxmox host, but the GPU is passed through to an AI virtual machine. Once the GPU is assigned to the VM, the guest OS has access to the GPU while the Proxmox host remains responsible for the physical hardware.

This creates a problem for GPU cooling:

* The GPU is physically attached to the Proxmox host.
* The GPU is used by the AI VM.
* GPU temperature and power consumption are relevant to the fan controller.
* Fan control needs to remain available independently of the VM.
* A failure of the MQTT connection or controller must not leave the GPU fan stopped.

This project provides a small MQTT service running on the **Proxmox host** to monitor and control the external GPU fan.

## Architecture

```text
                         Proxmox Host
┌───────────────────────────────────────────────────────────┐
│                                                           │
│   CMP 170HX                                               │
│   ┌──────────────────────┐                                │
│   │ GPU                  │                                │
│   │ Temperature          │◄──── Host telemetry            │
│   │ Power usage          │                                │
│   │ External fan         │◄──── Fan controller            │
│   └──────────┬───────────┘                                │
│              │                                            │
│              │ PCI passthrough                            │
│              ▼                                            │
│   ┌──────────────────────┐                                │
│   │ AI Lab VM            │                                │
│   │                      │                                │
│   │ AI workloads         │                                │
│   │ GPU access           │                                │
│   └──────────────────────┘                                │
│                                                           │
│   gpu-fan-mqtt.py                                          │
│   ┌──────────────────────┐                                │
│   │ MQTT subscriber      │                                │
│   │ Fan control          │                                │
│   │ Telemetry            │                                │
│   │ Reconnection         │                                │
│   └──────────┬───────────┘                                │
│              │                                            │
└──────────────┼────────────────────────────────────────────┘
               │ MQTT
               ▼
        ┌───────────────┐
        │ MQTT Broker   │
        └───────────────┘
```

The important design point is that **fan control remains on the Proxmox host**. The VM does not need to control the physical fan directly.

## MQTT

The service operates as an **MQTT subscriber** for fan-control commands.

MQTT is also used to expose GPU telemetry so that the host and guest can publish/use information about:

* GPU temperature
* GPU power usage
* fan control state

This allows the AI environment to observe the physical GPU while keeping the actual fan-control mechanism on the host.

The MQTT connection is intentionally resilient. If the broker connection is lost, the service attempts to reconnect automatically rather than requiring a systemd restart.

### Reconnection

MQTT reconnection attempts use an increasing delay based on a Fibonacci sequence.

This avoids continuously hammering the broker when it is unavailable while still progressively retrying the connection.

The service therefore handles transient MQTT failures internally.

Systemd remains responsible for recovering from a complete process failure.

## Fan Safety

The service is designed with a fail-safe behavior.

Before the controller starts, systemd executes:

```text
/usr/local/sbin/gpu-fan-safe.sh
```

This places the fan at maximum speed before the Python controller begins operating.

If the Python process exits for any reason, systemd executes the same script using `ExecStopPost`.

Therefore:

```text
Controller starts
       │
       ▼
Fan → MAX
       │
       ▼
MQTT controller starts
       │
       ├── MQTT connected → normal operation
       │
       └── MQTT disconnected → Fibonacci reconnect
       
If Python process dies
       │
       ▼
Fan → MAX
       │
       ▼
systemd restarts service
```

The fan therefore does not depend on the Python process remaining alive for safe cooling.

## systemd Service

The service is installed as:

```text
gpu-fan-mqtt.service
```

The unit runs:

```text
/usr/bin/python3 /usr/local/bin/gpu-fan-mqtt.py
```

with:

```ini
Restart=always
RestartSec=5
```

This provides a second level of recovery.

### Failure handling

There are two independent recovery mechanisms:

**MQTT failure**

Handled by the Python application:

```text
MQTT connection lost
        │
        ▼
Fibonacci reconnect attempts
        │
        ▼
MQTT connection restored
```

**Application failure**

Handled by systemd:

```text
Python process exits
        │
        ▼
gpu-fan-safe.sh
        │
        ▼
Fan → MAX
        │
        ▼
systemd waits 5 seconds
        │
        ▼
Python service restarted
```

This separation is intentional. MQTT connectivity problems should not require restarting the entire service, while an actual application failure should be recovered by systemd.

## Installation

The main components are:

```text
/usr/local/bin/gpu-fan-mqtt.py
/usr/local/sbin/gpu-fan-safe.sh
/etc/systemd/system/gpu-fan-mqtt.service
```

After installing or modifying the service:

```bash
systemctl daemon-reload
systemctl enable gpu-fan-mqtt.service
systemctl restart gpu-fan-mqtt.service
```

Check the service:

```bash
systemctl status gpu-fan-mqtt.service
```

Follow the logs:

```bash
journalctl -u gpu-fan-mqtt.service -f
```

## Service Definition

The systemd service follows this model:

```ini
[Unit]
Description=GPU Fan MQTT Controller
After=network-online.target
Wants=network-online.target

[Service]
Type=simple

ExecStartPre=/usr/local/sbin/gpu-fan-safe.sh

ExecStart=/usr/bin/python3 /usr/local/bin/gpu-fan-mqtt.py

ExecStopPost=/usr/local/sbin/gpu-fan-safe.sh

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

The `ExecStartPre` and `ExecStopPost` safety hooks are particularly important for a GPU that may be operating under sustained AI workloads.

## Why MQTT?

The GPU is being used by an AI VM, while the physical fan controller belongs on the Proxmox host.

MQTT provides a simple boundary between the host and the rest of the AI lab:

```text
AI VM / monitoring
        │
        │ MQTT
        ▼
     Broker
        │
        │ MQTT
        ▼
Proxmox host
        │
        ▼
Physical GPU fan
```

This avoids coupling the fan controller directly to the VM.

The VM can use the GPU normally through PCI passthrough while the host maintains control of the physical cooling system.

## Use Case

The primary use case is an AI lab where a CMP 170HX is passed through to a virtual machine for GPU workloads.

For example:

```text
Proxmox
  │
  ├── AI Lab VM
  │     └── CMP 170HX (PCI passthrough)
  │
  └── Host-side fan controller
        └── External GPU fan
```

The GPU can therefore be fully assigned to the AI VM without moving physical fan-control responsibilities into the guest.

## Design Goals

The project is intentionally small.

The main goals are:

* Control an external fan for the CMP 170HX.
* Keep physical fan control on the Proxmox host.
* Allow the GPU to remain passed through to an AI VM.
* Expose GPU telemetry through MQTT.
* Subscribe to MQTT control commands.
* Automatically recover from MQTT disconnections.
* Use progressively longer reconnect delays.
* Put the fan at maximum when the controller starts.
* Put the fan at maximum if the controller exits.
* Let systemd restart the controller automatically.
* Keep the fan in a safe state during software failures.

## Monitoring

Useful commands on the Proxmox host:

```bash
systemctl status gpu-fan-mqtt.service
```

```bash
journalctl -u gpu-fan-mqtt.service -f
```

Check the service configuration:

```bash
systemctl cat gpu-fan-mqtt.service
```

Check the running process:

```bash
ps aux | grep '[g]pu-fan-mqtt.py'
```

## Repository

Repository:

```text
git@github.com:genaro14/gpu_fan_mqtt_service.git
```

The project is intended to remain a small, host-side service rather than a complete GPU management stack.

## License

GPL v3

