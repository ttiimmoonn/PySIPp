import subprocess
import time
import threading
from datetime import datetime
import subprocess
import shlex

def RegisterUser (user, mode="reg"):
    if mode == "reg":
        # Взводим timer 
        user.SetRegistrationTimer()
        # Запускаем процесс
        process = start_ua(user.RegCommand, user.RegLogFile)
        if not process:
            print("    [ERROR] User", user.Number, "not registred. Detail:")
            print("    --> Can't start process {File not found}")
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
                print("    [ERROR] User", user.Number, "not registred. Detail:")
                print("    --> Registeration failed. SIPp process return bad exit code.", "ex_code:", user.RegProcess.poll())
                return False
            else:
                user.Status = "Registered"
                user.SetStatusCode(user.RegProcess.poll()) 
                print("    [DEBUG] User", user.Number, "registred at", datetime.strftime(datetime.now(), "%H:%M:%S"), "exp time = ", (int(user.Expires) * 2 / 3))
                return True
        except subprocess.TimeoutExpired:
            user.RegProcess.kill()
            user.Status = "Error of registration (timeout)"
            user.SetStatusCode(2)
            user.CleanRegistrationTimer()
            print("    [ERROR] User", user.Number, "not registred. Detail:")
            print("    -->Registeration failed. UA registration process break by timeout.")
            return False
    elif mode == "unreg":
        try:
            if user.RegProcess.poll() == None:
                user.RegProcess.wait()
        except AttributeError:
            return False
        process = start_ua(user.UnRegCommand, user.RegLogFile)
        if not process:
            print("    [ERROR] User registration", user.Number, "not dropped. Detail:")
            print("    --> Can't start process {File not found}")
            #Закрываем лог файл
            user.RegLogFile.close()
            return False
        else:
            user.UnRegProcess = process
        try:
            user.UnRegProcess.communicate(timeout=5)
            if user.UnRegProcess.poll() != 0:
                user.Status = "Error of drop"
                print("    [ERROR] User registration", user.Number, "not dropped. Detail:")
                print("    --> Drop failed. SIPp process return bad exit code.")
                #Закрываем лог файл
                user.RegLogFile.close()
                return False
            else:
                user.Status = "Dropped"
                print("    [DEBUG] User registration", user.Number, " is dropped.")
                #Закрываем лог файл
                user.RegLogFile.close()
                return True
        except subprocess.TimeoutExpired:
            user.UnRegProcess.kill()
            user.Status = "Error of drop (timeout)"
            print("    [ERROR] User registration", user.Number, "not dropped. Detail:")
            print("    --> Drop failed. UA registration process break by timeout.")
            #Закрываем лог файл
            user.RegLogFile.close()
            return False
    else:
        print("    [ERROR] Bad arg {set registration func}")
        return False

def DropRegistration (users):
    #Делаем остановку всех таймеров
    for user in users:
        #Если таймер существует, то дропаем его
        if users[user].Timer:
            users[user].CleanRegistrationTimer()
    # Делаем сброс регистрации
    for user in users:
        if users[user].ReadStatusCode() != 0:
            #Поскольку статус код регистрации не равен нулю
            #то дропать регистрацию такому юзеру не нужно
            #Закрываем лог файл и продолжаем перебор юзеров
            if users[user].RegLogFile != None:
                users[user].RegLogFile.close()
            continue
        #Если юзер уже разрегистрирован, то пропускаем его
        #Требуется в том случае если кто-то интерапнул программу после сброса регистрации
        if users[user].Status == "Dropped":
            print("[WARN] Registaration for user",users[user].Login,"already dropped")
            continue
        if not RegisterUser(users[user], "unreg"):
            continue
   
def start_ua (command, fd):
# Запуск подпроцесса регистрации
    args = shlex.split(str(command))
    try:
        # Пытаемся создать новый SIPp процесс.
        ua_process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=fd)
    except FileNotFoundError:
        # Если неправильно указан путь, то возвращаем false.
        return False
    # Если процесс запустился, то возвращаем его.
    return ua_process

def start_ua_thread(ua, event_for_stop):
#    event_for_wait.wait() # wait for event
#    event_for_wait.clear() # clean event for future
#    event_for_set.set() # set event for neighbor thread
    commandCount = 1
   
    for command in ua.Commands:
        if not event_for_stop.isSet():
            # Если пришла команда остановить thread выходим
            print("--> [DEBUG] UA", ua.Name, "with command", commandCount, "recv exit event.")
            ua.SetStatusCode(6)
            break        
        # Запускаем UA
        process = start_ua (command, ua.LogFd)
        if not process:
            ua.SetStatusCode(1)
            print("[ERROR] UA", ua.Name, "not started")
            return False
        ua.Status = "Starting"
        # Добавляем новый процесс в массив
        ua.Process.append(process)
        # Ждём
        time.sleep(0.2)
        if process.poll() != None and process.poll() != 0:
            ua.Status = "Not Started"
            print("--> [DEBUG] UA", ua.Name, "with command", commandCount, "not started")
            ua.SetStatusCode(2)
            # Если процесс упал, выходим
            return False
        else:
            ua.Status = "Started"
            print("--> [DEBUG] UA", ua.Name, "with command", commandCount, "started")
        try:
            while(event_for_stop.isSet()):
                code = process.poll()
                if code != None:
                    # Если процесс завершился самостоятельно, то выходим из цикла
                    break
                time.sleep(0.01)
            
            if not event_for_stop.isSet():
                process.kill()
                ua.SetStatusCode(3)
                print("--> [DEBUG] UA", ua.Name, "with command", commandCount, "recv exit event.")
                #print("--> [ERROR] UA", ua.Name, "with command", commandCount, "return", process.poll(), "exit code.")
                return False      
            
            if process.poll() != 0:
                    ua.Status = "SIPp error"
                    ua.SetStatusCode(4)
                    print("--> [ERROR] UA", ua.Name, "with command", commandCount, "return", process.poll(), "exit code.")
                    return False
            else:
                ua.Status = "Success"
                ua.SetStatusCode(process.poll())
                print("--> [DEBUG] UA", ua.Name, "with command", commandCount, "return", process.poll(), "exit code.")
        except subprocess.TimeoutExpired:
            process.kill()
            ua.SetStatusCode(5)
            ua.Status = "Timeout Error"
            print("--> [ERROR] UA", ua.Name, "killed by timeout")
            return False
        commandCount += 1
    return True

def start_process_controller(test):
    threads = []
    #Создаём ivent для threads
    event_for_threads = threading.Event()
    #Устанавливаем его в true
    event_for_threads.set()
   
    #Начинаем запуск UA по очереди
    print("[DEBUG] Trying to start UA...")
    for ua in test.UserAgent:
        time.sleep(0.5)
        # Инициализируем новый thread
        testThread = threading.Thread(target=start_ua_thread, args=(ua,event_for_threads,), name = ua.Name)
        testThread.setName(ua.Name)
        # Запускаем новый thread
        testThread.start()
        threads.append(testThread)
        
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
                        event_for_threads.clear()
                        #Выходим из диспетчера
                        event_for_mgm = False
        #Проверяем, что все процессы возращают 0 ex_code
        if event_for_mgm:
            for userAgent in test.UserAgent:
                ex_code = userAgent.ReadStatusCode()
                if ex_code == None:
                    continue
                if int(ex_code) != 0:
                    #Если процесс отвалился, останавливаем все thread
                    event_for_threads.clear()
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
    print("[ERROR] One or more threads not closed")
    return False

def CheckUaStatus(test):
    for ua in test.UserAgent:
        for proc in ua.Process:
            if proc.poll() != 0:
                return False
    return True