"""Air quality channel: MQ-135 gas sensor via ADC backends.

On machines without the hardware this channel simply reports
unavailable; the simulation path covers demos. The hardware backends
(serial, I2C/ADS1115, SPI/MCP3008) carry over from the original project
for when a Pi + sensor are available again.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .base import Channel

logger = logging.getLogger(__name__)


def classify_ppm(ppm: float) -> str:
    if ppm <= 50:
        return "excellent"
    if ppm <= 100:
        return "good"
    if ppm <= 150:
        return "moderate"
    if ppm <= 200:
        return "poor"
    return "hazardous"


class AirChannel(Channel):
    name = "air"
    unit = "ppm"

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.backend = self.cfg.get("backend", "auto")
        self.serial_port = self.cfg.get("serial_port", "/dev/ttyUSB0")
        self.sample_count = int(self.cfg.get("sample_count", 10))
        self.i2c_cfg = self.cfg.get("i2c", {}) or {}
        self._serial = None
        self._adc = None
        self._analog = None

    # --- backends ---------------------------------------------------------

    def _try_serial(self) -> bool:
        try:
            import serial  # pyserial

            if not os.path.exists(self.serial_port):
                return False
            self._serial = serial.Serial(self.serial_port, baudrate=9600, timeout=1)
            self._serial.reset_input_buffer()
            self.backend = "serial"
            return True
        except Exception:
            return False

    def _try_i2c(self) -> bool:
        try:
            import adafruit_ads1x15.ads1115 as ADS
            import board
            import busio
            from adafruit_ads1x15.analog_in import AnalogIn

            i2c = busio.I2C(board.SCL, board.SDA)
            address = int(self.i2c_cfg.get("address", 0x48))
            channel = int(self.i2c_cfg.get("channel", 0))
            adc = ADS.ADS1115(i2c, address=address)
            self._analog = AnalogIn(adc, {0: ADS.P0, 1: ADS.P1, 2: ADS.P2, 3: ADS.P3}[channel])
            _ = self._analog.value  # probe read
            self._adc = adc
            self.backend = "i2c"
            return True
        except Exception:
            return False

    def _try_spi(self) -> bool:
        try:
            import spidev

            spi = spidev.SpiDev()
            spi.open(0, 0)
            spi.max_speed_hz = 1_350_000
            self._adc = spi
            self.backend = "spi"
            return True
        except Exception:
            return False

    def check_available(self) -> bool:
        if self.backend == "mock":
            return False
        order = (self._try_i2c, self._try_serial, self._try_spi)
        if self.backend != "auto":
            order = {
                "i2c": (self._try_i2c,),
                "serial": (self._try_serial,),
                "spi": (self._try_spi,),
            }.get(self.backend, order)
        for attempt in order:
            try:
                if attempt():
                    return True
            except Exception:
                continue
        return False

    def start(self) -> bool:
        if self.backend == "mock":
            return True  # mock mode is handled by the manager/simulator
        return self.check_available()

    # --- reads ------------------------------------------------------------

    def _read_raw(self) -> float:
        if self.backend == "serial":
            line = self._serial.readline().decode("utf-8").strip()
            return float(line)
        if self.backend == "i2c":
            value = max(0, self._analog.value)
            return value / 32767.0 * 1023.0
        if self.backend == "spi":
            channel = int(self.cfg.get("gpio_pin", 0))
            raw = self._adc.xfer2([1, (8 + channel) << 4, 0])
            return float(((raw[1] & 3) << 8) + raw[2])
        raise RuntimeError(f"no air backend active: {self.backend}")

    def read(self) -> dict[str, Any]:
        if self.backend == "mock":
            raise RuntimeError("air mock mode is produced by the simulator")
        samples = [self._read_raw() for _ in range(max(1, self.sample_count))]
        raw = sum(samples) / len(samples)
        ppm = max(0.0, (raw / 1023.0) * 300.0)  # dev-grade linear mapping
        return {"value": round(ppm, 2), "label": classify_ppm(ppm)}

    def stop(self) -> bool:
        if self._serial is not None:
            self._serial.close()
            self._serial = None
        if self._adc is not None and hasattr(self._adc, "close"):
            try:
                self._adc.close()
            except Exception:
                pass
            self._adc = None
        self._analog = None
        return True
