import modules.test_class as test_class
import modules.test_parser as parser
from modules.diff_meter import TimeDiffMeterExp, TimeDiffMeter
from modules.cmd_builder import CmdBuildExp
import modules.process_contr as proc
import modules.cdr as cdr
import ftplib
from collections import namedtuple
import re
import sys
import uuid
import time
from datetime import datetime
import threading
import logging
logger = logging.getLogger("tester")


class Dict2Obj:
    def __init__(self, dictionary):
        """Constructor"""
        for key in dictionary:
            setattr(self, key, dictionary[key])


class TestProcessorExp(Exception):
    pass


class TestProcessor:
    def __init__(self, **kwargs):
        self.Tests = kwargs["Tests"]
        self.SSHInt = kwargs["SSHInt"]

        # Var dict
        self.TestVar = kwargs["TestVar"]
        # User and Trunk dict
        self.Users = kwargs["Users"]
        self.Trunks = kwargs["Trunks"]

        # Reg dict
        self.AutoRegTrunks = {trunk_id: trunk for trunk_id,trunk in self.Trunks.items() if trunk.RegType == "out" and trunk.RegMode == "Auto"}
        self.ManualRegTrunks = {trunk_id: trunk for trunk_id,trunk in self.Trunks.items() if trunk.RegType == "out" and trunk.RegMode == "Manual"}
        self.AutoRegUsers = {user_id: user for user_id, user in self.Users.items() if user.RegMode == "Auto"}
        self.ManualRegUsers = {user_id: user for user_id, user in self.Users.items() if user.RegMode == "Manual"}

        # Item gen for TestProcedure
        self.GenForTest = None
        self.GenForItem = None

        # Flags
        self.ShowSipFlowFlag = kwargs["ShowSipFlowFlag"]
        self.UacDropFlag = kwargs["UacDropFlag"]
        self.ForceQuitFlag = kwargs["ForceQuitFlag"]
        self.failed_flag = False

        # Paths
        self.LogPath = kwargs["LogPath"]
        # Realtime
        self.Status = "New"
        self.NowRunningTest = None
        self.NowRunningThreads = []

        # Locks
        self.RegLock = threading.Lock()
        self.RegThread = None
        self.CmdBuilder = kwargs["CmdBuilder"]

    def stop(self):
        self.Status = "Stopping test_processor"
        logger.debug("Drop all SIPp processes...")
        # Дропаем процессы
        if self.NowRunningTest != None:
            for ua in self.NowRunningTest.UserAgent + self.NowRunningTest.WaitBackGroundUA:
                for process in ua.Process:
                    if process.poll() == None:
                        process.kill()

        # Разрегистрируем транки
        if self.RegLock and len(self.AutoRegUsers) > 0:
            self._stop_user_registration(self.AutoRegTrunks)
        # Разрегистрируем юзеров
        if self.RegLock and len(self.AutoRegUsers) > 0:
            self._stop_user_registration(self.AutoRegUsers)

        # Для корректного завершения теста нужно выслать все ccn_cmd, которые он не послал.
        self._send_all_ssh_commands()

        # Даём время на сворачивание thread
        self._sleep(0.2)
        return True

    def _stop_user_registration(self, reg_objects):
        logger.info("Drop registration...")
        if not self._build_reg_command(reg_objects, mode="unreg"):
            return False
        thread = threading.Thread(target=proc.ChangeUsersRegistration, args=(reg_objects,self.RegLock,"unreg",))
        thread.start()
        # Даём завершиться thread'у разрегистрации
        thread.join()
        # Обновляем параметры регистрации
        for obj in reg_objects.values():
            obj.RegCSeq = 1
            obj.RegCallId = uuid.uuid4()
            obj.RegContactPort = None
            obj.RegContactIP = None
            obj.AddRegParams = None
            obj.Expires = 90
        if not proc.CheckUserRegStatus(reg_objects):
            return False
        return True

    def _start_user_registration(self, reg_objects):
        self.Status = "Start Registration..."
        if not self._build_reg_command(reg_objects):
            return False
        # Врубаем регистрацию для всех объектов
        logger.info("Starting of registration...")

        self.RegThread = threading.Thread(target=proc.ChangeUsersRegistration, args=(reg_objects,self.RegLock))
        self.RegThread.start()
        self.RegThread.join()
        if not proc.CheckUserRegStatus(reg_objects):
            return False
        return True

    def _build_reg_command(self, reg_objects, mode="reg"):
        if len(reg_objects) > 0:
            # Собираем команды для регистрации абонентов
            if mode == "reg":
                logger.info("Build commands for starting registration...")
            else:
                logger.info("Build commands for stopping registration...")

            for obj in reg_objects.values():
                try:
                    command = self.CmdBuilder.build_reg_command(obj, self.LogPath, self.TestVar, mode=mode)
                except CmdBuildExp as error:
                    raise TestProcessorExp(error)
                if mode == "reg":
                    obj.RegCommand = command
                else:
                    obj.UnRegCommand = command
        return True

    @staticmethod
    def _get_test_item_gen(Test):
        for item in Test:
            for method in item.items():
                yield method

    def _link_user_to_ua(self):
        # Массив для использованных id
        use_id = []
        use_trunk_id = []
        for ua in self.NowRunningTest.UserAgent + self.NowRunningTest.BackGroundUA:
            if ua.Type == "User":
                if not ua.UserId in use_id:
                    use_id.append(ua.UserId)
                    try:
                        ua.UserObject = self.Users[ua.UserId]
                    except KeyError:
                        logger.error("User with id = %d not found { UA : %s }",int(ua.UserId),ua.Name)
                        return False
                else:
                    logger.error("Duplicate UserId: %d { UA : %s }", int(ua.UserId),ua.Name)
                    return False
            elif ua.Type == "Trunk":
                if not ua.TrunkId in use_trunk_id:
                    use_trunk_id.append(ua.TrunkId)
                    try:
                        ua.TrunkObject = self.Trunks[ua.TrunkId]
                    except KeyError:
                        logger.error("Trunk with id = %d not found { UA : %s }",int(ua.TrunkId),ua.Name)
                        return False
                else:
                    logger.error("Duplicate TrunkId: %d { UA : %s }",int(ua.TrunkId),ua.Name)
                    return False
        return True

    def _build_sipp_command(self):
        logger.info("Build SIPp commands for UA...")
        try:
            self.CmdBuilder.build_sipp_command(self.NowRunningTest, self.TestVar,
                                               self.UacDropFlag, self.ShowSipFlowFlag)
        except CmdBuildExp as error:
            raise TestProcessorExp(error)
        return True

    def _build_sipp_sf_command(self, sf_ua, sf_code):
        # Собираем команду для активации сервис фичи
        try:
            cmd_desc = self.CmdBuilder.build_service_feature_command(self.NowRunningTest, sf_ua.UserObject,
                                                                     sf_code, self.TestVar)
        except CmdBuildExp as error:
            raise TestProcessorExp(error)
        else:
            sf_ua.Commands.append(cmd_desc)
            return True

    @staticmethod
    def _sleep(timeout=32):
        logger.info("Sleep on %ss", str(round(float(timeout), 1)))
        time.sleep(float(timeout))

    def _start_sipp_processes(self):
        self.NowRunningThreads = proc.start_process_controller(self.NowRunningTest)
        if len(self.NowRunningTest.UserAgent) > 0:
            logger.info("Waiting for closing threads...")
            if not proc.CheckThreads(self.NowRunningThreads):
                logger.error("One of UA's thread not closed.")
                # Останавливаем все thread
                self.NowRunningTest.ThreadEvent.clear()
                # Переносим отработавшие UA в завершенные
                self.NowRunningTest.ReplaceUaToComplite()
                # Даём thread завершиться
                self._sleep()
                return False

            # Проверяем UA на статусы
            logger.info("Check process StatusCode...")
            if not proc.CheckUaStatus(self.NowRunningTest.UserAgent):
                # Переносим отработавшие UA в завершенные
                logger.error("One of UAs return bad exit code")
                self.NowRunningTest.ReplaceUaToComplite()
                self._sleep()
                return False

            self.NowRunningTest.ReplaceUaToComplite()
        return True

    def _cdr_compare(self, method_body):
        cdr_conf = {}
        compare_result = []
        cdr_group = method_body.get("CDRGroup", "default")
        try:
            cdr_group = self.CmdBuilder.replace_var(cdr_group, self.TestVar)
        except CmdBuildExp as error:
            raise TestProcessorExp(error)
        # Make ftp config
        cdr_conf["host"] = self.TestVar["%%SERV_IP%%"]
        cdr_conf["user"] = "cdr"
        cdr_conf["passwd"] = "cdr"
        cdr_conf["timeout"] = 500
        # Make cdr finalize
        logger.info("Finalize cdr for group %s", cdr_group)
        finalize_command = "/domain/%%DEV_DOM%%/cdr/make_finalize_cdr " + cdr_group
        try:
            finalize_command = self.CmdBuilder.replace_var(finalize_command, self.TestVar)
        except CmdBuildExp as error:
            raise TestProcessorExp(error)
        if type(finalize_command) != str:
            return False
        if not self.SSHInt.push_cmd_string_to_ssh(finalize_command):
            self.NowRunningTest.Status = "Failed"
            return False
        # Trying to get cdr filename
        cdr_filename = re.search(r'\s([\w_]+\.csv)', self.SSHInt.Output)
        if not cdr_filename:
            logger.error("Can't parse cdr filename from ssh output.")
            self.NowRunningTest.Status = "Failed"
            return False
        else:
            # get cdr file
            cdr_filename = cdr_filename.group(1)
            # Make cdr path
            cdr_path = "/domain/%s/%s/csv" % (self.TestVar["%%DEV_DOM%%"], cdr_group)
        # Try ftp connect
        try:
            cdr_obj = cdr.CDR(**cdr_conf)
        except ftplib.error_perm as error:
            logger.error("Can't connect to ftp server. Reason: %s", error)
            self.NowRunningTest.Status = "Failed"
            return False
        except ConnectionRefusedError as error:
            logger.error("Can't connect to ftp server. Reason: %s", error)
            self.NowRunningTest.Status = "Failed"
            return False

        # Replace vars in cdr params
        cdr_params = method_body.get("CDRParams", {})
        try:
            self.CmdBuilder.replace_var_for_dict(cdr_params, self.TestVar)
        except CmdBuildExp as error:
            raise TestProcessorExp(error)
        for cdr_dict in cdr_obj.parse_cdr_file(cdr_path, cdr_filename):
            # cdr_params must be a subset of cdr_dict. Check it!
            if not set(cdr_params).issubset(set(cdr_dict)):
                logger.error("CDR compare failed. Next params not found: %s",
                             set(cdr_params).difference(set(cdr_dict)))
                compare_result.append(False)
                break
            for key in cdr_params.keys():
                if cdr_dict[key] != cdr_params[key]:
                    logger.error("CDR compare failed. Parameter %s equal %s, req value: %s",
                                key, cdr_dict[key], cdr_params[key])
                    compare_result.append(False)
                    break
                else:
                    compare_result.append(True)

        if compare_result and False not in compare_result:
            logger.info("CDR compare result: success.")
            return True
        else:
            logger.error("CDR compare result: failed.")
            self.NowRunningTest.Status = "Failed"
            return False

    def _exec_start_ua(self, ua_desc):
        logger.info("Parse UA from test.")
        parse = parser.Parser()
        if not parse.parse_user_agent(self.NowRunningTest, ua_desc):
            self.NowRunningTest.Status = "Failed"
            logger.error("Parse UA failed.")
            return False

        # Линкуем юзеров к юзер агентам
        logger.info("Link UA object with User object...")
        if not self._link_user_to_ua():
            self.NowRunningTest.Status = "Failed"
            logger.error("Link UA object with User object failed.")
            return False

        # Собираем команды для UA.
        if not self._build_sipp_command():
            self.NowRunningTest.Status = "Failed"
            logger.error("Build SIPp commands failed.")
            return False

        for ua in self.NowRunningTest.UserAgent + self.NowRunningTest.BackGroundUA:
            logging.info("PortInfo for UA: %s", ua.Name)
            logging.info("---| UA Type:     %s", str(ua.Type))
            if ua.Type == "User":
                logging.info("---| UA Number:   %s", str(ua.UserObject.Number))
                logging.info("---| UA Port:     %s", str(ua.UserObject.Port))
                logging.info("---| UA RtpPort:  %s", str(ua.UserObject.RtpPort))
            elif ua.Type == "Trunk":
                logging.info("---| UA Port:     %s", str(ua.TrunkObject.Port))
                logging.info("---| UA RtpPort:  %s", str(ua.TrunkObject.RtpPort))

        if self.UacDropFlag:
            # Remove all ua with empty start commands
            self.NowRunningTest.UserAgent = [ua for ua in self.NowRunningTest.UserAgent if ua.Commands]
            self.NowRunningTest.BackGroundUA = [ua for ua in self.NowRunningTest.BackGroundUA if ua.Commands]

        if not self._start_sipp_processes():
            self.NowRunningTest.Status = "Failed"
            return False
        return True

    def _exec_service_feature(self, sf_desc):
        # Проверка на уникальность uid в serviceFeature cmd
        already_used_uid = []
        for sf in sf_desc:
            try:
                sf_code = self.CmdBuilder.replace_var(sf['code'], self.TestVar)
            except CmdBuildExp as error:
                raise TestProcessorExp(error)

            sf_uid = sf['userId']

            if not sf_code:
                self.NowRunningTest.Status = "Failed"
                return False
            # Если есть дубликаты в команде ServiceFeature, то выходим
            if sf_uid in already_used_uid:
                logger.error("Duplicated UserId in ServiceFeature item: { UA : %d }",sf_uid)
                self.NowRunningTest.Status = "Failed"
                return False
            else:
                already_used_uid.append(sf_uid)

            # Ищём нужного нам юзера
            try:
                user = self.AutoRegUsers[sf_uid]
            except KeyError:
                logger.error("Can't get User Object with. ID = %d not found.",sf_uid)
                self.NowRunningTest.Status = "Failed"
                return False

            sf_ua = test_class.UserAgentClass()
            sf_ua = sf_ua.GetServiceFetureUA(sf_code,user)
            if not self._build_sipp_sf_command(sf_ua, sf_code):
                self.NowRunningTest.Status = "Failed"
                return False

            self.NowRunningTest.UserAgent.append(sf_ua)

        if not self._start_sipp_processes():
            self.NowRunningTest.Status = "Failed"
            return False

    def _exec_set_variables(self, **variables):
        logger.info("Set next variables: %s", variables)
        self.TestVar.update(variables)

    def _exec_ssh_command(self, cmd_list):
        logger.info("Send SSH commands...")
        try:
            self.CmdBuilder.replace_var_for_list(cmd_list, self.TestVar)
        except CmdBuildExp as error:
            raise TestProcessorExp(error)

        if not self.SSHInt.push_cmd_list_to_ssh(list(cmd_list)):
            logger.error("Executing ccn cmd failed.")
            self.NowRunningTest.Status = "Failed"
            return False
        return True

    @staticmethod
    def _exec_print_cmd(message):
        logging.info("\033[32m[TEST_INFO] %s \033[1;m",message)

    @staticmethod
    def _exec_stop_cmd(self):
        sys.stdin.flush()
        input("\033[1;31m[TEST_INFO] Test stopped. Please press any key to continue...\033[1;m")

    @staticmethod
    def _convert_orderdict(dict,name="GenericDict"):
        return namedtuple(str(name), dict.keys())(**dict)

    @staticmethod
    def _convert_ua2list(convert_str):
        ua_list = []
        if re.match("^[0-9]{1,2}$|^([0-9]{1,2},)+[0-9]{1,2}$", convert_str):
            # Конвертируем старый формат 1,2,3 в новый user:1,user:2,user:3.
            ua_list = list(map(lambda x: x, convert_str.split(",")))
            ua_list = list(map(lambda x: "user:" + str(x), ua_list))
        elif re.match("^(user|trunk):[0-9]{1,2}$|^((user|trunk):[0-9]{1,2},)+(user|trunk):[0-9]{1,2}", convert_str):
            ua_list = convert_str.split(",")
        return ua_list

    def _convert_difference(self, difference):
        if type(difference) is list:
            try:
                self.CmdBuilder.replace_var_for_list(difference, self.TestVar)
            except CmdBuildExp as error:
                raise TestProcessorExp(error)

            try:
                difference = list(map(float, difference))
            except ValueError:
                raise TestProcessorExp("Converting list of differences to float failed. List: %s" %
                                       ",".join(list(map(str, difference))))
            difference = list(map(lambda x: x/1000, difference))
        else:
            if type(difference) is str:
                try:
                    difference = self.CmdBuilder.replace_var(difference, self.TestVar)
                except CmdBuildExp as error:
                    raise TestProcessorExp(error)
            try:
                difference = float(difference)
            except ValueError:
                raise TestProcessorExp("Converting difference %s to float failed." % str(difference))
            difference /= 1000
        return difference

    def _exec_check_difference(self, method_body):
        # Создаём объект для измерения временных интервалов.
        time_meter_obj = TimeDiffMeter()
        for method_item in method_body:
            method_item = Dict2Obj(method_item)
            method_item.Difference = self._convert_difference(method_item.Difference)
            # Try to get call mask
            try:
                method_item.Calls = list(map(lambda x: x-1, method_item.Calls))
            except AttributeError:
                setattr(method_item, "Calls", False)
            # Try to get SearchMode
            try:
                getattr(method_item, "SearchMode")
            except AttributeError:
                setattr(method_item, "SearchMode", "between_calls")
            try:
                getattr(method_item, "MaxError")
            except AttributeError:
                setattr(method_item, "MaxError", 0.1)

            method_item.UA = self._convert_ua2list(method_item.UA)
            try:
                result = time_meter_obj.check_time_difference(method_item, self.NowRunningTest.CompleteUA)
            except TimeDiffMeterExp as error:
                logger.error("CheckDifference failed. Error: %s" % error)
                self.NowRunningTest.Status = "Failed"
                return False
            if not result:
                self.NowRunningTest.Status = "Failed"
                return False
        return True

    def _exec_check_msg_retransmission(self, method_body):
        time_meter_obj = TimeDiffMeter()
        for method_item in method_body:
            # Convert method item to object
            method_item = Dict2Obj(method_item)
            method_item.UA = self._convert_ua2list(method_item.UA)
            # Try to get call mask
            try:
                method_item.Calls = list(map(lambda x: x-1, method_item.Calls))
            except AttributeError:
                setattr(method_item, "Calls", False)
            try:
                result = time_meter_obj.check_timer(method_item, self.NowRunningTest.CompleteUA)
            except TimeDiffMeterExp as error:
                logger.error("CheckRetransmission failed. Error: %s" % error)
                self.NowRunningTest.Status = "Failed"
                return False

            if not result:
                self.NowRunningTest.Status = "Failed"
                return False
        return True

    def _chk_background_ua(self, timer=5):
        if len(self.NowRunningTest.WaitBackGroundUA) > 0:
            logger.info("Waiting for closing threads which started in background mode. Timer = %ds.", timer)
            if not proc.CheckThreads(self.NowRunningTest.BackGroundThreads, timer=timer):
                logger.error("One of Bg UA's thread not closed.")
                self.NowRunningTest.ThreadEvent.clear()
                # Переносим отработавшие UA в завершенные
                self.NowRunningTest.Status = "Failed"
                self.NowRunningTest.CompliteBgUA()
                self._sleep()
            elif not proc.CheckUaStatus(self.NowRunningTest.WaitBackGroundUA):
                # Переносим отработавшие UA в завершенные
                logger.error("One of UAs return bad exit code")
                self.NowRunningTest.Status = "Failed"
                self.NowRunningTest.CompliteBgUA()
                self._sleep()
            else:
                self.NowRunningTest.CompliteBgUA()

    def _send_all_ssh_commands(self):
        if self.NowRunningTest:
            logger.info("Trying send to CCN all commands from test: %s", self.NowRunningTest.Name)
            for item in self.GenForItem:
                if item[0] == "SendSSHCommand":
                    try:
                        self.CmdBuilder.replace_var_for_list(item[1], self.TestVar)
                    except CmdBuildExp as error:
                        logger.error("Send ssh command failed. Error: %s" % error)
                        return
                    self.SSHInt.push_cmd_list_to_ssh(list(item[1]))

    def _reg_manual(self, reg_objects, mode="user"):

        for obj_id in reg_objects.keys():
            # Проверяем, что запрашиваемый юезер существует
            if mode == "user":
                if not int(obj_id) in self.ManualRegUsers.keys():
                    logger.error("Can't find userId: %d in ManualRegUsers dict.", int(obj_id))
            # Проверяем, что запрашиваемый транк существует
            elif mode == "trunk":
                if not int(obj_id) in self.ManualRegTrunks.keys():
                    logger.error("Can't find trunkId: %d in ManualRegTrunks dict.", int(obj_id))

            # Если need_drop не был передан, то выставляем его в False
            if not "need_drop" in reg_objects[obj_id]:
                reg_objects[obj_id]["need_drop"] = False

            # Собираем словарь для регистрируемых объектов
            if mode == "user":
                reg_dict = {user_id: user for user_id, user in self.ManualRegUsers.items() if str(user_id) in reg_objects.keys()}
            elif mode == "trunk":
                reg_dict = {trunk_id: trunk for trunk_id, trunk in self.ManualRegTrunks.items() if str(trunk_id) in reg_objects.keys()}

            # Производим настройку объектов для рагистрации
            for obj_id, obj in reg_dict.items():
                obj.Script = reg_objects[str(obj_id)]["script"]
                # Если есть дополнительные параметры регистрации, то добавляем их
                try:
                    obj.AddRegParams = reg_objects[str(obj_id)]["additional_options"]
                except KeyError:
                    pass
                # Устанавливаем параметры RegContactPort и RegContactIP
                try:
                    obj.RegContactPort = reg_objects[str(obj_id)]["contact_port"]
                except KeyError:
                    obj.RegContactPort = None
                try:
                    obj.RegContactIP = reg_objects[str(obj_id)]["contact_ip"]
                except KeyError:
                    obj.RegContactIP = None
                try:
                    obj.Expires = reg_objects[str(obj_id)]["expires"]
                except KeyError:
                    pass
                # Выставляем флаг разовой регистрации
                obj.RegOneTime = True

        # Запускаем процесс регистрации
        if not self._start_user_registration(reg_dict):
            self.NowRunningTest.Status = "Failed"
        # Собираем в drop_users тех юзеров, которые запросили разрегистрацию
        drop_dict = False
        if mode == "user":
            drop_dict = {user_id: user for user_id, user in reg_dict.items() if reg_objects[str(user_id)]["need_drop"]==True}
        elif mode == "trunk":
            drop_dict = {trunk_id: trunk for trunk_id, trunk in reg_dict.items() if reg_objects[str(trunk_id)]["need_drop"]==True}
        if drop_dict:
            if not self._stop_user_registration(drop_dict):
                self.NowRunningTest.Status = "Failed"

    def _drop_manual_reg(self, obj_id_list, mode):
        drop_dict={}
        for obj_id in obj_id_list:
            if mode == "user":
                if not int(obj_id) in self.ManualRegUsers.keys():
                    logger.error("Can't find userId: %d in ManualRegUsers dict.", int(obj_id))
                    self.NowRunningTest.Status="Failed"
                    return False
                else:
                    drop_dict[int(obj_id)]=self.ManualRegUsers[int(obj_id)]
            elif mode=="trunk":
                if not int(obj_id) in self.ManualRegTrunks.keys():
                    logger.error("Can't find trunkId: %d in ManualRegTrunks dict.", int(obj_id))
                    self.NowRunningTest.Status="Failed"
                    return False
                else:
                    drop_dict[int(obj_id)]=self.ManualRegTrunks[int(obj_id)]
        if not self._stop_user_registration(drop_dict):
            self.NowRunningTest.Status = "Failed"
            return False

    def start(self):
        if not self._start_user_registration(self.AutoRegTrunks):
            self.Status = "Registration Failed"
            self.failed_flag = True
            return False
        else:
            self.Status = "Trunk Registration Complite"
        if not self._start_user_registration(self.AutoRegUsers):
            self.Status = "Registration Failed"
            self.failed_flag = True
            return False
        else:
            self.Status = "User Registration Complite"

        self.Status = "Test pocessing"
        for test in self.Tests:
            logger.info("Start test: %s",test.Name)
            self.NowRunningTest = test
            self.NowRunningTest.Status = "Running"
            self.NowRunningTest.StartTime = time.time()
            self._run_test_procedure(test)
            self.NowRunningTest.StopTime = time.time()
            if self.NowRunningTest.Status == "Failed":
                logger.error("Test: %s failed.",test.Name)
                self.failed_flag = True
                if self.ForceQuitFlag:
                    break
            else:
                logger.info("Test: %s complete.",test.Name)
            logger.info("Statistics for test: %s:",test.Name)
            logger.info("---| Status:          %s", str(test.Status))
            logger.info("---| CompleteUA:      %d", len(test.CompleteUA))
            logger.info("---| BgUA:            %d", len(test.BackGroundUA))
            logger.info("---| StartTime:       %s", str(datetime.fromtimestamp(self.NowRunningTest.StartTime).strftime('%H:%M:%S %Y-%m-%d')))
            logger.info("---| StopTime:        %s", str(datetime.fromtimestamp(self.NowRunningTest.StopTime).strftime('%H:%M:%S %Y-%m-%d')))
            logger.info("---| TestDuration:    %ss", str(test.getTestDuration()))

    def _run_test_procedure(self, test):
        self.GenForItem = self._get_test_item_gen(test.TestProcedure)
        for method, method_desc in self.GenForItem:
            if not test.ThreadEvent.isSet():
                logger.error("Some process thread set event for stop. Drop test procedure...")
                break
            logger.info("Exec method \"%s\"", method)
            try:
                if method == "StartUA":
                    # Передаём параметры startUa в метод _execStartUA
                    self._exec_start_ua(method_desc)
                elif method == "ServiceFeature":
                    self._exec_service_feature(method_desc)
                elif method == "SendSSHCommand":
                    self._exec_ssh_command(method_desc)
                elif method == "Print":
                    self._exec_print_cmd(method_desc)
                elif method == "Stop":
                    self._exec_stop_cmd()
                elif method == "WaitBackGroundUA":
                    self._chk_background_ua(timer=method_desc.get("timeout", 5))
                elif method == "Sleep":
                    self._sleep(method_desc)
                elif method == "CheckDifference":
                    self._exec_check_difference(method_desc)
                elif method == "CheckRetransmission":
                    self._exec_check_msg_retransmission(method_desc)
                elif method == "ManualReg":
                    if "Users" in method_desc:
                        self._reg_manual(method_desc["Users"], "user")
                    elif "Trunks" in method_desc:
                        self._reg_manual(method_desc["Trunks"], "trunk")
                elif method == "DropManualReg":
                    if "Users" in method_desc:
                        self._drop_manual_reg(method_desc["Users"], "user")
                    elif "Trunks" in method_desc:
                        self._drop_manual_reg(method_desc["Trunks"], "trunk")
                elif method == "CompareCDR":
                    self._cdr_compare(method_desc)
                elif method == "SetVar":
                    self._exec_set_variables(**method_desc)
                else:
                    raise TestProcessorExp("Unknown method: %s in test procedure. Test aborting." % method)
                if self.NowRunningTest.Status == "Failed":
                    self._send_all_ssh_commands()
                    break
            except TestProcessorExp as error:
                self.NowRunningTest.Status = "Failed"
                logger.error("Execution of %s failed. Error: %s", method, error)
                self._send_all_ssh_commands()
                break
        self._chk_background_ua()
        if self.NowRunningTest.Status != "Failed":
            self.NowRunningTest.Status = "Complete"
