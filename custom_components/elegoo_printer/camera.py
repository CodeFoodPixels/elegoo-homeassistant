from homeassistant.components.camera import CameraEntityFeature
from homeassistant.components.ffmpeg.camera import (
    CONF_EXTRA_ARGUMENTS,
    CONF_INPUT,
    FFmpegCamera,
)
from homeassistant.components.mjpeg.camera import MjpegCamera
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.elegoo_printer import ElegooDataUpdateCoordinator
from custom_components.elegoo_printer.const import (
    CONF_CENTAURI_CARBON,
    CONF_PROXY_ENABLED,
    LOGGER,
)
from custom_components.elegoo_printer.data import ElegooPrinterConfigEntry
from custom_components.elegoo_printer.definitions import (
    PRINTER_FFMPEG_CAMERAS,
    PRINTER_MJPEG_CAMERAS,
    ElegooPrinterSensorEntityDescription,
)
from custom_components.elegoo_printer.elegoo_sdcp.client import ElegooPrinterClient
from custom_components.elegoo_printer.elegoo_sdcp.models.enums import ElegooVideoStatus
from custom_components.elegoo_printer.entity import ElegooPrinterEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ElegooPrinterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """
    Asynchronously sets up Elegoo Printer MJPEG camera entities for a Home Assistant configuration entry.

    Initializes and adds camera entities if the Centauri Carbon feature is enabled in the printer configuration, and enables the printer's video stream.
    """
    coordinator: ElegooDataUpdateCoordinator = config_entry.runtime_data.coordinator
    FDM_PRINTER = coordinator.config_entry.data.get(CONF_CENTAURI_CARBON, False)

    if FDM_PRINTER:
        for camera in PRINTER_MJPEG_CAMERAS:
            async_add_entities([ElegooMjpegCamera(hass, coordinator, camera)])
    else:
        for camera in PRINTER_FFMPEG_CAMERAS:
            async_add_entities([ElegooFFmpegCamera(hass, coordinator, camera)])

    printer_client: ElegooPrinterClient = (
        coordinator.config_entry.runtime_data.client._elegoo_printer
    )
    printer_client.set_printer_video_stream(toggle=True)


class ElegooMjpegCamera(ElegooPrinterEntity, MjpegCamera):
    """Representation of an MjpegCamera"""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ElegooDataUpdateCoordinator,
        description: ElegooPrinterSensorEntityDescription,
    ) -> None:
        """
        Initialize the Elegoo MJPEG camera entity with its description and printer client.

        Assigns a unique ID based on the entity description and stores references to the printer client and MJPEG stream URL for later use.
        """
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = coordinator.generate_unique_id(
            self.entity_description.key
        )
        self._mjpeg_url = ""
        self._printer_client: ElegooPrinterClient = (
            coordinator.config_entry.runtime_data.client._elegoo_printer
        )

    async def stream_source(self) -> str:
        """
        Asynchronously retrieves the current MJPEG stream URL for the printer camera.

        If the printer video stream is successfully enabled, returns either a local proxy URL or the direct printer video URL based on configuration. Otherwise, returns the last known MJPEG URL.

        Returns:
            str: The MJPEG stream URL for the camera.
        """
        video = await self._printer_client.get_printer_video(toggle=True)
        if video.status and video.status == ElegooVideoStatus.SUCCESS:
            if self.coordinator.config_entry.data.get(CONF_PROXY_ENABLED, False):
                self._mjpeg_url = "http://127.0.0.1:3031/video"
            else:
                self._mjpeg_url = video.video_url

        return self._mjpeg_url

    @property
    def available(self) -> bool:
        """
        Return whether the camera entity is currently available.

        If the entity description specifies an availability function, this function is used to determine availability based on the printer's video data. Otherwise, falls back to the default availability check.
        """
        if (
            hasattr(self, "entity_description")
            and self.entity_description.available_fn is not None
        ):
            return self.entity_description.available_fn(
                self._printer_client.printer_data.video
            )
        return super().available


class ElegooFFmpegCamera(ElegooPrinterEntity, FFmpegCamera):
    """Representation of an FFmpeg Camera"""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ElegooDataUpdateCoordinator,
        description: ElegooPrinterSensorEntityDescription,
    ) -> None:
        """
        Initialize the Elegoo FFmpeg camera entity.
        """
        ElegooPrinterEntity.__init__(self, coordinator)
        FFmpegCamera.__init__(
            self,
            hass,
            # We provide a dummy input here; the real one comes from stream_source.
            {
                CONF_NAME: "Camera",
                CONF_INPUT: "dummy",
                CONF_EXTRA_ARGUMENTS: "-an -rtsp_transport tcp -hide_banner -v error -allowed_media_types video -fflags nobuffer -flags low_delay -timeout 5000000",
            },
        )

        self.entity_description = description
        self._attr_unique_id = coordinator.generate_unique_id(
            self.entity_description.key
        )
        self._attr_supported_features = CameraEntityFeature.STREAM
        self._printer_client: ElegooPrinterClient = (
            coordinator.config_entry.runtime_data.client._elegoo_printer
        )

    async def stream_source(self) -> str | None:
        """
        Return the source of the stream. Return None if not available.
        """
        LOGGER.info("stream_source called. Requesting video from printer...")
        video = await self._printer_client.get_printer_video(toggle=True)

        if video:
            LOGGER.info(
                f"Printer response received. Status: {video.status}, URL: '{video.video_url}'"
            )
            if video.status and video.status == ElegooVideoStatus.SUCCESS:
                LOGGER.info(f"SUCCESS: Returning stream URL: {video.video_url}")
                return video.video_url
        else:
            LOGGER.error("Did not receive a response object from get_printer_video.")

        LOGGER.warning("FAILURE: Stream source is returning None.")
        return None

    @property
    def available(self) -> bool:
        """
        Return whether the camera entity is currently available.
        """
        if (
            hasattr(self, "entity_description")
            and self.entity_description.available_fn is not None
        ):
            return self.entity_description.available_fn(
                self._printer_client.printer_data.video
            )
        return super().available
