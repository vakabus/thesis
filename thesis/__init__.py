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
from threading import Thread
from time import sleep
from typing import List, Optional, Type

import click
from openssh_wrapper import SSHError
from proxmoxer import ProxmoxAPI, ProxmoxResource, ResourceException
from typing_extensions import Self

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logging.getLogger("urllib3").setLevel(logging.INFO)


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
            except (SSHError, ResourceException):
                sleep(0.3)

    def wait_for_systemd(self):
        self.wait_for_agent_online()

        logger.info("waiting for system boot: system booted, waiting for systemd initialization")

        # wait for DHCP
        ips = self.list_ips()
        while not sum((isinstance(i, IPv4Address) for i in ips)):
            sleep(0.3)
            ips = self.list_ips()

        while self.run_ssh_command_blocking("systemctl is-system-running --wait"):
            sleep(0.3)

    def upload_file(self, file: Path, vmpath: str | Path):
        logger.debug("file upload starting: %s -> %s", file, vmpath)
        self.wait_for_agent_online()
        data = b64encode(file.read_bytes()).decode("ascii")
        self.api.agent("file-write").post(content=data, file=str(vmpath), encode=int(False))
        logger.debug("file upload complete")

    def rsync_files(self, source: Path, vmpath: str | Path):
        logger.debug("rsync file upload starting: %s -> %s", source, vmpath)
        ip = self.list_ips()[0]
        r = subprocess.call(
            [
                "rsync",
                "-e",
                "ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no",
                "--progress",
                "-r",
                str(source),
                f"vasek@{ip}:{vmpath}",
            ]
        )
        assert r == 0

    def run_agent_command(self, command: str, stdin: str = None):
        logger.info(f"running command: {command}")
        res = self.api.agent.exec.post(**{"command": command, "input-data": stdin})
        return res["pid"]

    def run_agent_command_blocking(self, *args, **kwargs) -> int:
        pid = self.run_agent_command(*args, **kwargs)
        logger.debug("running command: waiting for completion")
        data = {"exited": False}
        while not (data := self.api.agent("exec-status").get(pid=pid))["exited"]:
            sleep(0.3)
        exitcode = data.get("exitcode") or data.get("signal")
        logger.debug(f"command exited with exitcode {exitcode}")
        if "err-data" in data:
            logger.debug("stderr:\n%s", data["err-data"])
        if "out-data" in data:
            logger.debug("stdout:\n%s", data["out-data"])
        return exitcode

    def run_ssh_command_blocking(self, command: str | list[str]) -> int:
        ips = self.list_ips()
        if isinstance(command, str):
            command = shlex.split(command)
        retcode = subprocess.call(
            ["ssh", "-o", "UserKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=no", f"vasek@{ips[0]}"] + command
        )
        return retcode

    def run_ssh_command_get_output(self, command: str | list[str]) -> str:
        ips = self.list_ips()
        if isinstance(command, str):
            command = shlex.split(command)
        output = subprocess.check_output(
            ["ssh", "-o", "UserKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=no", f"vasek@{ips[0]}"] + command
        )
        return output.decode("utf8").strip()

    def list_ips(self) -> list[IPv4Address | IPv6Address]:
        self.wait_for_agent_online()
        res = self.api.agent("network-get-interfaces").get()

        addrs = []
        for interface in res["result"]:
            if interface["name"] == "lo" or interface["name"].startswith("docker"):
                continue  # skip loopback and docker
            for addr in interface.get("ip-addresses", []):
                addrs.append(ip_address(addr["ip-address"]))
        addrs.sort(key=lambda x: (str(type(x)), x))
        return addrs

    def interactive_ssh(self):
        ips = self.list_ips()
        subprocess.call(
            ["ssh", "-o", "UserKnownHostsFile=/dev/null", "-o", "StrictHostKeyChecking=no", f"vasek@{ips[0]}"]
        )


@cache
def get_root_password() -> str:
    """
    Utilizes unlocked ssh-agent to get the root password from the actual Proxmox cluster we are connecting to.
    """
    return subprocess.check_output(["ssh", "root@tapir.lan", "cat", "passwd"]).decode("utf8").strip()


@cache
def api_proxy() -> ProxmoxAPI:
    return ProxmoxAPI(
        "tapir.lan", user="root@pam", backend="https", password=get_root_password(), verify_ssl=False, service="pve"
    )


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
    return find_free_vmids(1)[0]


def find_free_vmids(cnt: int) -> list[int]:
    res = []
    ids = set((v.vmid for v in current_vms()))
    for i in count(start=500):
        if i not in ids:
            res.append(i)
        if len(res) == cnt:
            return res


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


def clone_fedora36(name: str, vmid: int | None = None) -> VM:
    logger.debug("new Fedora36 clone creation running")

    host = min(hosts().values(), key=lambda h: h.cpu_utilization())
    logger.debug(f"new Fedora36 clone, will be using host '{host.name}'")

    # clone
    if not vmid:
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


@cli.command("provision-node")
@click.option("--rm", required=False, default=False, help="delete vm after exit", is_flag=True)
@click.option(
    "--post-init-script",
    required=False,
    type=click.Path(exists=True, readable=True),
    is_flag=False,
    default=None,
    nargs=1,
    help="script to run after setup",
)
@click.option("-i", "--interactive", required=False, is_flag=True, help="run interactive session after setup")
@click.argument("name", required=True, nargs=1, type=str)
def provision_node(rm: bool, post_init_script: Optional[str], interactive: bool, name: str):
    provision_node_impl(rm, post_init_script, interactive, name)


def provision_node_impl(
    rm: bool, post_init_script: Optional[str], interactive: bool, name: str, vmid: int | None = None
):
    vm = None
    try:
        vm = clone_fedora36(name, vmid=vmid)
        try:
            vm.wait_for_systemd()

            vm.upload_file(Path("install-scripts/fedora36-general-init.sh"), "/tmp/init.sh")
            vm.run_ssh_command_blocking(f"bash /tmp/init.sh {name}")
            # the previous script ends with a reboot
            sleep(1)
            vm.wait_for_systemd()

            # copy ovn-kubernetes repository to the user's home and install the binaries
            vm.rsync_files("ovn-kubernetes", "")
            vm.run_ssh_command_blocking("sudo make -C ovn-kubernetes/go-controller install")

            if post_init_script:
                vm.upload_file(Path(post_init_script), "/tmp/post-init-script")
                vm.run_ssh_command_blocking("sudo chmod +x /tmp/post-init-script && /tmp/post-init-script")

            if interactive:
                vm.interactive_ssh()

        except KeyboardInterrupt:
            logger.info("received Ctrl+C, aborting...")
            pass
    finally:
        if vm and rm:
            logger.warning("Destroying the VM...")
            vm.destroy()


@cli.command("provision")
@click.argument("names", required=True, nargs=-1, type=str)
def provision(names: List[str]):
    if len(names) == 0:
        logger.error("at least one node is required in a cluster")
        return 1

    threads: list[Thread] = []

    # allocate vmids
    vmids = find_free_vmids(len(names))

    # setup master node
    t = Thread(
        target=provision_node_impl,
        args=(False, "install-scripts/ovn-kubernetes-master.sh", False, names[0]),
        kwargs={"vmid": vmids[0]},
    )
    threads.append(t)
    t.start()

    # setup workers
    for worker, vmid in zip(names[1:], vmids[1:]):
        sleep(3)  # stupid way to prevent races
        t = Thread(target=provision_node_impl, args=(False, None, False, worker), kwargs={"vmid": vmid})
        threads.append(t)
        t.start()

    # wait for all the threads
    for t in threads:
        t.join()
    logger.info("all nodes initialized")

    # let the workers join the cluster
    for worker in names[1:]:
        logger.info("node %s is joining the cluster", worker)
        join_command = get_vm_by_name(names[0]).run_ssh_command_get_output(
            "sudo kubeadm token create --print-join-command"
        )
        logger.debug(join_command)
        get_vm_by_name(worker).run_agent_command_blocking(
            join_command + " --cri-socket=unix:///var/run/cri-dockerd.sock"
        )


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
