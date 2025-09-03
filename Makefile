# Simple build targets for Karel Switcher

.PHONY: help build-linux build-mac clean run-linux

help:
	@echo "Targets:"
	@echo "  build-linux  - Build Linux executable (dist/karel-switcher)"
	@echo "  build-mac    - Build macOS app (dist/KarelSwitcher.app)"
	@echo "  clean        - Remove build artifacts and local venvs"
	@echo "  run-linux    - Run built Linux binary"

build-linux:
	bash ./build-linux.sh

build-mac:
	bash ./build-mac.sh

run-linux:
	ATEM_IP?=192.168.10.240
	ARDUINO_PORT?=/dev/ttyUSB0
	ATEM_IP=$(ATEM_IP) ARDUINO_PORT=$(ARDUINO_PORT) ./dist/karel-switcher

clean:
	rm -rf build dist .venv-linuxbuild .venv-macbuild

