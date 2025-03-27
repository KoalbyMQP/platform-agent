import sys
import logging
import asyncio
import threading
from typing import Any, Union, Optional, List
from bless import (
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions,
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(name=__name__)

# Determine synchronization trigger based on platform
trigger: Union[asyncio.Event, threading.Event]
if sys.platform in ["darwin", "win32"]:
    trigger = threading.Event()
else:
    trigger = asyncio.Event()


class BluetoothCharacteristic:
    def __init__(self, uuid: str, permissions: GATTAttributePermissions, properties: GATTCharacteristicProperties, value: bytearray = bytearray(), on_read: Optional[callable] = None, on_write: Optional[callable] = None):
        self.gatt_characteristic = BlessGATTCharacteristic(uuid, properties, permissions, value)
        self.uuid = uuid
        self.properties = properties
        self.permissions = permissions
        self.on_read = on_read
        self.on_write = on_write


    def send_notification(self, value: Any):
        self.gatt_characteristic.value = value
        pass


class BluetoothService:
    def __init__(self, uuid: str):
        self.uuid = uuid
        self.characteristics: List[BluetoothCharacteristic] = []


    def add_characteristic(self, characteristic: BluetoothCharacteristic):
        self.characteristics.append(characteristic)


class BluetoothConnection:
    def __init__(self,
                 device_name: str = "robot",
                 services: list[BluetoothService] = None):

        if services is None:
            services = list()

        self.services = services
        self.device_name = device_name
        self.server: Optional[BlessServer] = None
        self.loop = None

        self.characteristics = dict()
        self.buffers = dict()
        self.buffer_timestamps = dict()
        self.service_for_characteristic = dict()

        for service in services:
            for characteristic in service.characteristics:
                self.characteristics[characteristic.uuid] = characteristic
                self.service_for_characteristic[characteristic.uuid] = service


    def start(self):
        logger.debug("Starting Bluetooth server...")
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._run_server())
            self.loop.run_forever()
        except KeyboardInterrupt:
            logger.info("Server interrupted, stopping...")
            self.stop()

    def update_and_notify(self, characteristic_uuid: str, value: bytearray):
        characteristic = self.characteristics[characteristic_uuid]
        chunk_size = 250
        for i in range(0, len(value), chunk_size):
            chunk = value[i:i + chunk_size]
            self.server.get_characteristic(characteristic.uuid).value = chunk
            self.server.update_value(self.service_for_characteristic[characteristic_uuid].uuid, characteristic_uuid)
        # If the last chunk is exactly 250 characters, send an empty message
        if len(value) % chunk_size == 0:
            self.server.get_characteristic(characteristic.uuid).value = bytearray('', 'utf-8')
            self.server.update_value(
                self.service_for_characteristic[characteristic.uuid].uuid,
                characteristic.uuid
            )

    def stop(self):
        logger.debug("Stopping Bluetooth server...")
        self.loop.run_until_complete(self.server.stop())
        self.loop.stop()


    def _read_request(self, characteristic: BlessGATTCharacteristic) -> bytearray:
        characteristic = self.characteristics[characteristic.uuid]
        if characteristic.on_read:
            r = characteristic.on_read(characteristic.gatt_characteristic.value)
            characteristic.gatt_characteristic.value = r
            return r

        raise NotImplementedError(f"Read request for characteristic {characteristic.uuid} not implemented")


    def _write_request(self, characteristic: BlessGATTCharacteristic, value: Any, **kwargs):
        characteristic = self.characteristics[characteristic.uuid]
        if characteristic.on_write is None:
            raise NotImplementedError(f"Write request for characteristic {characteristic.uuid} not implemented")
        asyncio.create_task(self._async_write(characteristic, value))

    async def _async_write(self, characteristic: BluetoothCharacteristic, value: Any):
        v = value.decode()
        if len(value) == 250:
            if characteristic.uuid not in self.buffer_timestamps or asyncio.get_event_loop().time() - self.buffer_timestamps[characteristic.uuid] > 5:
                self.buffers[characteristic.uuid] = ""
            self.buffers[characteristic.uuid] = (self.buffers.get(characteristic.uuid) or "") + v
            self.buffer_timestamps[characteristic.uuid] = asyncio.get_event_loop().time()
            return

        self.buffer_timestamps[characteristic.uuid] = asyncio.get_event_loop().time()
        self.buffers[characteristic.uuid] = (self.buffers.get(characteristic.uuid) or "") + v
        write_response = await characteristic.on_write(self.buffers[characteristic.uuid])
        val, should_notify = write_response
        self.buffers[characteristic.uuid] = ""
        if should_notify:
            message = val
            chunk_size = 250
            for i in range(0, len(message), chunk_size):
                chunk = message[i:i + chunk_size]
                self.server.get_characteristic(characteristic.uuid).value = chunk
                self.server.update_value(self.service_for_characteristic[characteristic.uuid].uuid, characteristic.uuid)
            # If the last chunk is exactly 250 characters, send an empty message
            if len(message) % chunk_size == 0:
                self.server.get_characteristic(characteristic.uuid).value = bytearray('', 'utf-8')
                self.server.update_value(
                    self.service_for_characteristic[characteristic.uuid].uuid,
                    characteristic.uuid
                )
        else:
            self.server.get_characteristic(characteristic.uuid).value = val


    async def _run_server(self):
        trigger.clear()

        # Initialize server with device name
        self.server = BlessServer(
            name=self.device_name,
            loop=self.loop,
        )

        # Add services and characteristics
        for service in self.services:
            await self.server.add_new_service(service.uuid)
            for characteristic in service.characteristics:
                await self.server.add_new_characteristic(
                    service.uuid,
                    characteristic.uuid,
                    characteristic.properties,
                    None,
                    characteristic.permissions
                )
        self.server.read_request_func = self._read_request
        self.server.write_request_func = self._write_request

        logger.debug("Bluetooth services and characteristics added.")
        logger.debug("Services: " + str([service.uuid for service in self.services]))
        await self.server.start()

        logger.debug("Advertising Bluetooth service...")
        logger.info(f"BLE service '{self.device_name}' is now advertising")

