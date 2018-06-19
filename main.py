#!/usr/bin/env python3
import sys
import datetime
import modules.test_parser as parser
import modules.test_processor as processor
import modules.fs_worker as fs
import modules.ssh_interface as ssh
import modules.show_call_flow as sip_call_flow
import modules.diff_calc as diff_calc
import modules.cmd_builder as builder
import logging
import re
import os
import signal
import json
import threading
import argparse
from collections import OrderedDict

if sys.version_info < (3, 5):
    print("Error. Use python 3.5 or greater")
    sys.exit(1)


def signal_handler(current_signal, frame):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    logger.info("Received signal %s. Start test aborting", current_signal)
    if not 'test_processor' in globals():
        cp_test_processor = False
    else:
        cp_test_processor = test_processor
    if 'test_desc' not in globals():
        cp_test_desc = False
    else:
        cp_test_desc = test_desc
    if 'sshInt' not in globals():
        cp_ssh_int = False
    else:
        cp_ssh_int = sshInt
    stop_test(cp_test_processor, cp_test_desc, cp_ssh_int)
    sys.exit(1)


def stop_test(test_processor, test_desc, sshInt):
    logger.debug("Stop test thread...")
    if test_processor:
        test_processor.StopTestProcessor()
    if sshInt:
        if test_desc and test_desc.get("PostConf", False):
            if test_desc["PostConf"][0]:
                logger.info("Start system reconfiguration...")
                if cmd_builder.replace_var_for_list(test_desc["PostConf"], test_var):
                    sshInt.push_cmd_list_to_ssh(list(test_desc["PostConf"]))

# Добавляем трап на SIGINT
signal.signal(signal.SIGINT, signal_handler)


def create_parser():
    new_parser = argparse.ArgumentParser()
    new_parser.add_argument('-t', '--test_config', type=argparse.FileType(), required=True)
    new_parser.add_argument('-c', '--custom_config', type=argparse.FileType(), required=True)
    new_parser.add_argument('-n', '--test_numbers', type=match_test_numbers, required=False)
    new_parser.add_argument('--drop_uac', action='store_const', const=True)
    new_parser.add_argument('--show_ua_info', action='store_const', const=True)
    new_parser.add_argument('--show_sip_flow', action='store_const', const=True)
    new_parser.add_argument('--force_quit', action='store_const', const=True)
    new_parser.add_argument('-l', '--log_path', type=match_file_path, required=False)
    new_parser.add_argument('-g', '--global_ccn_lock', type=argparse.FileType('w'), required=False)
    new_parser.add_argument('--show_test_info', action='store_const', const=True)
    new_parser.add_argument('--show_cocon_output', action='store_const', const=True)
    return new_parser


def get_test_info(test):
    print("TestName:        ", test.Name)
    print("TestStatus:      ", test.Status)
    print("TestDesc:        ", test.Description)
    print("TestUA:          ", test.UserAgent)
    print("TestCompleteUA   ", test.CompliteUA)
    print("")
    for ua in test.CompliteUA:
        print("     UaName:         ", ua.Name)
        print("     UaStatus:       ", ua.Status)
        print("     UaStatusCode:   ", ua.StatusCode)
        print("     UaType:         ", ua.Type)
        if ua.UserObject:
            print("     UaUserId:       ", ua.UserObject.UserId)
            print("     UaUserObj:      ", ua.UserObject)
            print("     UaUserPort:     ", ua.UserObject.Port)
            print("     UaUserRtpPort:  ", ua.UserObject.RtpPort)
        if ua.TrunkObject:
            print("     UaTrunkId:      ", ua.TrunkObject.TrunkId)
            print("     UaTrunkObj:     ", ua.TrunkObject)
            print("     UaTrunkPort:    ", ua.TrunkObject.Port)
            print("     UaTrunkRtpPort: ", ua.TrunkObject.RtpPort)
        print("     UaCommand:")
        for command in ua.Commands:
            print("      ", command)
        print("")


def match_test_numbers(test_numbers):
    match_result = re.search("^[0-9]{1,2}$|^([0-9]{1,2},)*[0-9]{1,2}$",test_numbers)
    if match_result:
        test_numbers = [int(i) for i in test_numbers.split(",")]
        return test_numbers
    else:
        raise argparse.ArgumentTypeError("Arg 'n' does not match required format : num1,num2,num3")


def match_file_path(log_file):
    match_result = re.search("^([\w.-_]+\/)[\w.-_]+$", log_file)
    if match_result:
        return log_file
    else:
        raise argparse.ArgumentTypeError("Log file path is incorrect")

# Парсим аргументы командной строки
arg_parser = create_parser()
namespace = arg_parser.parse_args()
test_numbers = namespace.test_numbers
uac_drop_flag = namespace.drop_uac
force_quit = namespace.force_quit
show_sip_flow = namespace.show_sip_flow
show_ua_info = namespace.show_ua_info
show_test_info = namespace.show_test_info
show_cocon_output = namespace.show_cocon_output
global_ccn_lock = namespace.global_ccn_lock

# Забираем описание теста и общие настройки
jsonData = namespace.test_config.read()
customSettings = namespace.custom_config.read()
namespace.test_config.close()
namespace.custom_config.close()
log_path = namespace.log_path

# Декларируем lock объект для регистрации
reg_lock = threading.Lock()
# Декларируем массив для юзеров
test_users = {}
# Декларируем массив для транков
test_trunks = {}
# декларируем массив для тестов
tests = []
# Декларируем словарь пользовательских переменных
test_var = {}
# Создаем объект парсера
parse = parser.Parser()
# Создаем объект валидатора
validator = parser.Validator()
# Создаем объект fs_worker
fs_work = fs.fs_working()
# Создаём билдер комманд
cmd_builder = builder.CmdBuild()

py_sipp_path = os.path.dirname(__file__)

log_file = False
if log_path:
    now = datetime.datetime.now()
    log_path = "/".join((log_path, now.strftime("%Y_%m_%d_%H_%M_%S")))
    if not fs_work.create_log_dir(log_path):
        # Если не удалось создать директорию, выходим
        sys.exit(1)
    log_file = log_path + "/test.log"
    logging.basicConfig(filename=log_file,
                        format=u'%(asctime)-8s %(levelname)-8s [%(module)s:%(lineno)d] %(message)-8s',
                        filemode='w', level=logging.INFO)
else:
    log_path = False
    logging.basicConfig(format=u'%(asctime)-8s %(levelname)-8s [%(module)s:%(lineno)d] %(message)-8s',
                        level=logging.INFO)

logger = logging.getLogger("tester")
logger.info("Reading custom settings...")

try:
    custom_settings = json.loads(customSettings)
except (ValueError, KeyError, TypeError):
    logger.error("Wrong JSON format of test config. Detail: %s",sys.exc_info()[1])
    sys.exit(1)

try:
    custom_settings = parse.parse_sys_conf(custom_settings["SystemVars"][0], py_sipp_path)
    if not custom_settings:
        sys.exit(1)
except KeyError:
    logger.error("Custom config without \"SystemVars\"")
    sys.exit(1)

logger.info("Reading JSON script...")
try:
    # Загружаем json описание теста
    test_desc = json.loads(jsonData, object_pairs_hook=OrderedDict)
except (ValueError, KeyError, TypeError):
    logger.error("Wrong JSON format. Detail: %s", sys.exc_info()[1])
    sys.exit(1)

logger.info("Reading JSON schema...")
# Выгружаем содержимое схем в словарь
validator.schemas_dict_forming(py_sipp_path)

# Валидация тестового сценария
logger.info("Validating JSON script...")
valid = validator.validation_tests(test_desc)
if valid:
    logger.info("Validation completed successfully")

# Парсинг данных о пользователях
logger.info("Parse users from json...")
try:
    test_users = parse.parse_user_info(test_desc["Users"])
    if not test_users:
        sys.exit(1)
except KeyError:
    pass

# Парсинг данных о транках
logger.info("Parse trunks from json...")
try:
    test_trunks = parse.parse_trunk_info(test_desc["Trunks"])
    if not test_trunks:
        sys.exit(1)
except KeyError:
    pass

# Парсинг данных о тестах
logger.info("Parse tests from json string...")
tests = parse.parse_test_info(test_desc["Tests"])

# Если запросили show_test_info, показавыем информацию по тесту и выходим
if show_test_info:
    for count, test in enumerate(tests):
        if test_numbers and not count in test_numbers:
            continue
        print("Test ID:   ", count)
        print("---| Test Name: ", test.Name)
        print("---| Test Desc: ", test.Description)
    sys.exit(0)

# Если был передан test_numbers, то накладываем маску на массив тестов
if test_numbers:
    try:
        tests=list(tests[i] for i in test_numbers)
    except IndexError:
        logger.error("Test index out of range")
        sys.exit(1)

# Парсим тестовые переменные в словарь
test_var = parse.parse_test_var(test_desc)
# Добавляем системные переменные в словарь
test_var.update(custom_settings)
# Создаём директорию для логов
if not log_path:
    now = datetime.datetime.now()
    log_path = str(test_var["%%LOG_PATH%%"]) + "/" + test_desc["TestName"]
    log_path += "/" + now.strftime("%Y_%m_%d_%H_%M_%S")
    logger.info("Creating log dir.")
    if not fs_work.create_log_dir(log_path):
        # Если не удалось создать директорию, выходим
        sys.exit(1)
# Добавляем директорию с логами к тестам
for test in tests:
    test.LogPath = log_path

# Поднимаем thread для отправки SSH command
logger.info("Start configuration thread...")
sshInt = ssh.SSHInterface(custom_settings, gl_lock=global_ccn_lock, show_output=show_cocon_output)
# Создаём event для остановки thread
sshInt.eventForStop = threading.Event()

# Если требуется предварительное конфигурирование
if test_desc.get("PreConf", False):
    logger.info("Start system configuration...")
    # Переменные для настройки соединения
    if test_desc["PreConf"][0]:
        if not cmd_builder.replace_var_for_list(test_desc["PreConf"], test_var):
            sys.exit(1)
        if not sshInt.push_cmd_list_to_ssh(list(test_desc["PreConf"])):
            sys.exit(1)

test_pr_config = dict()
test_pr_config["Tests"] = tests
test_pr_config["ForceQuitFlag"] = force_quit
test_pr_config["Users"] = test_users
test_pr_config["Trunks"] = test_trunks
test_pr_config["SSHInt"] = sshInt
test_pr_config["TestVar"] = test_var
test_pr_config["ShowSipFlowFlag"] = show_sip_flow
test_pr_config["UacDropFlag"] = uac_drop_flag
test_pr_config["LogPath"] = log_path
test_pr_config["CmdBuilder"] = cmd_builder

test_processor = processor.TestProcessor(**test_pr_config)
test_processor.StartTestProcessor()

# Запускаем стоп тест
stop_test(test_processor, test_desc, sshInt)

if show_sip_flow:
    for test in tests:
        logger.info("Call flows for TEST %d:",test.TestId)
        test_diff = diff_calc.DifferCalc(test)
        call_flow = sip_call_flow.sip_flow(test_diff)
        call_flow.print_flow()


# Производим расчёт результатов теста
logger.info("Test info:")
# Если статус теста Failed, то поднимаем flag.
for index, test in enumerate(tests):
    # Если передавали параметр -n 1,3,4, то используем данные индексы.
    if test_numbers:
        index = test_numbers[index]
    if test.Status == "Failed":
        logger.info(" ---| Test %d: %s - fail.", index, test.Name)
    elif test.Status == "Complite":
        logger.info(" ---| Test %d: %s - succ.", index, test.Name)
    elif test.Status == "New":
        logger.info(" ---| Test %d: %s - not running.", index, test.Name)
    else:
        logger.error("Unknown test status. %s", test.Name)
        # Выводим дамп по этому тесту
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
