#!/usr/local/bin/python3.5
import modules.test_parser as parser
import modules.cmd_builder as builder
import modules.process_contr as proc
import modules.fs_worker as fs
import modules.cocon_interface as ssh
import modules.test_class as test_class
import modules.show_call_flow as stat_module
import modules.diff_calc as diff_calc
import logging
import re
import signal
import json
import sys
import time
import threading
import argparse
import math
from collections import OrderedDict



def signal_handler(current_signal, frame):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    logger.info("Receive SIGINT signal. Start test aborting")
    try:
        if tests and test_desc and coconInt:
            if test_users and reg_lock:
                stop_test(tests,test_desc,test_users,coconInt,reg_lock)
            else:
                logger.info("Test no users in description or reg_lock flag is not set.")
            logger.debug("Start stop_test without reg_lock")
            stop_test(tests,test_desc,test_users,coconInt)
    except NameError:
        logger.warn("Required variables are missing!")
    #print(threading.current_thread())
    sys.exit(1)


#Добавляем трап на SIGINT
signal.signal(signal.SIGINT, signal_handler)

def createParser ():
    parser = argparse.ArgumentParser()
    parser.add_argument ('-t', '--test_config', type=argparse.FileType(),required=True)
    parser.add_argument ('-c', '--custom_config', type=argparse.FileType(),required=True)
    parser.add_argument ('-n', '--test_numbers', type=match_test_numbers,required=False)
    parser.add_argument ('--drop_uac', action='store_const', const=True)
    parser.add_argument ('--show_ua_info', action='store_const', const=True)
    parser.add_argument ('--show_sip_flow', action='store_const', const=True)
    parser.add_argument ('--force_quit', action='store_const', const=True)
    parser.add_argument ('-l', '--log_file', type=match_file_path,required=False)
    parser.add_argument ('-g', '--global_ccn_lock', type=argparse.FileType('w'),required=False)
    parser.add_argument ('--show_test_info', action='store_const', const=True)
    parser.add_argument ('--show_cocon_output', action='store_const', const=True)
    return parser

def get_test_info (test):
    print("TestName:        ",test.Name)
    print("TestStatus:      ",test.Status)
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
    for ua in test.UserAgent + test.BackGroundUA:
        if ua.Type == "User":
            if not int(ua.UserId) in use_id:
                use_id.append(int(ua.UserId))
                try:
                    ua.UserObject = users[str(ua.UserId)]
                except KeyError:
                    logger.error("User with id = %d not found { UA : %s }",int(ua.UserId),ua.Name)
                    return False
            else:
                logger.error("Duplicate UserId: %d { UA : %s }",int(ua.UserId),ua.Name)
                return False
    return test

def stop_test(tests,test_desc,test_users,coconInt,reg_lock=False):
    logger.debug("Stop CoCoN Thread...")
    if coconInt.coconQueue and coconInt.myThread:
        if coconInt.myThread.is_alive():
            #Чистим текущие задачи из очереди
            coconInt.flush_queue()
            #Засовываем команды на деконфигурацию в очередь
            if "PostCoconConf" in test_desc:
                logger.info("Deconfigure of ECSS-10 system...")
                #Переменные для настройки соединения с CoCoN
                ssh.cocon_configure(test_desc["PostCoconConf"],coconInt,test_var)
            #Отрубаем thread
            #На всякий случай убеждаемся, что ccn thread существует и живой
            coconInt.eventForStop.set()
    logger.debug("Drop all processes...")
    #Дропаем процессы
    for test in tests:
        if test.Status!="New":
            for ua in test.UserAgent + test.WaitBackGroundUA:
                for process in ua.Process:
                    if process.poll() == None:
                        process.kill()
    logger.debug("Drop all registration...")
    #Разрегистрируем юзеров
    if reg_lock and test_users:
        logger.info("Drop registration of users.")
        unreg_thread = threading.Thread(target=proc.ChangeUsersRegistration, args=(test_users,reg_lock,"unreg",))
        unreg_thread.start()
        #Даём завершиться thread'у разрегистрации
        unreg_thread.join()
    logger.info("Close log files...")
    if tests:
        for test in tests:
            for ua in test.CompliteUA:
                if ua.LogFd:
                    ua.LogFd.close()
    #Даём время на сворачивание thread
    time.sleep(0.2)
    return True

def match_test_numbers(test_numbers):
    match_result = re.search("^[0-9]{1,2}$|^([0-9]{1,2},)*[0-9]{1,2}$",test_numbers)
    if match_result:
        test_numbers = [int(i) for i in test_numbers.split(",")]
        return  test_numbers
    else:
        raise argparse.ArgumentTypeError("Arg 'n' does not match required format : num1,num2,num3")

def match_file_path(log_file):
    match_result =re.search("^([\w.-_]+\/)[\w.-_]+$",log_file)
    if match_result:
        return  log_file
    else:
        raise argparse.ArgumentTypeError("Log file path is incorrect")


    
#Парсим аргументы командной строки
arg_parser = createParser()
namespace = arg_parser.parse_args()
test_numbers = namespace.test_numbers
uac_drop_flag = namespace.drop_uac
force_quit = namespace.force_quit
show_sip_flow = namespace.show_sip_flow
show_ua_info = namespace.show_ua_info
show_test_info = namespace.show_test_info
show_cocon_output = namespace.show_cocon_output
global_ccn_lock = namespace.global_ccn_lock
#Забираем описание теста и общие настройки
jsonData = namespace.test_config.read()
customSettings = namespace.custom_config.read()
namespace.test_config.close()
namespace.custom_config.close()
log_file = namespace.log_file

#Декларируем lock объект для регистрации
reg_lock = threading.Lock()
#Декларируем массив для юзеров
test_users = {}
#декларируем массив для тестов
tests = []
#Декларируем словарь пользовательских переменных
test_var = {}

try:
    logging.basicConfig(filename=log_file,format = u'%(asctime)-8s %(levelname)-8s %(message)-8s', filemode='w', level = logging.INFO)
except FileNotFoundError:
    match_result =re.search("^([\w.-_]+\/)[\w.-_]+$",log_file)
    fs.create_log_dir(match_result.group(1))
    logging.basicConfig(filename=log_file,format = u'%(asctime)-8s %(levelname)-8s %(message)-8s', filemode='w', level = logging.INFO)
except:
    print("Can't create log dir")
    sys.exit(1)

logger = logging.getLogger("tester")

logger.info("Reading custom settings...")
try:
    custom_settings = json.loads(customSettings)
except (ValueError, KeyError, TypeError):
    logger.error("Wrong JSON format of test config. Detail: %s",sys.exc_info()[1])
    sys.exit(1)

custom_settings = parser.parse_sys_conf(custom_settings["SystemVars"][0])
if not custom_settings:
    sys.exit(1)



logger.info("Reading JSON script...")
try:
    #Загружаем json описание теста
    test_desc = json.loads(jsonData,object_pairs_hook=OrderedDict)
except (ValueError, KeyError, TypeError):
    logger.error("Wrong JSON format. Detail: %s",sys.exc_info()[1])
    sys.exit(1)
    

#Парсим юзеров
logger.info("Parsing users from json string...")
if "Users" in test_desc:    
    test_users = parser.parse_user_info(test_desc["Users"])
else:
    logger.warn("No user in test")
#Если есть ошибки при парсинге, то выходим
if test_users == False:
    sys.exit(1)

#Парсим тесты
logger.info("Parsing tests from json string...")
try:
   tests = parser.parse_test_info(test_desc["Tests"])
except(KeyError):
   logger.error("No Test in test config")
#Если есть ошибки при парсинге, то выходим
if not tests:
    sys.exit(1)

#Если запросили show_test_info, показавыем информацию по тесту и выходим
if show_test_info:
    for count,test in enumerate(tests):
        print("Test ID:   ",count)
        print("---| Test Name: ",test.Name)
        print("---| Test Desc: ",test.Description)
    sys.exit(0)

#Если был передан test_numbers, то накладываем маску на массив тестов

if test_numbers:
    try:
        tests=list(tests[i] for i in test_numbers)
    except IndexError:
        logger.error("Test index out of range")
        sys.exit(1)

#Парсим тестовые переменные в словарь
test_var = parser.parse_test_var(test_desc)
#Добавляем системные переменные в словарь
test_var.update(custom_settings)
#Создаём директорию для логов
log_path = str(test_var["%%LOG_PATH%%"]) + "/" + test_desc["TestName"]
logger.info("Creating log dir.")
if not fs.create_log_dir(log_path):
    #Если не удалось создать директорию, выходим
    sys.exit(1)
#Добавляем директорию с логами к тестам
for test in tests:
    test.LogPath = log_path
    
#Поднимаем thread для отправки CoCoN command
logger.info("Start CoCoN thread...")
coconInt = ssh.coconInterface(test_var, show_cocon_output, global_ccn_lock)
#Создаём event для остановки thread
coconInt.eventForStop = threading.Event()
#Поднимаем thread
coconInt.myThread = threading.Thread(target=ssh.ccn_command_handler, args=(coconInt,))
coconInt.myThread.start()
#Проверяем, что он жив.
time.sleep(0.2)
if not coconInt.myThread.is_alive():
    logger.error("Can't start CCN configure thread")
    sys.exit(1)

#Если есть настройки для CoCon выполняем их
if "PreCoconConf" in test_desc:
    logger.info("Configuration of ECSS-10 system...")
    #Переменные для настройки соединения с CoCoN
    if not ssh.cocon_configure(test_desc["PreCoconConf"],coconInt,test_var):
        coconInt.eventForStop.set()
        coconInt.myThread.join()
        sys.exit(1)
    #Даём кокону очнуться
    time.sleep(1)

if len(test_users) != 0:
    #Собираем команды для регистрации абонентов
    logger.info("Building of registration command for UA...")
    for key in test_users:
        command = builder.build_reg_command(test_users[key],test_var)
        if command:
            test_users[key].RegCommand = command
        else:
            coconInt.eventForStop.set()
            sys.exit(1)

    #Собираем команды для сброса регистрации абонентов
    logger.info("Building command for dropping of users registration...")
    for key in test_users:
        command = builder.build_reg_command(test_users[key],test_var,"unreg")
        if command:
            test_users[key].UnRegCommand = command
        else:
            coconInt.eventForStop.set()
            sys.exit(1)
    #Врубаем регистрацию для всех юзеров
    logger.info("Starting of registration...")
    #Декларируем массив для thread регистрации
    for user in test_users:
        reg_log_name = "REG_" + str(test_users[user].Number)
        log_file = fs.open_log_file(reg_log_name,log_path)
        #Если не удалось создать лог файл, то выходим
        if not log_file:
            coconInt.eventForStop.set()
            sys.exit(1)
        else:
            test_users[user].RegLogFile = log_file

    reg_thread = threading.Thread(target=proc.ChangeUsersRegistration, args=(test_users,reg_lock))
    reg_thread.start()
    reg_thread.join()
    if not proc.CheckUserRegStatus(test_users):
        stop_test(tests,test_desc,test_users,coconInt,reg_lock)
        sys.exit(1)   
#Запускаем процесс тестирования
for indx,test in enumerate(tests):
    if indx  > 0:
        if force_quit and tests[indx - 1].Status == "Failed":
            break
    logger.info("Start test: %s",test.Name)
    #Выставляем статус теста
    test.Status = "Starting"
    #Читаем индекс и команду из описания теста
    #Индекс нужен для того, чтобы знать на какой команде мы остановились, когда тест получит статус failed
    for index,item in enumerate(test.TestProcedure):
        #Если статус теста Failed заканчиваем процесс тестирования
        if not test or test.Status == "Failed":
            #На данном этапе мы поняли, что тест провалился. Нужно предусмотреть деконфигурацию ссв.
            #Пока сделаю следующее. Если тест свалился, то я ищу все оставшиеся CoconCommand
            #и отправляю их на ссв.
            
            #Если отвалилось соединение с cocon, то дальше можно не пытаться ничего слать.
            #Просто переходим к следующему тесту. 
            if not coconInt.ConnectionStatus:
                logger.info("Connection Status: %s",coconInt.ConnectionStatus)
                break
            if test:
                logger.info("Trying send to CCN all commands from test: %s",test.Name)
                #Берём срез массива от индекса, где у нас всё упало и до конца
                for item in test.TestProcedure[index:]:
                    for method in item:
                        #Если метод равен CoconCommand, то отправляем команды в CCN handler
                        if method == "CoconCommand":
                            #Если не удалось отправить команду, выходим
                            if not ssh.cocon_configure(item[method],coconInt,test_var):
                                break
                            else:
                                #Если метод не CoconCommand, ищём дальше
                                continue
                        else:
                            #Если в item нет method CoconCommand, ищём дальше
                            continue
                #После перебора всего теста, выходим.
                break
            else:
                #Если объект теста  равен false, то просто идём к следующему тесту
                logger.warn("Test object eq false.")
                break

        for method in item:
            if method == "CoconCommand":
                logger.info("Send commands to CoCon...")
                #Переменные для настройки соединения с CoCoN
                if not ssh.cocon_configure(item[method],coconInt,test_var):  
                    #Выставляем статус теста
                    test.Status = "Failed"
                    break
                else:
                    time.sleep(1)

            elif method == "Print":
                message = str(item[method])
                logging.info("\033[32m[TEST_INFO] %s \033[1;m",message)

            elif method == "Stop":
                sys.stdin.flush()
                input("\033[1;31m[TEST_INFO] Test stopped. Please press any key to continue...\033[1;m")

            elif method == "ServiceFeature":
                #Список threads для SF
                sf_threads=[]
                sf_use_uid = []
                logger.info("SendServiceFeature command activated.")
                #Забираем фича-код и юзера с которого его выполнить
                #О наличии данных параметров заботится парсер тестов
                for sf in item[method]:
                    code = sf['code']
                    user_id = str(sf['userId'])
                    code = builder.replace_key_value(code, test_var)
                    if not code:
                        test.Status = "Failed"
                        break
                    if user_id in sf_use_uid:
                        logger.error("Duplicated UserId in ServiceFeature item: { UA : %d }",user_id)
                        test.Status = "Failed"
                        break
                    else:
                        sf_use_uid.append(user_id)

                    try:
                        user = test_users[str(user_id)]
                    except:
                        logger.error("Can't get User Object with. ID = %d not found.",user_id)
                        #Выставляем статус теста
                        test.Status = "Failed"
                        break
                
                    logger.info("Send ServiceFeature from User %s code = %s",user.Number,code)
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

                if test.Status == "Failed":
                    break
                #Запускаем активацию фича-кода через процесс контроллер
                sf_thread = proc.start_process_controller(test)

                #Проверяем, что вернувшиеся треды закрыты:
                logger.info("Waiting for closing threads...")
                if not proc.CheckThreads(sf_thread):
                    test.ThreadEvent.clear()
                    time.sleep(1)
                    #Переносим отработавшие UA в завершенные
                    test.Status = "Failed"
                    test.ReplaceUaToComplite()
                    logger.info("Sleep on 32s")
                    time.sleep(32)
                    break
                #Проверяем UA на статусы
                logger.info("Check process StatusCode...")
                if not proc.CheckUaStatus(test.UserAgent):
                    #Переносим отработавшие UA в завершенные
                    test.ReplaceUaToComplite()
                    logging.error("Can't send Feature code %s",code)
                    test.Status = "Failed"
                    logger.info("Sleep on 32s")
                    time.sleep(32)
                    break
                else:
                    test.ReplaceUaToComplite()

            elif method == "Sleep":
                logger.info("Sleep command activated.")
                try:
                    sleep_time = float(item[method])
                except:
                    logger.error("Bag sleep arg. Exit.")
                    coconInt.eventForStop.set()
                    sys.exit(1)
                logging.info("\033[32m[TEST_INFO] Sleep %.1f seconds\033[1;m",sleep_time)
                time.sleep(sleep_time)

            elif method == "StartUA":
                logger.info("StartUA command activate.")
                #Парсим Юзер агентов 
                logger.info("Parsing UA from test.")
                test = parser.parse_user_agent(test,item[method])
                if not test:
                    #Если неправильное описание юзер агентов, то выходим
                    break
                #Линкуем UA с объектами юзеров.
                logger.info("Linking UA object with User object...")
                test = link_user_to_test(test, test_users)
                #Если есть ошибки при линковке, то выходим
                if not test:
                    break
                #Собираем команды для UA.
                logger.info("Building of SIPp commands for UA...")
                test = builder.build_sipp_command(test,test_var,uac_drop_flag, show_sip_flow)
                #Если есть ошибки при сборке, то выходим
                if not test:
                    break
                #Линкуем лог файлы и UA
                logger.info("Linking of LogFd with UA object...")
                for ua in test.UserAgent + test.BackGroundUA:
                    log_fd = fs.open_log_file(ua.Name,log_path)
                    if not log_fd:
                        break
                    else:
                        ua.LogFd = log_fd
                #Если все предварительные процедуры выполнены успешно,
                #то запускаем процессы
                threads = proc.start_process_controller(test)
                logger.info("Waiting for closing threads...")
                if not proc.CheckThreads(threads):
                    #Переносим отработавшие UA в завершенные
                    #Останавливаем все thread
                    test.ThreadEvent.clear()
                    #Даём thread завершиться
                    time.sleep(1)
                    test.Status = "Failed"
                    test.ReplaceUaToComplite()
                    logger.info("Sleep on 32s")
                    time.sleep(32)
                    break
                #Проверяем UA на статусы
                logger.info("Check process StatusCode...")
                if not proc.CheckUaStatus(test.UserAgent):
                    #Переносим отработавшие UA в завершенные
                    test.ReplaceUaToComplite()
                    logger.error("One of UAs return bad exit code")
                    test.Status = "Failed"
                    logger.info("Sleep on 32s")
                    time.sleep(32)
                    break
                #Переносим все активные UA в завершённые
                test.ReplaceUaToComplite()
            elif method == "CheckDifference":
                logger.info("CheckDifference command activated.")
                test_diff = diff_calc.diff_timestamp(test)
                if test_diff.Status == "Failed":
                    test.Status = "Failed"
                    break
                for diff_item in item[method]:
                    msg_info = {}
                    req_diff = diff_item["Difference"]
                    diff_mode = diff_item["Mode"]
                    msg_info["msg_type"] = diff_item["Msg"][0]["MsgType"].lower()
                    if diff_item["Msg"][0]["Code"] == "None":
                        msg_info["resp_code"] = None
                    else:
                        msg_info["resp_code"] = diff_item["Msg"][0]["Code"]
                    msg_info["method"] = diff_item["Msg"][0]["Method"].upper()
                    chk_ua = diff_item["UA"].split(",")
                    test_diff.compare_msg_diff(req_diff,diff_mode,*chk_ua,**msg_info)
                    if test_diff.Status == "Failed":
                        test.Status = "Failed"
                        break

            elif method == "CheckRetransmission":
                logger.info("CheckRetransmission command activated.")
                test_diff = diff_calc.diff_timestamp(test)
                if test_diff.Status == "Failed":
                    test.Status = "Failed"
                    break
                for diff_item in item[method]:
                    msg_info = {}
                    timer_name = diff_item["Timer"]
                    msg_info["msg_type"] = diff_item["Msg"][0]["MsgType"].lower()
                    if diff_item["Msg"][0]["Code"] == "None":
                        msg_info["resp_code"] = None
                    else:
                        msg_info["resp_code"] = diff_item["Msg"][0]["Code"]
                    msg_info["method"] = diff_item["Msg"][0]["Method"].upper()
                    chk_ua = diff_item["UA"].split(",")
                    test_diff.compare_timer_seq(timer_name,*chk_ua,**msg_info)
                    if test_diff.Status == "Failed":
                        test.Status = "Failed"
                        break
            else:
                #Если передана неизвесная команда, то выходим
                test.Status = "Failed"
                logger.error("Unknown metod: %s in test procedure. Test aborting.",method)
                break
    #Устанавливаем статус теста в завершён
    if test == False:
        logger.error("Test procedure failed. Aborting...")
        stop_test(tests,test_desc,test_users,coconInt,reg_lock)
        sys.exit(1)

    if len(test.WaitBackGroundUA) > 0:
        logger.info("Waiting for closing threads which started in background mode...")
        if not proc.CheckThreads(test.BackGroundThreads):
            test.ThreadEvent.clear()
            #Даём thread завершиться
            time.sleep(1)
            #Переносим отработавшие UA в завершенные
            test.Status = "Failed"
            logger.info("Sleep on 32s")
            test.CompliteBgUA()
            time.sleep(32)
        elif not proc.CheckUaStatus(test.WaitBackGroundUA):
            #Переносим отработавшие UA в завершенные
            test.CompliteBgUA()
            logger.error("One of UAs return bad exit code")
            test.Status = "Failed"
            logger.info("Sleep on 32s")
            time.sleep(32)
        else:
            test.CompliteBgUA()

    if test.Status != "Failed":
        test.Status = "Complite"

        logger.info("Test: %s complite", test.Name)
    else:
        logger.error("Test: %s failed.",test.Name)

            
#Запускаем стоп тест
stop_test(tests,test_desc,test_users,coconInt,reg_lock)

if show_sip_flow:
    for test in tests:
        for ua in test.CompliteUA:
            if ua.WriteStat:
                print()
                logger.info("SIP flow for %s:",ua.Name)
                stat_module.get_seq_statistics(ua.TimeStampFile)


#Производим расчёт результатов теста
logger.info("Test info:")
failed_test_flag = False

#Если статус теста Failed, то поднимаем flag.
for index,test in enumerate(tests):
    #Если передавали параметр -n 1,3,4, то используем данные индексы.
    if test_numbers:
        index = test_numbers[index]

    if test.Status == "Failed":
        failed_test_flag = True
        logger.info(" ---| Test %d: %s - fail.",index,test.Name)

    elif test.Status == "Complite":
        logger.info(" ---| Test %d: %s - succ.",index,test.Name)
    elif test.Status == "New":
        logger.info(" ---| Test %d: %s - not running.",index,test.Name)

        
    else:
        logger.error("Unknown test status. %s",test.Name)
        failed_test_flag = True
        #Выводим дамп по этому тесту
        get_test_info(test)
if show_ua_info:
    for test in tests:
        if test:
            get_test_info(test)
        else:
            logger.error("Test obj corrupted. Get test info failed!")

if failed_test_flag:
    sys.exit(1)
else:
    sys.exit(0)
