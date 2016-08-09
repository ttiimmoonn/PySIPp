import re
import time
from datetime import datetime, date
def build_service_feature_command (user, code):
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
    return command    
    
def build_reg_command (user,list,mode="reg"):
    #Сборка команды для регистрации
    command=""
    command+="%%SIPP_PATH%%" + " "
    command+="-sf " + "%%REG_XML%%" + " "
    command+="%%EXTER_IP%%" + ":" + "%%EXTER_PORT%%" + " "
    command+="-i " + "%%IP%%" + " "
    command+=" -set DOMAIN " + str(user.SipDomain)
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
    command = replace_key_value(command, list)
    if command:
        return command
    else:
        return False
def build_sipp_command(test,list,uac_drop_flag=False, show_sip_flow=False):
    for ua in test.UserAgent:
         #Пытаемся достать параметры команды
         for command in ua.RawJsonCommands:
            try:
                sipp_sf = command["SourceFile"]
            except KeyError:
                print("[ERROR] Wrong Command description. Detail:")
                print("---> UA has no attribute:",sys.exc_info()[1],"{ Test:",test.Name,", UA:",ua.Name,"}")
                return False
            try:
                sipp_options = command["Options"]
            except KeyError:
                print("[ERROR] Wrong Command description. Detail:")
                print("---> UA has no attribute:",sys.exc_info()[1],"{ Test:",test.Name,", UA:",ua.Name,"}")
                return False
            try:
                sipp_type = command["SippType"]
            except KeyError:
                print("[ERROR] Wrong Command description. Detail:")
                print("---> UA has no attribute:",sys.exc_info()[1],"{ Test:",test.Name,", UA:",ua.Name,"}")
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
            command=""                
            command += "%%SIPP_PATH%%"
            command += " -sf " + "%%SRC_PATH%%" + "/" + sipp_sf + " "
            command += "%%EXTER_IP%%" + ":" + "%%EXTER_PORT%%"
            command += " -i " + "%%IP%%" + " "
            command += sipp_options
            if ua.Type == "User":
                command += " -p " + ua.UserObject.Port
            else:
                command += " -p " + ua.Port
            command+=" -nostdin"
            if sipp_auth and ua.Type=="User":
                command += " -s " + ua.UserObject.Number
                command += " -ap " + ua.UserObject.Password
            if sipp_type == "uac":
                command += " -timeout " + str(timeout)
                command += " -recv_timeout " + str(timeout)
                if ua.Type=="User":
                    command += " -set CGPNDOM " + ua.UserObject.SipDomain
            else:
                command += " -timeout " + str(timeout)
                command += " -recv_timeout " + str(timeout)
            
            #Если был передан флаг для записи timestamp, то добавляем соотвествующие ключи
            if show_sip_flow and ua.WriteStat:
                timestamp_file = test.LogPath + "/" + "TIMESTAMP_" + str(ua.Name)
                ua.TimeStampFile = timestamp_file
                command += " -shortmessage_overwrite false -trace_shortmsg -shortmessage_file " + str(timestamp_file)

            #Добавляем message trace
            command += " -message_overwrite false -trace_msg -message_file " + test.LogPath + "/" + "MESSAGE_" + str(ua.Name)
            #Добавляем screen trace
            command += " -screen_overwrite false -trace_screen -screen_file " + test.LogPath + "/" + "SCREEN_" + str(ua.Name)
            command = replace_key_value(command, list)

            if command:
                ua.Commands.append(command)
            else:
                return False
    return test

def replace_key_value(string, var_list):
    for counter in list(range(10)):
        #Ищем все переменные в исходной строке
        command_vars = re.findall(r'%%[\w\.+-]*%%',string)
        for eachVar in command_vars:
            #Если кто запросил текущее время +/- временной сдвиг в формате %%NowTime[+/-][delta]%%,
            #то отправляем данную переменную в функцию сборки времени.
            if re.match("%%NowTime([+,-]?)([0-9]{0,4})%%",eachVar):
                shift_time=get_time_with_shift(eachVar)
                if shift_time:
                    string = string.replace(str(eachVar),str(shift_time))
                else:
                    return False
            elif re.match("%%NowWeekDay%%",eachVar):
                string = string.replace(str(eachVar),str(datetime.today().isoweekday()))
            #Ищем значение в словаре.
            else:
                try:
                    string = string.replace(str(eachVar),str(var_list[eachVar]))
                except KeyError:
                    print("[ERROR] Command contain unexpected variable:", eachVar)
                    return False
        if string.find("%%") != -1:
            if counter == 9:
                print("[ERROR] Command contain a special character '%%' after replacing key values.")
                print("--> Command:",string)
                return False
            else:
                continue
    return string

def get_time_with_shift(time_string):   
    result=re.match("%%NowTime([+,-]?)([0-9]{0,4})%%",time_string)
    try:
        shift = int(result.group(2))
    except IndexError:
        print("[ERROR] Can't get time shift : \" no such group \"")
        return False
    try:
        sign = str(result.group(1))
    except IndexError:
        print("[ERROR] Can't get sign of shift : \" no such group \"")
        return False
    nowTime = time.time()
    if shift:
        if sign == "+":
            nowTime += shift
        elif sign == "-":
            nowTime -= shift
    #Возвращаем время
    return datetime.fromtimestamp(nowTime).strftime('%H%M')




