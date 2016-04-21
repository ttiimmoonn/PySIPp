def build_service_feature_command (user, code):
    #Сборка команды для регистрации
    command=""
    command+="%%SIPP_PATH" + " "
    command+="-sf " + "%%SF_XML" + " "
    command+="%%EXTER_IP" + ":" + "%%EXTER_PORT" + " "
    command+="-i " + "%%IP" + " "
    command+=" -p " + str(user.Port)
    command+=" -set CDPN " + str(code)
    command+=" -set CDPNDOM " + str(user.SipDomain)
    command+=" -set CGPNDOM " + str(user.SipDomain)
    command+=" -s " + str(user.Login)
    command+=" -ap " + str(user.Password)
    command+=" -m 1 "
    command+=" -timeout 20s"
    return command    
    
def build_reg_command (user,list,mode="reg"):
    #Сборка команды для регистрации
    command=""
    command+="%%SIPP_PATH" + " "
    command+="-sf " + "%%REG_XML" + " "
    command+="%%EXTER_IP" + ":" + "%%EXTER_PORT" + " "
    command+="-i " + "%%IP" + " "
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
def build_sipp_command(test,list):
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
            try:
                sipp_auth = command["NeedAuth"]
            except KeyError:
                sipp_auth = False
            try:
                timeout = command["Timeout"]
            except KeyError:
                timeout = 60
            command=""                
            command += "%%SIPP_PATH"
            command += " -sf " + "%%SRC_PATH" + "/" + sipp_sf + " "
            command += "%%EXTER_IP" + ":" + "%%EXTER_PORT"
            command += " -i " + "%%IP" + " "
            command += sipp_options
            if ua.Type == "User":
                command += " -p " + ua.UserObject.Port
            else:
                command += " -p " + ua.Port
            command+=" -nostdin"
            if sipp_auth:
                command += " -s " + ua.UserObject.Number
                command += " -ap " + ua.UserObject.Password
            if sipp_type == "uac":
                command += " -set CGPNDOM " + ua.UserObject.SipDomain
                command += " -recv_timeout " + str(timeout)
            else:
                command += " -timeout " + str(timeout)
                command += " -recv_timeout " + str(timeout)
            command = replace_key_value(command, list)
            if command:
                ua.Commands.append(command)
            else:
                return False
    return test

def replace_key_value(command, list):
    #Перебираем все ключи и если ключ встеречается в команда
    #Заменяем его на значение
    #Так как ссылки могут быть вложеными, прогоняем несколько раз
    #но не больше 10
    replace_flag = True
    replace_counter = 0
    while(replace_flag):
    
        for key in list.keys():
            command = command.replace(str(key),str(list[key])) 
        #Проверяем, что не осталось ни одного спецсимвола.  
        if command.find("%%") != -1:
            if replace_counter == 10:
                print("[ERROR] The SIPp command contain a special character '%%' after replacing key values.")
                print("--> Command:",command)
                return False
            else:
                replace_counter += 1
        else:
            replace_flag = False
    return command