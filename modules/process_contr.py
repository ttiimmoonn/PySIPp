from collections import namedtuple
import subprocess
import time
import threading
from datetime import datetime
import subprocess
import shlex
import logging
logger = logging.getLogger("tester")

ExCodes = namedtuple('ExCodes', ['NotStarted', 'Killed', 'WrongExitCode', 'Success', 'Timeout'])
StCodes = ExCodes(1,9,2,0,3)

def SubscribeToUser(user):
    pass

def RegisterUser (reg_obj, mode="reg"):
    # set log prefix
    if type(reg_obj).__name__ == "UserClass":
        log_prefix = "User " + reg_obj.Number
    elif type(reg_obj).__name__ == "TrunkClass":
        log_prefix = "Trunk " + reg_obj.TrunkName

    # if old registration process is running, waiting... 
    # this code should working if SIGINT signal is recieved
    try:
        if reg_obj.RegProcess and reg_obj.RegProcess.poll() == None:
            reg_obj.RegProcess.wait()
    except:
        return False

    if mode == "reg":
        cur_expires = reg_obj.Expires
        process = start_ua(reg_obj.RegCommand)
        if not reg_obj.RegOneTime:
            # Set refresh timer.
            reg_obj.SetRegistrationTimer()
    elif mode == "unreg":
        cur_expires = 0
        process = start_ua(reg_obj.UnRegCommand)
    else:
        process = False

    # If process not started
    if not process:
        logger.error("Set registration for %s failed. Detail: Can't start process {SIPp error}",log_prefix)
        reg_obj.Status = "Registration process not started."
        reg_obj.SetStatusCode(StCodes.NotStarted)
        reg_obj.CleanRegistrationTimer()
        return False
    else:
        reg_obj.RegProcess = process
    try:
        reg_obj.RegProcess.communicate(timeout=5)
        # If reg process complited, check status.
        if reg_obj.RegProcess.poll() != 0:
            reg_obj.Status = "Error of registration"
            # Cтавим код выхода
            reg_obj.SetStatusCode(StCodes.WrongExitCode)
            # Делаем сброс таймера
            reg_obj.CleanRegistrationTimer()
            logger.error(" ---| Set registration for %s failed. Detail: SIPp process return bad exit code: %d.",log_prefix,reg_obj.RegProcess.poll())    
            return False
        else:
            reg_obj.Status = "Registered"
            reg_obj.SetStatusCode(StCodes.Success)
            logger.info("Set registration for %s success. Port %d. Expires %d.",log_prefix,reg_obj.Port,cur_expires)
            return True
    # If Timeout
    except subprocess.TimeoutExpired:
        reg_obj.RegProcess.kill()
        reg_obj.Status = "Error of registration (timeout)."
        reg_obj.SetStatusCode(StCodes.Timeout)
        reg_obj.CleanRegistrationTimer()
        logger.error(" ---| Set registration for %s failed. Detail: UA registration process break by timeout.",log_prefix)
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
    if not 0 in list(map(lambda user: user.ReadStatusCode(),test_users.values())):
        return False
    else:
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