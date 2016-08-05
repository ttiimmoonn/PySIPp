import modules.cmd_builder as builder
import paramiko
import paramiko.ssh_exception as parm_excpt 
import queue
import time


class coconInterface:
    def __init__(self,test_var):
        self.Login = str(test_var["%%DEV_USER%%"])
        self.Password = str(test_var["%%DEV_PASS%%"])
        self.Ip = str(test_var["%%SERV_IP%%"])
        self.Port = int(8023)
        self.sshChannel = None
        self.ConnectionStatus = True
        self.coconQueue = queue.Queue()
        self.eventForStop = None
        self.myThread = None

    def flush_queue(self):
        print ("[DEBUG] Flashing CCN Queue. Num of tasks:", self.coconQueue.qsize())
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
            client.connect(hostname = self.Ip, username = self.Login, password = self.Password, port = self.Port, timeout=10)
        except:
            print("[ERROR] Can't connect to CoCon interface. {cocon thread}")
            print("--> Try to check connection settings.")
            self.sshChannel = False
            return False
        self.sshChannel = client
        return True

    def send_command(self,command):
        #Поднимаем SSH до COCON
        self.get_channel()
         #Если соединение удалось поднять, то начинаем отправку команды
        if self.sshChannel:
            print("---> Command:",command)
            stdin, stdout, stderr = self.sshChannel.exec_command(command,get_pty=True,bufsize=-1)
            #Сохраняем вывод
            data = stdout.read() + stderr.read()
            #Закрываем ssh соединение
            self.sshChannel.close()
            #Устанавливаем sshChannel в None
            self.sshChannel = None
            #Даём кокону очнуться            
            time.sleep(0.5)
            #print(data.decode("utf-8", "strict"))
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
            print("[DEBUG] Stop event is set. I'm going down...{cocon thread}")
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
            print("[DEBUG] Get task from CCN Queue. Exec command... {cocon thread}")
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


