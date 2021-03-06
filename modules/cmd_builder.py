import re
import time
from datetime import datetime, date
import logging
from collections import namedtuple
logger = logging.getLogger("tester")

SUPPORT_ENCODING = ["cp1251", "latin-1"]


class CmdBuildExp(Exception):
    pass


class CmdBuild:
    def build_reg_command(self, reg_obj, log_path, test_var, mode="reg"):
        # Building reg command
        command = list()
        command.append("%%SIPP_PATH%% %%EXTER_IP%%:{}".format(reg_obj.RemotePort if reg_obj.RemotePort
                                                          else "%%EXTER_PORT%% "))
        command.append("-i %%IP%%")
        command.append("-set DOMAIN {}".format(reg_obj.SipDomain))

        if type(reg_obj).__name__ == "UserClass":
            command.append(" -set NUMBER {}".format(reg_obj.Number))
            log_prefix = "REG_USER_NUMBER_" + reg_obj.Number + "_"

        elif type(reg_obj).__name__ == "TrunkClass":
            command.append(" -set NUMBER {}".format(reg_obj.TrunkName))
            log_prefix = "REG_TRUNK_" + reg_obj.TrunkName + "_"
        else:
            logger.error("Unknown type of reg obj: %s", str(type(reg_obj)))
            raise CmdBuildExp("CmdBuildError")

        command.append("-set USER_IP {}".format(reg_obj.RegContactIP if reg_obj.RegContactIP else "%%IP%%"))
        command.append("-set PORT {}".format(reg_obj.RegContactPort if reg_obj.RegContactPort else reg_obj.Port))
        if reg_obj.BindPort:
            command.append(" -p {}".format(reg_obj.BindPort))

        if mode == "reg":
            if reg_obj.AddRegParams:
                command.append(reg_obj.AddRegParams)
            command.append("-set EXPIRES {}".format(reg_obj.Expires))
            command.append("-sf {}".format("%%REG_XML%%" if not reg_obj.Script else "%%SRC_PATH%%/" + reg_obj.Script ))
        else:
            command.append("-set EXPIRES 0")
            command.append("-sf %%REG_XML%%")

        command.append("-set USER_Q {}".format(str(reg_obj.QParam)))
        command.append("-s {} -ap {}".format(reg_obj.Login, reg_obj.Password))
        command.append("-m 1 -nostdin -timeout_error")
        if reg_obj.SipTransport == "TCP":
            command.append("-t tn -max_socket 25")
        if reg_obj.SipTransport:
            command.append(" -set USER_TRANSPORT {}".format(reg_obj.SipTransport.lower()))
        command.append("-message_overwrite false -trace_msg -message_file {}/{}MESSAGE".format(log_path, log_prefix))
        command.append("-error_overwrite false -trace_err -error_file {}/{}ERROR".format(log_path, log_prefix))
        command.append("-cid_str {} -base_cseq {}".format(reg_obj.RegCallId, reg_obj.RegCSeq))
        command_str = " ".join(command)
        command_str = self.replace_var(command_str, test_var)
        return command_str

    def build_service_feature_command(self, test, user, code, test_var):
        # Building service feature command
        media_path = test_var.get("%%MEDIA_PATH%%")
        command = list()
        command.append("%%SIPP_PATH%% -sf %%SF_XML%%")
        command.append("%%EXTER_IP%%:%%EXTER_PORT%%")
        command.append("-i %%IP%% -p {}".format(user.Port))
        command.append("-set CDPN {} -set CDPNDOM {}".format(code, user.SipDomain))
        command.append("-set CGPNDOM {}".format(user.SipDomain))
        command.append("-s {} -ap {}".format(user.Login, user.Password))
        command.append("-m 1 -timeout 20s -recv_timeout 20s")
        if user.SipTransport == "TCP":
            command.append("-t tn -max_socket 25")
        if media_path:
            command.append("-key media_path {}".format(media_path))
        log_prefix = "TEST_%s_NUMBER_%s_SF_%s_" % (test.TestId, user.Number, code)
        command.append("-message_overwrite false -trace_msg")
        command.append("-message_file {}/{}MESSAGE".format(test.LogPath, log_prefix))
        command.append("-error_overwrite false -trace_err -error_file {}/{}ERROR".format(test.LogPath, log_prefix))
        command_str = " ".join(command)
        command_str = self.replace_var(command_str, test_var)
        CmdInfo = namedtuple('CmdInfo', ['cmd_str', 'req_ex_code'])
        return CmdInfo(command_str, 0)

    def build_sipp_command(self, test, test_var, uac_drop_flag=False, show_sip_flow=False):
        for ua in test.UserAgent + test.BackGroundUA:
            # Пытаемся достать параметры команды
            for cmd_desc in ua.RawJsonCommands:
                media_path = test_var.get("%%MEDIA_PATH%%")
                sipp_sf = cmd_desc["SourceFile"]
                sipp_options = cmd_desc["Options"]
                sipp_type = cmd_desc["SippType"]
                # Если был передан флаг о сбросе UAC команд, то просто не собираем их.
                if uac_drop_flag and sipp_type == "uac":
                    continue
                sipp_auth = cmd_desc.get("NeedAuth", False)
                timeout = cmd_desc.get("Timeout", "60s")

                # В некоторых случаях полезно, чтобы UA завершился по timeout и при этом вернул 0 ex code
                # Для таких случаев на уровне команды передаем параметр NoTimeOutError
                no_timeout_err = cmd_desc.get("NoTimeOutError", False)

                command = list()
                command.append("%%SIPP_PATH%% -sf %%SRC_PATH%%/{}".format(sipp_sf))
                if ua.Type == "Trunk":
                    command.append("%%EXTER_IP%%:{}".format(ua.TrunkObject.RemotePort if ua.TrunkObject.RemotePort
                                                            else "%%EXTER_PORT%%"))
                    command.append("-p {}".format(ua.TrunkObject.Port))
                    if ua.TrunkObject.SipTransport == "TCP":
                        command.append("-t tn -max_socket 25")
                    if ua.TrunkObject.RtpPort:
                        command.append("-mp {}".format(ua.TrunkObject.RtpPort))

                if ua.Type == "User":
                    command.append("%%EXTER_IP%%:%%EXTER_PORT%%")
                    command.append("-p {}".format(ua.UserObject.Port))
                    command.append("-s {}".format(ua.UserObject.Login))
                    if sipp_auth:
                        command.append("-ap {}".format(ua.UserObject.Password))
                    if ua.UserObject.SipTransport == "TCP":
                        command.append("-t tn -max_socket 25")
                    if ua.UserObject.RtpPort:
                        command.append("-mp {}".format(ua.UserObject.RtpPort))
                    if sipp_type == "uac":
                        command.append("-set CGPNDOM {}".format(ua.UserObject.SipDomain))
                elif ua.Type == "Trunk":
                    if sipp_auth:
                        command.append("-s {}".format(ua.TrunkObject.Login))
                        command.append("-ap {}".format(ua.TrunkObject.Password))

                command.append("-i %%IP%%")
                command.append(sipp_options)

                if media_path:
                    command.append("-key media_path {}".format(media_path))

                # Выставляем Call-ID и CSeq, если требуется.
                try:
                    command.append("-cid_str {}".format(str(cmd_desc["CidStr"])))
                except KeyError:
                    pass
                try:
                    command.append("-base_cseq {}".format(str(cmd_desc["StartCseq"])))
                except KeyError:
                    pass

                command.append("-timeout {}".format(timeout))

                if not no_timeout_err:
                    command.append("-timeout_error")

                if sipp_type == "uac":
                    command.append("-recv_timeout {}".format(timeout))

                command.append("-rtcheck {}".format(ua.RtCheck))
                command.append("-nostdin")

                if ua.Type == "User":
                    log_prefix = "TEST_{}_NUMBER_{}_".format(test.TestId, ua.UserObject.Number)
                elif ua.Type == "Trunk":
                    log_prefix = "TEST_{}_TRUNK_{}_PORT_{}_".format(test.TestId, ua.TrunkObject.TrunkName.upper(),
                                                                    ua.TrunkObject.Port)

                # Если был передан флаг для записи timestamp, то добавляем соотвествующие ключи
                if ua.WriteStat:
                    timestamp_file = "{}/{}{}_TIMESTAMP".format(test.LogPath, log_prefix, ua.Name)
                    ua.TimeStampFile = timestamp_file
                    command.append("-shortmessage_overwrite false -trace_shortmsg")
                    command.append("-shortmessage_file {}".format(timestamp_file))
                # Добавляем message trace
                command.append("-message_overwrite false -trace_msg")
                command.append("-message_file {}/{}{}_MESSAGE".format(test.LogPath, log_prefix, ua.Name))
                # Добавляем screen trace
                command.append("-screen_overwrite false -trace_screen")
                command.append("-screen_file {}/{}{}_SCREEN".format(test.LogPath, log_prefix, ua.Name))
                # Добавляем error trace
                command.append("-error_overwrite false -trace_err")
                command.append("-error_file {}/{}{}_ERROR".format(test.LogPath, log_prefix, ua.Name))

                command_str = " ".join(command)
                command_str = self.replace_var(command_str, test_var)
                CmdInfo = namedtuple('CmdInfo', ['cmd_str', 'req_ex_code'])
                ua.Commands.append(CmdInfo(command_str, cmd_desc.get("ReqExCode", 0)))
        return test

    def replace_var_for_dict(self, dictionary, varlst):
        for k, v in dictionary.items():
            dictionary[k] = self.replace_var(v, varlst)

    def replace_var_for_list(self, l, varlst):
        for count, item in enumerate(l):
            l[count] = self.replace_var(item, varlst) if type(item) == str else item

    @staticmethod
    def _remove_range_duplicates(string):
        # Удаляем дубликаты только для цифровых диапазонов
        pattern = re.compile(r'{(([0-9]+,)+[0-9]+)}')
        str_ranges = re.findall(pattern, string)
        if not str_ranges:
            return string
        for cur_range in str_ranges:
            range_list, _ = cur_range
            range_list = range_list.split(",")
            # Получаем только уникальные значения
            range_list = sorted(set(range_list))
            # Пересобираем строку с новым диапазоном
            new_range_str = "{" + ",".join(range_list) + "}"
            string = re.sub(pattern, new_range_str, string, count=1)
        return string

    @staticmethod
    def _replace_range(string):
        # Ищём все диапазоны следующего вида {%%1.Param%% - %%3.Param%%}
        # И меняем на {%%1.Param%%,%%2.Param%%,%%3.Param%%}
        pattern = re.compile(r'{\s?%%([0-9]+)\.([^%]+)%%\s?-\s?%%([0-9]+)\.[^%]+%%\s?}')
        str_ranges = re.findall(pattern, string)
        if not str_ranges:
            return string
        for range_params in str_ranges:
            start, pr, end = range_params
            new_range_str = "{" + ",".join(["%%{}.{}%%".format(x, pr) for x in range(int(start), int(end) + 1)]) + "}"
            string = re.sub(pattern, new_range_str, string, count=1)
        return string

    def replace_var(self, string, var_list):
        # Заменяем диапазоны в командах
        string = self._replace_range(string)
        for counter in list(range(10)):
            # Ищем все переменные в исходной строке
            command_vars = re.findall(r'%%.*?%%', string)
            for var in command_vars:
                if var.find("%%NowTime") != -1:
                    string = self._replace_time_shift_function(string)
                    continue
                if var.find("%%NowWeekDay") != -1:
                    string = self._replace_weekday_shift_function(string)
                    continue
                try:
                    string = string.replace(str(var), str(var_list[var]))
                except KeyError:
                    logger.error("Command contain unexpected variable: %s", str(var))
                    raise CmdBuildExp("CmdBuildError")
            if string.find("%%") != -1:
                if counter == 9:
                    logger.error("Command contain a special character '%%' after replacing variables. Cmd: %s", string)
                    raise CmdBuildExp("CmdBuildError")
                else:
                    continue
        string = self._replace_len_function(string)
        string = self._remove_range_duplicates(string)
        string = self._replace_encode_function(string)
        return string

    @staticmethod
    def _replace_encode_function(string):
        pattern = re.compile(r'encode\("([^"]+)"[\s]*,[\s]*"([^"]+)"\)')
        match = re.search(pattern, string)
        while match:
            raw_str, encoder = match.groups()
            if encoder not in SUPPORT_ENCODING:
                logger.error("Encoding to %s not supported for encode function.", str(encoder))
                raise CmdBuildExp("CmdBuildError")
            string = re.sub(pattern, "@BINARY:{}:{}".format(raw_str, encoder), string, count=1)
            match = re.search(pattern, string)
        return string

    @staticmethod
    def _replace_len_function(string):
        pattern = re.compile(r'len\((.*)\)')
        match = re.search(pattern, string)
        while match:
            string = re.sub(pattern, str(len(match.group(1))), string, count=1)
            match = re.search(pattern, string)
        return string

    @staticmethod
    def _replace_weekday_shift_function(string):
        reg_exp = re.compile(r'%%NowWeekDay([+,-]?)([1-6]{0,4})%%')
        match = re.search(reg_exp, string)
        while match:
            try:
                shift = int(match.group(2))
            except IndexError:
                logger.error("Can't get weekday shift from: %s", str(string))
                raise CmdBuildExp("CmdBuildError")
            except ValueError:
                shift = 0
            try:
                sign = str(match.group(1))
            except IndexError:
                logger.error("Can't get sign of weekday shift from: %s", str(string))
                raise CmdBuildExp("CmdBuildError")
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
                        now_day += 7
            string = string.replace(match.group(0), str(now_day), 1)
            match = re.search(reg_exp, string)
        return string

    @staticmethod
    def _replace_time_shift_function(string):
        reg_exp = re.compile(r'%%NowTime\s?([+,-]?)\s?([0-9]{0,4});?(.*?)?%%')
        match = re.search(reg_exp, string)
        while match:
            try:
                shift = int(match.group(2))
            except IndexError:
                logger.error("Can't get time shift from: %s", str(string))
                raise CmdBuildExp("CmdBuildError")
            except ValueError:
                shift = 0
            try:
                sign = str(match.group(1))
            except IndexError:
                logger.error("Can't get sign of time shift from: %s", str(string))
                raise CmdBuildExp("CmdBuildError")
            except ValueError:
                sign = "+"
            # Если передали формат, то забираем его, иначе присваиваем дефолтный формат
            format_time = None
            try:
                format_time = match.group(3)
            except IndexError:
                logger.error("Can't get time format : \" no such group \"")
            except (AttributeError, ValueError):
                format_time = "%H%M"
            if not format_time:
                format_time = "%H%M"

            now_time = time.time()
            if shift:
                if sign == "+":
                    now_time += shift
                elif sign == "-":
                    now_time -= shift
            # Возвращаем время
            time_w_shift = datetime.fromtimestamp(now_time).strftime(format_time)
            string = string.replace(match.group(0), time_w_shift, 1)
            match = re.search(reg_exp, string)
        return string
