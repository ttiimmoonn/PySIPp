import subprocess
import time
import threading
from datetime import datetime
import subprocess
import shlex
import logging
logger = logging.getLogger("tester")

def RegisterUser (user, mode="reg"):
    if mode == "reg":
        # Взводим timer 
        user.SetRegistrationTimer()
        # Запускаем процесс
        process = start_ua(user.RegCommand, user.RegLogFile)
        if not process:
            logger.error(" ---| User %s not registred. Detail: Can't start process {SIPp not found}",user.Number)
            user.Status = "Registration process not started."
            # Выставляем Status код равный 1
            user.SetStatusCode(1)
            # Удаляем timer
            user.CleanRegistrationTimer()
            return False
        else:
            user.RegProcess = process

        try:
            user.RegProcess.communicate(timeout=5)
            if user.RegProcess.poll() != 0:
                user.Status = "Error of registration"
                # Cтавим код выхода
                user.SetStatusCode(user.RegProcess.poll())
                # Делаем сброс таймера
                user.CleanRegistrationTimer()
                logger.error(" ---| User %s not registred. Detail: Registeration failed. SIPp process return bad exit code: %d.",user.Number,user.RegProcess.poll())
                return False
            else:
                user.Status = "Registered"
                user.SetStatusCode(user.RegProcess.poll()) 
                logger.info(" ---| User %s registred at %s exp time = %d",user.Number,str(datetime.strftime(datetime.now(), "%H:%M:%S")),(int(user.Expires) * 2 / 3))
                return True
        except subprocess.TimeoutExpired:
            user.RegProcess.kill()
            user.Status = "Error of registration (timeout)."
            user.SetStatusCode(2)
            user.CleanRegistrationTimer()
            logger.error(" ---| User %s not registred. Detail: UA registration process break by timeout.",user.Number)
            return False
    elif mode == "unreg":
        try:
            if user.RegProcess.poll() == None:
                user.RegProcess.wait()
        except AttributeError:
            return False
        process = start_ua(user.UnRegCommand, user.RegLogFile)
        if not process:
            logger.error(" ---| User registration %s not dropped. Detail: Can't start process {SIPp not found}",user.Number)
            #Закрываем лог файл
            user.RegLogFile.close()
            user.SetStatusCode(3)
            return False
        else:
            user.UnRegProcess = process
        try:
            user.UnRegProcess.communicate(timeout=5)
            if user.UnRegProcess.poll() != 0:
                user.Status = "Error of drop registration"
                logger.error(" ---| User registration %s not dropped. Detail: SIPp process return bad exit code.",user.Number)
                user.SetStatusCode(user.RegProcess.poll())
                #Закрываем лог файл
                user.RegLogFile.close()
                return False
            else:
                user.Status = "Dropped"
                logger.info(" ---| User registration %s is dropped.",user.Number)
                #Закрываем лог файл
                user.RegLogFile.close()
                user.SetStatusCode(user.RegProcess.poll())
                return True
        except subprocess.TimeoutExpired:
            user.UnRegProcess.kill()
            user.Status = "Error of drop (timeout)"
            logger.error(" ---| User registration %s not dropped. Detail: UA registration process break by timeout.",user.Number)
            user.SetStatusCode(4)
            #Закрываем лог файл
            user.RegLogFile.close()
            return False
    else:
        logger.error(" ---| Bad arg {set registration func}")
        return False


            
def preexec_process():
    import os
    os.setpgrp()


def start_ua (command, fd):
# Запуск подпроцесса регистрации
    args = shlex.split(str(command))
    try:
        # Пытаемся создать новый SIPp процесс.
        ua_process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=fd, preexec_fn = preexec_process)
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
            process = start_ua (command, ua.LogFd)
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
                logger.error("UA %s with command %s started.",ua.Name,commandCount)
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
    logger.info("Trying to start UA...")
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

                for user in test_users:
                    if test_users[user].RegLogFile != None:
                        test_users[user].RegLogFile.close()
        finally:
            lock.release()