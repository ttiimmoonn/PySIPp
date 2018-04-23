from collections import namedtuple
import subprocess
import time
import threading
from datetime import datetime
import subprocess
import shlex
import logging
logger = logging.getLogger("tester")

ExCodes = namedtuple('ExCodes', ['NotStarted', 'Killed', 'WrongExitCode', 'Success'])
StCodes = ExCodes(1,9,2,0)

def SubscribeToUser(user):
    pass

def RegisterUser (reg_obj, mode="reg"):
    if mode == "reg":
        # Взводим timer если нет флага onetimereg
        if not reg_obj.RegOneTime:
            reg_obj.SetRegistrationTimer()
        # Запускаем процесс
        process = start_ua(reg_obj.RegCommand)
        if not process:
            if type(reg_obj).__name__ == "UserClass":
                logger.error(" ---| User %s not registred. Detail: Can't start process {SIPp not found}",reg_obj.Number)
            elif type(reg_obj).__name__ == "TrunkClass":
                logger.error(" ---| Trunk %s not registred. Detail: Can't start process {SIPp not found}",reg_obj.TrunkName)
            reg_obj.Status = "Registration process not started."
            # Выставляем Status код равный 1
            reg_obj.SetStatusCode(1)
            # Удаляем timer
            reg_obj.CleanRegistrationTimer()
            return False
        else:
            reg_obj.RegProcess = process

        try:
            reg_obj.RegProcess.communicate(timeout=5)
            if reg_obj.RegProcess.poll() != 0:
                reg_obj.Status = "Error of registration"
                # Cтавим код выхода
                reg_obj.SetStatusCode(reg_obj.RegProcess.poll())
                # Делаем сброс таймера
                reg_obj.CleanRegistrationTimer()
                if type(reg_obj).__name__ == "UserClass":
                    logger.error(" ---| User %s not registred. Detail: Registration failed. SIPp process return bad exit code: %d.",reg_obj.Number,reg_obj.RegProcess.poll())
                elif type(reg_obj).__name__ == "TrunkClass":
                    logger.error(" ---| Trunk %s not registred. Detail: Registration failed. SIPp process return bad exit code: %d.",reg_obj.TrunkName,reg_obj.RegProcess.poll())
                return False
            else:
                reg_obj.Status = "Registered"
                reg_obj.SetStatusCode(reg_obj.RegProcess.poll())
                if type(reg_obj).__name__ == "UserClass":
                    logger.info(" ---| User %s registred at %s; on port %s; exp time = %d, mode = %s",reg_obj.Number,str(datetime.strftime(datetime.now(), "%H:%M:%S")),reg_obj.Port,(int(reg_obj.Expires) * 2 / 3),reg_obj.RegMode)
                elif type(reg_obj).__name__ == "TrunkClass":
                    logger.info(" ---| Trunk %s registred at %s; on port %s; exp time = %d",reg_obj.TrunkName,str(datetime.strftime(datetime.now(), "%H:%M:%S")),reg_obj.Port,(int(reg_obj.Expires) * 2 / 3))
                return True
        except subprocess.TimeoutExpired:
            reg_obj.RegProcess.kill()
            reg_obj.Status = "Error of registration (timeout)."
            reg_obj.SetStatusCode(2)
            reg_obj.CleanRegistrationTimer()
            if type(reg_obj).__name__ == "UserClass":
                logger.error(" ---| User %s not registred. Detail: UA registration process break by timeout.",reg_obj.Number)
            elif type(reg_obj).__name__ == "TrunkClass":
                logger.error(" ---| Trunk %s not registred. Detail: UA registration process break by timeout.",reg_obj.TrunkName)
            return False
    elif mode == "unreg":
        try:
            if reg_obj.RegProcess.poll() == None:
                reg_obj.RegProcess.wait()
        except AttributeError:
            return False
        process = start_ua(reg_obj.UnRegCommand)
        if not process:
            if type(reg_obj).__name__ == "UserClass":
                logger.error(" ---| User registration %s not dropped. Detail: Can't start process {SIPp not found}",reg_obj.Number)
            elif type(reg_obj).__name__ == "TrunkClass":
                logger.error(" ---| Trunk registration %s not dropped. Detail: Can't start process {SIPp not found}",reg_obj.TrunkName)
            reg_obj.SetStatusCode(3)
            return False
        else:
            reg_obj.UnRegProcess = process
        try:
            reg_obj.UnRegProcess.communicate(timeout=5)
            if reg_obj.UnRegProcess.poll() != 0:
                reg_obj.Status = "Error of drop registration"
                if type(reg_obj).__name__ == "UserClass":
                    logger.error(" ---| User registration %s not dropped. Detail: SIPp process return bad exit code.",reg_obj.Number)
                elif type(reg_obj).__name__ == "TrunkClass":
                    logger.error(" ---| Trunk registration %s not dropped. Detail: SIPp process return bad exit code.",reg_obj.Trunk)
                reg_obj.SetStatusCode(reg_obj.RegProcess.poll())
                return False
            else:
                reg_obj.Status = "Dropped"
                if type(reg_obj).__name__ == "UserClass":
                    logger.info(" ---| User registration %s is dropped.",reg_obj.Number)
                elif type(reg_obj).__name__ == "TrunkClass":
                    logger.info(" ---| Trunk registration %s is dropped.",reg_obj.TrunkName)
                reg_obj.SetStatusCode(reg_obj.RegProcess.poll())
                return True
        except subprocess.TimeoutExpired:
            reg_obj.UnRegProcess.kill()
            reg_obj.Status = "Error of drop (timeout)"
            if type(reg_obj).__name__ == "UserClass":
                logger.error(" ---| User registration %s not dropped. Detail: UA registration process break by timeout.",reg_obj.Number)
            elif type(reg_obj).__name__ == "TrunkClass":
                logger.error(" ---| Trunk registration %s not dropped. Detail: UA registration process break by timeout.",reg_obj.TrunkName)
            reg_obj.SetStatusCode(4)
            return False
    else:
        logger.error(" ---| Bad arg {set registration func}")
        return False


def preexec_process():
    import os
    os.setpgrp()


def start_ua(command):
# Запуск подпроцесса регистрации
    try:
        args = shlex.split(str(command))
    except ValueError:
        logger.error("Can't split command: %s",command)
        return False
    try:
        # Пытаемся создать новый SIPp процесс.
        ua_process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn = preexec_process)
    except FileNotFoundError:
        # Если неправильно указан путь, то возвращаем false.
        return False
    # Если процесс запустился, то возвращаем его.
    return ua_process

def start_ua_thread(ua, event_for_stop):
    while event_for_stop.isSet():
        for count, cmd in enumerate(ua.Commands, start=1):
            # Запускаем процесс
            ua.Status = "Starting"
            process = start_ua(cmd.cmd_str)
            # Если процесс не запустился, то сигналим остальным thread, чтобы завершались.
            if not process:
                event_for_stop.clear()
                ua.SetStatusCode(StCodes.NotStarted)
                logger.error("UA %s not started",ua.Name)
                return False
            ua.Status = "Started"
            logger.info("UA %s with command %s started.",ua.Name,count)
            # Добавляем новый процесс в массив
            ua.Process.append(process)
            # Ожидание exit code от процесса
            while(event_for_stop.isSet()):
                if process.poll() != None:
                    #Процесс что-то нам вернул
                    break
                time.sleep(0.05)
            # В данной точке может быть два кейса.
            # 1. Соседний thread прислал event на завершение.
            # 2. Процесс отработал и вернул нам exit code

            # Обрабатываем первый кейс:
            if not event_for_stop.isSet():
                if process.poll() == None: process.kill()
                ua.Status = "Killed (recv stop event)"
                ua.SetStatusCode(StCodes.Killed)
                logger.warning("UA %s with command %s killed (recv exit event).",ua.Name,count)
                return False
            else:
                # Обрабатываем второй кейс
                if process.poll() != cmd.req_ex_code:
                    ua.Status = "SIPp error"
                    # Выставляем статус код процессу.
                    ua.SetStatusCode(StCodes.WrongExitCode)
                    #Сигналим в соседний thread
                    logger.error("UA %s with command %s return %d exit code. Req exit code: %d",ua.Name,count,process.poll(),cmd.req_ex_code)
                    event_for_stop.clear()
                    return False
                else:
                    ua.Status = "Success"
                    ua.SetStatusCode(StCodes.Success)
                    logger.info("UA %s with command %s return %d exit code. Req exit code: %d",ua.Name,count,process.poll(),cmd.req_ex_code)
        # Если UA был запущен в циклическом режиме, то перезапускаемся.
        if not ua.Cyclic:
            #Выходим из цикла.
            break
        else:
            logger.info("UA %s is started in Cyclic mode. Restarting UA processes...",ua.Name)
            #Увеличиваем каунтер цикла
            continue


def start_process_controller(test):
    threads = []
  
    #Начинаем запуск UA по очереди
    logger.info("Try to start UA...")
    for ua in test.UserAgent + test.BackGroundUA:
        time.sleep(0.01)
        # Инициализируем новый thread
        testThread = threading.Thread(target=start_ua_thread, args=(ua,test.ThreadEvent,), name = ua.Name)
        testThread.setName(ua.Name)
        # Запускаем новый thread
        testThread.start()
        #Разделяем Thread
        if ua.BackGround:
            logger.info("UA: %s will be started in background mode.",ua.Name)
            test.BackGroundThreads.append(testThread)
        else:
            threads.append(testThread)

    test.ReplaceBgUaToWait()
        
    #Включаем цикл опроса статусов процессов.
    #Включаем флажок для выхода из диспетчера
    event_for_mgm = True
    
    while(event_for_mgm):
        if event_for_mgm:
            #Проверяем, что все регистрации живы.
            for ua in test.UserAgent:
                if ua.Type == "User": # or ua.Type == "ServiceFeatureUA":
                    ex_code = ua.UserObject.ReadStatusCode()
                    if ex_code != 0:
                        #Если регистрация отвалилась, останавливаем все thread
                        test.ThreadEvent.clear()
                        #Выходим из диспетчера
                        event_for_mgm = False
        #Проверяем, что все процессы возращают 0 ex_code
        if event_for_mgm:
            for userAgent in test.UserAgent:
                ex_code = userAgent.ReadStatusCode()
                if ex_code == None:
                    continue
                if int(ex_code) != 0:
                    #Выходим из диспетчера
                    event_for_mgm = False
                    
        if event_for_mgm:  
            #Если все thread завершились то выходим из диспетчера
            thread_alive_flag = 0                 
            for thread in threads:                
                if thread.is_alive():             
                    thread_alive_flag = 1
                    break
            if thread_alive_flag == 0:           
                event_for_mgm = False
        time.sleep(0.01)
    return threads

def CheckThreads(threads):
    #Взводим таймер на 5 сек
    for Timer in list(range(5)):
        #Флаг для посдсчёта активных тредов
        thread_alive_flag = 0
        for thread in threads:
            if thread.is_alive():
                #Если в массиве есть живой thread инкрементируем флаг
                thread_alive_flag += 1
        if thread_alive_flag == 0:
            return True
        else:
            time.sleep(1)
    logger.error("One or more threads not closed")
    return False

def CheckUaStatus(user_agents):
    for ua in user_agents:
        if ua.StatusCode != StCodes.Success and ua.StatusCode != StCodes.Killed:
            return False
    return True

def CheckUserRegStatus(test_users):
    for user in test_users:
        if test_users[user].ReadStatusCode() != 0:
            return False
    return True

def ChangeUsersRegistration(reg_objs, lock, mode="reg"):
    if lock.locked():
        logger.warning("Registration lock object is acquired. Waiting release...")
    if not lock.acquire():
        #не удалось заблокировать ресурс
        return False
    else:
        try:
            if mode == "reg":
                reg_threads=[]
                #Запускаем регистрацию
                for obj in reg_objs:
                    reg_thread = threading.Thread(target=RegisterUser, args=(reg_objs[obj],mode))
                    reg_thread.start()
                    reg_objs[obj].RegCSeq += 2
                    #Добавляем thread в массив
                    reg_threads.append(reg_thread)

                #Ждём пока все thread завершатся
                for reg_thread in reg_threads:
                    reg_thread.join()


            elif mode == "unreg":
                reg_threads=[]
                #Делаем остановку всех таймеров
                for user in reg_objs:
                    #Если таймер существует, то дропаем его
                    if reg_objs[user].Timer:
                        reg_objs[user].CleanRegistrationTimer()

                for obj in reg_objs:
                    if reg_objs[obj].Status == "Dropped":
                        logger.warning("Registaration for user %s already dropped",reg_objs[obj].Login)
                        continue
                    if reg_objs[obj].Status == "Failed":
                        logger.warning("Previous registaration for user %s failed",reg_objs[obj].Login)
                        continue
                    #Дропаем только успешные регистрации
                    if reg_objs[obj].ReadStatusCode() == 0:
                        reg_thread = threading.Thread(target=RegisterUser, args=(reg_objs[obj],mode))
                        reg_thread.start()
                        #Добавляем thread в массив
                        reg_threads.append(reg_thread)

                #Ждём пока все thread завершатся
                for reg_thread in reg_threads:
                    reg_thread.join()
        finally:
            lock.release()