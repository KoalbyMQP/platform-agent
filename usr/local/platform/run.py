from server import Server
from server.BLEServer import BLEServer
from server.TCPServer import TCPServer
import threading

def main():
    ble: Server = BLEServer()
    tcp: Server = TCPServer()

    ble_thread = threading.Thread(target=ble.start, daemon=True)
    tcp_thread = threading.Thread(target=tcp.start, daemon=True)

    ble_thread.start()
    tcp_thread.start()

    # Keep the main thread alive while the others run
    ble_thread.join()
    tcp_thread.join()


if __name__ == "__main__":
    main()
