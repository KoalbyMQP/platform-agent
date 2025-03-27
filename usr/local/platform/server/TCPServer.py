import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from server.Server import Server
from utils.CommandCenter import CommandCenter
from utils.ExecutionManager import ExecutionManager
from utils.DeviceManager import DeviceManager


class WebSocketConnection:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.last_heartbeat = None


class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[WebSocket, WebSocketConnection] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = WebSocketConnection(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    async def send_message(self, websocket: WebSocket, message: dict):
        if websocket in self.active_connections:
            await websocket.send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await self.send_message(connection, message)


class TCPServer(Server):
    def __init__(self):
        super().__init__()
        self.app = FastAPI()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.websocket_manager = WebSocketManager()

        self.execution_manager = ExecutionManager(
            stdout=self.__send_execution_stdout,
            stderr=self.__send_execution_stderr
        )
        self.device_manager = DeviceManager(device_updated=self.__device_updated)
        self.command_center = CommandCenter(
            execution_manager=self.execution_manager,
            device_manager=self.device_manager
        )

        self.setup_routes()

    def setup_routes(self):
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.websocket_manager.connect(websocket)
            try:
                while True:
                    data = await websocket.receive_json()
                    await self.__handle_websocket_message(websocket, data)
            except WebSocketDisconnect:
                self.websocket_manager.disconnect(websocket)

    async def __handle_websocket_message(self, websocket: WebSocket, data: dict):
        request_id = data.get('id')
        endpoint = data.get('endpoint')
        payload = data.get('data', {})

        if endpoint == 'heartbeat':
            self.execution_manager.beat()
            await self.websocket_manager.send_message(websocket, {
                'id': request_id,
                'type': 'heartbeat',
                'success': True
            })
            return

        if endpoint == 'name':
            await self.websocket_manager.send_message(websocket, {
                'id': request_id,
                'type': 'name',
                'success': True,
                'response': self.__get_name()
            })
            return

        # Handle shell command execution
        if endpoint == 'execute-command':
            command = payload.get('command', '')
            success, response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self.command_center.execute_shell_command,
                (command,)
            )
        else:
            # Handle all other commands through command center
            command_str = self.__build_command_string(endpoint, payload)
            success, response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self.command_center.execute_command,
                command_str
            )

        await self.websocket_manager.send_message(websocket, {
            'id': request_id,
            'success': success,
            'response': response.decode('utf-8') if isinstance(response, bytearray) else str(response)
        })

    @staticmethod
    def __get_name():
        config = json.load(open("manifest.json"))
        return config.get("name", "robot")

    def __build_command_string(self, endpoint: str, payload: dict) -> str:
        if endpoint == 'install-project':
            project_id = payload.get('project_id', '')
            url = payload.get('url', '')
            token = payload.get('token')
            return f"install-project {project_id} {url} {token}" if token else f"install-project {project_id} {url}"

        elif endpoint in ['switch-project', 'switch-branch', 'change-target']:
            value = payload.get('project_id') or payload.get('branch_name') or payload.get('target_name', '')
            return f"{endpoint} {value}"

        elif endpoint == 'set-state':
            str_state = json.dumps(self.__convert_json(payload))
            return f"set-state {str_state}"

        elif endpoint == 'get-state':
            return f"get-state {payload.get('device_id', '')}"

        return endpoint  # For commands without parameters

    def __convert_json(self, data: str):
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                return self.__convert_json(parsed)
            except json.JSONDecodeError:
                return data
        if isinstance(data, dict):
            return {
                key: self.__convert_json(value)
                for key, value in data.items()
            }
        if isinstance(data, list):
            return [self.__convert_json(item) for item in data]
        return data

    def __device_updated(self, device):
        state = {str(device): self.device_manager.state_for_device(device)}
        asyncio.run(self.websocket_manager.broadcast({
            'type': 'device_update',
            'state': state
        }))

    def __send_execution_stdout(self, data: str):
        asyncio.run(self.websocket_manager.broadcast({
            'type': 'log',
            'log_type': 'stdout',
            'message': data
        }))

    def __send_execution_stderr(self, data: str):
        asyncio.run(self.websocket_manager.broadcast({
            'type': 'log',
            'log_type': 'stderr',
            'message': data
        }))

    def start(self, host: str = "0.0.0.0", port: int = 5467):
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)


if __name__ == "__main__":
    server = TCPServer()
    server.start()
