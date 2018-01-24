import modules.diff_calc as diff_calc
import modules.test_class as test_class
import modules.test_parser as parser
import modules.cocon_interface as ssh
import modules.cmd_builder as builder
import modules.process_contr as proc
import modules.fs_worker as fs
from collections import namedtuple
import re
import sys
import uuid
import time
from datetime import datetime
import threading
import logging

logger = logging.getLogger("tester")
cmd_build = builder.Command_building()


class TestProcessor():
    def __init__(self,**kwargs):
        self.Tests = kwargs["Tests"]
        self.CoconInt = kwargs["CoconInt"]

        #Словарь для сборки команд
        self.TestVar = kwargs["TestVar"]
        #Словари юзеров и транков
        self.Users = kwargs["Users"]
        self.Trunks = kwargs["Trunks"]

        #Словари для объектов с регистрацией
        self.AutoRegTrunks = {trunk_id: trunk for trunk_id,trunk in self.Trunks.items() if trunk.RegType == "out" and trunk.RegMode == "Auto"}
        self.ManualRegTrunks = {trunk_id: trunk for trunk_id,trunk in self.Trunks.items() if trunk.RegType == "out" and trunk.RegMode == "Manual"}
        self.AutoRegUsers = {user_id: user for user_id, user in self.Users.items() if user.RegMode == "Auto"}
        self.ManualRegUsers = {user_id: user for user_id, user in self.Users.items() if user.RegMode == "Manual"}
        self.PjSipUsers = {user_id: user for user_id, user in self.Users.items() if user.RegMode == "pjsip"}

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
        # PjLib
        self.pjlib = None


    def StopTestProcessor(self):
        self.Status = "Stopping test_processor"
        logger.debug("Drop all SIPp processes...")
        #Дропаем процессы
        if self.NowRunningTest != None:
            for ua in self.NowRunningTest.UserAgent + self.NowRunningTest.WaitBackGroundUA:
                for process in ua.Process:
                    if process.poll() == None:
                        process.kill()

        # Разрегистрируем транки
        if self.RegLock and len(self.AutoRegUsers) > 0:
            self._StopUserRegistration(self.AutoRegTrunks)
        # Разрегистрируем юзеров
        if self.RegLock and len(self.AutoRegUsers) > 0:
            self._StopUserRegistration(self.AutoRegUsers)
        # Разрегистрируем pjsip юзеров.
        if len(self.PjSipUsers) > 0:
            self._StopPjUserRegistration(self.PjSipUsers)

        #Для корректного завершения теста нужно выслать все ccn_cmd, которые он не послал.
        self._SendAllCcnCmd()

        #Даём время на сворачивание thread
        self._sleep(0.2)
        return True

    def _ReInitRegObj(self,reg_objects):
        for obj in reg_objects.values():
            obj.RegCSeq = 1
            obj.RegCallId = uuid.uuid4()
            obj.RegContactPort = None
            obj.RegContactIP = None
            obj.AddRegParams = None
            obj.Expires = 90


    def _StopUserRegistration(self,reg_objects):
        logger.info("Drop registration...")
        if not self._buildRegCommands(reg_objects,mode="unreg"):
            return False
        unreg_thread = threading.Thread(target=proc.ChangeUsersRegistration, args=(reg_objects,self.RegLock,"unreg",))
        unreg_thread.start()
        #Даём завершиться thread'у разрегистрации
        unreg_thread.join()
        #Обновляем параметры регистрации
        self._ReInitRegObj(reg_objects)
        if not proc.CheckUserRegStatus(reg_objects):
            return False
        return True

    def _StopPjUserRegistration(self,reg_objects):
        for obj in reg_objects.values():
            obj.PjAccount.set_registration(False)
        for obj in reg_objects.values():
            if not obj.PjAccountCb.check_registration():
                return False
        return True


    def _StartUserRegistration(self, reg_objects):
        if not reg_objects: return True
        if not self._buildRegCommands(reg_objects):
            return False
        self.Status = "Start Registration..."
        #Врубаем регистрацию для всех объектов
        logger.info("Start Registration..")
        self.RegThread  = threading.Thread(target=proc.ChangeUsersRegistration, args=(reg_objects,self.RegLock))
        self.RegThread.start()
        self.RegThread.join()
        if not proc.CheckUserRegStatus(reg_objects):
            return False
        return True

    def _StartPjUserRegistration(self,users):
        if not users: return True
        try:
            import modules.pjsua_fsm as pjfsm
            # Инициализируем pjsua
            self.pjlib = pjfsm.LibPjsua()
        except:
            logger.error("PjSIP not initialized.")
            return False     
        self.Status = "Start Registration for pjsip users..."       
        logger.info("Start Registration for pjsip users..")
        # Создаём аккаунты
        for user in users.values():
            user.SipDomain = cmd_build.replace_key_value(user.SipDomain, self.TestVar)
            user.Registrar = cmd_build.replace_key_value(user.Registrar, self.TestVar)
            user.Proxy = cmd_build.replace_key_value(user.Proxy, self.TestVar)
            try:
                user.PjAccount,user.PjAccountCb = self.pjlib.CreateAccount(user)
            except:
                logger.error("PjSIP accont not created. Start params: SipDom:%s,Reg:%s,Proxy:%s",user.SipDomain,user.Registrar,user.Proxy)
                return False
        for user in users.values():
            if not user.PjAccountCb.check_registration():
                return False
        return True


    def _buildRegCommands(self, reg_objects, mode="reg"):
        if len(reg_objects) > 0:
            #Собираем команды для регистрации абонентов
            if mode =="reg":
                logger.info("Build commands for starting registration...")
            else:
                logger.info("Build commands for stopping registration...")

            for obj in reg_objects.values():
                command = cmd_build.build_reg_command(obj,self.LogPath,self.TestVar,mode=mode)
                if command:
                    if mode=="reg":
                        obj.RegCommand = command 
                    else:
                        obj.UnRegCommand = command 
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
                    logger.error("Duplicate UserId: %d { UA : %s }",int(ua.UserId),ua.Name)
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

    def _buildSippCmd(self):
        logger.info("Build SIPp commands for UA...")
        if not cmd_build.build_sipp_command(self.NowRunningTest,self.TestVar, self.UacDropFlag, self.ShowSipFlowFlag):
            return False
        else:
            return True

    def _buildSippCmdSF(self, serv_feature_ua, sf_code):
        #Собираем команду для активации сервис фичи
        cmd_desc = cmd_build.build_service_feature_command(self.NowRunningTest,serv_feature_ua.UserObject, sf_code, self.TestVar)
        if not cmd_desc:
            return False
        else:
            serv_feature_ua.Commands.append(cmd_desc)
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
        logger.info("Parse UA from test.")
        parse = parser.Parser()
        if not parse.parse_user_agent(self.NowRunningTest,ua_desc):
            self.NowRunningTest.Status = "Failed"
            logger.error("Parse UA failed.")
            return False

        #Линкуем юзеров к юзер агентам
        logger.info("Link UA object with User object...")
        if not self._link_user_to_ua():
            self.NowRunningTest.Status = "Failed"
            logger.error("Link UA object with User object failed.")
            return False

        #Собираем команды для UA.
        if not self._buildSippCmd():
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

        if not self._execSippProcess():
            self.NowRunningTest.Status = "Failed"
            return False
        return True

    def _execServiceFeature(self, sf_desc):
        #Проверка на уникальность uid в serviceFeature cmd
        already_used_uid = []
        for serv_feature in sf_desc:
            sf_code =  cmd_build.replace_key_value(serv_feature['code'], self.TestVar)
            sf_uid  =  serv_feature['userId']

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
            serv_feature_ua = serv_feature_ua.GetServiceFetureUA(sf_code,user)
            if not self._buildSippCmdSF(serv_feature_ua,sf_code):
                self.NowRunningTest.Status = "Failed"
                return False

            self.NowRunningTest.UserAgent.append(serv_feature_ua)

        if not self._execSippProcess():
            self.NowRunningTest.Status = "Failed"
            return False

    def _execCoconCmd(self,cmd_list):
        logger.info("Send SSH commands...")
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

    def _convert_orderdict(self,dict,name="GenericDict"):
        return namedtuple(str(name), dict.keys())(**dict)

    def _convert_old_ua_format(self,convert_str,namedtpl):
        # Конвертируем старый формат 1,2,3 в новый user:1,user:2,user:3.
        ua_for_chk = list(map(lambda x:x, convert_str.split(",")))
        ua_for_chk = list(map(lambda x:"user:"+str(x),ua_for_chk))
        ua_for_chk = list(map(lambda ua: namedtpl(*ua.split(":")) ,ua_for_chk))
        return ua_for_chk

    def _execCheckDifference(self,method_body):
        # Парсим short_msg_log sipp, чтобы рассичитать дифы между сообщениями
        test_diff = diff_calc.diff_timestamp(self.NowRunningTest)
        # Если не удалось пропарсить лог, то выходим.
        if test_diff.Status == "Failed":
            self.NowRunningTest.Status = "Failed"
            return False

        for method_item in method_body:
            # Конвертируем описание метода в namedtuple
            cur_diff = self._convert_orderdict(method_item,name="cur_diff")
            # Если в Difference строка, значит кто-то передал в данный параметр имя переменной,
            # поэтому пытаемся найти данную переменную в словаре и присвоить её зачение переменной req_diff.
            # В противном случае просто приравниваем req_diff к Difference
            if type(cur_diff.Difference) == str:
                req_diff = cmd_build.replace_key_value(cur_diff.Difference, self.TestVar)
            else:
                req_diff = cur_diff.Difference
            #Пытамся привести req_diff к int.
            try:
                if req_diff:
                    req_diff = int(req_diff)
                else:
                    self.NowRunningTest == "Failed"
                    return False
            except ValueError:
                # Если не удалось привести req_diff к int, то выходим.
                self.NowRunningTest == "Failed"
                return False
            # Получаем список UA, для которых будут производиться вычисления.
            # TODO. в дальнейшем нужно избавить в скриптах от старого формата 0,1,2... 
            # После введения транков формат должен быть следующим user:1,trunk:1,user:2...
            # Для обратной совместимости будем обрабатывать все форматы
            ua_info = namedtuple('UaInfo', ['type', 'id'])
            if re.match("^[0-9]{1,2}$|^([0-9]{1,2},)+[0-9]{1,2}$",cur_diff.UA):
                # Обнаружен старый формат, даём warn и конвертим его в новый.
                logger.warning("You are using the old format for the parameter UA in CheckDifference. Please fix it!")
                ua_for_chk = self._convert_old_ua_format(cur_diff.UA,ua_info)
            elif re.match("^(user|trunk):[0-9]{1,2}$|^((user|trunk):[0-9]{1,2},)+(user|trunk):[0-9]{1,2}",cur_diff.UA): 
                ua_for_chk = list(map(lambda ua: ua_info(*ua.split(":")) ,cur_diff.UA.split(",")))
            else:
                # Если передали в неверном формате
                logger.error("Wrong format of: %s",cur_diff.UA)
                self.NowRunningTest == "Failed"
                return False

            # Начинаем попорядку проверять дифы всех сообщений
            for cur_msg in cur_diff.Msg:
                msg_desc = self._convert_orderdict(cur_msg,name="msg_desc")
                # Словарь для хранения параметров сообщения.
                msg_info = {}
                # Забираем тип сообщения
                msg_info["msg_type"] = msg_desc.MsgType.lower()
                # Забираем код ответа, если он присутствует
                msg_info["resp_code"] = None if msg_desc.Code == None else msg_desc.Code
                # Забираем метод сообщения
                msg_info["method"] = msg_desc.Method.upper()
                # Производим расчёт
                test_diff.compare_msg_diff(req_diff,cur_diff.Mode,*ua_for_chk,**msg_info)
                # Ecли расчитанное значение не совпадает с req_diff,
                # то test_diff.Status будет равен false. В этом случае выходим.
                if test_diff.Status == "Failed":
                    self.NowRunningTest.Status = "Failed"
                    return False
        return True

    def _execCheckRetransmission(self,method_body):
        # Парсим short_msg_log sipp, чтобы рассичитать дифы между сообщениями
        test_diff = diff_calc.diff_timestamp(self.NowRunningTest)
        # Если не удалось пропарсить лог, то выходим.
        if test_diff.Status == "Failed":
            self.NowRunningTest.Status = "Failed"
            return False
        for method_item in method_body:
            # Конвертируем описание метода в namedtuple
            cur_retrans = self._convert_orderdict(method_item,name="cur_retrans")
            # Получаем список UA, для которых будут производиться вычисления.
            ua_info = namedtuple('UaInfo', ['type', 'id'])
            if re.match("^[0-9]{1,2}$|^([0-9]{1,2},)+[0-9]{1,2}$",cur_retrans.UA):
                # Обнаружен старый формат, даём warn и конвертим его в новый.
                logger.warning("You are using the old format for the parameter UA in CheckRetransmission. Please fix it!")
                ua_for_chk = self._convert_old_ua_format(cur_retrans.UA,ua_info)
            elif re.match("^(user|trunk):[0-9]{1,2}$|^((user|trunk):[0-9]{1,2},)+(user|trunk):[0-9]{1,2}",cur_retrans.UA): 
                ua_for_chk = list(map(lambda ua: ua_info(*ua.split(":")) ,cur_retrans.UA.split(",")))
            else:
                # Если передали в неверном формате
                logger.error("Wrong format of: %s",cur_retrans.UA)
                self.NowRunningTest == "Failed"
                return False
            # Начинаем попорядку проверять перепосылки всех сообщений
            for cur_msg in cur_retrans.Msg:
                msg_desc = self._convert_orderdict(cur_msg,name="msg_desc")
                # Словарь для хранения параметров сообщения.
                msg_info = {}
                # Забираем тип сообщения
                msg_info["msg_type"] = msg_desc.MsgType.lower()
                # Забираем код ответа, если он присутствует
                msg_info["resp_code"] = None if msg_desc.Code == None else msg_desc.Code
                # Забираем метод сообщения
                msg_info["method"] = msg_desc.Method.upper()
                # Сравниваем числовую последовательность, полученную от UA
                # C требуемой последовательностью для текущего таймера.
                test_diff.compare_timer_seq(cur_retrans.Timer,*ua_for_chk,**msg_info)
                # Ecли рассчитая последовательность не совпадает с требуемой,
                # то test_diff.Status будет равен false. В этом случае выходим.
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

    def _SendAllCcnCmd(self):
        if self.NowRunningTest != None:
            logger.info("Trying send to CCN all commands from test: %s",self.NowRunningTest.Name)
            for item in self.GenForItem:
                if item[0] == "SendSSHCommand":
                    ssh.cocon_configure(item[1],self.CoconInt,self.TestVar)

    def _RegManual(self, reg_objects, mode="user"):

        for obj_id in reg_objects.keys():
            #Проверяем, что запрашиваемый юезер существует
            if mode == "user":
                if not int(obj_id) in self.ManualRegUsers.keys():
                    logger.error("Can't find userId: %d in ManualRegUsers dict.", int(obj_id))
            #Проверяем, что запрашиваемый транк существует
            elif mode == "trunk":
                if not int(obj_id) in self.ManualRegTrunks.keys():
                    logger.error("Can't find trunkId: %d in ManualRegTrunks dict.", int(obj_id))

            #Если need_drop не был передан, то выставляем его в False
            if not "need_drop" in reg_objects[obj_id]:
                reg_objects[obj_id]["need_drop"] = False

            #Собираем словарь для регистрируемых объектов
            if mode == "user":
                reg_dict = {user_id: user for user_id, user in self.ManualRegUsers.items() if str(user_id) in reg_objects.keys()}
            elif mode == "trunk":
                reg_dict = {trunk_id: trunk for trunk_id, trunk in self.ManualRegTrunks.items() if str(trunk_id) in reg_objects.keys()}

            #Производим настройку объектов для рагистрации
            for obj_id, obj in reg_dict.items():
                obj.Script = reg_objects[str(obj_id)]["script"]
                #Если есть дополнительные параметры регистрации, то добавляем их
                try:
                    obj.AddRegParams = reg_objects[str(obj_id)]["additional_options"]
                except KeyError:
                    pass
                #Устанавливаем параметры RegContactPort и RegContactIP
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
                #Выставляем флаг разовой регистрации
                obj.RegOneTime = True

        #Запускаем процесс регистрации
        if not self._StartUserRegistration(reg_dict):
            self.NowRunningTest.Status="Failed"
        #Собираем в drop_users тех юзеров, которые запросили разрегистрацию
        if mode == "user":
            drop_dict = {user_id: user for user_id, user in reg_dict.items() if reg_objects[str(user_id)]["need_drop"]==True}
        elif mode == "trunk":
            drop_dict = {trunk_id: trunk for trunk_id, trunk in reg_dict.items() if reg_objects[str(trunk_id)]["need_drop"]==True}
        if drop_dict:
            if not self._StopUserRegistration(drop_dict):
                self.NowRunningTest.Status="Failed"

    def _DropManualReg(self, obj_id_list,mode):
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
        if not self._StopUserRegistration(drop_dict):
            self.NowRunningTest.Status="Failed"
            return False

    def StartTestProcessor(self):
        if not self._StartUserRegistration(self.AutoRegTrunks):
            self.Status == "Registration Failed"
            self.failed_flag = True
            return False
        else:
            self.Status = "Trunk Registration Complite"

        if not self._StartUserRegistration(self.AutoRegUsers):
            self.Status == "Registration Failed"
            self.failed_flag = True
            return False
        if not self._StartPjUserRegistration(self.PjSipUsers):
            self.Status == "Registration Failed"
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
            if not test.ThreadEvent.isSet():
                logger.error("Some process thread set event for stop. Drop test procedure...")
                break
            logger.info("Exec method \"%s\"",item[0])
            if item[0] == "StartUA":
                #Передаём параметры startUa в метод _execStartUA
                self._execStartUA(item[1])
            elif item[0] == "ServiceFeature":
                self._execServiceFeature(item[1])
            elif item[0] == "SendSSHCommand":
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
                if "Users" in item[1]:
                    self._RegManual(item[1]["Users"],"user")
                elif "Trunks" in item[1]:
                    self._RegManual(item[1]["Trunks"],"trunk")
            elif item[0] == "DropManualReg":
                if "Users" in item[1]:
                    self._DropManualReg(item[1]["Users"],"user")
                elif "Trunks" in item[1]:
                    self._DropManualReg(item[1]["Trunks"],"trunk")
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