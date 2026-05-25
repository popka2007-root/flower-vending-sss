# Linux packaging

## systemd unit

`flower-vending.service` is a systemd unit template for running the kiosk
UI as a user service with automatic restart on failure.

### Installation

```bash
# 1. Adjust paths in the unit file if needed
sudo cp packaging/linux/flower-vending.service /etc/systemd/system/

# 2. Create the runtime user (if not already present)
sudo useradd --system --shell /usr/sbin/nologin flower-vending

# 3. Create the config directory and copy your machine YAML
sudo mkdir -p /etc/flower-vending
sudo cp config/examples/machine.simulator.yaml /etc/flower-vending/machine.yaml

# 4. Reload systemd and enable the service
sudo systemctl daemon-reload
sudo systemctl enable flower-vending.service
sudo systemctl start flower-vending.service

# 5. Check status
sudo systemctl status flower-vending.service
journalctl -u flower-vending.service -f
```

### Environment variables

| Variable                     | Default                                    |
|------------------------------|--------------------------------------------|
| `FLOWER_VENDING_CONFIG`      | `/etc/flower-vending/machine.yaml`         |
| `DISPLAY`                    | `:0`                                       |
| `XAUTHORITY`                 | `/home/flower-vending/.Xauthority`         |

Edit the unit file to change these values for your deployment.

### Uninstall

```bash
sudo systemctl stop flower-vending.service
sudo systemctl disable flower-vending.service
sudo rm /etc/systemd/system/flower-vending.service
sudo systemctl daemon-reload
```
