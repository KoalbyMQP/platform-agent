# Platform Agent

This is the Core Platform Agent for Debiand based systems. It is run directly on the robot and connects user-level code, written using the python library to the driverstation. 

## Installation
1. `git clone git@github.com:KoalbyMQP/platform-agent.git`
2. `sudo chmod +x platform-agent/DEBIAN/postinst`
3. `dpkg-deb --build platform`
4. `sudo dpkg -i platform.deb`
5. `sudo apt install ./platform.deb`
