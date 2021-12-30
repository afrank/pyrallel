#!/usr/bin/python3

import threading
import subprocess
import json
import queue
import time
import paramiko
import sys
import datetime

class HostThread(threading.Thread):
    def __init__(self, hostname, q, shutdown, cmd="echo", interval=30, proxy=None):
        super().__init__()
        self.hostname = hostname
        self.setName(self.hostname)
        self.interval = interval
        self.q = q
        self.shutdown = shutdown
        self.cmd = cmd
        self.proxy = proxy

    def run(self):
        self.host = Host(self.hostname, proxy=self.proxy)
        while not self.shutdown():
            for _ in range(self.interval):
                if self.shutdown():
                    break
                time.sleep(1)
            stdout, stderr = self.host.cmd(self.cmd)
            #obj = json.loads(stdout)
            ts = datetime.datetime.now()
            self.q.put( (self.hostname, ts, stdout, stderr) )

        self.host.disconnect()

class Host:
    def __init__(self, hostname, proxy=None, username="root", port=22):
        self.hostname = hostname
        self.connected = False
        self.proxy = proxy
        self.sock = None
        self.username = username
        self.port = port

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if self.proxy:
            self.sock = paramiko.ProxyCommand(f"ssh -W {self.hostname}:{self.port} {self.proxy}")

        self.client.connect(
            hostname=self.hostname,
            username=self.username,
            port=self.port,
            sock=self.sock
        )

        self.connected = True

    def cmd(self, cmd):
        if not self.connected:
            self.connect()
        try:
            stdin, stdout, stderr = self.client.exec_command(cmd)
        except paramiko.ssh_exception.ProxyCommandFailure:
            self.disconnect()
            self.connect()
            stdin, stdout, stderr = self.client.exec_command(cmd)

        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        return (out, err)

    def disconnect(self):
        self.client.close()


class Controller(threading.Thread):
    def __init__(self, hosts, q, shutdown):
        super().__init__()
        self.hosts = hosts
        self.q = q
        self.shutdown = shutdown

        self.threads = {}

    def run(self):
        while not self.shutdown():
            for host in self.hosts.keys():
                opts = self.hosts[host]
                opts["interval"] = opts.get("interval", 30)
                if host not in self.threads or not self.threads[host].is_alive():
                    self.threads[host] = HostThread(host, self.q, self.shutdown, **opts)
                    self.threads[host].start()
            time.sleep(1)

        for t in self.threads.values():
            t.join()

class Pyrallel:
    def __init__(self, hosts):
        self._shutdown = False
        self._q = queue.Queue()

        self.hosts = hosts # this is a dict of host keys and dict values

        self.ctl = Controller(self.hosts, self.q, lambda: self.shutdown)
        self.ctl.start()

    @property
    def shutdown(self):
        return self._shutdown

    @shutdown.setter
    def shutdown(self, shutdown):
        self._shutdown = shutdown

    @property
    def q(self):
        return self._q

    def stop(self):
        self.shutdown = True
        self.ctl.join()

