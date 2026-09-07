import gc
import ujson
import uos

import config


def _exists(path):
    try:
        uos.stat(path)
        return True
    except OSError:
        return False


def _mkdir(path):
    if not _exists(path):
        uos.mkdir(path)


class Storage:
    """Small storage abstraction so onboard flash and SD use identical paths."""

    def __init__(self):
        self.using_sd = False
        self.root = config.INTERNAL_ROOT
        self._sd = None
        self._spi = None

        if config.USE_SD_IF_AVAILABLE:
            self._try_mount_sd()

        if not self.using_sd:
            _mkdir(config.INTERNAL_ROOT)
            self.root = config.INTERNAL_ROOT

        print("Athena storage:", self.root)

    def _try_mount_sd(self):
        try:
            import machine
            import sdcard

            _mkdir(config.SD_MOUNT)

            self._spi = machine.SPI(
                config.SD_SPI_ID,
                sck=machine.Pin(config.SD_SCK_PIN, machine.Pin.OUT),
                mosi=machine.Pin(config.SD_MOSI_PIN, machine.Pin.OUT),
                miso=machine.Pin(config.SD_MISO_PIN, machine.Pin.OUT),
            )
            self._sd = sdcard.SDCard(
                self._spi,
                machine.Pin(config.SD_CS_PIN),
            )
            uos.mount(self._sd, config.SD_MOUNT)
            _mkdir(config.SD_ROOT)
            self.root = config.SD_ROOT
            self.using_sd = True
            print("SD card mounted")
        except Exception as exc:
            # No SD is a normal v0.1 configuration, not an error condition.
            print("SD unavailable, using onboard flash:", exc)
            self.root = config.INTERNAL_ROOT
            self.using_sd = False
            self._sd = None
            self._spi = None
            gc.collect()

    def path(self, name):
        return self.root + "/" + name

    def exists(self, name):
        return _exists(self.path(name))

    def remove(self, name):
        path = self.path(name)
        try:
            uos.remove(path)
        except OSError:
            pass

    def load_json(self, name, default=None):
        path = self.path(name)
        try:
            with open(path, "r") as handle:
                return ujson.load(handle)
        except Exception as exc:
            print("Could not read", path, exc)
            return default

    def save_json(self, name, value):
        path = self.path(name)
        temp = path + ".tmp"

        with open(temp, "w") as handle:
            ujson.dump(value, handle)

        try:
            uos.remove(path)
        except OSError:
            pass
        uos.rename(temp, path)

    def promote(self, temp_name, final_name):
        temp = self.path(temp_name)
        final = self.path(final_name)
        try:
            uos.remove(final)
        except OSError:
            pass
        uos.rename(temp, final)

    def free_bytes(self):
        try:
            stats = uos.statvfs(self.root)
            return stats[0] * stats[3]
        except Exception:
            return None
