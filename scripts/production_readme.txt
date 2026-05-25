# Flower Vending System — Production Quick Start
#
# Run these commands from the project root directory.

# 1. Install dependencies
pip install -e ".[serial]"
pip install pyserial

# 2. Find connected hardware
python -m flower_vending discover

# 3. Test DBV-300-SD communication (replace COM3 with actual port)
python -m flower_vending dbv300sd-serial-smoke --port COM3 --baudrate 9600 --tx-hex "02 02 01 01 03" --read-size 16

# 4. Start production runtime
python -m flower_vending run --config config/machine.production.yaml

# 5. Start with UI (if PySide6 is installed)
python -m flower_vending run --config config/machine.production.yaml

# 6. Validation only
python -m flower_vending validate-config --config config/machine.production.yaml

# 7. Print test receipt
python -m flower_vending printer-test --port COM#
