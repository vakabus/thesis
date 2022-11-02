import time

from proxmoxer import ProxmoxAPI

proxmox = ProxmoxAPI("tapir.lan", user="root", backend="openssh", service="pve")


def wait_for_last_n_tasks(n: int):
    print("waiting for previous tasks to finish")
    while True:
        tasks = tapir.tasks.get(limit=len(kbs), source="all")
        running = False
        for t in tasks:
            running |= t["status"] == "RUNNING"
        if not running:
            break
        print("\tnot yet")
        time.sleep(1)


existing_kb_nodes = []
print("CURRENT VMS")
print("-----------")
for pve_node in proxmox.nodes.get():
    print("{0}:".format(pve_node["node"]))
    try:
        for container in proxmox.nodes(pve_node["node"]).qemu.get():
            print("\t{0}. {1} => {2}".format(container["vmid"], container["name"], container["status"]))
            if container["name"].startswith("kb"):
                existing_kb_nodes.append((pve_node["node"], container))
    except:
        print("\terror")


if existing_kb_nodes:
    print()
    print("There are some existing kb nodes. Stopping and deleting...")
    for node, vm in existing_kb_nodes:
        if vm["status"] == "running":
            proxmox.nodes(node).qemu(vm["vmid"]).status.stop()
        proxmox.nodes(node).qemu(vm["vmid"]).delete()
        print(f"\t{vm['name']} stopped and deleted")


print("Creating new cluster nodes")
tapir = proxmox.nodes("tapir")
kbs = []
for i in range(500, 502):
    tapir.qemu("9010").clone.post(newid=i, name=f"kb{i-500}")
    kbs.append(f"kb{i-500}")
    print(f"\tnode kb{i-500} created")

print("starting")
for kb in kbs:
    tapir.qemu(kb).status.start.post()
    print(f"\tstarted {kb}")
