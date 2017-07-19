import modules.cmd_builder as builder
import paramiko
import paramiko.ssh_exception as parm_excpt 
import queue
import time
import logging
import random
import socket
import fcntl
logger = logging.getLogger("tester")
MAX_ATTEMPT = 2

class coconInterface:
    def __init__(self,test_var, show_cocon_output=False,global_ccn_lock = None):
        self.Login = str(test_var["%%DEV_USER%%"])
        self.Password = str(test_var["%%DEV_PASS%%"])
        self.Ip = str(test_var["%%SERV_IP%%"])
        self.Port = 8023
        self.sshChannel = None
        self.sshClient = None
        self.ConnectionStatus = True
        self.coconQueue = queue.Queue()
        self.eventForStop = None
        self.myThread = None
        self.attempt = 0
        self.ShowCoConOutput = show_cocon_output
        self.read_buff = b""
        self.buff_size = 1024
        self.data = b""
        self.global_ccn_lock = global_ccn_lock

    def flush_queue(self):
        logger.info("Flashing CCN Queue. Num of tasks: %s", self.coconQueue.qsize())
        while not self.coconQueue.empty():
            #Если поймали SIGINT, то чтобы не ждать исполнения всех команд
            #просто вычитываем их.
            self.coconQueue.get()
            self.coconQueue.task_done()
        return True

    def get_channel(self):
        if self.global_ccn_lock:
            logger.info("Try to get global_ccn_lock")
            self.lock_acquire()
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname = self.Ip, username = self.Login, password = self.Password, port = self.Port, timeout=10, banner_timeout = 10, look_for_keys=False, allow_agent=False)
            self.sshClient = client
        except KeyError:
            logger.warning("KeyError exception on ssh connect.")
            if client:
                logger.debug("Close ssh connect")
                client.close()
            logger.debug("Set ssh channel to disable.")
            self.Client = False
        except:
            logger.warning("Exception on ssh connect.")
            if client:
                logger.debug("Close ssh connect")
                client.close()
            logger.debug("Set ssh channel to disable.")
            self.Client = False


        if self.sshClient:
            try:
                self.sshChannel = self.sshClient.invoke_shell()
            except:
                self.sshChannel = False
        if self.sshChannel != False:
            return True
        else:
            logger.debug("Exit from get_channel method.")
            return False

    def lock_acquire(self):
        fcntl.lockf(self.global_ccn_lock, fcntl.LOCK_EX)
    def lock_release(self):
        fcntl.lockf(self.global_ccn_lock, fcntl.LOCK_UN)

    def send_command(self,command):
         #Если соединение удалось поднять, то начинаем отправку команды
        if self.get_channel():
            logger.info("---> Command: %s",command)
            try:
                self.sshChannel.sendall(command)
                #Ждём когда отпустит ccn
                logger.debug("Waiting for recv_exit_status.")
                self.sshChannel.recv_exit_status()
            except:
                 logger.warning("Exception on exec ssh command! Close ssh connection")
                 return False
            finally:
                if self.global_ccn_lock:
                    self.lock_release()
            logger.debug("Recv ccn output.")
            #Сохраняем вывод
            self.data = b""
            while True:
                self.read_buff = self.sshChannel.recv(self.buff_size)
                if len(self.read_buff) == 0:
                    break
                else:
                    self.data += self.read_buff
            #Даём кокону очнуться
            time.sleep(0.1)
            if self.ShowCoConOutput:
                logger.info("Output: ")
                logger.info(self.data.decode("utf-8", "strict"))
            #Возвращаем True
            #Закрываем ssh соединение
            logger.debug("Close ssh connection.")
            self.close_connection()
            #Проверяем, что команда существует
            if (self.data.decode("utf-8", "strict").find("There is no such command:") != -1 or
               self.data.decode("utf-8", "strict").find("Command error:") != -1 or
               self.data.decode("utf-8", "strict").find("Invalid command's arguments:") != -1):
                    logger.warning("Find \"There is no such command:|Command error:|Invalid command's arguments:\" substring in ccn output.")
            #Проверяем, что в output нет следующей подстроки: temporary locked
            if self.data.decode("utf-8", "strict").find("temporary locked") != -1:
                logger.warning("Command temporary locked. Try retrans cmd to ccn...")
                return False
            else:
                return True
        else:
            if self.global_ccn_lock:
                self.lock_release()
            #Возвращаем False
            return False

    def close_connection(self):
        self.sshChannel.close()
        self.sshClient.close()
        self.sshChannel = None
        self.sshClient = None
        self.read_buff = b""

def ccn_command_handler(coconInt):
    command = ""
    while True:
        #Если прищёл event на завершение треда
        #И при этом очередь пуста, то выходим
        if coconInt.eventForStop.isSet() and coconInt.coconQueue.empty():
            logger.info("Stop event is set. I'm going down...{test thread}")
            break
        #Если очередь пустая, то делаем паузу (чтобы не тратить ресурсы)
        if coconInt.coconQueue.empty() and command == "":
            time.sleep(0.1)
            continue
        if not coconInt.ConnectionStatus:
            if coconInt.coconQueue.qsize() != 0:
                #Если состояние коннекта False, то нет смысла дальше слать команды
                #Просто начинаем разгребать очередь
                command = coconInt.coconQueue.get()
                coconInt.coconQueue.task_done()
            continue
        else:
            logger.info("Get task from CCN Queue. Exec command. Attempt %d {test thread}", coconInt.attempt)
            #Получаем новую команду из очереди.
            if coconInt.attempt == 0:
                command = coconInt.coconQueue.get()
            #Отправляем её
            #Если отправка успешна
            if coconInt.send_command(command):
                #Если команда прошла успешно, то завершаем задачу. 
                coconInt.coconQueue.task_done()
                command = ""
                coconInt.attempt = 0
            else:
                coconInt.attempt += 1
                if coconInt.attempt > MAX_ATTEMPT:
                    logger.error("Can't connect to remote interface. {test thread}. Try to check connection settings")
                    coconInt.ConnectionStatus = False
                    coconInt.coconQueue.task_done()
                logger.info("CCN overload. Sleep before next attempt.")
                time.sleep(random.randint(2, 5))
                continue

    
def cocon_configure(Commands,coconInt,test_var = None):
    Commands = Commands[0]
    if not Commands:
        return True
    cmd_string = ""
    for Command in Commands.values():
        #Пропускаем команду через словарь
        if test_var:
            Command = builder.replace_key_value(Command, test_var)
        if Command:
            cmd_string += Command + "\n"
        else:
            return False
    cmd_string += "exit\n"
    #Если команда собралась без ошибок отправляем её в thread
    coconInt.coconQueue.put(cmd_string)
    #Ждём пока thread разгребёт очередь
    coconInt.coconQueue.join()
    #Проверяем, что все команды были отправлены
    if coconInt.ConnectionStatus:
        return True
    else:
        return False

#For pakru tests
def cocon_push_string_command(Commands,coconInt):
    cmd_string = Commands
    cmd_string += "exit\n"
    #Если команда собралась без ошибок отправляем её в thread
    coconInt.coconQueue.put(cmd_string)
    #Ждём пока thread разгребёт очередь
    coconInt.coconQueue.join()
    #Проверяем, что все команды были отправлены
    if coconInt.ConnectionStatus:
        return True
    else:
        return False