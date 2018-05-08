import modules.cmd_builder as builder
import paramiko
import queue
import time
import logging
import random
import re
import fcntl
import socket

logger = logging.getLogger("tester")
MAX_ATTEMPT = 2


class SshConnectionExp(Exception):
    pass


class SshCmdErrorExp(Exception):
    pass


class SshCmdLockedExp(Exception):
    pass


class SSHInterface:
    def __init__(self, test_var, show_cocon_output=False, global_ccn_lock=None, log_file=None):
        self.Login = str(test_var["%%DEV_USER%%"])
        self.Password = str(test_var["%%DEV_PASS%%"])
        self.Ip = str(test_var["%%SERV_IP%%"])
        self.Port = int(test_var["%%DEV_CONFIG_PORT%%"])
        self.sshChannel = None
        self.Status = True
        self.sshClient = paramiko.SSHClient()
        self.sshQueue = queue.Queue()
        self.eventForStop = None
        self.myThread = None
        self.attempt = 0
        self.log_file = log_file
        self.ShowCoConOutput = show_cocon_output
        self.read_buff = b""
        self.buff_size = 2048
        self.data = b""
        self.global_ccn_lock = global_ccn_lock

    def flush_queue(self):
        logger.info("Flashing CCN Queue. Num of tasks: %s", self.sshQueue.qsize())
        while not self.sshQueue.empty():
            # Если поймали SIGINT, то чтобы не ждать исполнения всех команд
            # просто вычитываем их.
            self.sshQueue.get()
            self.sshQueue.task_done()
        return True

    def _get_channel(self):
        try:
            self.sshClient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.sshClient.connect(hostname=self.Ip,
                                   username=self.Login,
                                   password=self.Password,
                                   port=self.Port,
                                   timeout=10,
                                   banner_timeout=10,
                                   look_for_keys=False,
                                   allow_agent=False)
        except KeyError as error:
            logger.warning("SSH connection failed. Reason: %s", error)
            return False
        except paramiko.ssh_exception.NoValidConnectionsError as error:
            logger.warning("SSH connection failed. Reason: %s", error)
            return False
        except socket.timeout as error:
            logger.warning("SSH connection failed. Reason: %s", error)
            return False
        except paramiko.ssh_exception.AuthenticationException as error:
            logger.warning("SSH connection failed. Reason: %s", error)
            return False
        except paramiko.ssh_exception.SSHException as error:
            logger.warning("SSH connection failed. Reason: %s", error)
            return False

        try:
            self.sshChannel = self.sshClient.invoke_shell()
        except paramiko.ssh_exception.SSHException as error:
            logger.warning("Creation of SSH channel failed. Reason: %s", error)
            return False
        return True

    def lock_acquire(self):
        fcntl.lockf(self.global_ccn_lock, fcntl.LOCK_EX)

    def lock_release(self):
        fcntl.lockf(self.global_ccn_lock, fcntl.LOCK_UN)

    def _handle_ssh_output(self):
        # Clearing old data
        self.data = b""
        if self.ShowCoConOutput:
            logger.info("SSH output:")
        while(not self.sshChannel.exit_status_ready() or
              self.sshChannel.recv_ready()):
            try:
                self.read_buff = self.sshChannel.recv(self.buff_size)
            except socket.timeout as error:
                raise SshConnectionExp("Receiving data failed. Reason: %s" % error)
            self.data = b"".join((self.data, self.read_buff))
            if len(self.read_buff) > 0 and self.ShowCoConOutput:
                if not self.log_file:
                    print(self.read_buff.decode("utf-8", "strict"), end="")
            else:
                time.sleep(0.01)
        if self.log_file:
            logger.info("%s", self.data.decode("utf-8", "strict"))
        return True

    def send_command(self, command):
        # Exit if ssh connection is not opened.
        if not self._get_channel():
            raise SshConnectionExp("Connection failed")

        logger.info("Trying to send next ssh commands:")
        _ = list(map(logger.info, (command.rstrip('\nexit\n')).split('\n')))
        try:
            self.sshChannel.sendall(command)
        except socket.timeout as error:
            raise SshConnectionExp("Sending commands failed. Reason: %s" % error)
        except socket.error as error:
            raise SshConnectionExp("Sending commands failed. Reason: %s" % error)

        if not self._handle_ssh_output():
            return False

        logger.debug("Waiting exit status from ssh channel")
        self.sshChannel.recv_exit_status()
        # Sleeping..
        time.sleep(0.05)
        # Check ssh output for warnings
        self.data = self.data.decode("utf-8", "strict")
        if (self.data.find("There is no such command") != -1 or
            self.data.find("Command error") != -1 or
            self.data.find("Invalid command's arguments") != -1):
                raise SshCmdErrorExp("Find errors substring in ccn output.")
            # Проверяем, что в output нет следующей подстроки: temporary locked
        if self.data.find("temporary locked") != -1:
            raise SshCmdLockedExp("Command temporary locked.")
        return True

    def close_connection(self):
        try:
            self.sshChannel.close()
            self.sshClient.close()
        except AttributeError:
            pass
        self.sshChannel = None
        self.read_buff = b""


def ccn_command_handler(ssh_int):
    command = ""
    while True:
        # Если прищёл event на завершение треда
        # И при этом очередь пуста, то выходим
        if ssh_int.eventForStop.isSet() and ssh_int.sshQueue.empty():
            logger.info("Stop event is set. I'm going down...{test thread}")
            break
        # Если очередь пустая, то делаем паузу (чтобы не тратить ресурсы)
        if ssh_int.sshQueue.empty() and command == "":
            time.sleep(0.1)
            continue
        if not ssh_int.Status:
            if ssh_int.sshQueue.qsize() != 0:
                # Если состояние коннекта False, то нет смысла дальше слать команды
                # Просто начинаем разгребать очередь
                command = ssh_int.sshQueue.get()
                ssh_int.sshQueue.task_done()
            continue
        logger.info("Trying to send ssh commands. Attempt %d {test thread}", ssh_int.attempt)
        # Получаем новую команду из очереди.
        if ssh_int.attempt == 0:
            command = ssh_int.sshQueue.get()
        try:
            ssh_int.send_command(command)
        except (SshCmdLockedExp, SshConnectionExp) as error:
            logger.warning("%s", error)
            ssh_int.attempt += 1
            if ssh_int.attempt > MAX_ATTEMPT:
                logger.error("Sending ssh commands failed. Reason: The number of attempts is exceeded")
                ssh_int.Status = False
                ssh_int.sshQueue.task_done()
            else:
                logger.info("Try to resend commands. Sleep before next attempt.")
                time.sleep(random.randint(2, 5))
        except SshCmdErrorExp as error:
            ssh_int.sshQueue.task_done()
            ssh_int.Status = False
            logger.error("%s", error)
        else:
            ssh_int.sshQueue.task_done()
            command = ""
            ssh_int.attempt = 0
        finally:
            ssh_int.close_connection()


def cocon_configure(commands, ssh_int, test_var = None):
    commands = commands[0]
    if not commands:
        return True
    # Пытаемся захватить lock
    if ssh_int.global_ccn_lock:
        logger.info("Try to get global_ccn_lock")
        ssh_int.lock_acquire()
    cmd_build = builder.CommandBuilding()
    commands = list(commands.values())
    commands.append("exit\n")
    if test_var:
        commands = list(map(lambda x: cmd_build.replace_var(x, test_var), commands))
        if False in commands:
            # Отпускаем lock
            if ssh_int.global_ccn_lock:
                ssh_int.lock_release()
            return False
    # Добавляем sleep 0.5 для команд с blf и import
    commands = [str(cmd) if not re.search(r'blf|import', cmd) else str(cmd) + "\nsleep 0.5" for cmd in commands]
    # Собираем итоговую стороку
    commands = '\n'.join(commands)
    # Если команда собралась без ошибок отправляем её в thread
    ssh_int.sshQueue.put(commands)
    # Ждём пока thread разгребёт очередь
    ssh_int.sshQueue.join()
    # Отпускаем lock
    if ssh_int.global_ccn_lock:
        ssh_int.lock_release()

    return ssh_int.Status


def ssh_push_string_command(command, ssh_int, test_var=False):
    # Пытаемся захватить lock
    if ssh_int.global_ccn_lock:
        logger.info("Try to get global_ccn_lock")
        ssh_int.lock_acquire()
    cmd_string = command
    cmd_string += "\nexit\n"
    # Пропускаем команду через словарь
    if test_var:
        cmd_build = builder.CommandBuilding()
        cmd_string = cmd_build.replace_var(cmd_string, test_var)
        if type(cmd_string) != str:
            return False

    # Если команда собралась без ошибок отправляем её в thread
    ssh_int.sshQueue.put(cmd_string)
    # Ждём пока thread разгребёт очередь
    ssh_int.sshQueue.join()
    # Отпускаем lock
    if ssh_int.global_ccn_lock:
        ssh_int.lock_release()
    # Проверяем, что все команды были отправлены
    return ssh_int.Status
