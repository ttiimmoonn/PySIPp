import modules.test_parser as parser
import modules.cmd_builder as builder
import modules.process_contr as proc
import modules.fs_worker as fs
import modules.cocon_interface as ssh
import json
import sys
import time
import threading
import math



def show_test_info (test):
    print("TestName:    ",test.Name)
    print("TestDesc:    ",test.Description)
    print("TestUA:")
    print("")
    for ua in test.UserAgent:
        print("     UaName:     ",ua.Name)
        print("     UaStatus:   ",ua.Status)
        print("     UaType:     ",ua.Type)
        print("     UaUserId:   ",ua.UserId)
        print("     UaUserObj:  ",ua.UserObject)
        print("     UaPort:     ",ua.Port)
        print("     UaLogFd:    ",ua.LogFd)
        print("     UaCommand:")
        for command in ua.Commands:
            print("      ",command)
        print("")

def link_user_to_test(tests, users):
    #Массив для использованных id
    for test in tests:
        use_id = []
        for ua in test.UserAgent:
            if ua.Type == "User":
                if not int(ua.UserId) in use_id:
                    use_id.append(int(ua.UserId))
                    try:
                        ua.UserObject = users[str(ua.UserId)]
                    except KeyError:
                        print("[ERROR] User with id =",ua.UserId,"not found","{ UA :",ua.Name,"}")
                        return False
                else:
                    print("[ERROR] Duplicate UserId:",ua.UserId,"{ UA :",ua.Name,"}")
                    return False
    return tests

def stop_test(test):
    if "PostCoconConf" in test_desc:
        print("[DEBUG] Deconfigure of the ECSS-10 system...")
        #Переменные для настройки соединения с CoCoN
        ssh.cocon_configure(test_desc,test_var,"PostCoconConf")
    

jsonData = open("/home/vragov/scripts/ecss.3.6.0/oa_exchange/oa_exchange.json").read()
customSettings = '''
{
"SystemVars" : [
    {
        "%%SIPP_PATH" : "/home/vragov/sipp/sipp-3.4.1/sipp",
        "%%SRC_PATH" : "/home/vragov/scripts/ecss.3.6.0",
        "%%TEMP_PATH" : "/home/vragov/scripts/ecss.3.6.0/temp",
        "%%REG_XML" : "./xml/reg_user.xml",
        "%%LOG_PATH" : "/home/vragov/scripts/ecss.3.6.0/temp/log",
        "%%IP" : "192.168.118.249",
        "%%SERV_IP" : "192.168.118.245",
        "%%EXTER_IP" : "192.168.118.245",
        "%%EXTER_PORT" : "5015",
        "%%DEV_USER" : "admin",
        "%%DEV_PASS" : "password",
        "%%DEV_DOM" : "pv.ssw2"
    }
]
}
'''

#Декларируем массив для юзеров
test_users = {}
#декларируем массив для тестов
tests = []
#Декларируем словарь пользовательских переменных
test_var = {}

print("[DEBUG] Reading custom settings...")
try:
    custom_settings = json.loads(customSettings)
except (ValueError, KeyError, TypeError):
    print("[ERROR] Wrong JSON format. Detail:")
    print("--->",sys.exc_info()[1])
    exit()

custom_settings = parser.parse_sys_conf(custom_settings["SystemVars"][0])
if not custom_settings:
    exit()


print("[DEBUG] Reading JSON script...")
try:
    test_desc = json.loads(jsonData)
except (ValueError, KeyError, TypeError):
    print("[ERROR] Wrong JSON format. Detail:")
    print("--->",sys.exc_info()[1])
    exit()
    

#Парсим юзеров
print ("[DEBUG] Parsing users from the json string...")
try:
    test_users = parser.parse_user_info(test_desc["Users"])
except KeyError:
    print("[WARN] Test has no users")
#Если есть ошибки при парсинге, то выходим
if not test_users:
    exit()

#Парсим тесты
print ("[DEBUG] Parsing tests from the json string...")
tests = parser.parse_test_info(test_desc["Tests"])
#Если есть ошибки при парсинге, то выходим
if not tests:
    exit()

#Парсим тестовые переменные в словарь
test_var = parser.parse_test_var(test_desc)
#Добавляем системные переменные в словарь
test_var.update(custom_settings)

#Линкуем UA с объектами юзеров.
print("[DEBUG] Linking the UA object with the User object...")
tests = link_user_to_test(tests, test_users)
#Если есть ошибки при линковке, то выходим
if not tests:
    exit()


#Собираем команды для регистрации абонентов
print("[DEBUG] Building of the registration command for the UA...")
for key in test_users:
    command = builder.build_reg_command(test_users[key],test_var)
    if command:
        test_users[key].RegCommand = command
    else:
        exit()

#Собираем команды для регистрации абонентов
print("[DEBUG] Building of the registration command for the UA...")
for key in test_users:
    command = builder.build_reg_command(test_users[key],test_var)
    if command:
        test_users[key].RegCommand = command
    else:
        exit()

#Собираем команды для сброса регистрации абонентов
print("[DEBUG] Building command for the dropping of users registration...")
for key in test_users:
    command = builder.build_reg_command(test_users[key],test_var,"unreg")
    if command:
        test_users[key].UnRegCommand = command
    else:
        exit()
        
        

#Если есть настройки для CoCon выполняем их
if "PreCoconConf" in test_desc:
    print("[DEBUG] Configuration of the ECSS-10 system...")
    #Переменные для настройки соединения с CoCoN
    ssh.cocon_configure(test_desc,test_var,"PreCoconConf")
    #Даём кокону очнуться
    time.sleep(1)

if "SSMgmCommands" in test_desc:
    print("[DEBUG] Ativation of the ss...")
    ss_conf = test_desc["SSMgmCommands"][0]
    print(ss_conf["Activation"])


#Запускаем процесс тестирования
for test in tests:
    
    #Собираем команды для UA.
#print("[DEBUG] Building of the SIPp commands for the UA...")
#tests = builder.build_sipp_command(tests,test_var)
#Если есть ошибки при линковке, то выходим
#if not tests:
#    exit()

#Создаём директорию для логов
#log_path = str(test_var["%%LOG_PATH"]) + "/" + test_desc["TestName"]
#print("[DEBUG] Creating the log directory...")
#if not fs.create_log_dir(log_path):
    #Если не удалось создать директорию, выходим
#    exit()
#Линкуем лог файлы и UA
#print("[DEBUG] Linking of the LogFd with the UA object...")
#for test in tests:
#    for ua in test.UserAgent:
#        log_fd = fs.open_log_file(ua.Name,log_path)
#        if not log_fd :
#            exit()
#        else:
#            ua.LogFd = log_fd

    
    threads = []
    #Флаг для выхода из диспетчера при ошибке регистрации
    registration_flag = True
    print("[DEBUG] Start test: ",test.Name)

    #Для юзеров запускаем регистрацию.
    print ("[DEBUG] Starting of the registration...")
    for ua in test.UserAgent:
        if ua.Type == "User":
            if not proc.RegisterUser(ua):
                #Если регистрация не прошла начинаем новый тест
                proc.DropRegistration(test.UserAgent)
                registration_flag = False
                break
    #Если регистрация провалилась переходим к следующему тесту
    if not registration_flag:
        continue
                
                
    #Создаём ivent для threads
    event_for_threads = threading.Event()
    #Устанавливаем его в true
    event_for_threads.set()
    
    #Начинаем запуск UA по очереди
    print("[DEBUG] Trying to start UA...")
    for ua in test.UserAgent:
        time.sleep(0.5)
        # Инициализируем новый thread
        testThread = threading.Thread(target=proc.start_ua_thread, args=(ua,event_for_threads,), name = ua.Name)
        testThread.setName(ua.Name)
        # Запускаем новый thread
        testThread.start()
        threads.append(testThread)
        
    #Включаем цикл опроса статусов процессов.
    #Включаем флажок для выхода из диспетчера
    event_for_mgm = True
    
    while(event_for_mgm):
        #Проверяем, что все регистрации живы.
        for ua in test.UserAgent:
            if ua.Type == "User":
                ex_code = ua.UserObject.ReadStatusCode()
                if ex_code != 0:
                    #Если регистрация отвалилась, останавливаем все thread
                    event_for_threads.clear()
                    #Пытаемся остановить регистрацию
                    proc.DropRegistration(test.UserAgent)
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
                    #Пытаемся остановить регистрацию
                    proc.DropRegistration(test.UserAgent)
                    #Выходим из диспетчера
                    event_for_mgm = False
                    break
        if event_for_mgm:  
            #Если все thread завершились кроме основного, то выходим из диспетчера
            thread_alive_flag = 0                 
            for thread in threads:                
                if thread.is_alive():             
                    thread_alive_flag = 1
                    break
            if thread_alive_flag == 0:           
                event_for_mgm = False
        time.sleep(0.01)
    #Заводим таймер на 5 сек.
    print("[DEBUG] Waiting for closing threads...")
    Timer = 5

    while Timer != 0:
        Timer -= 1
        time.sleep(1)
        thread_alive_flag = 0
        for thread in threads:
            if thread.is_alive():
                thread_alive_flag += 1
        if thread_alive_flag == 0:
            break

    #Рассчитывает результат теста
    result = 0
    for userAgent in test.UserAgent:
        for process in userAgent.Process:
            result += math.fabs(int(process.poll()))

            

    if result != 0:
        print("[ERROR] Test:",test.Name," - failed.")
    else:
        print("[DEBUG] Test:",test.Name," - success.")
    #Делаем сброс регистрации
    proc.DropRegistration(test.UserAgent)
    #Закрываем лог файлы
    for ua in test.UserAgent:
        ua.LogFd.close()

#Деконфигурируем ссв и закрываем лог файлы
stop_test(test)
print("[DEBUG] exit.")