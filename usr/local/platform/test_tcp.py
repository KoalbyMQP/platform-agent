import asyncio
import websockets
import json
import time


async def test_heartbeat():
    uri = "ws://raspberrypi.local:8000/ws"
    # uri = "ws://127.0.0.1:8000/ws"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to server")

            for i in range(3):
                # Send heartbeat
                heartbeat_request = {
                    "id": i,
                    "endpoint": "heartbeat"
                }
                print(f"\nSending heartbeat {i + 1}")
                await websocket.send(json.dumps(heartbeat_request))

                # Wait for response
                response = await websocket.recv()
                print(f"Received response: {response}")

                # Wait a second before next heartbeat
                await asyncio.sleep(1)

            print("\nTest completed successfully")

    except websockets.exceptions.ConnectionClosed:
        print("Connection closed unexpectedly")
    except Exception as e:
        print(f"Error occurred: {e}")


if __name__ == "__main__":
    print("Starting heartbeat test...")
    asyncio.run(test_heartbeat())