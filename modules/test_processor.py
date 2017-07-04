import modules.diff_calc as diff_calc
import modules.test_class as test_class
import modules.test_parser as parser
import modules.cocon_interface as ssh
import modules.cmd_builder as builder
import modules.process_contr as proc
import modules.fs_worker as fs
import sys
import time
from datetime import datetime
import threading
import logging
logger = logging.getLogger("tester")

class TestProcessor():
    def __init__(self,**kwargs):
        self.Tests = kwargs["Tests"]
        self.CoconInt = kwargs["CoconInt"]

        #Словарь для сборки команд
        self.TestVar = kwargs["TestVar"]
        #Объекты юзеров и транков
        self.Users = kwargs["Users"]
        self.AutoRegUsers = {user_id: user for user_id, user in kwargs["Users"].items() if user.Mode == "Auto"}
        self.ManualRegUsers = {user_id: user for user_id, user in kwargs["Users"].items() if user.Mode == "Manual"}
        self.Trunks = kwargs["Trunks"]

        #Генератор Item для TestProcedure
        self.GenForTest = None
        self.GenForItem = None

        #Флаги
        self.ShowSipFlowFlag = kwargs["ShowSipFlowFlag"]
        self.UacDropFlag = kwargs["UacDropFlag"]
        self.ForceQuitFlag = kwargs["ForceQuitFlag"]

        #Paths
        self.LogPath = kwargs["LogPath"]
        #Реалтайм параметры
        self.Status = "New"
        self.NowRunningTest = None
        self.NowRunningThreads = []

        #Регистрации юзеров
        self.RegLock = threading.Lock()
        self.RegThread = None

        self.failed_flag = False


    def StopTestProcessor(self):
        self.Status = "Stopping test_processor"

        #Для корректного завершения теста нужно выслать все ccn_cmd, которые он непослал.
        self._SendAllCcnCmd()
        logger.debug("Drop all SIPp processes...")
        
        #Дропаем процессы
        if self.NowRunningTest != None:
            for ua in self.NowRunningTest.UserAgent + self.NowRunningTest.WaitBackGroundUA:
                for process in ua.Process:
                    if process.poll() == None:
                        process.kill()

        #Разрегистрируем юзеров
        if self.RegLock and len(self.AutoRegUsers) > 0:
            self._StopUserRegistration(self.AutoRegUsers)

        logger.info("Close log files...")
        if self.Tests:
            for test in self.Tests:
                for ua in test.CompliteUA:
                    if ua.LogFd:
                        ua.LogFd.close()
        #Даём время на сворачивание thread
        self._sleep(0.2)
        return True

    def _StopUserRegistration(self, reg_users):
        logger.info("Drop registration of users.")
        unreg_thread = threading.Thread(target=proc.ChangeUsersRegistration, args=(reg_users,self.RegLock,"unreg",))
        unreg_thread.start()
        #Даём завершиться thread'у разрегистрации
        unreg_thread.join()
        if not proc.CheckUserRegStatus(reg_users):
            return False
        return True

    def _StartUserRegistration(self, reg_users):
        self.Status = "Register users"
        if not self._buildRegCommands(reg_users):
            return False
        #Врубаем регистрацию для всех юзеров
        logger.info("Starting of registration...")
        #Декларируем массив для thread регистрации
        for user in reg_users.items():
            log_file = fs.open_log_file("REG_" + str(user[1].Number),self.LogPath)
            #Если не удалось создать лог файл, то выходим
            if not log_file:
                return False
            else:
                user[1].RegLogFile = log_file

        self.RegThread  = threading.Thread(target=proc.ChangeUsersRegistration, args=(reg_users,self.RegLock))
        self.RegThread.start()
        self.RegThread.join()
        if not proc.CheckUserRegStatus(reg_users):
            return False
        return True


    def _buildRegCommands(self, users):
        if len(users) > 0:
            #Собираем команды для регистрации абонентов
            logger.info("Building of registration command for UA...")
            for user in users.values():
                command = builder.build_reg_command(user,self.TestVar)
                if command:
                    user.RegCommand = command
                else:
                    return False

            #Собираем команды для сброса регистрации абонентов
            logger.info("Building command for dropping of users registration...")
            for user in users.values():
                command = builder.build_reg_command(user,self.TestVar,"unreg")
                if command:
                    user.UnRegCommand = command
                else:
                    return False
        return True

    def _getTestItemGen(self,Test):
        for item in Test:
            for method in item.items():
                yield method

    def _link_user_to_ua(self):
        #Массив для использованных id
        use_id = []
        for ua in self.NowRunningTest.UserAgent + self.NowRunningTest.BackGroundUA:
            if ua.Type == "User":
                if not ua.UserId in use_id:
                    use_id.append(ua.UserId)
                    try:
                        ua.UserObject = self.AutoRegUsers[ua.UserId]
                    except KeyError:
                        logger.error("User with id = %d not found { UA : %s }",int(ua.UserId),ua.Name)
                        return False
                else:
                    logger.error("Duplicate UserId: %d { UA : %s }",int(ua.UserId),ua.Name)
                    return False
        return True

    def _createLogFiles(self):
        logger.info("Creating log files for UA...")
        for ua in self.NowRunningTest.UserAgent + self.NowRunningTest.BackGroundUA:
            filename = ua.Name + "_TEST" + str(self.NowRunningTest.TestId)
            log_fd = fs.open_log_file(filename,self.LogPath)
            if log_fd:
                logger.info("File %s created.",filename)
                ua.LogFd = log_fd
            else:
                return False
        return True



    def _buildSippCmd(self):
        logger.info("Building SIPp commands for UA...")
        if not builder.build_sipp_command(self.NowRunningTest,self.TestVar, self.UacDropFlag, self.ShowSipFlowFlag):
            return False
        else:
            return True

    def _buildSippCmdSF(self, serv_feature_ua, sf_code):
        #Собираем команду для активации сервис фичи
        command = builder.build_service_feature_command(serv_feature_ua.UserObject, sf_code, self.TestVar)
        if not command:
            return False
        else:
            serv_feature_ua.Commands.append(command)
            return True

    def _sleep(self,timeout = 32):
        logger.info("Sleep on %ss",str(round(float(timeout),1)))
        time.sleep(float(timeout))

    def _execSippProcess(self):
        self.NowRunningThreads = proc.start_process_controller(self.NowRunningTest)
        if len(self.NowRunningTest.UserAgent) > 0:
            logger.info("Waiting for closing threads...")
            if not proc.CheckThreads(self.NowRunningThreads):
                logger.error("One of UA's thread not closed.")
                #Останавливаем все thread
                self.NowRunningTest.ThreadEvent.clear()
                #Переносим отработавшие UA в завершенные
                self.NowRunningTest.ReplaceUaToComplite()
                #Даём thread завершиться
                self._sleep()
                return False

            #Проверяем UA на статусы
            logger.info("Check process StatusCode...")
            if not proc.CheckUaStatus(self.NowRunningTest.UserAgent):
                #Переносим отработавшие UA в завершенные
                logger.error("One of UAs return bad exit code")
                self.NowRunningTest.ReplaceUaToComplite()
                self._sleep()
                return False

            self.NowRunningTest.ReplaceUaToComplite()
        return True

    def _execStartUA(self, ua_desc):
        logger.info("Parsing UA from test.")
        if not parser.parse_user_agent(self.NowRunningTest,ua_desc):
            self.NowRunningTest.Status = "Failed"
            logger.error("Parsing UA failed.")
            return False

        #Линкуем юзеров к юзер агентам
        logger.info("Linking UA object with User object...")
        if not self._link_user_to_ua():
            self.NowRunningTest.Status = "Failed"
            logger.error("Linking UA object with User object failed.")
            return False

        #Собираем команды для UA.
        if not self._buildSippCmd():
            self.NowRunningTest.Status = "Failed"
            logger.error("Building SIPp commands failed.")
            return False

        if not self._createLogFiles():
            self.NowRunningTest.Status = "Failed"
            logger.error("Creating log files for UA failed.")
            return False

        for ua in self.NowRunningTest.UserAgent + self.NowRunningTest.BackGroundUA:
            logging.info("PortInfo for UA: %s", ua.Name)
            logging.info("---| UA Type:     %s", str(ua.Type))
            if ua.Type == "User":
                logging.info("---| UA Number:   %s", str(ua.UserObject.Number))
                logging.info("---| UA Port:     %s", str(ua.UserObject.Port))
                logging.info("---| UA RtpPort:  %s", str(ua.UserObject.RtpPort))
            elif ua.Type == "Trunk":
                logging.info("---| UA Port:     %s", str(ua.Port))

        if not self._execSippProcess():
            self.NowRunningTest.Status = "Failed"
            return False
        return True

    def _execServiceFeature(self, sf_desc):
        #Проверка на уникальность uid в serviceFeature cmd
        already_used_uid = []
        for serv_feature in sf_desc:
            sf_code =  builder.replace_key_value(serv_feature['code'], self.TestVar)
            sf_uid  =  int(serv_feature['userId'])

            if not sf_code:
                self.NowRunningTest.Status = "Failed"
                return False
            #Если есть дубликаты в команде ServiceFeature, то выходим
            if sf_uid in already_used_uid:
                logger.error("Duplicated UserId in ServiceFeature item: { UA : %d }",sf_uid)
                self.NowRunningTest.Status = "Failed"
                return False
            else:
                already_used_uid.append(sf_uid)

            #Ищём нужного нам юзера
            try:
                user = self.AutoRegUsers[sf_uid]
            except KeyError:
                logger.error("Can't get User Object with. ID = %d not found.",sf_uid)
                self.NowRunningTest.Status = "Failed"
                return False

            serv_feature_ua = test_class.UserAgentClass()
            serv_feature_ua =serv_feature_ua.GetServiceFetureUA(sf_code,user)
            if not self._buildSippCmdSF(serv_feature_ua,sf_code):
                self.NowRunningTest.Status = "Failed"
                return False

            self.NowRunningTest.UserAgent.append(serv_feature_ua)

        if not self._createLogFiles():
            self.NowRunningTest.Status = "Failed"
            logger.error("Creating log files for ua failed.")
            return False

        if not self._execSippProcess():
            self.NowRunningTest.Status = "Failed"
            return False

    def _execCoconCmd(self,cmd_list):
        logger.info("Send commands to CoCon...")
        if not ssh.cocon_configure(cmd_list,self.CoconInt,self.TestVar):
            logger.error("Executing ccn cmd failed.")
            self.NowRunningTest.Status = "Failed"
            return False
        return True

    def _execPrintCmd(self, message):
        logging.info("\033[32m[TEST_INFO] %s \033[1;m",message)

    def _execStopCmd(self):
        sys.stdin.flush()
        input("\033[1;31m[TEST_INFO] Test stopped. Please press any key to continue...\033[1;m")

    def _execCheckDifference(self,diff_desc):
        test_diff = diff_calc.diff_timestamp(self.NowRunningTest)

        if test_diff.Status == "Failed":
            self.NowRunningTest.Status = "Failed"
            return False

        for diff_item in diff_desc:
            msg_info = {}
            req_diff = diff_item["Difference"]
            req_diff = builder.replace_key_value(req_diff, self.TestVar)
            diff_mode = diff_item["Mode"]
            msg_info["msg_type"] = diff_item["Msg"][0]["MsgType"].lower()
            if diff_item["Msg"][0]["Code"] == "None":
                msg_info["resp_code"] = None
            else:
                msg_info["resp_code"] = diff_item["Msg"][0]["Code"]

            msg_info["method"] = diff_item["Msg"][0]["Method"].upper()
            chk_ua = list(map(int,diff_item["UA"].split(",")))
            test_diff.compare_msg_diff(req_diff,diff_mode,*chk_ua,**msg_info)

            if test_diff.Status == "Failed":
                self.NowRunningTest.Status = "Failed"
                return False
        return True

    def _execCheckRetransmission(self, retrans_desc):
        test_diff = diff_calc.diff_timestamp(self.NowRunningTest)

        if test_diff.Status == "Failed":
            self.NowRunningTest.Status = "Failed"
            return False

        for diff_item in retrans_desc:
            msg_info = {}
            timer_name = diff_item["Timer"]
            msg_info["msg_type"] = diff_item["Msg"][0]["MsgType"].lower()
            if diff_item["Msg"][0]["Code"] == "None":
                msg_info["resp_code"] = None
            else:
                msg_info["resp_code"] = diff_item["Msg"][0]["Code"]
                
            msg_info["method"] = diff_item["Msg"][0]["Method"].upper()
            chk_ua = list(map(int,diff_item["UA"].split(",")))
            test_diff.compare_timer_seq(timer_name,*chk_ua,**msg_info)

            if test_diff.Status == "Failed":
                self.NowRunningTest.Status = "Failed"
                return False
        return True

    def _ChkBackgroundUA(self):
        if len(self.NowRunningTest.WaitBackGroundUA) > 0:
            logger.info("Waiting for closing threads which started in background mode...")
            if not proc.CheckThreads(self.NowRunningTest.BackGroundThreads):
                logger.error("One of Bg UA's thread not closed.")
                self.NowRunningTest.ThreadEvent.clear()
                #Переносим отработавшие UA в завершенные
                self.NowRunningTest.Status = "Failed"
                self.NowRunningTest.CompliteBgUA()
                self._sleep()
            elif not proc.CheckUaStatus(self.NowRunningTest.WaitBackGroundUA):
                #Переносим отработавшие UA в завершенные
                logger.error("One of UAs return bad exit code")
                self.NowRunningTest.Status = "Failed"
                self.NowRunningTest.CompliteBgUA()
                self._sleep()
            else:
                self.NowRunningTest.CompliteBgUA()

    def _SendAllCcnCmd(self):
        if self.NowRunningTest != None:
            logger.info("Trying send to CCN all commands from test: %s",self.NowRunningTest.Name)
            for item in self.GenForItem:
                if item[0] == "CoconCommand":
                    ssh.cocon_configure(item[1],self.CoconInt,self.TestVar)

    def _RegUserManual(self, reg_scripts):
        for user_id, mode in  reg_scripts.items():
            if not int(user_id) in self.ManualRegUsers.keys():
                logger.error("Can't find userId: %d in ManualRegUsers dict.", int(user_id))
                self.NowRunningTest.Status="Failed"
                return 1
        reg_users = {user_id: user for user_id, user in self.ManualRegUsers.items() if str(user_id) in reg_scripts.keys()}
        for user_id, user in reg_users.items():
            user.Script = reg_scripts[str(user_id)]["script"]
            #Выставляем флаг разовой регистрации
            user.RegOneTime = True
        #Запускаем процесс регистрации
        if not self._StartUserRegistration(reg_users):
            self.NowRunningTest.Status="Failed"
        drop_users = {user_id: user for user_id, user in reg_users.items() if reg_scripts[str(user_id)]["need_drop"]=="True"}
        if not self._StopUserRegistration(drop_users):
            self.NowRunningTest.Status="Failed"






    def StartTestProcessor(self):
        if not self._StartUserRegistration(self.AutoRegUsers):
            self.Status == "Registration Failed"
            self.failed_flag = True
            return False
        else:
            self.Status = "Registration Complite"

        self.Status = "Test pocessing"
        for test in self.Tests:
            logger.info("Start test: %s",test.Name)
            self.NowRunningTest = test
            self.NowRunningTest.Status = "Running"
            self.NowRunningTest.StartTime = time.time()
            self._RunTestProcedure(test)
            self.NowRunningTest.StopTime = time.time()
            if self.NowRunningTest.Status == "Failed":
                logger.error("Test: %s failed.",test.Name)
                self.failed_flag = True
                if self.ForceQuitFlag:
                    break
            else:
                logger.info("Test: %s complite.",test.Name)
            logger.info("Statistics for test: %s:",test.Name)
            logger.info("---| Status:          %s", str(test.Status))
            logger.info("---| CompliteUA:      %d", len(test.CompliteUA))
            logger.info("---| CompliteBgUA:    %d", len(test.BackGroundUA))
            logger.info("---| StartTime:       %s", str(datetime.fromtimestamp(self.NowRunningTest.StartTime).strftime('%H:%M:%S %Y-%m-%d')))
            logger.info("---| StopTime:        %s", str(datetime.fromtimestamp(self.NowRunningTest.StopTime).strftime('%H:%M:%S %Y-%m-%d')))
            logger.info("---| TestDuration:    %ss", str(test.getTestDuration()))


    def _RunTestProcedure(self, test):
        self.GenForItem = self._getTestItemGen(test.TestProcedure)
        for item in self.GenForItem:
            logger.info("Exec method \"%s\"",item[0])
            if item[0] == "StartUA":
                #Передаём параметры startUa в метод _execStartUA
                self._execStartUA(item[1])
            elif item[0] == "ServiceFeature":
                self._execServiceFeature(item[1])
            elif item[0] == "CoconCommand":
                self._execCoconCmd(item[1])
            elif item[0] == "Print":
                self._execPrintCmd(item[1])
            elif item[0] == "Stop":
                self._execStopCmd()
            elif item[0] == "Sleep":
                self._sleep(item[1])
            elif item[0] == "CheckDifference":
                self._execCheckDifference(item[1])
            elif item[0] == "CheckRetransmission":
                self._execCheckRetransmission(item[1])
            elif item[0] == "ManualReg":
                self._RegUserManual(item[1])
            else:
                logger.error("Unknown metod: %s in test procedure. Test aborting.",item[0])
                self.NowRunningTest.Status = "Failed"
                break
            if self.NowRunningTest.Status == "Failed":
                self._SendAllCcnCmd()
                break
        self._ChkBackgroundUA()
        if self.NowRunningTest.Status != "Failed":
            self.NowRunningTest.Status = "Complite"