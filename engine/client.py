#!/usr/bin/env python3
import docker
import uuid
import time
from miniboa.telnet import TelnetClient
from threading import Thread
import os

class HoneyTelnetClient(TelnetClient):
    def __init__(self, sock, addr_tup):
        super().__init__(sock, addr_tup)
        self.dclient = docker.from_env()
        self.APIClient = docker.APIClient(base_url='unix://var/run/docker.sock')
        self.container = self.dclient.containers.run(
            "honeybox", "/bin/sh",
            detach=True,
            tty=True,
            environment=["SHELL=/bin/sh"])
        self.pwd = "/"
        self.input_list = []
        self.active_cmds = []
        self.username = None
        self.password = None
        self.exit_status = 0
        self.uuid = uuid.uuid4()
        self.passwd_flag = None
        self.ip = self.addrport().split(":")[0]

    def cleanup_container(self, server):
        """
        Cleans up a container.
        """
        self.check_changes(server)
        self.APIClient.remove_container(self.container.id, force=True)

    def check_changes(self, server):
        """
        Checks for the difference between the container's base image and the
        current state of the container and sends any new/changed files off to
        save_file.
        """
        if self.container.diff() is not None:
            for difference in self.container.diff():
                result = self.container.exec_run(
                    '/bin/sh -c "test -d {} || echo NO"'.format(
                        difference['Path']))
                if "NO" in str(result):  # If echo 'NO' runs, file is not a dir
                    self.save_file(server, difference['Path'])


    def save_file(self, server, filepath):
        """
        Grabs an MD5 of a file and decides if we're going to save it or not.
        """
        md5 = self.container.exec_run("md5sum {}".format(
            filepath)).decode("utf-8")
        md5 = md5.split(' ')[0]
        fname = "{}-{}".format(md5, filepath.split('/')[-1])
        if os.path.isfile("./logs/{}.tar".format(fname)):
            server.logger.info(
                "Not saving duplicate file {} from {}.".
                format(fname, self.ip))
            return
        server.logger.info(
            "Saving file {} from {}".
            format(fname, self.ip))
        with open("./logs/{}.tar".format(fname), "bw+") as f:
            strm, stat = self.container.get_archive(filepath)
            f.write(strm.data)


    def run_in_container(self, line):
        """
        Takes in a command (pre-parsed/sanitized) and runs it in the client's
        container.

        Needs to use the low level APIClient in order to snag the exit code.
        """
        newcmd = '/bin/sh -c "cd {} && {};exit $?"'.format(self.pwd, line)
        self.exec = self.APIClient.exec_create(self.container.id, newcmd)
        result = self.APIClient.exec_start(self.exec['Id']).decode(
          "utf-8", "replace")
        self.exit_status = self.APIClient.exec_inspect(self.exec['Id'])['ExitCode']
        return(result)
