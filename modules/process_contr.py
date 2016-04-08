import subprocess
import time
from datetime import datetime


def RegisterUser (ua, mode="reg"):
    if mode == "reg":
        # Взводим timer 
        ua.UserObject.SetRegistrationTimer(ua)
        # Запускаем процесс
        process = start_ua(ua.UserObject.RegCommand, ua.LogFd)
        if not process:
            print("    [ERROR] User", ua.UserObject.Number, "not registred. Detail:")
            print("    --> Can't start the process {File not found}")
            ua.UserObject.Status = "Registration process not started."
            # Выставляем Status код равный 1
            ua.UserObject.SetStatusCode(1)
            # Удаляем timer
            ua.UserObject.CleanRegistrationTimer()
            return False
        else:
            ua.UserObject.RegProcess = process

        try:
            ua.UserObject.RegProcess.communicate(timeout=5)
            if ua.UserObject.RegProcess.poll() != 0:
                ua.UserObject.Status = "Error of registration"
                # Cтавим код выхода
                ua.UserObject.SetStatusCode(ua.UserObject.RegProcess.poll())
                # Делаем сброс таймера
                ua.UserObject.CleanRegistrationTimer() 
                print("    [ERROR] User", ua.UserObject.Number, "not registred. Detail:")
                print("    --> Registeration failed. The SIPp process return bad exit code.", "ex_code:", ua.UserObject.RegProcess.poll())
                return False
            else:
                ua.UserObject.Status = "Registered"
                ua.UserObject.SetStatusCode(ua.UserObject.RegProcess.poll()) 
                print("    [DEBUG] User", ua.UserObject.Number, "registred at", datetime.strftime(datetime.now(), "%H:%M:%S"), "exp time = ", (int(ua.UserObject.Expires) * 2 / 3))
                return True
        except subprocess.TimeoutExpired:
            ua.UserObject.RegProcess.kill()
            ua.UserObject.Status = "Error of registration (timeout)"
            ua.UserObject.SetStatusCode(2)
            ua.UserObject.CleanRegistrationTimer()
            print("    [ERROR] User", ua.UserObject.Number, "not registred. Detail:")
            print("    -->Registeration failed. The UA registration process break by timeout.")
            return False
    elif mode == "unreg":
        ua.UserObject.CleanRegistrationTimer()
        try:
            if ua.UserObject.RegProcess.poll() == None:
                ua.UserObject.RegProcess.wait()
        except AttributeError:
            return False
        process = start_ua(ua.UserObject.UnRegCommand, ua.LogFd)
        if not process:
            print("    [ERROR] User registration", ua.UserObject.Number, "not dropped. Detail:")
            print("    --> Can't start the process {File not found}")
            return False
        else:
            ua.UserObject.UnRegProcess = process
        try:
            ua.UserObject.UnRegProcess.communicate(timeout=5)
            if ua.UserObject.UnRegProcess.poll() != 0:
                ua.UserObject.Status = "Error of drop"
                print("    [ERROR] User registration", ua.UserObject.Number, "not dropped. Detail:")
                print("    --> Drop failed. The SIPp process return bad exit code.")
                return False
            else:
                ua.UserObject.Status = "Dropped"
                print("    [DEBUG] User registration", ua.UserObject.Number, " is dropped.")
                return True
        except subprocess.TimeoutExpired:
            ua.UserObject.UnRegProcess.kill()
            ua.UserObject.Status = "Error of drop (timeout)"
            print("    [ERROR] User registration", ua.UserObject.Number, "not dropped. Detail:")
            print("    --> Drop failed. The UA registration process break by timeout.")
            return False
    else:
        print("    [ERROR] Bad arg {set registration func}")
        return False

def DropRegistration (test_ua):
    # Делаем сброс регистрации
    for ua in test_ua:
        if ua.Type == "User":
            if ua.UserObject.Status == None or ua.UserObject.Status == "Dropped":
                continue
            if not RegisterUser(ua, "unreg"):
                continue
   
def start_ua (command, fd):
# Запуск подпроцесса регистрации
    import subprocess
    import shlex
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
        time.sleep(0.8)
        if process.poll() != None:
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
