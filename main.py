import modules.test_parser as parser
import modules.cmd_builder as builder
import modules.process_contr as proc
import modules.fs_worker as fs
import modules.cocon_interface as ssh
import json
import sys
import time
import threading
import argparse
import math
from collections import OrderedDict

def createParser ():
    parser = argparse.ArgumentParser()
    parser.add_argument ('-t', '--test_config', type=argparse.FileType(),required=True)
    parser.add_argument ('-c', '--custom_config', type=argparse.FileType(),required=True)
    return parser

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

def link_user_to_test(test, users):
    #Массив для использованных id
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
    return test

def stop_test(test):
    if "PostCoconConf" in test_desc:
        print("[DEBUG] Deconfigure of the ECSS-10 system...")
        #Переменные для настройки соединения с CoCoN
        ssh.cocon_configure(test_desc,test_var,"PostCoconConf")
    
#Парсим аргументы командной строки
arg_parser = createParser()
namespace = arg_parser.parse_args()
#Забираем описание теста и общие настройки
jsonData = namespace.test_config.read()
customSettings = namespace.custom_config.read()
namespace.test_config.close()
namespace.custom_config.close()

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
    #Загружаем json описание теста
    test_desc = json.loads(jsonData,object_pairs_hook=OrderedDict)
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
    if not ssh.cocon_configure(test_desc,test_var,"PreCoconConf"):
        exit()
    #Даём кокону очнуться
    time.sleep(1)

#Создаём директорию для логов
log_path = str(test_var["%%LOG_PATH"]) + "/" + test_desc["TestName"]
print("[DEBUG] Creating the log dir.")
if not fs.create_log_dir(log_path):
    #Если не удалось создать директорию, выходим
    exit()

#Врубаем регистрацию для всех юзеров
print ("[DEBUG] Starting of the registration...")
for user in test_users:
    reg_log_name = "REG_" + str(test_users[user].Number)
    log_file = fs.open_log_file(reg_log_name,log_path)
    #Если не удалось создать лог файл, то выходим
    if not log_file:
        exit()
    else:
        test_users[user].RegLogFile = log_file
    if not proc.RegisterUser(test_users[user]):
        #Если регистрация не прошла
        #Пытаемся разрегистировать тех кого удалось зарегать
        proc.DropRegistration(test_users)
        #Выходим
        exit()

#Запускаем процесс тестирования
for test in tests:
    print("[DEBUG] Start test: ",test.Name)
    for item in test.TestProcedure:
        for key in item:
            if key == "ServiceFeature":
                #Забираем фича-код и юзера с которого его выполнить
                try:
                    code = item[key][0]['code']
                    user_id = str(item[key][0]['userId'])
                except:
                    print("[ERROR] Can't get service code or user from \"ServiceFeature\" command")
                    exit()
                print ("[DEBUG] Send ServiceFeature code =", code)
                try:
                    user = test_users[str(user_id)]
                except:
                    print("[ERROR] Can't get User Object with.")
                    print("    --> ID = ", user_id, "not found.")
                    exit()
                #Собираем команду для активации сервис фичи
                command = builder.build_service_feature_command(user,code)
                #Прогоняем её через словарь
                command = builder.replace_key_value(command, test_var)
                if not command:
                    exit()
                else:
                    import subprocess
                    proc.start_ua(command,subprocess.DEVNULL )
                    time.sleep(2)
            elif key == "Sleep":
                try:
                    sleep_time = int(item[key])
                except:
                    print("[ERROR] Bag sleep arg. Exit.")
                    exit()
                print("[DEBUG] Sleep on", sleep_time, "seconds")
                time.sleep(sleep_time)
                continue
            elif key == "StartUA":
                #Парсим Юзер агентов 
                print ("[DEBUG] Parsing UA from the test.")
                test = parser.parse_user_agent(test,item[key])
                if not test:
                    #Если неправильное описание юзер агентов, то выходим
                    continue
                #Линкуем UA с объектами юзеров.
                print("[DEBUG] Linking the UA object with the User object...")
                test = link_user_to_test(test, test_users)
                #Если есть ошибки при линковке, то выходим
                if not test:
                    continue
                #Собираем команды для UA.
                print("[DEBUG] Building of the SIPp commands for the UA...")
                test = builder.build_sipp_command(test,test_var)
                #Если есть ошибки при линковке, то выходим
                if not test:
                    continue
                #Линкуем лог файлы и UA
                print("[DEBUG] Linking of the LogFd with the UA object...")
                for ua in test.UserAgent:
                    log_fd = fs.open_log_file(ua.Name,log_path)
                    if not log_fd :
                        continue
                    else:
                        ua.LogFd = log_fd
                #Если все предварительные процедуры выполнены успешно,
                #то запускаем процессы
                threads = proc.start_process_controller(test)
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
                            print(123)
                    if thread_alive_flag == 0:
                        break

            

#Разрегистрируем юзеров
print("[DEBUG] Drop registration of users.")
proc.DropRegistration(test_users)
#Деконфигурируем ссв и закрываем лог файлы
stop_test(test)
print("[DEBUG] exit.")




for test in tests:
    show_test_info(test)


 


       
    
    exit()    


    
      
        

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
