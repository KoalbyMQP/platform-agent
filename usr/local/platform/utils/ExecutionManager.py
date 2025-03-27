import os
import subprocess
import threading
import time
from time import sleep


class ExecutionManager:
    def __init__(self, stdout, stderr):
        self.is_running = False
        self.pid = None
        self.stdout = stdout
        self.stderr = stderr
        self.heartbeat_timestamp = time.time()
        self.heartbeat_thread = threading.Thread(target=self._monitor_heartbeat, daemon=True)
        self.heartbeat_thread.start()

    def beat(self):
        self.heartbeat_timestamp = time.time()

    def _monitor_heartbeat(self):
        while True:
            if time.time() - self.heartbeat_timestamp > 2.5:
                self.kill_program()
            sleep(1)

    def run_python_program(
            self,
            environment: str,
            script_path: str
    ) -> bool:
        """
        Executes a Python script using the Python interpreter from the specified virtual environment.
        Sends stdout and stderr data as it comes in to self.stdout(data) and self.stderr(data).

        :param environment: Path to the virtual environment directory.
        :param script_path: Absolute path to the Python script to execute.
        :return: True if the process starts successfully, False otherwise.
        """

        try:
            # Determine the path to the Python executable inside the virtual environment
            if os.name == 'nt':  # For Windows
                python_executable = os.path.join(environment, 'Scripts', 'python.exe')
            else:  # For Unix/Linux/MacOS
                python_executable = os.path.join(environment, 'bin', 'python')

            # Check if the Python executable exists
            if not os.path.isfile(python_executable):
                print(f"Python executable not found at: {python_executable}")
                return False

            # Start the subprocess without using the shell
            self.is_running = True
            self.pid = subprocess.Popen(
                [python_executable, '-u', script_path],  # '-u' for unbuffered output
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,  # For Python 3.7+, ensures output is in string format
                bufsize=1,  # Line-buffered
                universal_newlines=True
            )

            # Start threads to read stdout and stderr and send data to self.stdout and self.stderr
            if self.pid.stdout:
                stdout_thread = threading.Thread(
                    target=self.__read_stream,
                    args=(self.pid.stdout, self.stdout),
                    daemon=True
                )
                stdout_thread.start()

            if self.pid.stderr:
                stderr_thread = threading.Thread(
                    target=self.__read_stream,
                    args=(self.pid.stderr, self.stderr),
                    daemon=True
                )
                stderr_thread.start()

            # Start a thread to wait for process termination
            process_thread = threading.Thread(
                target=self.__wait_for_process,
                daemon=True
            )
            process_thread.start()

            return self.pid.poll() is None  # True if process is running

        except FileNotFoundError as fnf_error:
            print(f"File not found error: {fnf_error}")
            self.is_running = False
            return False
        except PermissionError as perm_error:
            print(f"Permission error: {perm_error}")
            self.is_running = False
            return False
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            self.is_running = False
            return False


    def kill_program(self):
        if self.is_running:
            self.pid.kill()
            self.is_running = False


    def __read_stream(self, stream, output_func):
        """
        Reads the stream line by line and sends the data to the given output function.

        :param stream: The stream to read from (stdout or stderr).
        :param output_func: The function to call with the stream data.
        """
        try:
            for line in iter(stream.readline, ''):
                output_func(line)
        except Exception as e:
            print(f"Error reading stream: {e}")
        finally:
            stream.close()

    def __wait_for_process(self):
        """
        Waits for the subprocess to finish and updates the is_running flag.
        """
        if self.pid:
            self.pid.wait()
            self.is_running = False