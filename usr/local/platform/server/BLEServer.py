import asyncio
import json
import threading

from bless import (
    GATTCharacteristicProperties,
    GATTAttributePermissions,
)

# from ..BluetoothUUIDs import BluetoothUUIDs
from BluetoothUUIDs import BluetoothUUIDs
from utils.BluetoothConnection import BluetoothConnection, BluetoothService, BluetoothCharacteristic
from utils.CommandCenter import CommandCenter
from utils.ExecutionManager import ExecutionManager
from utils.DeviceManager import DeviceManager

from .Server import Server
from concurrent.futures import ThreadPoolExecutor

class BLEServer(Server):

    def __init__(self):
        super().__init__()
        self.heart_count = -1
        self.execution_manager = ExecutionManager(self.__send_execution_stdout, self.__send_execution_stderr)
        self.device_manager = DeviceManager(device_updated=self.__device_updated)
        self.command_center = CommandCenter(execution_manager=self.execution_manager, device_manager=self.device_manager)
        self.executor = ThreadPoolExecutor(max_workers=1)

        interactive_service = self.__get_interactive_service()
        self.connection = BluetoothConnection(self.__get_name(), services=[interactive_service])
        self.connection.onDeviceConnected = lambda: print("Connected!")
        self.connection.onDeviceDisconnected = lambda: print("Disconnected!")

    def start(self):
        self.connection.start()

    @staticmethod
    def __get_name():
        config = json.load(open("manifest.json"))
        return config.get("name", "robot")

    def __device_updated(self, device):
        uuid = BluetoothUUIDs.DEVICE_CHARACTERISTIC_UUID.value
        state = {str(device): self.device_manager.state_for_device(device)}
        state_bytes = bytearray(json.dumps(state), "utf-8")
        self.connection.update_and_notify(uuid, state_bytes)

    def __send_execution_stdout(self, data: str):
        data = f"0,{data}"
        self.connection.update_and_notify(BluetoothUUIDs.LOGGING_CHARACTERISTIC_UUID.value, bytearray(data, "utf-8"))

    def __send_execution_stderr(self, data: str):
        data = f"1,{data}"
        self.connection.update_and_notify(BluetoothUUIDs.LOGGING_CHARACTERISTIC_UUID.value, bytearray(data, "utf-8"))

    async def __execute_shell_command(self, command: str) -> (bytearray, bool):
        success, response = await asyncio.get_event_loop().run_in_executor(
            self.executor, self.command_center.execute_shell_command, (command,)
        )
        msg = f"0,{response}" if success else f"1,{response}"
        return bytearray(msg, "utf-8"), True


    async def __run_command(self, command: str) -> (bytearray, bool):
        success, response = await asyncio.get_event_loop().run_in_executor(
            self.executor, self.command_center.execute_command, command
        )
        msg = f"0,{response}" if success else f"1,{response}"
        return bytearray(msg, "utf-8"), True  # Notify subscribers


    async def __receive_heartbeat(self, heartbeat: str) -> (bytearray, bool):
        self.execution_manager.beat()
        return bytearray("0,", "utf-8"), True

    def __get_interactive_service(self):
        interactive_service = BluetoothService(BluetoothUUIDs.INTERACTIVE_SERVICE_UUID.value)
        device_characteristic = BluetoothCharacteristic(
            BluetoothUUIDs.DEVICE_CHARACTERISTIC_UUID.value,
            permissions=GATTAttributePermissions.readable,
            properties=GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify,
            on_read=lambda value: value,
        )
        interactive_service.add_characteristic(device_characteristic)
        exec_characteristic = BluetoothCharacteristic(
            BluetoothUUIDs.EXECUTION_CHARACTERISTIC_UUID.value,
            permissions=(GATTAttributePermissions.readable | GATTAttributePermissions.writeable),
            properties=(GATTCharacteristicProperties.read | GATTCharacteristicProperties.write | GATTCharacteristicProperties.notify),
            on_read=lambda value: value,
            on_write=self.__execute_shell_command
        )
        interactive_service.add_characteristic(exec_characteristic)
        comm_characteristic = BluetoothCharacteristic(
            BluetoothUUIDs.COMMUNICATION_CHARACTERISTIC_UUID.value,
            permissions=GATTAttributePermissions.readable | GATTAttributePermissions.writeable,
            properties=GATTCharacteristicProperties.read | GATTCharacteristicProperties.write | GATTCharacteristicProperties.notify,
            on_read=lambda value: value,
            on_write=self.__run_command
        )
        interactive_service.add_characteristic(comm_characteristic)

        log_characteristic = BluetoothCharacteristic(
            BluetoothUUIDs.LOGGING_CHARACTERISTIC_UUID.value,
            permissions=GATTAttributePermissions.readable,
            properties=GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify,
            on_read=lambda value: value
        )
        interactive_service.add_characteristic(log_characteristic)

        heartbeat_characteristic = BluetoothCharacteristic(
            BluetoothUUIDs.HEARTBEAT_CHARACTERISTIC_UUID.value,
            permissions=GATTAttributePermissions.readable | GATTAttributePermissions.writeable,
            properties=GATTCharacteristicProperties.read | GATTCharacteristicProperties.write | GATTCharacteristicProperties.notify,
            on_read=lambda value: bytearray("", "utf-8"),
            on_write=self.__receive_heartbeat
        )
        interactive_service.add_characteristic(heartbeat_characteristic)
        return interactive_service


if __name__ == '__main__':
    server = BLEServer()
    server.start()
