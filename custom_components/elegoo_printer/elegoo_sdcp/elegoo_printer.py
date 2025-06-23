"""Elegoo Printer."""

import asyncio
import json
import os
import socket
import time
from threading import Thread
from typing import Any, Optional

import netifaces
import websocket

from .const import DEBUG, LOGGER
from .models.attributes import PrinterAttributes
from .models.print_history_detail import PrintHistoryDetail
from .models.printer import Printer, PrinterData
from .models.status import PrinterStatus

DISCOVERY_TIMEOUT = 10
DEFAULT_PORT = 54780
DISCOVERY_PORT = 3000


class ElegooPrinterClientWebsocketError(Exception):
    """Exception to indicate a general API error."""


class ElegooPrinterClientWebsocketConnectionError(Exception):
    """Exception to indicate a Websocket Connection error."""


class ElegooPrinterClient:
    """
    Client for interacting with an Elegoo printer.

    Uses the SDCP Protocol (https://github.com/cbd-tech/SDCP-Smart-Device-Control-Protocol-V3.0.0).
    """

    def __init__(
        self, ip_address: str, centauri_carbon: bool = False, logger: Any = LOGGER
    ) -> None:
        """Initialize the ElegooPrinterClient."""
        self.ip_address: str = ip_address
        self.centauri_carbon: bool = centauri_carbon
        self.printer_websocket: websocket.WebSocketApp | None = None
        self.printer: Printer = Printer()
        self.printer_data = PrinterData()
        self.logger = logger

    def get_printer_status(self) -> PrinterData:
        """Retreves the printer status."""
        try:
            self._send_printer_cmd(0)
        except (ElegooPrinterClientWebsocketError, OSError):
            self.logger.exception(
                "Error sending printer command in process_printer_job"
            )
            raise
        return self.printer_data

    def get_printer_attributes(self) -> PrinterData:
        """Retreves the printer attributes."""
        try:
            self._send_printer_cmd(1)
        except (ElegooPrinterClientWebsocketError, OSError):
            self.logger.exception(
                "Error sending printer command in process_printer_job"
            )
            raise
        return self.printer_data

    def set_printer_video_stream(self, *, toggle: bool) -> None:
        """Toggles the printer video stream."""
        self._send_printer_cmd(386, {"Enable": int(toggle)})

    def get_printer_historical_tasks(self) -> None:
        """Retreves historical tasks from printer."""
        self._send_printer_cmd(320)

    def get_printer_task_detail(self, id_list: list[str]) -> None:
        """Retreves historical tasks from printer."""
        self._send_printer_cmd(321, data={"Id": id_list})

    async def get_printer_current_task(self) -> list[PrintHistoryDetail]:
        """Retreves current task."""
        if self.printer_data.status.print_info.task_id:
            self.get_printer_task_detail([self.printer_data.status.print_info.task_id])

            await asyncio.sleep(2)
            return self.printer_data.print_history

        return []

    async def get_current_print_thumbnail(self) -> str | None:
        """
        Asynchronously retrieves the thumbnail URL of the current print task.

        Returns:
            str | None: The thumbnail URL if a current print task exists, otherwise None.
        """
        print_history = await self.get_printer_current_task()
        if print_history:
            return print_history[0].thumbnail

        return None

    def _send_printer_cmd(self, cmd: int, data: dict[str, Any] | None = None) -> None:
        """Send a command to the printer."""
        ts = int(time.time())
        data = data or {}
        payload = {
            "Id": self.printer.connection,
            "Data": {
                "Cmd": cmd,
                "Data": data,
                "RequestID": os.urandom(8).hex(),
                "MainboardID": self.printer.id,
                "TimeStamp": ts,
                "From": 0,
            },
            "Topic": f"sdcp/request/{self.printer.id}",
        }
        if DEBUG:
            self.logger.debug(f"printer << \n{json.dumps(payload, indent=4)}")
        if self.printer_websocket:
            try:
                self.printer_websocket.send(json.dumps(payload))
            except (
                websocket.WebSocketConnectionClosedException,
                websocket.WebSocketException,
            ) as e:
                self.logger.exception("WebSocket connection closed error")
                raise ElegooPrinterClientWebsocketError from e
            except (
                OSError
            ):  # Catch potential OS errors like Broken Pipe, Connection Refused
                self.logger.exception("Operating System error during send")
                raise  # Re-raise OS errors
        else:
            self.logger.warning(
                "Attempted to send command but websocket is not connected."
            )
            raise ElegooPrinterClientWebsocketConnectionError from Exception(
                "Not connected"
            )

    def _get_broadcast_addresses(self) -> list[str]:
        """
        Retrieves a list of IPv4 broadcast addresses for all active network interfaces.
        """
        broadcast_addrs = []
        try:
            for iface in netifaces.interfaces():
                # Get the addresses for the AF_INET (IPv4) family
                if netifaces.AF_INET in netifaces.ifaddresses(iface):
                    for addr_info in netifaces.ifaddresses(iface)[netifaces.AF_INET]:
                        # Each interface can have multiple addresses; we need the one with a broadcast address
                        if "broadcast" in addr_info:
                            broadcast_addrs.append(addr_info["broadcast"])
        except Exception as e:
            self.logger.error(f"Could not get network interface information: {e}")
            # Fallback for systems where netifaces might fail
            self.logger.warning(
                "Falling back to limited broadcast address '255.255.255.255'"
            )
            return ["255.255.255.255"]

        # Return a list of unique broadcast addresses
        return list(set(broadcast_addrs))

    def discover_printer(self) -> Optional[Printer]:
        """Discover the Elegoo printer on all local subnets."""
        self.logger.info("Starting printer discovery...")
        msg = b"M99999"
        broadcast_addresses = self._get_broadcast_addresses()

        if not broadcast_addresses:
            self.logger.error("No network interfaces found for broadcasting.")
            return None

        self.logger.info(f"Will broadcast on: {broadcast_addresses}")

        with socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        ) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(DISCOVERY_TIMEOUT)

            # You need to bind to receive the response. Binding to "" means it will
            # listen on all available interfaces on the specified port.
            try:
                # Note: The original code used DEFAULT_PORT here. Ensure this is correct.
                # If the printer responds to a different port, adjust accordingly.
                sock.bind(("", DEFAULT_PORT))
            except OSError as e:
                self.logger.exception(
                    f"Error binding to port {DEFAULT_PORT}: {e}. Port may be in use."
                )
                return None

            # Send the discovery message to all identified broadcast addresses
            for addr in broadcast_addresses:
                try:
                    sock.sendto(msg, (addr, DISCOVERY_PORT))
                    self.logger.debug(
                        f"Discovery message sent to {addr}:{DISCOVERY_PORT}"
                    )
                except OSError as e:
                    self.logger.error(f"Failed to send to {addr}: {e}")

            # After sending to all, wait for a response
            try:
                self.logger.info("Waiting for printer response...")
                # Note: This will only capture the FIRST printer to respond.
                data, remote_addr = sock.recvfrom(8192)
                self.logger.info(f"Received response from {remote_addr[0]}")

                printer = self._save_discovered_printer(data)
                if printer:
                    self.logger.info("Printer discovered successfully.")
                    self.printer = printer
                    return printer

            except TimeoutError:
                self.logger.warning(
                    "Printer discovery timed out. No response received."
                )
            except OSError as e:
                self.logger.exception(f"Socket error during discovery: {e}")

        return None

    def _save_discovered_printer(self, data: bytes) -> Printer | None:
        try:
            printer_info = data.decode("utf-8")
        except UnicodeDecodeError:
            self.logger.exception(
                "Error decoding printer discovery data. Data may be malformed."
            )
        else:
            try:
                printer = Printer(printer_info, centauri_carbon=self.centauri_carbon)
            except (ValueError, TypeError):
                self.logger.exception("Error creating Printer object")
            else:
                self.logger.info(f"Discovered: {printer.name} ({printer.ip_address})")
                return printer

        return None

    async def connect_printer(self) -> bool:
        """
        Connect to the Elegoo printer.

        Establishes a WebSocket connection to the printer using the
        discovered IP address and port.

        Returns:
            True if the connection was successful, False otherwise.

        """
        url = f"ws://{self.printer.ip_address}:3030/websocket"
        self.logger.info(f"Connecting to: {self.printer.name}")

        websocket.setdefaulttimeout(1)

        def ws_msg_handler(ws, msg: str) -> None:  # noqa: ANN001, ARG001
            self._parse_response(msg)

        def ws_connected_handler(name: str) -> None:
            self.logger.info(f"Connected to: {name}")

        def on_close(
            ws,  # noqa: ANN001, ARG001
            close_status_code: str,
            close_msg: str,
        ) -> None:
            self.logger.debug(
                f"Connection to {self.printer.name} closed: {close_msg} ({close_status_code})"  # noqa: E501
            )
            self.printer_websocket = None

        def on_error(ws, error) -> None:  # noqa: ANN001, ARG001
            self.logger.error(f"Connection to {self.printer.name} error: {error}")
            self.printer_websocket = None

        ws = websocket.WebSocketApp(
            url,
            on_message=ws_msg_handler,
            on_open=ws_connected_handler(self.printer.name),
            on_close=on_close,
            on_error=on_error,
        )
        self.printer_websocket = ws

        thread = Thread(target=ws.run_forever, kwargs={"reconnect": 1}, daemon=True)
        thread.start()

        start_time = time.monotonic()
        timeout = 5
        while time.monotonic() - start_time < timeout:
            if ws.sock and ws.sock.connected:
                await asyncio.sleep(2)
                self.logger.info(f"Connected to {self.printer.name}")
                return True

        self.logger.warning(f"Failed to connect to {self.printer.name} within timeout")
        self.printer_websocket = None
        return False

    def _parse_response(self, response: str) -> None:
        try:  # Add try-except block for json.loads
            data = json.loads(response)
            topic = data.get("Topic")  # Use .get to handle missing "Topic"
            if topic:  # Check if topic exists
                match topic.split("/")[1]:
                    case "response":
                        self._response_handler(data)  # Pass the parsed JSON data
                    case "status":
                        self._status_handler(data)
                    case "attributes":
                        self._attributes_handler(data)
                    case "notice":
                        self.logger.debug(f"notice >> \n{json.dumps(data, indent=5)}")
                    case "error":
                        self.logger.debug(f"error >> \n{json.dumps(data, indent=5)}")
                    case _:
                        self.logger.debug("--- UNKNOWN MESSAGE ---")
                        self.logger.debug(data)
                        self.logger.debug("--- UNKNOWN MESSAGE ---")
            else:
                self.logger.warning(
                    "Received message without 'Topic'"
                )  # Log if Topic is missing
                self.logger.debug(
                    f"Message content: {response}"
                )  # Log the whole message for debugging
        except json.JSONDecodeError:
            self.logger.exception("Invalid JSON received")

    def _response_handler(self, data: dict[str, Any]) -> None:  # Pass parsed data
        if DEBUG:
            self.logger.debug(f"response >> \n{json.dumps(data, indent=5)}")
        try:
            data_data = data.get("Data", {}).get("Data", {})
            self._print_history_handler(data_data)
        except json.JSONDecodeError:
            self.logger.exception("Invalid JSON")

    def _status_handler(self, data: dict[str, Any]) -> None:  # Pass parsed data
        if DEBUG:
            self.logger.debug(f"status >> \n{json.dumps(data, indent=5)}")
        printer_status = PrinterStatus.from_json(json.dumps(data))
        self.printer_data.status = printer_status

    def _attributes_handler(self, data: dict[str, Any]) -> None:  # Pass parsed data
        if DEBUG:
            self.logger.debug(f"attributes >> \n{json.dumps(data, indent=5)}")
        printer_attributes = PrinterAttributes.from_json(json.dumps(data))
        self.printer_data.attributes = printer_attributes

    def _print_history_handler(self, data_data: dict[str, Any]) -> None:
        history_data_list = data_data.get("HistoryDetailList")
        if history_data_list:
            print_history_detail_list: list[PrintHistoryDetail] = [
                PrintHistoryDetail(history_data) for history_data in history_data_list
            ]
            self.printer_data.print_history = print_history_detail_list
