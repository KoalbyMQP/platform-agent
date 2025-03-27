from abc import ABC, abstractmethod

class Server(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def start(self):
        pass