import modules.cmd_builder as builder
import paramiko
import paramiko.ssh_exception as parm_excpt 
import queue
import time
import logging
logger = logging.getLogger("tester")

class coconInterface:
    def __init__(self,test_var, show_cocon_output=False):
        self.Login = str(test_var["%%DEV_USER%%"])
        self.Password = str(test_var["%%DEV_PASS%%"])
        self.Ip = str(test_var["%%SERV_IP%%"])
        self.Port = int(8023)
        self.sshChannel = None
        self.ConnectionStatus = True
        self.coconQueue = queue.Queue()
        self.eventForStop = None
        self.myThread = None
        self.ShowCoConOutput = show_cocon_output

    def flush_queue(self):
        logger.info("Flashing CCN Queue. Num of tasks: %s", self.coconQueue.qsize())
        while not self.coconQueue.empty():
            #Если поймали SIGINT, то чтобы не ждать исполнения всех команд
            #просто вычитываем их.
            self.coconQueue.get()
            self.coconQueue.task_done()
        return True

    def get_channel(self):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname = self.Ip, username = self.Login, password = self.Password, port = self.Port, timeout=10, look_for_keys=False, allow_agent=False)
        except:
            logger.error("Can't connect to CoCon interface. {cocon thread}. Try to check connection settings.")
            self.sshChannel = False
            return False
        self.sshChannel = client
        return True

    def send_command(self,command):
        #Поднимаем SSH до COCON
        self.get_channel()
         #Если соединение удалось поднять, то начинаем отправку команды
        if self.sshChannel:
            logger.info("---> Command: %s",command)
            stdin, stdout, stderr = self.sshChannel.exec_command(command,get_pty=True,bufsize=-1)
            #Сохраняем вывод
            data = stdout.read() + stderr.read()
            #Закрываем ssh соединение
            self.sshChannel.close()
            #Устанавливаем sshChannel в None
            self.sshChannel = None
            #Даём кокону очнуться            
            time.sleep(0.5)
            if self.ShowCoConOutput:
                logger.info("CoconOutput: ")
                print(data.decode("utf-8", "strict"))
            #Возвращаем True
            return True
        else:
            #Возвращаем False
            return False


def ccn_command_handler(coconInt):
    while True:
        #Если прищёл event на завершение треда
        #И при этом очередь пуста, то выходим
        if coconInt.eventForStop.isSet() and coconInt.coconQueue.empty():
            logger.info("Stop event is set. I'm going down...{cocon thread}")
            break
        #Если очередь пустая, то делаем паузу. (чтобы не тратить ресурсы)
        elif coconInt.coconQueue.empty():
            time.sleep(0.1)
        elif not coconInt.ConnectionStatus:
            #Если состояние коннекта False, то нет смысла дальше слать команды
            #Просто начинаем разгребать очередь
            command = coconInt.coconQueue.get()
            coconInt.coconQueue.task_done()
        else:
            logger.info("Get task from CCN Queue. Exec command... {cocon thread}")
            #Получаем команду из очереди.
            command = coconInt.coconQueue.get()
            #Отправляем её
            #Если отправка успешна
            if coconInt.send_command(command):
                #Если команда прошла успешно, то завершаем задачу. 
                coconInt.coconQueue.task_done()
            else:
                coconInt.ConnectionStatus = False
                coconInt.coconQueue.task_done()

    
def cocon_configure(CoconCommands,coconInt,test_var):
    CoconCommands = CoconCommands[0]
    for CoconCmdName in CoconCommands:
        #Пропускаем команду через словарь
        CoconCommand = builder.replace_key_value(CoconCommands[CoconCmdName], test_var)
        if CoconCommand:
            #Если команда собралась без ошибок отправляем её в thread
            coconInt.coconQueue.put(CoconCommand)
        else:
            return False
    #Ждём пока thread разгребёт очередь
    coconInt.coconQueue.join()
    #Проверяем, что все команды были отправлены
    if coconInt.ConnectionStatus:
        return True
    else:
        return False


