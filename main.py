#!/usr/local/bin/python3.5

import modules.test_parser as parser
import modules.cmd_builder as builder
import modules.process_contr as proc
import modules.fs_worker as fs
import modules.cocon_interface as ssh
import modules.test_class as test_class
import modules.timestamp_calc as stat_module
import re
import signal
import json
import sys
import time
import threading
import argparse
import math
from collections import OrderedDict


def signal_handler(signal, frame):
    print("[DEBUG] Receive SIGINT signal. Start test aborting")
    if tests and test_desc and test_users:
        stop_test(tests,test_desc,test_users)
    for test in tests:
        if test.Status!="New":
            for ua in test.UserAgent:
                for process in ua.Process:
                    if process.poll() == None:
                        process.kill()
    #print(threading.current_thread())
    sys.exit(0)

def createParser ():
    parser = argparse.ArgumentParser()
    parser.add_argument ('-t', '--test_config', type=argparse.FileType(),required=True)
    parser.add_argument ('-c', '--custom_config', type=argparse.FileType(),required=True)
    parser.add_argument ('-n', '--test_numbers', type=match_test_numbers,required=False)
    parser.add_argument ('--drop_uac', action='store_const', const=True)
    parser.add_argument ('--timestamp_calc', action='store_const', const=True)
    return parser

def show_test_info (test):
    print("TestName:        ",test.Name)
    print("TestDesc:        ",test.Description)
    print("TestUA:          ",test.UserAgent)
    print("TestCompliteUA   ",test.CompliteUA)
    print("")
    for ua in test.CompliteUA:
        print("     UaName:         ",ua.Name)
        print("     UaStatus:       ",ua.Status)
        print("     UaStatusCode:   ",ua.StatusCode)
        print("     UaType:         ",ua.Type)
        print("     UaUserId:       ",ua.UserId)
        print("     UaUserObj:      ",ua.UserObject)
        print("     UaPort:         ",ua.Port)
        print("     UaLogFd:        ",ua.LogFd)
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

def stop_test(tests,test_desc,test_users):
    if "PostCoconConf" in test_desc:
        print("[DEBUG] Deconfigure of the ECSS-10 system...")
        #Переменные для настройки соединения с CoCoN
        ssh.cocon_configure(test_desc["PostCoconConf"],test_var)
    #Разрегистрируем юзеров
    print("[DEBUG] Drop registration of users.")
    proc.DropRegistration(test_users)
    print("[DEBUG] Close log files...")
    for test in tests:
        for ua in test.CompliteUA:
            if ua.LogFd:
                ua.LogFd.close()
    return True

def match_test_numbers(test_numbers):
    match_result = re.search("^[0-9]*$|^([0-9]*,)*[0-9]$",test_numbers)
    if match_result:
        test_numbers = [int(i) for i in test_numbers.split(",")]
        return  test_numbers
    else:
        raise argparse.ArgumentTypeError("Arg 'n' does not match required format : num1,num2,num3")


#Добавляем трап на SIGINT
signal.signal(signal.SIGINT, signal_handler)
#Парсим аргументы командной строки
arg_parser = createParser()
namespace = arg_parser.parse_args()
test_numbers = namespace.test_numbers
uac_drop_flag = namespace.drop_uac
timestamp_calc = namespace.timestamp_calc
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
    print("[ERROR] Wrong JSON format of test config. Detail:")
    print("--->",sys.exc_info()[1])
    exit(1)

custom_settings = parser.parse_sys_conf(custom_settings["SystemVars"][0])
if not custom_settings:
    exit(1)



print("[DEBUG] Reading JSON script...")
try:
    #Загружаем json описание теста
    test_desc = json.loads(jsonData,object_pairs_hook=OrderedDict)
except (ValueError, KeyError, TypeError):
    print("[ERROR] Wrong JSON format. Detail:")
    print("--->",sys.exc_info()[1])
    exit(1)
    

#Парсим юзеров
print ("[DEBUG] Parsing users from the json string...")
if "Users" in test_desc:    
    test_users = parser.parse_user_info(test_desc["Users"])
else:
    print("[WARN] Test has no users")
#Если есть ошибки при парсинге, то выходим
if test_users == False:
    exit(1)

#Парсим тесты
print ("[DEBUG] Parsing tests from the json string...")
try:
   tests = parser.parse_test_info(test_desc["Tests"])
except(KeyError):
   print("[ERROR] No Test in the test config")
#Если есть ошибки при парсинге, то выходим
if not tests:
    exit(1)

#Если был передан test_numbers, то накладываем маску на массив тестов

if test_numbers:
    try:
        tests=list(tests[i] for i in test_numbers)
    except IndexError:
        print("[ERROR] Test index out of range")
        sys.exit(1)

#Парсим тестовые переменные в словарь
test_var = parser.parse_test_var(test_desc)
#Добавляем системные переменные в словарь
test_var.update(custom_settings)
#Создаём директорию для логов
log_path = str(test_var["%%LOG_PATH%%"]) + "/" + test_desc["TestName"]
print("[DEBUG] Creating the log dir.")
if not fs.create_log_dir(log_path):
    #Если не удалось создать директорию, выходим
    exit(1)
#Добавляем директорию с логами к тестам
for test in tests:
    test.LogPath = log_path

#Если есть настройки для CoCon выполняем их
if "PreCoconConf" in test_desc:
    print("[DEBUG] Configuration of the ECSS-10 system...")
    #Переменные для настройки соединения с CoCoN
    if not ssh.cocon_configure(test_desc["PreCoconConf"],test_var):
        exit()
    #Даём кокону очнуться
    time.sleep(1)


if len(test_users) != 0:
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
            stop_test(tests,test_desc,test_users)
            exit()
        


#Запускаем процесс тестирования
for test in tests:
    print("[DEBUG] Start test:",test.Name)
    #Выставляем статус теста
    test.Status = "Starting"
    for item in test.TestProcedure:
        #Если статус теста Failed заканчиваем процесс тестирования
        if not test or test.Status == "Failed":
            print("[ERROR] Test:",test.Name,"Failed.")
            break

        for method in item:
            if method == "CoconCommand":
                print("[DEBUG] Send commands to CoCon...")
                #Переменные для настройки соединения с CoCoN
                if not ssh.cocon_configure(item[method],test_var):  
                    #Выставляем статус теста
                    test.Status = "Failed"
                    break
                else:
                    time.sleep(1)


            elif method == "ServiceFeature":
                print("[DEBUG] SendServiceFeature command activate.")
                #Забираем фича-код и юзера с которого его выполнить
                #О наличии данных параметров заботится парсер тестов
                code = item[method][0]['code']
                user_id = str(item[method][0]['userId'])
                code = builder.replace_key_value(code, test_var)
                if not code:
                    test.Status = "Failed"
                    break
                print ("[DEBUG] Send ServiceFeature code =", code)

                try:
                    user = test_users[str(user_id)]
                except:
                    print("[ERROR] Can't get User Object with.")
                    print("    --> ID = ", user_id, "not found.")
                    #Выставляем статус теста
                    test.Status = "Failed"
                    break
                
                #Собираем команду для активации сервис фичи
                command = builder.build_service_feature_command(user,code)
                #Прогоняем её через словарь
                command = builder.replace_key_value(command, test_var)
                
                if not command:
                    #Выставляем статус теста
                    test.Status = "Failed"
                    break
                
                service_ua = test_class.UserAgentClass()
                service_ua = service_ua.GetServiceFetureUA(command,code,user,user_id)
                sf_log_name = "SF_" + str(service_ua.Name)
                log_file = fs.open_log_file(sf_log_name,log_path)
                if not log_file:
                    #Выставляем статус теста
                    test.Status = "Failed"
                    break
                else:
                    service_ua.LogFd = log_file
                #Добавляем сервис UA в активные UA теста
                test.UserAgent.append(service_ua)
                #Запускаем активацию фича-кода через процесс контроллер
                sf_thread = proc.start_process_controller(test)
                #Проверяем, что вернувшиеся треды закрыты:
                print("[DEBUG] Waiting for closing threads...")
                if not proc.CheckThreads(sf_thread):
                    #Переносим отработавшие UA в завершенные
                    test.Status = "Failed"
                    test.CompliteSFUA()
                    print("[ERROR] Send SF",code,"failed")
                    break
                #Проверяем UA на статусы
                print("[DEBUG] Check process StatusCode...")
                if not proc.CheckUaStatus(test):
                    #Переносим отработавшие UA в завершенные
                    test.CompliteSFUA()
                    print("[ERROR] Can't send Feature code",code)
                    test.Status = "Failed"
                    break
                else:
                    test.CompliteSFUA()

            elif method == "Sleep":
                print("[DEBUG] Sleep command activate.")
                try:
                    sleep_time = int(item[method])
                except:
                    print("[ERROR] Bag sleep arg. Exit.")
                    exit()
                print("[DEBUG] Sleep on", sleep_time, "seconds")
                time.sleep(sleep_time)
                continue

            elif method == "StartUA":
                print("[DEBUG] StartUA command activate.")
                #Парсим Юзер агентов 
                print ("[DEBUG] Parsing UA from the test.")
                test = parser.parse_user_agent(test,item[method])
                if not test:
                    #Если неправильное описание юзер агентов, то выходим
                    break
                #Линкуем UA с объектами юзеров.
                print("[DEBUG] Linking the UA object with the User object...")
                test = link_user_to_test(test, test_users)
                #Если есть ошибки при линковке, то выходим
                if not test:
                    break
                #Собираем команды для UA.
                print("[DEBUG] Building of the SIPp commands for the UA...")
                test = builder.build_sipp_command(test,test_var,uac_drop_flag, timestamp_calc)
                #Если есть ошибки при сборке, то выходим
                if not test:
                    break
                #Линкуем лог файлы и UA
                print("[DEBUG] Linking of the LogFd with the UA object...")
                for ua in test.UserAgent:
                    log_fd = fs.open_log_file(ua.Name,log_path)
                    if not log_fd:
                        break
                    else:
                        ua.LogFd = log_fd
                #Если все предварительные процедуры выполнены успешно,
                #то запускаем процессы
                threads = proc.start_process_controller(test)
                #Заводим таймер на 5 сек.
                print("[DEBUG] Waiting for closing threads...")
                if not proc.CheckThreads(threads):
                    #Переносим отработавшие UA в завершенные
                    test.Status = "Failed"
                    test.CompliteSFUA()
                    print("[ERROR] Send SF",code,"failed")
                    break
                #Проверяем UA на статусы
                print("[DEBUG] Check process StatusCode...")
                if not proc.CheckUaStatus(test):
                    #Переносим отработавшие UA в завершенные
                    test.CompliteSFUA()
                    print("[ERROR] One of UAs failed")
                    test.Status = "Failed"
                    break
                #Переносим все активные UA в завершённые
                test.CompliteSFUA()
            else:
                #Если передана неизвесная команда, то выходим
                test.Status = "Failed"
                print("[ERROR] Unknown metod:",method,"in test procedure. Test aborting")
                break
    #Устанавливаем статус теста в завершён
    if test == False:
        print("[ERROR] Test procedure failed. Aborting")
        stop_test(tests,test_desc,test_users)
        exit(1)
    if test.Status != "Failed":
        test.Status = "Complite"
        print("[DEBUG] Test:",test.Name,"complite")

            
#Запускаем стоп тест
stop_test(tests,test_desc,test_users)

if timestamp_calc:
    for test in tests:
        for ua in test.CompliteUA:
            if ua.WriteStat:
                print()
                print("Statistics for", ua.Name, ":")
                stat_module.get_seq_statistics(ua.TimeStampFile)


#Производим расчёт результатов теста
print("[DEBUG] Test info:")
for test in tests:
    failed_test_flag = False
    if test.Status == "Failed":
        failed_test_flag = True
        print("     Test:",test.Name,"- failed.")
        continue
    elif test.Status == "Complite":
        for ua in test.CompliteUA:
            for process in ua.Process:
                if process.poll() != 0:
                    failed_test_flag = True
    else:
        print("     [ERROR] Unknown test status.")
        failed_test_flag = True
    if failed_test_flag:
        print("     Test:",test.Name,"- failed.") 
    else:
        print("     Test:",test.Name,"- success.")
if failed_test_flag:
    exit(1)
else:
    exit(0)
