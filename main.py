#!/usr/local/bin/python3.6
import modules.test_parser as parser
import modules.cmd_builder as builder
import modules.test_processor as processor
import modules.process_contr as proc
import modules.fs_worker as fs
import modules.cocon_interface as ssh
import modules.test_class as test_class
import modules.show_call_flow as sip_call_flow
import modules.diff_calc as diff_calc
import logging
import re
import os
import signal
import json
import jsonschema
from jsonschema import Draft4Validator
import sys
import time
import threading
import argparse
import math
from collections import OrderedDict

def signal_handler(current_signal, frame):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    logger.info("Receive SIGINT signal. Start test aborting")
    if not 'test_processor' in globals():
        cp_test_processor = False
    else:
        cp_test_processor = test_processor
    if not 'test_desc' in globals():
        cp_test_desc = False
    else:
        cp_test_desc = test_desc
    if not 'coconInt' in globals():
        cp_coconInt = False
    else:
        cp_coconInt = coconInt
    stop_test(cp_test_processor,cp_test_desc,cp_coconInt)
    sys.exit(1)

def stop_test(test_processor,test_desc,coconInt):
    logger.debug("Stop test thread...")
    if test_processor:
        test_processor.StopTestProcessor()
    if coconInt:
        if coconInt.coconQueue and coconInt.myThread:
            if coconInt.myThread.is_alive():
                #Чистим текущие задачи из очереди
                coconInt.flush_queue()
                #Засовываем команды на деконфигурацию в очередь
                if test_desc:
                    if "PostConf" in test_desc:
                        logger.info("Start system reconfiguration...")
                        #Переменные для настройки соединения
                        ssh.cocon_configure(test_desc["PostConf"],coconInt,test_var)
                #Отрубаем thread
                #На всякий случай убеждаемся, что ccn thread существует и живой
                coconInt.eventForStop.set()

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
        print("     UaCommand:")
        for command in ua.Commands:
            print("      ",command)
        print("")

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

#Функция для вывода ошибок JSON файла       
def output_validate_errors(errors):
    for e in errors:
        #Если обязательное свойство отсутствует
        if "is a required property" in str(e.message):
            try:        
                logger.error("In item [%s] of section [%s]: value %s" % (e.path.pop(), e.path.popleft(), e.message))
            except (IndexError, TypeError):
                if not "CheckRetransmission" and "CheckDifference" in str(e.message):
                    logger.error("Missing property: %s" % e.message)
                elif "Code" in str(e.message):
                    logger.error("Missing property in CheckRetransmission or CheckDifference: %s" % (e.message))
                elif not "CheckDifference":
                    logger.error(e.message)
                #else:
                    #logger.error(e.message)    
        #Если задаваемое свойство не соответствует шаблону       
        elif "does not match any of the regexes" in str(e.message):
            logger.error("In item %s of section [%s]: value %s" % (re.findall(r"\d",str(e.path)), e.path.popleft(), e.message)) 
        #Если ошибка присутствует во вложенных секциях 
        elif "is not valid under any of the given schemas" in str(e.message):
            output_validate_errors(sorted(e.context, key=lambda e: e.path))
        #Действия во всех остальных случаях
        else:
            try:
                logger.error("In item %s of section [%s]: %s value %s" % (re.findall(r"\d",str(e.path)), e.path.popleft(), e.path.pop(), e.message))
            except (IndexError, TypeError):
                if "Sleep" in str(e.schema_path):
                    logger.error("In section Sleep: value %s" % (e.message))
                if "ServiceFeature" in str(e.schema_path):
                    logger.error("In section ServiceFeature: value %s" % (e.message))
                if "Code" in str(e.schema_path):
                    logger.error("In section CheckRetransmission or CheckDifference value Code: %s" % (e.message))
                else:
                   logger.error(e.message)

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
#Создаем инстанс парсера
parse = parser.Parser()

try:
    logging.basicConfig(filename=log_file,format = u'%(asctime)-8s %(levelname)-8s [%(module)s -> %(funcName)s:%(lineno)d] %(message)-8s', filemode='w', level = logging.DEBUG)
except FileNotFoundError:
    match_result = re.search("^([\w.-_]+\/)[\w.-_]+$",log_file)
    fs.create_log_dir(match_result.group(1))
    logging.basicConfig(filename=log_file,format = u'%(asctime)-8s %(levelname)-8s [%(module)s -> %(funcName)s:%(lineno)d] %(message)-8s', filemode='w', level = logging.DEBUG)
except:
    logger.error("Can't create log dir")
    sys.exit(1)

logger = logging.getLogger("tester")

logger.info("Reading custom settings...")
try:
    custom_settings = json.loads(customSettings)
except (ValueError, KeyError, TypeError):
    logger.error("Wrong JSON format of test config. Detail: %s",sys.exc_info()[1])
    sys.exit(1)

try:
    custom_settings = parse.parse_sys_conf(custom_settings["SystemVars"][0])
    if not custom_settings:
        sys.exit(1)
except KeyError:
    logger.error("Custom config without \"SystemVars\"")
    sys.exit(1)

logger.info("Reading JSON script...")
try:
    #Загружаем json описание теста
    test_desc = json.loads(jsonData,object_pairs_hook=OrderedDict)
except (ValueError, KeyError, TypeError):
    logger.error("Wrong JSON format. Detail:", sys.exc_info()[1])
    sys.exit(1)

logger.info("Reading JSON schema...")
try:
    schema_file = open(os.path.dirname(__file__)+"/schema/tests.schema","r",encoding="utf-8")
except FileNotFoundError:
    logger.error("JSON schema file not found")
    sys.exit(1)
try:
    schemaData = json.loads(schema_file.read())
except json.decoder.JSONDecodeError: 
    logger.error("Reading JSON schema error")
    schema_file.close
    sys.exit(1)
else:
    schema_file.close

#Проверка тестового сценария на соответствие схеме
logger.info("Validating JSON script...")
validation_errors = sorted(Draft4Validator(schemaData).iter_errors(test_desc), key=lambda e: e.path)
if validation_errors:
    output_validate_errors(validation_errors)
    sys.exit(1)
else:
    logger.info("Validation completed successfully")

#Парсинг данных о пользователях
logger.info("Parsing users from json string...")
if "Users" in test_desc:  
    test_users = parse.parse_user_info(test_desc["Users"])
else:
    logger.warn("No user in test")
#Если есть ошибки при парсинге, то выходим
if not test_users:
    sys.exit(1)

#Парсинг данных о тестах
logger.info("Parsing tests from json string...")
tests = parse.parse_test_info(test_desc["Tests"])
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
test_var = parse.parse_test_var(test_desc)
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
    
#Поднимаем thread для отправки SSH command
logger.info("Start configuration thread...")
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

#Если требуется предварительное конфигурирование
if "PreConf" in test_desc:
    logger.info("Start system configuration...")
    #Переменные для настройки соединения
    if not ssh.cocon_configure(test_desc["PreConf"],coconInt,test_var):
        coconInt.eventForStop.set()
        coconInt.myThread.join()
        sys.exit(1)
    time.sleep(1)

test_pr_config = {}
test_pr_config["Tests"] = tests
test_pr_config["ForceQuitFlag"] = force_quit
test_pr_config["Users"] = test_users
test_pr_config["Trunks"] = []
test_pr_config["CoconInt"] = coconInt
test_pr_config["TestVar"] = test_var
test_pr_config["ShowSipFlowFlag"] = show_sip_flow
test_pr_config["UacDropFlag"] = uac_drop_flag
test_pr_config["LogPath"] = log_path

test_processor = processor.TestProcessor(**test_pr_config)
test_processor.StartTestProcessor()

#Запускаем стоп тест
stop_test(test_processor,test_desc,coconInt)

if show_sip_flow:
    for test in tests:
        logger.info("Call flows for TEST %d:",test.TestId)
        test_diff = diff_calc.diff_timestamp(test)
        call_flow = sip_call_flow.sip_flow(test_diff)
        call_flow.print_flow()


#Производим расчёт результатов теста
logger.info("Test info:")
#Если статус теста Failed, то поднимаем flag.
for index,test in enumerate(tests):
    #Если передавали параметр -n 1,3,4, то используем данные индексы.
    if test_numbers:
        index = test_numbers[index]
    if test.Status == "Failed":
        logger.info(" ---| Test %d: %s - fail.",index,test.Name)
    elif test.Status == "Complite":
        logger.info(" ---| Test %d: %s - succ.",index,test.Name)
    elif test.Status == "New":
        logger.info(" ---| Test %d: %s - not running.",index,test.Name)
    else:
        logger.error("Unknown test status. %s",test.Name)
        #Выводим дамп по этому тесту
        get_test_info(test)
if show_ua_info:
    for test in tests:
        if test:
            get_test_info(test)
        else:
            logger.error("Test obj corrupted. Get test info failed!")


if test_processor.failed_flag:
    sys.exit(1)
else:
    sys.exit(0)
