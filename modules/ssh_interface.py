import paramiko
import time
import logging
import random
import re
import fcntl
import socket
import threading

logger = logging.getLogger("tester")
MAX_ATTEMPT = 2


class SSHIntExp(Exception):
    pass


class SSHInterface(paramiko.SSHClient):
    def __init__(self, settings, gl_lock=False, show_output=True):
        paramiko.SSHClient.__init__(self)
        self.GlobalLock = gl_lock
        self.ShowOutput = show_output
        self.Output = b""
        self.BuffSize = 2048
        self.IP = settings.get("%%SERV_IP%%", False)
        self.Port = settings.get("%%DEV_CONFIG_PORT%%", 22)
        self.Login = settings.get("%%DEV_USER%%", "admin")
        self.Pass = settings.get("%%DEV_PASS%%", "password")
        self.Thread = threading.Thread()
        self.Result = False
        self.LogFormat = u'%(asctime)-8s [ssh output] %(message)-8s'

    def _lock_acquire(self):
        fcntl.lockf(self.GlobalLock, fcntl.LOCK_EX)

    def _lock_release(self):
        fcntl.lockf(self.GlobalLock, fcntl.LOCK_UN)

    def _get_ssh_channel(self):
        logger.info("Trying to connect %s:%d", self.IP, self.Port)
        self.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.connect(hostname=self.IP,
                     username=self.Login,
                     password=self.Pass,
                     port=self.Port,
                     timeout=5,
                     banner_timeout=5,
                     look_for_keys=False,
                     allow_agent=False)
        return self.invoke_shell()

    @staticmethod
    def _logging_ssh_output(buff):
        while buff.find(b"\n") != -1:
            line, buff = buff.split(b"\n", maxsplit=1)
            try:
                logger.info(line.decode("utf-8"))
            except UnicodeDecodeError as error:
                logger.error("%s" % error)
        return buff

    def _receive_ssh_output(self, channel):
        # Clearing old data
        self.Output = b""
        if self.ShowOutput:
            logger.info("SSH output:")

        read_buff = b""
        while(not channel.exit_status_ready() or
              channel.recv_ready()):
            raw_data = channel.recv(self.BuffSize)
            self.Output = b"".join((self.Output, raw_data))
            read_buff = b"".join((read_buff, raw_data))
            if len(read_buff) > 0 and self.ShowOutput:
                read_buff = self._logging_ssh_output(read_buff)
            else:
                time.sleep(0.01)

    def _handle_ssh_output(self):
        try:
            self.Output = self.Output.decode('utf-8')
        except UnicodeDecodeError as error:
            raise SSHIntExp("%s" % error)

        if (self.Output.find("There is no such command") != -1 or
                self.Output.find("Command error") != -1 or
                self.Output.find("Invalid command's arguments") != -1):
            raise SSHIntExp("Found error substring in ssh output.")

        if self.Output.find("temporary locked") != -1:
            raise SSHIntExp("SSH command temporary locked.")

    def _send_ssh_command(self, cmd):
        logger.info("Commands list:")
        _ = list(map(logger.info, cmd.strip("exit\n").split("\n")))
        try:
            if self.GlobalLock:
                logger.info("Acquire global ssh lock")
                self._lock_acquire()
            channel = self._get_ssh_channel()
            channel.sendall(cmd)
            self._receive_ssh_output(channel)
            self._handle_ssh_output()
        except KeyError as error:
            logger.warning("Send SSH commands failed. Reason: %s", error)
            return False
        except paramiko.ssh_exception.NoValidConnectionsError as error:
            logger.warning("Send SSH commands failed. Reason: %s", error)
            return False
        except socket.timeout as error:
            logger.warning("Send SSH commands failed: %s", error)
            return False
        except paramiko.ssh_exception.AuthenticationException as error:
            logger.warning("Send SSH commands failed. Reason: %s", error)
            return False
        except paramiko.ssh_exception.SSHException as error:
            logger.warning("Send SSH commands failed. Reason: %s", error)
            return False
        except SSHIntExp as error:
            logger.warning("Send SSH commands failed. Reason: %s", error)
            return False
        finally:
            if self.GlobalLock:
                logger.info("Release global ssh lock")
                self._lock_release()
            self.close()
        return True

    def _push_cmd_with_attempts(self, cmd):
        self.Result = False
        for attempt in range(MAX_ATTEMPT):
            logger.info("Trying to send commands. Attempt: %d", attempt + 1)
            self.Result = self._send_ssh_command(cmd)
            if self.Result:
                break
            time.sleep(random.randint(2, 5))

    def _push_cmd_in_thread(self, cmd):
        if self.Thread.is_alive():
            logger.info("Previous commands are sending now. Waiting...")
            self.Thread.join()
        self.Thread = threading.Thread(target=self._push_cmd_with_attempts, args=(cmd,))
        self.Thread.start()
        self.Thread.join()

    def push_cmd_list_to_ssh(self, cmd_list):
        cmd_list.append("exit\n")
        cmd_list = [str(cmd) if not re.search(r'blf|import', cmd)else str(cmd) + "\nsleep 0.5"
                    for cmd in cmd_list]
        self._push_cmd_in_thread("\n".join(cmd_list))
        return self.Result

    def push_cmd_string_to_ssh(self, cmd):
        cmd = "\n".join((cmd, "exit\n"))
        self._push_cmd_in_thread(cmd)
        return self.Result
