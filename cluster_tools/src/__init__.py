from __future__ import annotations
from abc import ABC, abstractmethod

import logging
import shlex
import subprocess
from base64 import b64encode
from dataclasses import dataclass
from enum import Enum, auto
from functools import cache
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from itertools import count
from pathlib import Path
from threading import Thread
from time import sleep
from typing import Callable, List, Literal, Optional, Type, TypeVar
import os

import click
from openssh_wrapper import SSHError
from proxmoxer import ProxmoxAPI, ProxmoxResource, ResourceException
from typing_extensions import Self

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logging.getLogger("urllib3").setLevel(logging.INFO)


class NotReadyError(Exception):
    pass


class Constants:
    PROXMOX_API_HOST: str = "tapir.folk-stork.ts.net"
    PROXMOX_USER = "root@pam"
    PROXMOX_TEMPLATE_VMIDS: dict[str, int] = {"tapir": 9020, "zebra": 9011}
    PROXMOX_TEMPLATE_USER: str = "root"
    PROXMOX_PROTECTED_VMIDS: list[Callable[[int], bool]] = [
        lambda vmid: vmid < 500,
        lambda vmid: vmid >= 1000
    ]

    @staticmethod
    def is_vmid_protected(vmid: int):
        for check in Constants.PROXMOX_PROTECTED_VMIDS:
            if check(vmid):
                return True
        return False

    @staticmethod
    def _get_proxmox_password() -> str:
        """
        Utilizes unlocked ssh-agent to get the root password from the actual Proxmox cluster we are connecting to.
        """
        return subprocess.check_output(["ssh", f"root@tapir.folk-stork.ts.net", "cat", "passwd"]).decode("utf8").strip()

    PROXMOX_PASSWORD = _get_proxmox_password()

    HOME_NETWORK: list[ip_network] = [
        ip_network("192.168.1.0/24"),
        ip_network("2001:67c:2190:1506::/64"),
    ]

    SSH_OPTS: list[str] = [
        "-t",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "StrictHostKeyChecking=no",
    ]


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


class Machine(ABC):
    @abstractmethod
    def wait_for_systemd(self) -> None:
        pass

    @abstractmethod
    def upload_files(self, file: Path, vmpath: str | Path):
        pass

    @abstractmethod
    def run_ssh_command_blocking(self, command: str | list[str]) -> int:
        pass

    @abstractmethod
    def run_ssh_command_get_output(self, command: str | list[str]) -> str:
        pass

    def interactive_ssh(self, command: list[str] | str = []):
        self.run_ssh_command_blocking(command)


def rsync(source: Path | str, dest: Path | str, user: str, host: str, sudo_rsync:bool=False):
    args = [
        "rsync",
        "-e",
        f"ssh {' '.join(Constants.SSH_OPTS)}",
        #"--progress",
        "-a",
            # the --stats option is meaningless, we just dont want an empty argument there
        #"--rsync-path='sudo_rsync'" if sudo_rsync else "--stats",
        str(source),
        f"{user}@[{host}]:{dest}",
    ]
    r = subprocess.call(args)
    assert r == 0


T = TypeVar("T")
def _ssh(invoke: Callable[[list[str]], T], user: str, host: str, opts: list[str], command: list[str] | str) -> T:
    if isinstance(command, str):
        command = shlex.split(command)
    if isinstance(command, tuple):
        command = list(command)
    return invoke(
        [
            "ssh",
            *opts,
            f"{user}@{host}",
        ]
        + command
    )

def ssh_call(user: str, host: str, opts: list[str], command: list[str] | str) -> int:
    return _ssh(subprocess.call, user, host, opts, command)

def ssh_output(user: str, host: str, opts: list[str], command: list[str] | str) -> str:
    invoke = lambda *a, **k: subprocess.check_output(*a, **k).decode("utf-8").strip()
    return _ssh(invoke, user, host, opts, command)

@dataclass
class NetMachine(Machine):
    ip: str

    def wait_for_systemd(self) -> None:
        while self.run_ssh_command_blocking("true"):
            sleep(1)

    def upload_files(self, file: Path, dest: str | Path):
        rsync(file, dest, "root", self.ip)

    def run_ssh_command_blocking(self, command: str | list[str]) -> int:
        return ssh_call("root", self.ip, Constants.SSH_OPTS, command)


    def run_ssh_command_get_output(self, command: str | list[str]) -> str:
        return ssh_output("root", self.ip, Constants.SSH_OPTS, command)


@dataclass
class VM(Machine):
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

        # wait for proper IP assignment
        logger.debug("waiting for ip")
        while True:
            try:
                _ = self.get_ip()
                break
            except NotReadyError:
                pass

        logger.debug("waiting for functional ssh")
        while self.run_ssh_command_blocking("true"):
            sleep(1)

    def upload_file(self, file: Path, vmpath: str | Path):
        logger.debug("file upload starting: %s -> %s", file, vmpath)
        self.wait_for_agent_online()
        data = b64encode(file.read_bytes()).decode("ascii")
        self.api.agent("file-write").post(content=data, file=str(vmpath), encode=int(False))
        logger.debug("file upload complete")

    def upload_files(self, source: Path, vmpath: str | Path, as_root: bool = True):
        rsync(source, vmpath, Constants.PROXMOX_TEMPLATE_USER, self.get_ip(), sudo_rsync=as_root)
    
    def rsync_files_back(self, vmpath: str | Path, source: Path, as_root: bool = True):
        logger.debug("rsync file upload starting: %s -> %s", source, vmpath)
        ip = self.get_ip()
        args = [
            "rsync",
            "-e",
            f"ssh {' '.join(Constants.SSH_OPTS)}",
            "--progress",
            "-r",
                # the --stats option is meaningless, we just dont want an empty argument there
            "--rsync-path='sudo_rsync'" if as_root else "--stats",
            f"{Constants.PROXMOX_TEMPLATE_USER}@[{ip}]:{vmpath}",
            str(source),
        ]

        logger.debug("rsync args: %s", str(args))
        r = subprocess.call(args)
        logger.debug("rsync command exited with exit code %d", r)
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
        return ssh_call(Constants.PROXMOX_TEMPLATE_USER, str(self.get_ip()), Constants.SSH_OPTS, command)

    def run_ssh_command_get_output(self, command: str | list[str]) -> str:
        return ssh_output(Constants.PROXMOX_TEMPLATE_USER, str(self.get_ip()), Constants.SSH_OPTS, command)

    def list_ips(self) -> list[IPv4Address | IPv6Address]:
        self.wait_for_agent_online()
        res = self.api.agent("network-get-interfaces").get()

        addrs = []
        for interface in res["result"]:
            for addr in interface.get("ip-addresses", []):
                addrs.append(ip_address(addr["ip-address"]))
        addrs.sort(key=lambda x: (str(type(x)), x))
        return addrs

    def get_ip(self) -> IPv4Address | IPv6Address:
        """
        Returns an IP address that is inside the home network.
        """
        for ip in self.list_ips():
            for net in Constants.HOME_NETWORK:
                try:
                    if ip_network(ip).subnet_of(net):
                        return ip
                except TypeError:  # ignore IP version mismatch
                    pass
        raise NotReadyError


@cache
def api_proxy() -> ProxmoxAPI:
    return ProxmoxAPI(
        Constants.PROXMOX_API_HOST,
        user=Constants.PROXMOX_USER,
        backend="https",
        password=Constants.PROXMOX_PASSWORD,
        verify_ssl=False,
        service="pve",
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
def current_vms() -> list[VM]:
    logger.debug("VM detection running")
    vms: list[VM] = []
    for host in hosts().values():
        for vm in host.api.qemu.get():
            if not Constants.is_vmid_protected(vm["vmid"]):  # prevent manipulation with protected VMs
                vms.append(VM(vmid=vm["vmid"], name=vm["name"], api=host.api.qemu(vm["vmid"]), host=host))
    logger.debug(f"VM detection completed, found {len(vms)} VMs")

    # check for name collisions
    names = set()
    for vm in vms:
        if vm.name not in names:
            names.add(vm.name)
        else:
            logger.error(f"Duplicate VM name '{vm.name}'")
            exit(1)

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


def get_machine_by_name(name: str) -> Machine:
    if '.' in name:
        try:
            import socket
            return NetMachine(ip=socket.gethostbyname(name))
        except socket.gaierror:
            return get_vm_by_name(name)
    else:
        return get_vm_by_name(name)
    


def get_vm_by_vmid(vmid: int) -> VM:
    for vm in current_vms():
        if vm.vmid == vmid:
            return vm
    raise KeyError(f"VM with vmid '{vmid}' not found")


def clone_fedora(name: str, vmid: int | None = None) -> VM:
    logger.debug("new Fedora clone creation running")

    host = min(hosts().values(), key=lambda h: h.cpu_utilization())
    logger.debug(f"new Fedora clone, will be using host '{host.name}'")

    # clone
    if not vmid:
        vmid = find_free_vmid()
    templateid = Constants.PROXMOX_TEMPLATE_VMIDS[host.name]

    host.api.qemu(templateid).clone.post(name=name, newid=vmid)
    host.wait_for_all_tasks()
    current_vms.cache_clear()

    # start
    vm = get_vm_by_vmid(vmid)
    vm.start()
    logger.debug("new Fedora clone creation completed")

    return vm

def node_hostname(num: int) -> str:
    assert num > 0
    return f"kb{num}"

@click.group
def cli():
    """
    Utilities for working with the dev environment, automatically provisioning configured Kubernetes clusters and
    interacting with the nodes.
    """


@cli.command("destroy")
@click.option("-i", "--vmid", is_flag=True, required=False, help="use VMID instead of human-readable name")
@click.option("--all", is_flag=True, required=False, help="destroy all VMs")
@click.argument("name", nargs=-1, type=str)
def destroy(vmid, name, all):
    if all:
        if len(name) != 0:
            logger.error("asking to destroy ALL VMs and providing some names at the same time is not supported")
            exit(1)

        cnt = len(current_vms())
        if cnt == 0:
            logger.error("nothing to destroy")
            exit(0)

        logger.warning(f"DESTROYING ALL {cnt} VMs in 3 seconds")
        sleep(1)
        logger.warning(f"DESTROYING ALL {cnt} VMs in 2 seconds")
        sleep(1)
        logger.warning(f"DESTROYING ALL {cnt} VMs in 1 seconds")
        sleep(1)
        logger.warning(f"DESTROYING ALL {cnt} VMs NOW")

        for vm in current_vms():
            vm.destroy()
    else:
        for n in name:
            if vmid:
                get_vm_by_vmid(int(n)).destroy()
            else:
                get_vm_by_name(n).destroy()


@cli.command("list")
def list_vms():
    for vm in current_vms():
        logger.info("%s [%i]: %s", vm.name, vm.vmid, vm.status)


@cli.command("ssh")
@click.option("-i", "--vmid", is_flag=True, required=False, help="use VMID instead of human-readable name")
@click.argument("name", type=str, nargs=1)
@click.argument("cmd", type=str, nargs=-1)
def ssh(vmid, name, cmd):
    if vmid:
        get_vm_by_vmid(int(name)).interactive_ssh(cmd)
    else:
        get_machine_by_name(name).interactive_ssh(cmd)


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
        vm = clone_fedora(name, vmid=vmid)
        install_node_impl(post_init_script, interactive, name)
    finally:
        if vm and rm:
            logger.warning("Destroying the VM...")
            vm.destroy()


@cli.command("install-node")
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
def install_node(post_init_script: Optional[str], interactive: bool, name: str):
    install_node_impl(post_init_script, interactive, name)


def install_node_impl(post_init_script: Optional[str], interactive: bool, name: str):
    try:
        vm = get_machine_by_name(name)
        vm.wait_for_systemd()

        # if it's not there, we can't push our script there
        vm.run_ssh_command_blocking("sudo dnf install -y rsync")

        vm.upload_files(Path("install-scripts/fedora36-general-init.sh"), "/tmp/init.sh")
        ret = vm.run_ssh_command_blocking(f"bash /tmp/init.sh {name}")
        if ret not in (0, 1, 255):
            raise RuntimeError(f"init failed with exit code {ret}")
        
        # the machine will reboot itself shortly
        # ret = vm.run_ssh_command_blocking("sudo reboot")
        # assert ret != 0  # reboot does not end well :D, this is pointless
        sleep(5)
        vm.wait_for_systemd()

        # copy ovn-kubernetes repository to the user's home and install the binaries
        # vm.upload_files("../ovn-kubernetes", "", as_root=False)
        # ret = vm.run_ssh_command_blocking("sudo make -C ovn-kubernetes/go-controller install")
        # if ret != 0:
        #    raise RuntimeError(f"ovn prep failed with exit code {ret}")

        if post_init_script:
            vm.upload_files(Path(post_init_script), "/tmp/post-init-script")
            vm.run_ssh_command_blocking("sudo chmod +x /tmp/post-init-script && /tmp/post-init-script")

        if interactive:
            vm.interactive_ssh()

    except KeyboardInterrupt:
        logger.info("received Ctrl+C, aborting...")
        pass


@cli.command("provision")
@click.argument("num_nodes", required=True, nargs=1, type=int)
def provision(num_nodes: int):
    if num_nodes == 0:
        logger.error("at least one node is required in a cluster")
        return 1
    
    names = list(map(node_hostname, range(1, num_nodes+1)))

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

@cli.command("configure-nodes")
@click.argument("machine_names", required=True, nargs=-1, type=str)
def configure_nodes(machine_names: list[str]):
    threads: list[Thread] = []

    # setup master node
    t = Thread(
        target=install_node_impl,
        args=("install-scripts/ovn-kubernetes-master.sh", False, machine_names[0]),
    )
    threads.append(t)
    t.start()

    # setup workers
    for name in machine_names[1:]:
        t = Thread(target=install_node_impl, args=(None, False, name))
        threads.append(t)
        t.start()

    # wait for all the threads
    for t in threads:
        t.join()
    logger.info("all nodes initialized")

    # let the workers join the cluster
    for worker in machine_names[1:]:
        logger.info("node %s is joining the cluster", worker)
        join_command = get_machine_by_name(machine_names[0]).run_ssh_command_get_output(
            "sudo kubeadm token create --print-join-command"
        )
        logger.debug(join_command)
        get_machine_by_name(worker).run_ssh_command_blocking(
            join_command + " --cri-socket=unix:///var/run/cri-dockerd.sock"
        )


@cli.command()
@click.argument("vm_name", type=str, nargs=1)
@click.argument("source", type=click.Path(exists=True), nargs=1)
@click.argument("dest", type=click.Path(exists=False), nargs=1)
def upload(vm_name: str, source: str, dest: str):
    vm = get_machine_by_name(vm_name)
    vm.upload_files(Path(source), dest)


@cli.command()
@click.argument("source", type=click.Path(exists=True), nargs=1)
@click.argument("dest", type=click.Path(exists=False), nargs=1)
def upload_everywhere(source: str, dest: str):
    for vm in current_vms():
        vm.upload_files(Path(source), dest)


@cli.command()
@click.argument("vm_name", type=str, nargs=1)
def start(vm_name: str):
    get_vm_by_name(vm_name).start()


@cli.command()
@click.argument("master_node", type=str, nargs=1)
def deploy_arch(master_node: str):
    vm = get_vm_by_name(master_node)
    vm.upload_file(Path("kube_configs/arch.yaml"), "/arch.yaml")
    vm.run_ssh_command_blocking("kubectl apply -f /arch.yaml")
    sleep(1)
    vm.run_ssh_command_blocking("while ! (kubectl describe pod arch | grep -E ^Node:\\\\|^IP:); do sleep 1; done")


pod_master: str

@cli.group("pod")
@click.option("-m", "--master-node", "master_node", type=str, required=False, help="master node", default=node_hostname(1))
def pod(master_node):
    """
    Commands related to pods
    """
    global pod_master
    pod_master = master_node

@pod.command("deploy")
@click.argument("pod_name", type=str, nargs=1)
def deploy_pod(pod_name: str):
    vm = get_machine_by_name(pod_master)

    def_file = Path(f"kube_configs/{pod_name}.yaml")
    if not def_file.exists():
        print(f"Pod definition file with name '{pod_name}' does not exist!")
        exit(1)

    vm.upload_files(def_file, "/pod.yaml")
    vm.run_ssh_command_blocking("kubectl apply -f /pod.yaml")
    sleep(1)
    vm.run_ssh_command_blocking(f"while ! (kubectl describe pod {pod_name} | grep -E ^Node:\\\\|^IP:); do sleep 1; done")

@pod.command("delete")
@click.argument("pod_name", type=str, nargs=1)
def pod_delete(pod_name: str):
    vm = get_machine_by_name(pod_master)

    def_file = Path(f"kube_configs/{pod_name}.yaml")
    if not def_file.exists():
        print(f"Pod definition file with name '{pod_name}' does not exist!")
        exit(1)

    vm.upload_files(def_file, "/pod.yaml")
    vm.run_ssh_command_blocking("kubectl delete -f /pod.yaml")

@pod.command("ip")
@click.argument("pod_name", type=str, nargs=1)
def pod_ip(pod_name: str):
    vm = get_machine_by_name(pod_master)
    vm.run_ssh_command_blocking(f"while ! (kubectl describe pod {pod_name} | grep -E ^Node:\\\\|^IP:); do sleep 1; done")



@pod.command("ssh")
@click.argument("pod", type=str, nargs=1)
@click.argument("cmd", type=str, nargs=-1)
def pod_shell(pod: str, cmd: list[str]):
    vm = get_machine_by_name(pod_master)
    if len(cmd) == 0:
        cmd = ["bash"]
    vm.interactive_ssh(["kubectl", "exec", "-ti", pod, "--"] + list(cmd))


@pod.command("upload")
@click.argument("pod", type=str, nargs=1)
@click.argument("source", type=click.Path(exists=True), nargs=1)
@click.argument("dest", type=click.Path(exists=False), nargs=1)
def pod_upload(pod: str, source: str, dest: str):
    vm = get_machine_by_name(pod_master)
    vm.upload_files(source, "/.upload")
    vm.run_ssh_command_blocking(f"kubectl cp /.upload default/{pod}:{dest}; sudo rm -fr /.upload")
    if Path(source).stat().st_mode & 0o111 > 0:
        vm.run_ssh_command_blocking(f"kubectl exec -ti arch -- chmod +x {dest}")
    #vm.interactive_ssh(["kubectl", "exec", "-ti", "arch", "--", "bash"])

@cli.command()
@click.argument("master_node", type=str, nargs=1)
@click.argument("dest", type=click.Path(exists=True, dir_okay=True, file_okay=False), nargs=1)
def fetch_arch(master_node: str, dest: str):
    vm = get_vm_by_name(master_node)
    vm.run_ssh_command_blocking("rm -rf fetch; mkdir fetch; for f in $(kubectl exec arch -- ls | grep -E '^.*pcap\\|.*csv\\|.*jsonl'); do echo $f; kubectl exec arch -- cp $f file; kubectl cp arch:file ./file; mv ./file fetch/$f; done")
    vm.rsync_files_back("./fetch", Path(dest))
    logger.info("Files were downloaded to \"fetch\" directory")




if __name__ == "__main__":
    cli()
