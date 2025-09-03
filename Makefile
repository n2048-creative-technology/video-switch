# Simple build targets for Karel Switcher

.PHONY: help build-linux build-mac clean run-linux run-mpv

help:
	@echo "Targets:"
	@echo "  build-linux  - Build Linux executable (dist/karel-switcher)"
	@echo "  build-mac    - Build macOS app (dist/KarelSwitcher.app)"
	@echo "  clean        - Remove build artifacts and local venvs"
	@echo "  run-linux    - Run built Linux binary"
	@echo "  run-mpv      - Run source UI with mpv integration"

build-linux:
	bash ./build-linux.sh

build-mac:
	bash ./build-mac.sh

run-linux:
	ATEM_IP?=192.168.10.240
	ARDUINO_PORT?=/dev/ttyUSB0
	ATEM_IP=$(ATEM_IP) ARDUINO_PORT=$(ARDUINO_PORT) ./dist/karel-switcher

run-mpv:
	# Optional overrides for VIDEO_FILE and MPV_SOCKET; .env is also read by the script.
	VIDEO_FILE?=
	MPV_SOCKET?=
	VIDEO_FILE=$(VIDEO_FILE) MPV_SOCKET=$(MPV_SOCKET) python3 run_mpv.py

clean:
	rm -rf build dist .venv-linuxbuild .venv-macbuild
