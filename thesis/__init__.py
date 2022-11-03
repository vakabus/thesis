from __future__ import annotations

import logging
import shlex
import subprocess
from base64 import b64encode
from dataclasses import dataclass
from enum import Enum, auto
from functools import cache
from ipaddress import IPv4Address, IPv6Address, ip_address
from itertools import count
from pathlib import Path
from time import sleep
from typing import Type

import click
from openssh_wrapper import SSHError
from proxmoxer import ProxmoxAPI, ProxmoxResource
from typing_extensions import Self

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Status(Enum):
    RUNNING = auto()
    STOPPED = auto()
    UNKNOWN = auto()

    @classmethod
    def from_str(cls: Type[Status], s: str) -> Self:
        return {"running": cls.RUNNING, "stopped": cls.STOPPED}.get(s, cls.UNKNOWN)


@dataclass
class Host:
    api: ProxmoxResource
    name: str

    def wait_for_all_tasks(self):
        while self.api.tasks.get(source="active"):
            sleep(0.3)

    def cpu_utilization(self) -> float:
        """
        number of allocated vcpu cores / real cpu cores
        """
        cpus = self.api.status.get()["cpuinfo"]["cpus"]
        allocated_cpus = sum((vm["cpus"] for vm in self.api.qemu.get() if vm["status"] == "running"))
        return allocated_cpus / cpus


@dataclass
class VM:
    api: ProxmoxResource
    vmid: int
    name: str
    host: Host

    @property
    def status(self) -> Status:
        for vm in self.host.api.qemu.get():
            if vm["vmid"] == self.vmid:
                return Status.from_str(vm["status"])
        else:
            raise AssertionError

    def start(self):
        wait_for_task(self.api.status.start.post())

    def destroy(self):
        if self.status is Status.RUNNING:
            logger.debug("Stopping the VM")
            wait_for_task(self.api.status.stop.post())
        logger.debug("Deleting...")
        wait_for_task(self.api.delete())
        current_vms.cache_clear()
        logger.info(f"VM destroyed (vmid={self.vmid})")

    def wait_for_agent_online(self):
        while True:
            try:
                self.api.agent.info.get()
                return
            except SSHError:
                sleep(0.5)

    def upload_file(self, file: Path, vmpath: str | Path):
        logger.debug("file upload starting: %s -> %s", file, vmpath)
        self.wait_for_agent_online()
        data = b64encode(file.read_bytes()).decode("ascii")
        self.api.agent("file-write").post(content=data, file=str(vmpath), encode=False)
        logger.debug("file upload complete")

    def run_command(self, command: str, stdin: str = None):
        logger.info(f"running command: {command}")
        self.wait_for_agent_online()
        res = self.api.agent.exec.post(**{"command": command, "input-data": stdin})
        return res["pid"]

    def run_command_blocking(self, *args, **kwargs):
        pid = self.run_command(*args, **kwargs)
        logger.debug("running command: waiting for completion")
        data = {"exited": False}
        while not (data := self.api.agent("exec-status").get(pid=pid))["exited"]:
            sleep(0.3)
        exitcode = data.get("exitcode") or data.get("signal")
        logger.info(f"command exited with exitcode {exitcode}")
        if "err-data" in data:
            logger.debug("stderr:\n%s", data["err-data"])
        if "out-data" in data:
            logger.debug("stdout:\n%s", data["out-data"])
        # do something ??

    def run_command_over_blocking_ssh(self, command: str | list[str]) -> int:
        ips = self.list_ips()
        if isinstance(command, str):
            command = shlex.split(command)
        retcode = subprocess.call(
            ["ssh", "-o", "UserKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=no", f"vasek@{ips[0]}"] + command
        )
        return retcode

    def list_ips(self) -> list[IPv4Address | IPv6Address]:
        self.wait_for_agent_online()
        res = self.api.agent("network-get-interfaces").get()

        addrs = []
        for interface in res["result"]:
            if interface["name"] == "lo":
                continue  # skip loopback
            for addr in interface["ip-addresses"]:
                addrs.append(ip_address(addr["ip-address"]))
        return addrs

    def interactive_ssh(self):
        ips = self.list_ips()
        subprocess.call(
            ["ssh", "-o", "UserKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=no", f"vasek@{ips[0]}"]
        )


@cache
def api_proxy() -> ProxmoxAPI:
    return ProxmoxAPI("tapir.lan", user="root", backend="openssh", service="pve")


@cache
def hosts() -> dict[str, Host]:
    logger.info("host detection running")
    prox = api_proxy()
    res = {}
    for x in prox.nodes.get():
        if x["status"] == "offline":
            continue

        res[x["node"]] = Host(api=prox.nodes(x["node"]), name=x["node"])
    logger.info(f"host detection complete, found {len(res)} usable hosts")
    return res


@cache
def current_vms():
    logger.debug("VM detection running")
    vms = []
    for host in hosts().values():
        for vm in host.api.qemu.get():
            if vm["vmid"] != 100:  # protect vrejsek, do not touch this VM
                vms.append(VM(vmid=vm["vmid"], name=vm["name"], api=host.api.qemu(vm["vmid"]), host=host))
    logger.debug(f"VM detection completed, found {len(vms)} VMs")
    return vms


def wait_for_task(task: str):
    if isinstance(task, dict):
        if "errors" in task:
            msg: str = task["errors"].decode("utf8")
            task = msg[msg.index("UPID") : msg.index("root@pam:") + len("root@pam:")]
            logger.warning("weird return value, attempt to extract task id resulted in '%s'", task)
        else:
            raise ValueError("can't wait for a non-task", task)
    elif isinstance(task, ProxmoxResource):
        raise ValueError("expected task id, got object type ProxmoxResource")
    elif isinstance(task, str):
        if not task.startswith("UPID") or not task.endswith("root@pam:"):
            logger.warning("weird task ID: '%s'", task)
            task = task[task.index("UPID") : task.index("root@pam:") + len("root@pam:")]
            logger.warning("weird task id, attempt to extract task id resulted in '%s'", task)
        pass
    else:
        logger.warning("weird task ID: '%s'", task)

    hostname = task.split(":")[1]
    host = hosts()[hostname]

    data = {"status": ""}
    while data["status"] != "stopped":
        data = host.api.tasks(task).status.get()
        sleep(0.3)
    return data


def find_free_vmid() -> int:
    ids = set((v.vmid for v in current_vms()))
    for i in count(start=500):
        if i not in ids:
            return i


def get_vm_by_name(name: str) -> VM:
    for vm in current_vms():
        if vm.name == name:
            return vm
    raise KeyError(f"VM with name '{name}' not found")


def get_vm_by_vmid(vmid: int) -> VM:
    for vm in current_vms():
        if vm.vmid == vmid:
            return vm
    raise KeyError(f"VM with vmid '{vmid}' not found")


def clone_fedora36(name: str) -> VM:
    logger.debug("new Fedora36 clone creation running")

    host = min(hosts().values(), key=lambda h: h.cpu_utilization())
    logger.debug(f"new Fedora36 clone, will be using host '{host.name}'")

    # clone
    vmid = find_free_vmid()
    templateid = {"tapir": 9010, "zebra": 9011}[host.name]

    host.api.qemu(templateid).clone.post(name=name, newid=vmid)
    host.wait_for_all_tasks()
    current_vms.cache_clear()

    # start
    vm = get_vm_by_vmid(vmid)
    vm.start()
    logger.debug("new Fedora36 clone creation completed")

    return vm


@click.group
def cli():
    pass


@cli.group()
def destroy():
    pass


@destroy.command(name="vmid")
@click.argument("vmid", nargs=-1, type=int)
def destroy_vmid(vmid: list[int]):
    for i in vmid:
        get_vm_by_vmid(i).destroy()


@destroy.command(name="name")
@click.argument("name", nargs=-1, type=str)
def destroy_name(name: list[str]):
    for n in name:
        get_vm_by_name(n).destroy()


@cli.group()
def ssh():
    pass


@ssh.command("vmid")
@click.argument("vmid", type=int, nargs=1)
def ssh_vmid(vmid: int):
    get_vm_by_vmid(vmid).interactive_ssh()


@ssh.command("name")
@click.argument("name", type=str, nargs=1)
def ssh_vmid(name: str):
    get_vm_by_name(name).interactive_ssh()


@cli.command()
@click.option("--rm", required=False, default=False, help="delete vm after exit", is_flag=True)
@click.argument("name", required=True, nargs=1, type=str)
def provision(rm, name):
    vm = None
    try:
        vm = clone_fedora36(name)
        try:
            vm.wait_for_agent_online()

            vm.upload_file(Path("install-scripts/fedora36-general-init.sh"), "/tmp/init.sh")
            vm.run_command_over_blocking_ssh(f"bash /tmp/init.sh {name}")
            # the previous script ends with a reboot
            sleep(1)
            vm.wait_for_agent_online()
            vm.interactive_ssh()

        except KeyboardInterrupt:
            logger.info("received Ctrl+C, aborting...")
            pass
    finally:
        if vm and rm:
            logger.warning("Destroying the VM...")
            vm.destroy()


@cli.command()
@click.argument("vm_name", type=str, nargs=1)
@click.argument("source", type=click.Path(exists=True), nargs=1)
@click.argument("dest", type=click.Path(exists=False), nargs=1)
def upload(vm_name: str, source: str, dest: str):
    vm = get_vm_by_name(vm_name)
    vm.upload_file(Path(source), dest)


@cli.command()
@click.argument("vm_name", type=str, nargs=1)
def start(vm_name: str):
    get_vm_by_name(vm_name).start()


if __name__ == "__main__":
    cli()
