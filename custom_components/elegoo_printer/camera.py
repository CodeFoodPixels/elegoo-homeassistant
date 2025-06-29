from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.mjpeg.camera import MjpegCamera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.elegoo_printer import ElegooDataUpdateCoordinator
from custom_components.elegoo_printer.const import (CONF_CENTAURI_CARBON,
                                                    CONF_PROXY_ENABLED, LOGGER)
from custom_components.elegoo_printer.data import ElegooPrinterConfigEntry
from custom_components.elegoo_printer.definitions import (
    PRINTER_FFMPEG_CAMERAS, PRINTER_MJPEG_CAMERAS,
    ElegooPrinterSensorEntityDescription)
from custom_components.elegoo_printer.elegoo_sdcp.client import \
    ElegooPrinterClient
from custom_components.elegoo_printer.elegoo_sdcp.models.enums import \
    ElegooVideoStatus
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
            async_add_entities([ElegooGo2RTCCamera(hass, coordinator, camera)])

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


class ElegooGo2RTCCamera(ElegooPrinterEntity, Camera):
    """Representation of a go2rtc-powered Camera"""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ElegooDataUpdateCoordinator,
        description: ElegooPrinterSensorEntityDescription,
    ) -> None:
        """
        Initialize the Elegoo go2rtc camera entity.
        """
        ElegooPrinterEntity.__init__(self, coordinator)
        Camera.__init__(self)

        self.entity_description = description
        self._attr_unique_id = coordinator.generate_unique_id(
            self.entity_description.key
        )
        self._attr_name = "Camera"
        self._attr_supported_features = CameraEntityFeature.STREAM
        self._printer_client: ElegooPrinterClient = (
            coordinator.config_entry.runtime_data.client._elegoo_printer
        )
        LOGGER.info("ElegooGo2RTCCamera initialized.")

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """
        Return a still image from the camera.
        This implementation asks the stream component for an image,
        which is the most efficient way when a stream is active.
        """
        if self.stream:
            return await self.stream.async_get_image(width=width, height=height)

        return None

    async def stream_source(self) -> str | None:
        """
        Return the source of the stream for go2rtc, formatted correctly.
        """
        LOGGER.info("go2rtc stream_source called. Requesting video from printer...")
        video = await self._printer_client.get_printer_video(toggle=True)

        if video and video.status and video.status == ElegooVideoStatus.SUCCESS:
            # Build the special go2rtc ffmpeg source string
            source_url = f"ffmpeg:{video.video_url}?#input=rtsp/udp#video=h264#media=video#resolution=960x540"
            LOGGER.info(f"SUCCESS: Providing formatted source to go2rtc: {source_url}")
            return source_url

        LOGGER.warning("FAILURE: No stream source available for go2rtc.")
        return None

    @property
    def available(self) -> bool:
        """
        Return whether the camera entity is currently available.
        """
        is_available = super().available
        if (
            hasattr(self, "entity_description")
            and self.entity_description.available_fn is not None
        ):
            is_available = self.entity_description.available_fn(
                self._printer_client.printer_data.video
            )
        return is_available
