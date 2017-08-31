import subprocess
import time
import threading
from datetime import datetime
import subprocess
import shlex
import logging
logger = logging.getLogger("tester")

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
                    logger.info(" ---| User %s registred at %s; on port %s; exp time = %d, mode = %s",reg_obj.Number,str(datetime.strftime(datetime.now(), "%H:%M:%S")),reg_obj.Port,(int(reg_obj.Expires) * 2 / 3),reg_obj.Mode)
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


def start_ua (command):
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
#    event_for_wait.wait() # wait for event
#    event_for_wait.clear() # clean event for future
#    event_for_set.set() # set event for neighbor thread
    while  event_for_stop.isSet():
        for commandCount, command in enumerate(ua.Commands,start=1):
            if not event_for_stop.isSet():
                # Если пришла команда остановить thread выходим
                logger.warning("UA %s with command %s recv exit event.",ua.Name,commandCount)
                ua.SetStatusCode(1)
                break 
            # Запускаем UA
            process = start_ua (command)
            if not process:
                ua.SetStatusCode(2)
                #Сигналим в соседний thread
                event_for_stop.clear()
                logger.error("UA %s not started",ua.Name)
                return False
            ua.Status = "Starting"
            # Добавляем новый процесс в массив
            ua.Process.append(process)
            # Ждём
            time.sleep(0.2)
            if process.poll() != None and process.poll() != 0:
                ua.Status = "Not Started"
                logger.error("UA %s with command %s not started.",ua.Name,commandCount)
                ua.SetStatusCode(3)
                #Сигналим в соседний thread
                event_for_stop.clear()
                # Если процесс упал, выходим
                return False
            else:
                ua.Status = "Started"
                logger.info("UA %s with command %s started.",ua.Name,commandCount)
            try:
                while(event_for_stop.isSet()):
                    code = process.poll()
                    if code != None:
                        # Если процесс завершился самостоятельно, то выходим из цикла
                        break
                    time.sleep(0.01)
                
                if not event_for_stop.isSet():
                    process.kill()
                    ua.Status = "Killed (recv stop event)"
                    ua.SetStatusCode(4)
                    #Сигналим в соседний thread
                    event_for_stop.clear()
                    logger.warning("UA %s with command %s recv exit event.",ua.Name,commandCount)
                    #print("--> [ERROR] UA", ua.Name, "with command", commandCount, "return", process.poll(), "exit code.")
                    return False      
                
                if process.poll() != 0:
                        ua.Status = "SIPp error"
                        # Выставляем статус код процессу.
                        ua.SetStatusCode(process.poll())
                        #Сигналим в соседний thread
                        event_for_stop.clear()
                        logger.error("UA %s with command %s return %d exit code.",ua.Name,commandCount,process.poll())
                        return False
                else:
                    ua.Status = "Success"
                    ua.SetStatusCode(process.poll())
                    logger.info("UA %s with command %s return %d exit code.",ua.Name,commandCount,process.poll())
            except subprocess.TimeoutExpired:
                process.kill()
                ua.Status = "Killed by timeout"
                ua.SetStatusCode(5)
                logger.error("UA %s killed by timeout",ua.Name)
                #Сигналим в соседний thread
                event_for_stop.clear()
                return False
            commandCount += 1
        #Если передали параметр Cyclic = True
        if not ua.Cyclic:
            #Выходим из цикла.
            break
        else:
            logger.info("UA %s is started in Cyclic mode. Restarting UA processes...",ua.Name)
            #Увеличиваем каунтер цикла
            continue


def start_process_controller(test):
    threads = []
    #Устанавливаем его в true
    test.ThreadEvent.set()
   
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
        for proc in ua.Process:
            if proc.poll() != 0:
                return False
    return True

def CheckUserRegStatus(test_users):
    for user in test_users:
        if test_users[user].ReadStatusCode() != 0:
            return False
    return True

def ChangeUsersRegistration(test_users, lock, mode="reg"):
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
                for user in test_users:
                    reg_thread = threading.Thread(target=RegisterUser, args=(test_users[user],mode))
                    reg_thread.start()
                    #Добавляем thread в массив
                    reg_threads.append(reg_thread)

                #Ждём пока все thread завершатся
                for reg_thread in reg_threads:
                    reg_thread.join()

            elif mode == "unreg":
                reg_threads=[]
                #Делаем остановку всех таймеров
                for user in test_users:
                    #Если таймер существует, то дропаем его
                    if test_users[user].Timer:
                        test_users[user].CleanRegistrationTimer()

                for user in test_users:
                    if test_users[user].Status == "Dropped":
                        logger.warning("Registaration for user %s already dropped",test_users[user].Login)
                        continue
                    #Дропаем только успешные регистрации
                    if test_users[user].ReadStatusCode() == 0:
                        reg_thread = threading.Thread(target=RegisterUser, args=(test_users[user],mode))
                        reg_thread.start()
                        #Добавляем thread в массив
                        reg_threads.append(reg_thread)

                #Ждём пока все thread завершатся
                for reg_thread in reg_threads:
                    reg_thread.join()
        finally:
            lock.release()