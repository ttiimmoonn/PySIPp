import re
import time
from datetime import datetime, date
import logging
logger = logging.getLogger("tester")

class Command_building:

    def build_reg_command(self, reg_obj, log_path, test_var, mode="reg"):
        #Сборка команды для регистрации
        command=""
        command+="%%SIPP_PATH%%" + " "
        command+="%%EXTER_IP%%" + ":"
        try:
            if reg_obj.RemotePort != None:
                command+=reg_obj.RemotePort + " "
            else:
                command+="%%EXTER_PORT%%" + " "
        except:
            command+="%%EXTER_PORT%%" + " "
        command+="-i " + "%%IP%%" + " "
        command+=" -set DOMAIN " + str(reg_obj.SipDomain) + " "

        if type(reg_obj).__name__ == "UserClass":
            command+=" -set NUMBER " + reg_obj.Number
            LOG_PREFIX = "REG_" + "USER_NUMBER_" + reg_obj.Number + "_"

        elif type(reg_obj).__name__ == "TrunkClass":
            command+=" -set NUMBER " + reg_obj.TrunkName
            LOG_PREFIX = "REG_" + "TRUNK_" + reg_obj.TrunkName + "_"

        if reg_obj.RegContactIP != None:
            command += " -set USER_IP " + str(reg_obj.RegContactIP)
        else:
            command += " -set USER_IP " + "%%IP%%"
        if reg_obj.RegContactPort != None:
            command += " -set PORT " + str(reg_obj.RegContactPort)
        else:
            command+=" -set PORT " + str(reg_obj.Port)

        if reg_obj.BindPort != None:
            command+=" -p " + str(reg_obj.BindPort)

        if reg_obj.Script == None:
            command+=" -sf " + "%%REG_XML%%" + " "
        else:
            command+=" -sf "  + "%%SRC_PATH%%" + "/" + reg_obj.Script + " "
        if mode == "reg":
            if reg_obj.AddRegParams != None:
                command+=" " + str(reg_obj.AddRegParams)

        if mode == "reg":
            command+=" -set EXPIRES " + str(reg_obj.Expires)
        elif mode == "unreg":
            command+=" -set EXPIRES " + "0"
        command+=" -set USER_Q " + str(reg_obj.QParam)
        command+=" -s " + reg_obj.Login + " -ap " + reg_obj.Password
        command+=" -m 1"
        command+=" -nostdin"
        command+=" -timeout_error"
        if reg_obj.SipTransport == "TCP":
            command+=" -t tn -max_socket 25"
        if reg_obj.SipTransport != None:
            command+=" -set USER_TRANSPORT " +  reg_obj.SipTransport.lower()
        #Добавляем message trace
        command += " -message_overwrite false -trace_msg -message_file " + log_path + "/" + LOG_PREFIX + "MESSAGE"
        #Добавляем error trace
        command += " -error_overwrite false -trace_err -error_file " + log_path + "/" + LOG_PREFIX + "ERROR"
        command = self.replace_key_value(command, test_var)
        if command:
            return command
        else:
            return False

    def build_service_feature_command(self, test, user, code, test_var):
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
        command = self.replace_key_value(command, test_var)
        LOG_PREFIX = "TEST_" + str(test.TestId) + "_NUMBER_" + user.Number + "_SF_" + code + "_"
        #Добавляем message trace
        command += " -message_overwrite false -trace_msg -message_file " + test.LogPath + "/" + LOG_PREFIX + "MESSAGE"
        #Добавляем error trace
        command += " -error_overwrite false -trace_err -error_file " + test.LogPath + "/" + LOG_PREFIX + "ERROR"
        return command

    def build_sipp_command(self, test, test_var, uac_drop_flag=False, show_sip_flow=False):
        for ua in test.UserAgent + test.BackGroundUA:
            #Пытаемся достать параметры команды
            for command in ua.RawJsonCommands:
                sipp_sf = command["SourceFile"]
                sipp_options = command["Options"]
                sipp_type = command["SippType"]
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
                command += "%%EXTER_IP%%" + ":"
                try:
                    if ua.TrunkObject.RemotePort != None:
                        command+=str(ua.TrunkObject.RemotePort) + " "
                    else:
                        command+="%%EXTER_PORT%%" + " "
                except:
                    command+="%%EXTER_PORT%%" + " "
                command += " -i " + "%%IP%%" + " "
                command += sipp_options
                if ua.Type == "User":
                    command += " -p " + str(ua.UserObject.Port)
                    command += " -s " + ua.UserObject.Login
                    if ua.UserObject.SipTransport == "TCP":
                        command+=" -t tn -max_socket 25"
                    if ua.UserObject.RtpPort:
                        command += " -mp " + str(ua.UserObject.RtpPort)
                elif ua.Type == "Trunk":
                    command += " -p " + str(ua.TrunkObject.Port)
                    if ua.TrunkObject.SipTransport == "TCP":
                        command+=" -t tn -max_socket 25"
                command+=" -nostdin"

                if sipp_auth and ua.Type=="User":
                    command += " -ap " + ua.UserObject.Password

                if sipp_type == "uac":
                    command += " -timeout " + timeout
                    command += " -recv_timeout " + timeout
                    if ua.Type=="User":
                        command += " -set CGPNDOM " + ua.UserObject.SipDomain
                else:
                    command += " -timeout " + timeout

                #Выставляем ленивый режим детектирования перепосылок.
                command += " -rtcheck loose"

                if ua.Type == "User":
                    LOG_PREFIX = "TEST_" + str(test.TestId) + "_NUMBER_" + ua.UserObject.Number + "_"
                elif ua.Type == "Trunk":
                    LOG_PREFIX = "TEST_" + str(test.TestId) + "_TRUNK_PORT_" + str(ua.Port) + "_"
                else:
                    LOG_PREFIX = "TEST_" + str(test.TestId) + "_UNKNOWN_TYPE_"

                #Если был передан флаг для записи timestamp, то добавляем соотвествующие ключи
                if ua.WriteStat:
                    timestamp_file = test.LogPath + "/" + LOG_PREFIX + ua.Name + "_TIMESTAMP"
                    ua.TimeStampFile = timestamp_file
                    command += " -shortmessage_overwrite false -trace_shortmsg -shortmessage_file " + str(timestamp_file)
                #Добавляем message trace
                command += " -message_overwrite false -trace_msg -message_file " + test.LogPath + "/" + LOG_PREFIX + ua.Name + "_MESSAGE"
                #Добавляем screen trace
                command += " -screen_overwrite false -trace_screen -screen_file " + test.LogPath + "/" + LOG_PREFIX + ua.Name + "_SCREEN"
                #Добавляем error trace
                command += " -error_overwrite false -trace_err -error_file " + test.LogPath + "/" + LOG_PREFIX + ua.Name + "_ERROR"
                if not no_timeout_err:
                    command += " -timeout_error"
                command = self.replace_key_value(command, test_var)
                if command:
                    ua.Commands.append(command)
                else:
                    return False
        return test

    def replace_key_value(self, string, var_list):
        for counter in list(range(10)):
            #Ищем все переменные в исходной строке
            command_vars = re.findall(r'%%.*?%%',string)
            for eachVar in command_vars:
                #Если кто запросил текущее время +/- временной сдвиг в формате %%NowTime[+/-][delta]%%,
                #то отправляем данную переменную в функцию сборки времени.
                if re.match(r'%%NowTime([+,-]?)([0-9]{0,4})(;.*)?%%',eachVar):
                    shift_time=self.get_time_with_shift(eachVar)
                    if shift_time:
                        string = string.replace(str(eachVar),str(shift_time),1)
                    else:
                        return False
                elif re.match(r'\%\%NowWeekDay([+,-]?)([1-6]{1})?\%\%',eachVar):
                    shift_weekday=self.get_weekday_with_shift(eachVar)
                    if shift_weekday:
                        string = string.replace(str(eachVar),str(shift_weekday),1)
                    else:
                        return False
                #Ищем значение в словаре
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
        string = self.replace_len_function(string)
        return string

    def replace_len_function(self, string):
        pattern = re.compile(r'len\((.*)\)')
        match = re.search(pattern, string)
        while match:
            string = re.sub(pattern, str(len(match.group(1))), string, count=1)
            match = re.search(pattern, string)
        return string

    def get_weekday_with_shift(self, weekday_string):
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


    def get_time_with_shift(self, time_string):
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