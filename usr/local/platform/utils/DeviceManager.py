import gc
from typing import Callable
from uuid import uuid4

from cyberonics_py import Robot, Device
import importlib.util
import os

class DeviceManager:
    def __init__(self, device_updated: Callable[[uuid4], None]):
        self.robot = None
        self.robot_path = None
        self.device_updated = device_updated
        # Keep a cache of current states for each device so we don't get into a loop
        self.state_cache = {}


    @property
    def all_device_states(self):
        if self.robot is None:
            raise ValueError("No robot loaded")
        return {str(device.uuid): device.get_state() for device in self.robot.devices}

    def listen_to_robot(self, robot_path):
        if not os.path.isfile(robot_path):
            raise FileNotFoundError(f"No such file: {robot_path}")

        # Unload existing robot
        self.deload_robot()

        # Load the module from the file path
        module_name = os.path.splitext(os.path.basename(robot_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, robot_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for attribute_name in dir(module):
            attribute = getattr(module, attribute_name)
            if isinstance(attribute, type) and issubclass(attribute, Robot) and attribute is not Robot:
                self.robot = attribute()
                self.robot_path = robot_path
                for device in self.robot.devices:
                    self.state_cache[str(device.uuid)] = device.get_state()
                    self.__device_updated(device)
                    device.add_listener(self.__device_updated)
                break
        else:
            raise TypeError("No subclass of Robot found in the specified file.")


    def reload_robot(self):
        if self.robot_path is None:
            raise ValueError("No robot loaded")
        self.listen_to_robot(self.robot_path)
        for device in self.get_devices():
            self.device_updated(device)

    def get_devices(self) -> [str]:
        if self.robot is None:
            return []
        devices = [str(device.uuid) for device in self.robot.devices]
        return devices

    def state_for_device(self, device_uuid: uuid4) -> dict:
        if self.robot is None:
            raise ValueError("No robot loaded")
        for device in self.robot.devices:
            if str(device.uuid) == str(device_uuid):
                return device.get_state()
        raise ValueError(f"No device with UUID {str(device_uuid)}. Found devices {[str(device.uuid) for device in self.robot.devices]}")

    def deload_robot(self):
        self.robot_path = None
        if self.robot is not None:
            self.robot = None
            gc.collect()


    def update_device_state(self, device_data: dict[str, any]):
        device_state = device_data.get("state")
        device_uuid = device_data.get("uuid")
        if self.robot is None:
            raise ValueError("No robot loaded")
        if device_state is None or device_uuid is None:
            raise ValueError("device_data must contain 'state' and 'uuid' keys")
        for device in self.robot.devices:
            if str(device.uuid) == str(device_uuid):
                device.set_state(device_state)
                return
        raise ValueError(f"No device with UUID {str(device_uuid)}. Found devices {[str(device.uuid) for device in self.robot.devices]}")

    # Checks to see if the state is actually different than the last one we sent before we send it
    def __device_updated(self, device: Device):
        device_uuid = str(device.uuid)
        if self.state_cache.get(device_uuid) == device.get_state():
            return
        self.state_cache[device_uuid] = device.get_state()
        self.device_updated(device_uuid)


if __name__ == "__main__":
    dm = DeviceManager(lambda x: print(f"Device {x} updated"))
    dm.listen_to_robot("projects/pytester/robot.py")
    devices = dm.get_devices()
    dev = devices[0]
    print("Device: ", dev)
    state = dm.state_for_device(dev)
    print("State: ", state)
    print(dm.all_device_states)
