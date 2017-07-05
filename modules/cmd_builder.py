import re
import time
from datetime import datetime, date
import logging
logger = logging.getLogger("tester")


def build_reg_command (user,test_var,mode="reg"):
    #Сборка команды для регистрации
    command=""
    command+="%%SIPP_PATH%%" + " "
    if user.Script == None:
        command+="-sf " + "%%REG_XML%%" + " "
    else:
        command+="-sf "  + "%%SRC_PATH%%" + "/" + user.Script + " "
    command+="%%EXTER_IP%%" + ":" + "%%EXTER_PORT%%" + " "
    command+="-i " + "%%IP%%" + " "
    command+=" -set DOMAIN " + str(user.SipDomain)
    if user.UserIP != None:
        command+=" -set USER_IP " + str(user.UserIP)
    if user.FakePort != None:
        command+=" -set PORT " + str(user.FakePort)
    else:
        command+=" -set PORT " + str(user.Port)
    if mode == "reg":
        command+=" -set EXPIRES " + str(user.Expires)
    elif mode == "unreg":
        command+=" -set EXPIRES " + "0"
    command+=" -set USER_Q " + str(user.QParam)
    command+=" -set NUMBER " + str(user.Number)
    command+=" -s " + str(user.Login) + " -ap " + str(user.Password)
    command+=" -m 1"
    command+=" -nostdin"
    command+=" -timeout_error"
    if user.BindPort != None:
        command+=" -p " + user.BindPort
    if user.SipTransport == "TCP":
        command+=" -t tn -max_socket 25"
    command = replace_key_value(command, test_var)
    if command:
        return command
    else:
        return False

def build_service_feature_command (user, code, test_var):
    #Сборка команды для регистрации
    command=""
    command+="%%SIPP_PATH%%" + " "
    command+="-sf " + "%%SF_XML%%" + " "
    command+="%%EXTER_IP%%" + ":" + "%%EXTER_PORT%%" + " "
    command+="-i " + "%%IP%%" + " "
    command+=" -p " + str(user.Port)
    command+=" -set CDPN " + str(code)
    command+=" -set CDPNDOM " + str(user.SipDomain)
    command+=" -set CGPNDOM " + str(user.SipDomain)
    command+=" -s " + str(user.Login)
    command+=" -ap " + str(user.Password)
    command+=" -m 1 "
    command+=" -timeout 20s -recv_timeout 20s"
    if user.SipTransport == "TCP":
        command+=" -t tn -max_socket 25"
    command = replace_key_value(command,test_var)
    return command


def build_sipp_command(test,test_var,uac_drop_flag=False, show_sip_flow=False):
    for ua in test.UserAgent + test.BackGroundUA:
         #Пытаемся достать параметры команды
         for command in ua.RawJsonCommands:
            try:
                sipp_sf = command["SourceFile"]
            except KeyError:
                logger.error("Wrong Command description. Detail: UA has no attribute: %s { Test: %s, UA: %s }",sys.exc_info()[1],test.Name,ua.Name)
                return False
            try:
                sipp_options = command["Options"]
            except KeyError:
                logger.error("Wrong Command description. Detail: UA has no attribute: %s { Test: %s, UA: %s }",sys.exc_info()[1],test.Name,ua.Name)
                return False
            try:
                sipp_type = command["SippType"]
            except KeyError:
                logger.error("Wrong Command description. Detail: UA has no attribute: %s { Test: %s, UA: %s }",sys.exc_info()[1],test.Name,ua.Name)
                return False
            #Если был передан флаг о сбросе UAC команд, то просто не собираем их.
            if uac_drop_flag:
                if sipp_type == "uac":
                    continue
            try:
                sipp_auth = command["NeedAuth"]
            except KeyError:
                sipp_auth = False
            try:
                timeout = command["Timeout"]
            except KeyError:
                timeout = "60s"

            #В некоторых случаях полезно, чтобы UA завершился по timeout и при этом вернул 0 ex code
            #Для таких случаев на уровне команды передаем параметр NoTimeOutError
            try:
                no_timeout_err = command["NoTimeOutError"]
            except KeyError:
                no_timeout_err = False

            command=""                
            command += "%%SIPP_PATH%%"
            command += " -sf " + "%%SRC_PATH%%" + "/" + sipp_sf + " "
            command += "%%EXTER_IP%%" + ":" + "%%EXTER_PORT%%"
            command += " -i " + "%%IP%%" + " "
            command += sipp_options
            if ua.Type == "User":
                command += " -p " + ua.UserObject.Port
                command += " -s " + ua.UserObject.Login
                if ua.UserObject.SipTransport == "TCP":
                    command+=" -t tn -max_socket 25"
                if ua.UserObject.RtpPort:
                    command += " -mp " + ua.UserObject.RtpPort
            else:
                command += " -p " + ua.Port
            command+=" -nostdin"

            if sipp_auth and ua.Type=="User":
                command += " -ap " + ua.UserObject.Password

            if sipp_type == "uac":
                command += " -timeout " + str(timeout)
                command += " -recv_timeout " + str(timeout)
                if ua.Type=="User":
                    command += " -set CGPNDOM " + ua.UserObject.SipDomain
            else:
                command += " -timeout " + str(timeout)

            #Выставляем ленивый режим детектирования перепосылок.
            command += " -rtcheck loose"
            
            #Если был передан флаг для записи timestamp, то добавляем соотвествующие ключи
            if ua.WriteStat:
                timestamp_file = test.LogPath + "/" + "TIMESTAMP_" + str(ua.Name) + "_TEST" + str(test.TestId)
                ua.TimeStampFile = timestamp_file
                command += " -shortmessage_overwrite false -trace_shortmsg -shortmessage_file " + str(timestamp_file)
            #Добавляем message trace
            command += " -message_overwrite false -trace_msg -message_file " + test.LogPath + "/" + "MESSAGE_" + str(ua.Name) + "_TEST" + str(test.TestId)
            #Добавляем screen trace
            command += " -screen_overwrite false -trace_screen -screen_file " + test.LogPath + "/" + "SCREEN_" + str(ua.Name) + "_TEST" + str(test.TestId)
            #Добавляем error trace
            command += " -error_overwrite false -trace_err -error_file " + test.LogPath + "/" + "ERROR_" + str(ua.Name) + "_TEST" + str(test.TestId)
            if not no_timeout_err:
                command += " -timeout_error"
            command = replace_key_value(command, test_var)
            if command:
                ua.Commands.append(command)
            else:
                return False
    return test

def replace_key_value(string, var_list):
    for counter in list(range(10)):
        #Ищем все переменные в исходной строке
        command_vars = re.findall(r'%%.*?%%',string)
        for eachVar in command_vars:
            #Если кто запросил текущее время +/- временной сдвиг в формате %%NowTime[+/-][delta]%%,
            #то отправляем данную переменную в функцию сборки времени.
            if re.match(r'%%NowTime([+,-]?)([0-9]{0,4})(;.*)?%%',eachVar):
                shift_time=get_time_with_shift(eachVar)
                if shift_time:
                    string = string.replace(str(eachVar),str(shift_time),1)
                else:
                    return False
            elif re.match(r'\%\%NowWeekDay([+,-]?)([1-6]{1})?\%\%',eachVar):
                shift_weekday=get_weekday_with_shift(eachVar)
                if shift_weekday:
                    string = string.replace(str(eachVar),str(shift_weekday),1)
                else:
                    return False
            #Ищем значение в словаре.
            else:
                try:
                    string = string.replace(str(eachVar),str(var_list[eachVar]))
                except KeyError:
                    logger.error("Command contain unexpected variable: %s", eachVar)
                    return False
        if string.find("%%") != -1:
            if counter == 9:
                logger.error("Command contain a special character '%%' after replacing key values. Command: %s",string)
                return False
            else:
                continue
    string = replace_len_function(string)
    return string

def replace_len_function(string):
    pattern = re.compile(r'len\((.*)\)')
    match = re.search(pattern, string)
    while match:
        string = re.sub(pattern, str(len(match.group(1))), string, count=1)
        match = re.search(pattern, string)
    return string

def get_weekday_with_shift(weekday_string):
    result = re.match(r'%%NowWeekDay([+,-]?)([1-6]{0,4})%%',weekday_string)
    try:
        shift = int(result.group(2))
    except IndexError:
        logger.error("Can't get time shift : \" no such group \"")
        return False
    except ValueError:
        shift = 0
    try:
        sign = str(result.group(1))
    except IndexError:
        logger.error("Can't get sign of shift : \" no such group \"")
        return False
    except ValueError:
        sign = "+"
    now_day = int(datetime.today().isoweekday())
    if shift:
        if sign == "+":
            now_day += shift
            if now_day > 7:
                now_day -= 7
        elif sign == "-":
            now_day -= shift
            if now_day < 1:
                now_day = 7 + now_day
    return now_day


def get_time_with_shift(time_string):
    result=re.match(r'%%NowTime([+,-]?)([0-9]{0,4})(;.*)?%%',time_string)
    try:
        shift = int(result.group(2))
    except IndexError:
        logger.error("Can't get time shift : \" no such group \"")
        return False
    except ValueError:
        shift = 0
    try:
        sign = str(result.group(1))
    except IndexError:
        logger.error("Can't get sign of shift : \" no such group \"")
        return False
    except ValueError:
        sign = "+"
    #Если передали формат, то забираем его, иначе присваиваем дефолтный формат
    try:
        format_time = str(result.group(3)).replace(";","")
    except IndexError:
        logger.error("Can't get time format : \" no such group \"")
    except ValueError:
        format_time = "%H%M"

    if format_time == "None":
        format_time = "%H%M"

    nowTime = time.time()
    if shift:
        if sign == "+":
            nowTime += shift
        elif sign == "-":
            nowTime -= shift
    #Возвращаем время
    return datetime.fromtimestamp(nowTime).strftime(format_time)