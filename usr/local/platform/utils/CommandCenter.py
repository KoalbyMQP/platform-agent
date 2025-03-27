import json
import os.path
import subprocess
import socket

from utils.ExecutionManager import ExecutionManager
from utils.DeviceManager import DeviceManager

class CommandCenter:

    def __init__(self, execution_manager: ExecutionManager, device_manager: DeviceManager):
        self.execution_manager = execution_manager
        self.device_manager = device_manager

    def execute_command(self, command: str) -> (bool, bytearray):
        components = command.split(" ")
        args = "".join(components[1:])
        match components[0]:
            case "get-ip":
                return self.__get_ip()
            case "switch-project":
                if len(components) < 2:
                    return False, "Invalid usage. Usage: switch-project <project_id>"
                return self.__switch_project(components[1])
            case "list-projects":
                return self.__list_projects()
            case "get-project":
                return self.__get_project()
            case "get-branch":
                return self.__get_branch()
            case "get-branches":
                return self.__get_branches()
            case "get-commit-hash":
                return self.__get_commit_hash()
            case "get-target":
                return self.__get_target()
            case "get-targets":
                return self.__get_targets()
            case "get-project-directory":
                return self.__get_project_directory()
            case "switch-branch":
                if len(components) < 2:
                    return False, "Invalid usage. Usage: switch-branch <branch_name>"
                return self.__switch_branch(components[1])
            case "change-target":
                if len(components) < 2:
                    return False, "Invalid usage. Usage: switch-target <target_name>"
                return self.__change_target(components[1])
            case "pull-changes":
                return self.__pull_changes()
            case "install-project":
                if len(components) < 3:
                    return False, "Invalid usage. Usage: install-project <project_id> <url> [token]"
                return self.__install_project(components[1], components[2], components[3] if len(components) > 3 else None)
            case "execute-target":
                return self.__execute_target()
            case "tinker":
                return self.__tinker()
            case "stop-execution":
                return self.__stop_execution()
            case "list-devices":
                return self.__list_devices()
            case "set-state":
                return self.__set_state(args)
            case "get-state":
                state = self.device_manager.state_for_device(components[1])
                return True, json.dumps(state)
            case "get-states":
                states = self.device_manager.all_device_states
                states_json = json.dumps(states)
                return True, bytearray('0,' + states_json, "utf-8")
            case _:
                print("Unknown command: ", command)
                return False, "Command not recognized"

    def execute_shell_command(self, command: str, atRoot=False) -> (bool, str):
        base_dir = os.getcwd()
        try:
            with open(os.getcwd() + "/manifest.json") as manifest_file:
                project_id = json.load(manifest_file)["selected_project"]
            if project_id is None:
                return False, "No projects installed"
            if not atRoot:
                os.chdir(os.path.join(os.getcwd(), "projects", project_id))

            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            os.chdir(base_dir)
            if stderr:
                return False, stderr.decode("utf-8")
            return True, stdout.decode("utf-8")
        except Exception as e:
            return False, str(e)
        finally:
            os.chdir(base_dir)


    def __get_ip(self) -> (bool, str):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                lan_ip = s.getsockname()[0]
            return True, lan_ip
        except Exception as e:
            return False, str(e)

    def __switch_project(self, project_id: str) -> (bool, str):
        project_exists, _ = self.__get_project()
        if not project_exists:
            return False, "No projects installed"

        with open(os.getcwd() + "/manifest.json") as f:
            manifest = json.load(f)

        for project in manifest["projects"]:
            if project["id"] == project_id:
                manifest["selected_project"] = project_id
                with open(os.getcwd() + "/manifest.json", "w") as f:
                    json.dump(manifest, f, indent=4)

                _, directory = self.__get_project_directory()
                self.device_manager.listen_to_robot(directory + "/robot.py")
                return True, ""
        return False, "Project not found"

    def __list_projects(self) -> (bool, str):
        with open(os.getcwd() + "/manifest.json") as f:
            manifest = json.load(f)
        return True, ",".join(p['id'] for p in manifest["projects"])

    def __get_project(self) -> (bool, str):
        with open(os.getcwd() + "/manifest.json") as f:
            manifest = json.load(f)
        project = manifest["selected_project"]
        if project is None:
            return False, "No projects installed"
        return True, project

    def __get_branch(self) -> (bool, str):
        result, data = self.execute_shell_command("git branch")
        if not result:
            return False, data
        branches = data.split("\n")

        for branch in branches:
            if branch.startswith("*"):
                return True, branch[2:]

        return False, "Unexpected error occurred"

    def __get_branches(self) -> (bool, str):
        result, data = self.execute_shell_command("git branch -a")
        if not result:
            return False, data
        branches = set()
        for item in data.split("\n"):
            if item.startswith("*"):
                branches.add(item[2:].strip())
            elif "/" in item:
                branches.add(item[item.rindex("/") + 1:].strip())
            else:
                branches.add(item.strip())
        if '' in branches:
            branches.remove('')
        alphabetical = sorted(branches, key=lambda x: x.lower())
        return True, ",".join(alphabetical)

    def __get_commit_hash(self) -> (bool, str):
        result, data = self.execute_shell_command("git rev-parse HEAD")
        if result:
            return True, data[:7]
        return False, data

    def __get_target(self) -> (bool, str):
        with open(os.getcwd() + "/manifest.json") as f:
            manifest = json.load(f)
        current_project = manifest["selected_project"]
        for project in manifest["projects"]:
            if project["id"] == current_project:
                return True, project["target"]
        return False, "Project not found"


    def __get_project_directory(self) -> (bool, str):
        with open(os.getcwd() + "/manifest.json") as f:
            manifest = json.load(f)
        current_project = manifest["selected_project"]
        return True, os.path.join(os.getcwd(), "projects", current_project)

    def __get_targets(self) -> (bool, str):
        result, data = self.execute_shell_command("find . -type f \\( -name '*.py' -o -name '*.c' -o -name '*.cpp' \\)")
        if not result:
            return False, data
        return True, data.replace("\n", ",").strip(",")

    def __switch_branch(self, branch: str) -> (bool, str):
        result, data = self.execute_shell_command(f"git checkout {branch}")

        if not result or data.startswith("error"):
            return False, data

        with open(os.getcwd() + "/manifest.json") as f:
            manifest = json.load(f)
        self.__install_requirements(manifest["selected_project"])

        # Check if target file still exists. If not, switch to random .py/.c/.cpp file
        for i in range(len(manifest["projects"])):
            if manifest["projects"][i]["id"] == manifest["selected_project"]:
                target = manifest["projects"][i]["target"]
                if not os.path.exists(target):
                    result, data = self.execute_shell_command("find . -type f \\( -name '*.py' -o -name '*.c' -o -name '*.cpp' \\)")
                    if not result:
                        return False, data
                    files = data.split("\n")
                    manifest["projects"][i]["target"] = files[0]
                    with open(os.getcwd() + "/manifest.json", "w") as f:
                        json.dump(manifest, f, indent=4)
        return True, ""

    def __change_target(self, target: str) -> (bool, str):
        with open(os.getcwd() + "/manifest.json") as f:
            manifest = json.load(f)
        current_project = manifest["selected_project"]
        for project in manifest["projects"]:
            if project["id"] == current_project:
                project["target"] = target
                with open(os.getcwd() + "/manifest.json", "w") as f:
                    json.dump(manifest, f, indent=4)
                return True, ""
        return False, "Project not found"

    def __pull_changes(self) -> (bool, str):
        result, data = self.execute_shell_command("git pull")
        self.__install_requirements(json.load(open(os.getcwd() + "/manifest.json"))["selected_project"])
        if not result:
            return False, data

        return True, ""

    def __install_project(self, id, url, token=None) -> (bool, str):
        with open(os.getcwd() + "/manifest.json") as f:
            manifest = json.load(f)
        for project in manifest["projects"]:
            if project["id"] == id:
                return False, "Project already installed"

        if token is not None:
            key_path = os.path.expanduser("~/.ssh/github_deploy_key")
            os.makedirs(os.path.expanduser("~/.ssh"), exist_ok=True)
            with open(key_path, "w") as key_file:
                key_file.write(token)
            os.chmod(key_path, 0o600)

        current_project = manifest["selected_project"]
        _, response = self.execute_shell_command(f"git clone --progress {url} projects/{id}", atRoot=True)

        # Git writes everything to stderr, so we need to manually check if the folder exists. This is stupid.
        # https://stackoverflow.com/questions/32685568/git-clone-writes-to-sderr-fine-but-why-cant-i-redirect-to-stdout
        if not os.path.exists(f"projects/{id}"):
            return False, "Failed to clone project"

        _, response = self.execute_shell_command(f"python3 -m venv pyenvs/{id}", atRoot=True)
        self.__install_requirements(id)

        manifest["projects"].append({
            "id": id,
            "target": ""
        })
        with open(os.getcwd() + "/manifest.json", "w") as f:
            json.dump(manifest, f, indent=4)

        switch_project_status, _ = self.__switch_project(id)
        list_targets_status, targets = self.__get_targets()
        if switch_project_status and list_targets_status:
            set_target_status, _ = self.__change_target(targets.split(",")[0])
            if set_target_status:
                return True, ""
        for project in manifest["projects"]:
            if project["id"] == id:
                manifest["projects"].remove(project)
                manifest["selected_project"] = current_project
                with open(os.getcwd() + "/manifest.json", "w") as f:
                    json.dump(manifest, f, indent=4)
        os.removedirs(f"projects/{id}")
        return False, "Failed to find targets"

    def __execute_target(self) -> (bool, str):
        with open(os.getcwd() + "/manifest.json") as f:
            manifest = json.load(f)
        project = manifest["selected_project"]
        if project is None:
            return False, "No projects installed"

        target = ""
        env = os.getcwd() + "/pyenvs/" + project
        for p in manifest["projects"]:
            if p["id"] == project:
                target = os.getcwd() +  "/projects/" + project + "/" + p["target"]
                break

        if target == "":
            return False, "No target set"

        if target.endswith(".py"):
            return self.execution_manager.run_python_program(env, target), ""
        else:
            filetype = target.split(".")[-1]
            return False, f"{filetype} files are not yet supported"

    def __tinker(self) -> (bool, str):
        _, directory = self.__get_project_directory()
        self.device_manager.listen_to_robot(f"{directory}/robot.py")
        return True, ""

    def __stop_execution(self) -> (bool, str):
        self.device_manager.reload_robot()
        self.execution_manager.kill_program()
        return True, ""

    def __install_requirements(self, project_id):
        envPath = os.getcwd() + "/pyenvs/" + project_id
        requirements_path = None
        # Check all files recursively within projects/project_id for requirements.txt
        for root, dirs, files in os.walk(os.getcwd() + "/projects/" + project_id):
            for file in files:
                if file == "requirements.txt":
                    requirements_path = os.path.join(root, file)
                    break
            if requirements_path:
                break
        if requirements_path:
            print("Installing...")
            self.execute_shell_command(f"{envPath}/bin/pip install -r {requirements_path}")
        else:
            print("Exiting without install")

    def __list_devices(self) -> (bool, str):
        devices = [d for d in self.device_manager.get_devices()]
        return True, ",".join(devices)


    def __get_state(self, uuid: str) -> (bool, str):
        state = self.device_manager.state_for_device(uuid)
        state_json = json.dumps(state)
        return True, bytearray('0,' + state_json, "utf-8")

    def __set_state(self, state: str) -> (bool, str):
        print(type(state))
        print(state)
        try:
            state = json.loads(state)
            if isinstance(state["state"], str):
                state["state"] = json.loads(state["state"])
            self.device_manager.update_device_state(state)
            return True, bytearray("0,", "utf-8")
        except(ValueError, json.JSONDecodeError) as e:
            print(e)
            return False, "Failed to parse state"
