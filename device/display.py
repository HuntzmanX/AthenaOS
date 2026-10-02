import config
from picographics import PicoGraphics


def create_graphics():
    """Create Athena's framebuffer without importing the full scene renderer."""
    if config.DISPLAY_KIND == "legacy7":
        from picographics import DISPLAY_INKY_FRAME_7 as DISPLAY
    elif config.DISPLAY_KIND == "spectra7":
        try:
            from picographics import DISPLAY_INKY_FRAME_SPECTRA_7 as DISPLAY
        except ImportError:
            raise RuntimeError(
                "Spectra display support is missing. Flash a current Pimoroni "
                "Inky Frame firmware, or set DISPLAY_KIND='legacy7'."
            )
    else:
        raise ValueError("Unknown DISPLAY_KIND: " + str(config.DISPLAY_KIND))

    graphics = PicoGraphics(DISPLAY)
    graphics.set_font("bitmap8")
    return graphics
