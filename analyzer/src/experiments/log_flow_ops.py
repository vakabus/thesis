#!/usr/bin/env python3

import signal
from bcc import BPF
import argparse
import sys
import time
import json
import enum
import subprocess
import os
from dataclasses import dataclass

ebpf_source = """
#include <linux/sched.h>
#include <linux/skbuff.h>
#include <uapi/linux/bpf.h>
#include <net/genetlink.h>


enum {
    EVENT_FLOW_CMD_SET = 0,
    EVENT_FLOW_CMD_NEW = 1,
    EVENT_FLOW_CMD_DEL = 2,
    EVENT_TABLE_FLUSH = 3,
    EVENT_TABLE_INSERT = 4,
    EVENT_TABLE_REMOVE = 5,
    EVENT_UPCALL = 6,
    _EVENT_MAX_EVENT
};

struct event_t {
    u32 event;
    u32 cpu;
    u32 pid;
    u64 ts;
    char comm[TASK_COMM_LEN];  
};

BPF_RINGBUF_OUTPUT(events, <BUFFER_PAGE_CNT>);
BPF_TABLE("percpu_array", uint32_t, uint64_t, dropcnt, _EVENT_MAX_EVENT);

static struct event_t *init_event(u32 type) {
    struct event_t *event = events.ringbuf_reserve(sizeof(struct event_t));

    if (!event) {
        uint64_t *value = dropcnt.lookup(&type);
        if (value)
            __sync_fetch_and_add(value, 1);

        return NULL;
    }

    event->event = type;
    event->cpu =  bpf_get_smp_processor_id();
    event->pid = bpf_get_current_pid_tgid();
    event->ts = bpf_ktime_get_ns();
    bpf_get_current_comm(&event->comm, sizeof(event->comm));

    return event;
}

static inline int handle(u32 type) {
    struct event_t *event = init_event(type);
    if (!event) {
        return 1;
    }

    events.ringbuf_submit(event, 0);
    return 0;
}
"""
ebpf_source_table_ops = """
int kprobe__ovs_flow_tbl_flush(struct pt_regs *ctx) {
    return handle(EVENT_TABLE_FLUSH);
}

int kprobe__ovs_flow_tbl_insert(struct pt_regs *ctx) {
    return handle(EVENT_TABLE_INSERT);
}

int kprobe__ovs_flow_tbl_remove(struct pt_regs *ctx) {
    return handle(EVENT_TABLE_REMOVE);
}

"""
ebpf_source_upcalls = """
int kprobe__ovs_dp_upcall(struct pt_regs *ctx) {
    return handle(EVENT_UPCALL);
}
"""

ebpf_source_cmd = """
int kprobe__ovs_flow_cmd_set(struct pt_regs *ctx) {
    return handle(EVENT_FLOW_CMD_SET);
}

int kprobe__ovs_flow_cmd_del(struct pt_regs *ctx) {
    return handle(EVENT_FLOW_CMD_DEL);
}

int kprobe__ovs_flow_cmd_new(struct pt_regs *ctx) {
    return handle(EVENT_FLOW_CMD_NEW);
}
"""

class EventType(enum.Enum):
    CMD_SET = 0
    CMD_NEW = 1
    CMD_DEL = 2
    TABLE_FLUSH = 3
    TABLE_INSERT = 4
    TABLE_REMOVE = 5
    UPCALL = 6


@dataclass
class Event:
    event: EventType
    cpu: int
    pid: int
    ts: int
    comm: str

    @staticmethod
    def write_csv_header(file):
        print("event,cpu,pid,ts,comm", file=file)
    
    def write_csv_line(self, file):
        print(f"{self.event},{self.cpu},{self.pid},{self.ts},{self.comm}", file=file)

def event_to_dict(event):
    event_dict = {}

    for field, _ in event._fields_:
        val = getattr(event, field)
        if isinstance(val, int):
            event_dict[field] = getattr(event, field)
        elif isinstance(val, bytes):
            event_dict[field] = val.decode(errors="ignore")
        
        # convert enums
        if field == "event":
            event_dict[field] = EventType(event_dict[field]).name

    return event_dict



def receive_event_bcc(ctx, data, size):
    global events_received
    events_received += 1

    event = b['events'].event(data)

    assert export_file is not None
    Event(**event_to_dict(event)).write_csv_line(export_file)


def next_power_of_two(val):
    np = 1
    while np < val:
        np *= 2
    return np


def main():
    #
    # Don't like these globals, but ctx passing does not seem to work with the
    # existing open_ring_buffer() API :(
    #
    global b
    global options
    global events_received
    global export_file

    #
    # Argument parsing
    #
    parser = argparse.ArgumentParser()

    parser.add_argument("--buffer-page-count",
                        help="Number of BPF ring buffer pages, default 1024",
                        type=int, default=1024, metavar="NUMBER")
    parser.add_argument("-D", "--debug",
                        help="Enable eBPF debugging",
                        type=lambda x: int(x, 0), const=0x3f, default=0,
                        nargs='?')
    parser.add_argument("-w", "--write-events",
                        help="Write events to FILE",
                        type=str, required=True, metavar="FILE")
    parser.add_argument("-l", "--log",
                        help="Write log to FILE",
                        type=str, required=True, metavar="FILE")
    parser.add_argument("--no-cmd", help="Do not trace commands between userspace and kernel",
                        action='store_false', default=True, dest="cmd")  # inverted
    parser.add_argument("--no-table-ops", help="Do not trace flow table changes",
                        action="store_false", default=True, dest="table")  # inverted
    parser.add_argument("--no-upcalls", help="Do not trace upcalls",
                        action="store_false", default=True, dest="upcalls")  # inverted
    parser.add_argument("--signal-ready", help="Send SIGUSR1 to parent when tracing ready", action="store_true", default=False)



    options = parser.parse_args()


    options.buffer_page_count = next_power_of_two(options.buffer_page_count)

    #
    # Open write handle
    #
    try:
        export_file = open(options.write_events, "w")
        Event.write_csv_header(export_file)
    except (FileNotFoundError, IOError, PermissionError) as e:
        print("ERROR: Can't create export file \"{}\": {}".format(
            options.write_events, e.strerror))
        sys.exit(-1)


    #
    # Uncomment to see how arguments are decoded.
    #   print(u.get_text())
    #
    print("- Compiling eBPF programs...")

    #
    # Attach probes to the running process
    #
    
    source = ebpf_source.replace("<BUFFER_PAGE_CNT>",
                            str(options.buffer_page_count))
    if options.cmd:
        source += ebpf_source_cmd
    if options.upcalls:
        source += ebpf_source_upcalls
    if options.table:
        source += ebpf_source_table_ops

    b = BPF(text=source, debug=options.debug & 0xffffff)

    #
    # Dump out all events
    #
    print("- Capturing events [Press ^C to stop]...")
    subprocess.check_call(["ovs-dpctl","del-flows"])  # makes sure there are no flows we don't know about
    if options.signal_ready:
         os.kill(os.getppid(), signal.SIGUSR1)
         

    events_received = 0


    b['events'].open_ring_buffer(receive_event_bcc)
    while 1:
        try:
            b.ring_buffer_poll()
            time.sleep(0.5)
        except KeyboardInterrupt:
            break
    
    from bcc.table import PerCpuArray
    dropcnt: PerCpuArray = b.get_table("dropcnt")
    events_dropped = sum([sum(x) for x in dropcnt.values()])
    print(f"received {events_received} events, dropped {events_dropped} events")

    export_file.close()

    # write log
    with open(options.log, 'w') as f:
        print(json.dumps({"event": "LOG", "events_dropped": events_dropped, "events_received": events_received}), file=f)


if __name__ == '__main__':
    os.setpgrp()
    main()
