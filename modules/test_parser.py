import modules.test_class as testClass
from jsonschema import Draft4Validator
from os import listdir
import json
import sys
import logging
import pprint
import re
logger = logging.getLogger("tester")

class Validator:

    def __init__(self):
        #Словарь для хранения содержимого схем
        self.schemas_data = {}
        #Директория, в которой хранятся схемы
        self.schemas_directory = "/schema/"
        #Кортеж глобальных секций
        self.global_sections = ("Users","UserVar","PreConf","PostConf", "Trunks")
        #Кортеж тестовых процедур
        self.simple_procedure_sections = ("Sleep","Print","Stop","ServiceFeature","ManualReg","DropManualReg","SendSSHCommand") 

    #Метод записи информации схем в словарь
    def schemas_dict_forming(self, py_sipp_path):
        path_to_schemas_directory = py_sipp_path + self.schemas_directory
        for schema_file in listdir(path_to_schemas_directory):
            file_path = path_to_schemas_directory + schema_file
            file = open(file_path, "r", encoding="utf-8")
            try:
                schema = json.loads(file.read())
            except json.decoder.JSONDecodeError:
                file.close
                logger.error("Wrong schema format in %s file. Detail: %s" % (schema_file, sys.exc_info()[1]))
                sys.exit(1)
            else:
                self.schemas_data[schema_file] = schema
                file.close

    def pretty_print(self, section, error_path, isreq=False, error_key=None):
        log_prefix = "  "
        error_tag = "__ERROR_TAG__"
        for path in error_path:
            section = section[path]
        if not isreq:
            section[error_key] = str(section[error_key]) + error_tag
        error_lines = pprint.pformat(section).split('\n')
        for line in error_lines:
            line=line.replace(r'        ','  ')
            line=line.replace('OrderedDict','')
            if line.find(error_tag) != -1:
                line=line.replace(error_tag,"")
                line=str("\033[1;31m" + line +  "\033[1;m")
            line = log_prefix + line
            logger.info(line)

    def validate_sections(self, section, section_schema, section_name):
        errors = sorted(Draft4Validator(section_schema).iter_errors(section), key=lambda e: e.path)
        if errors:
            logger.error("Validation error in section %s:" % section_name)
            for e in errors:
                error_path = e.path
                if "is a required property" in e.message:
                    self.pretty_print(section, error_path, isreq=True)
                else:
                    if section_name == "PreConf" or section_name == "PostConf" or section_name == "SendSSHCommand":
                        if len(error_path) == 2 or len(error_path) == 3:
                            error_path_ = error_path
                            dummy = error_path_.pop()
                            self.pretty_print(section, error_path_, isreq=True)
                        else:
                            self.pretty_print(section, error_path, isreq=True)
                    else:
                        try:
                            error_key = error_path.pop()
                            self.pretty_print(section, error_path, error_key=error_key)
                        except IndexError:
                            print(e)
                logger.info("Error description: \033[1;31m%s\033[1;m" % e.message)
                sys.exit(1)

    def validate_difference(self, diff, section):
        try:
            diff["Difference"]
        except KeyError:
            pass
        else:
            if type(diff["Difference"]) == str: 
                if re.search("^\%\%[a-zA-Z-0-9_]+\%\%$",diff["Difference"]) == None:
                    logger.error("Validation error in section CheckDifference:")
                    self.pretty_print(section, [], error_key="Difference")
                    logger.error("Error description: \033[1;31mDifference must be number or var (var pattern = ^%%[a-zA-Z-0-9_]+%%$)\033[1;m")
                    sys.exit(1)
            elif type(diff["Difference"]) != float and type(diff["Difference"]) != int:
                loger.error("Validation error in section CheckDifference:")
                self.pretty_print(section, [], error_key="Difference")
                logger.info("Error description: \033[1;31mDifference must be number or var (var pattern = ^%%[a-zA-Z-0-9_]+%%$)\033[1;m")
                sys.exit(1)
            elif diff["Difference"] < 0:
                logger.error("Validation error in section CheckDifference:")
                self.pretty_print(section, [], error_key="Difference")
                logger.info("Error description: \033[1;31mDifference must be greater or equal than zero\033[1;m")
                sys.exit(1)

    def validate_msg_code(self, msg, section):
        try:
            msg["Code"]
        except KeyError:
            logger.error("Validation error in section Msg:")
            self.pretty_print(section, [], isreq=True)
            logger.info("Error description: \033[1;31mCode is a required property\033[1;m")
            sys.exit(1) 
        if msg["MsgType"] == "request" and msg["Code"] != None:
            logger.error("Validation error in section Msg:")
            self.pretty_print(section, ["Msg",0], error_key="Code")
            logger.info("Error description: \033[1;31mCode must be null then MsgType=request\033[1;m")
            sys.exit(1)
        if msg["MsgType"] == "response":
            if type(msg["Code"]) != int:
                logger.error("Validation error in section Msg")
                self.pretty_print(section, ["Msg",0], error_key="Code")
                logger.info("Error description: \033[1;31mCode must be integer then MsgType=response\033[1;m")
                sys.exit(1)
            elif msg["Code"] < 100 or msg["Code"] > 699:
                logger.error("Validation error in section Msg:")
                self.pretty_print(section, ["Msg",0], error_key="Code")
                logger.info("Error description: \033[1;31mCode should match the range of 100 and 699\033[1;m")
                sys.exit(1)
    
    def validate_startua_type(self, items):
        if items["Type"] == "User":
            try:
                items["UserId"]
            except KeyError:
                logger.error("Validation error in section StartUA:")
                self.pretty_print(items,[],isreq=True)
                logger.info("Error description: \033[1;31mUserId is a required property then Type=User\033[1;m")
                sys.exit(1)
        if items["Type"] == "Trunk":
            try:
                items["TrunkId"]
            except KeyError:
                logger.error("Validation error in StartUA:")
                self.pretty_print(items,[],isreq=True)
                logger.info("Error description: \033[1;31mTrunkId is a required property then Type=Trunk\033[1;m")
                sys.exit(1)

    def validation_tests(self, json_file):
        #Валидация глобальных свойств
        if not "TestName" in json_file:
            logger.error("Validation error in global section: \033[1;31mTestName is a required property\033[1;m")
            sys.exit(1)
        elif type(json_file["TestName"]) != str or len(json_file["TestName"]) == 0:
            logger.error("Validation error in global section: \033[1;31mTestName must be non-zero string\033[1;m")
            sys.exit(1)  
        if "AutoTest" in json_file and type(json_file["AutoTest"]) != bool:
            logger.error("Validation error in global section: \033[1;31mAutoTest must be bool\033[1;m")
            sys.exit(1) 
        if "Isolate" in json_file and type(json_file["Isolate"]) != bool:
            logger.error("Validation error in global section: \033[1;31mIsolate must be bool\033[1;m")
            sys.exit(1)
        #Валидация глобальных секций
        for section in self.global_sections:
            if section in json_file:
                self.validate_sections(json_file[section], self.schemas_data[section], section)
        if not "Tests" in json_file:
            logger.error("Validation error in global section: \033[1;31mTests is required a property\033[1;m")
            sys.exit(1)
        else:
            #Валидация тестов
            for test in json_file["Tests"]:
                if "Name" in test:
                    if type(test["Name"]) != str or len(test["Name"]) == 0:
                        logger.error("Validation error in section Tests: \033[1;31mName must be non-zero string\033[1;m")
                        sys.exit(1)
                if "Description" in test:
                    if type(test["Description"]) != str or len(test["Description"]) == 0:
                        logger.error("Validation error in section Tests: \033[1;31mDescription must be non-zero string\033[1;m")
                        sys.exit(1)
                if not "TestProcedure" in test:
                    logger.error("Validation error in section Tests: \033[1;31mTestProcedure is a required property\033[1;m")
                    sys.exit(1)
                else:
                    #Валидация тестовых процедур
                    for procedure in test["TestProcedure"]:
                        if "CheckRetransmission" in procedure:
                            self.validate_sections(procedure["CheckRetransmission"], self.schemas_data["CheckRetransmission"],"CheckRetransmission")
                            if not "Msg" in procedure["CheckRetransmission"][0]:
                                logger.error("Validation error in section CheckRetransmission: \033[1;31mMsg is a required property\033[1;m")
                                sys.exit(1)
                            else:
                                self.validate_sections(procedure["CheckRetransmission"][0]["Msg"], self.schemas_data["Msg"], "CheckRetransmission")
                                self.validate_msg_code(procedure["CheckRetransmission"][0]["Msg"][0], procedure["CheckRetransmission"][0])
                        if "CheckDifference" in procedure:
                            self.validate_sections(procedure["CheckDifference"], self.schemas_data["CheckDifference"], "CheckDifference")
                            self.validate_difference(procedure["CheckDifference"][0], procedure["CheckDifference"][0])
                            if not "Msg" in procedure["CheckDifference"][0]:
                                logger.error("Validation error in section CheckDifference: \033[1;31mMsg is a required property\033[1;m")
                                sys.exit(1)
                            else:
                                self.validate_sections(procedure["CheckDifference"][0]["Msg"], self.schemas_data["Msg"], "CheckDifference")
                                self.validate_msg_code(procedure["CheckDifference"][0]["Msg"][0], procedure["CheckDifference"][0])
                        if "StartUA" in procedure:
                            self.validate_sections(procedure, self.schemas_data["StartUA"], "StartUA")
                            for items in procedure["StartUA"]:
                                self.validate_startua_type(items)
                                if not "Commands" in items:
                                    logger.error("Validation error in section StartUA: Commands is a required property")
                                    sys.exit(1)
                                else:
                                    self.validate_sections(items["Commands"], self.schemas_data["Commands"], "StartUA")
                        for section in self.simple_procedure_sections:
                            if section in procedure:
                                self.validate_sections(procedure, self.schemas_data[section], section)
        return True

class Parser:
    def parse_trunk_info(self,json_trunks):
        #словарь для хранения транков
        trunks={}
        for trunk in json_trunks:
            new_trunk = testClass.TrunkClass()
            new_trunk.Status = "New"
            new_trunk.TrunkId = trunk["TrunkId"]
            new_trunk.SipDomain = trunk["SipDomain"]
            new_trunk.SipGroup = trunk["SipGroup"]
            new_trunk.Port = trunk["Port"]
            new_trunk.TrunkName = trunk["TrunkName"]
            try:
                new_trunk.RemotePort = trunk["RemotePort"]
            except:
                pass
            try:
                new_trunk.SipTransport = trunk["SipTransport"]
            except KeyError:
                pass
            try:
                new_trunk.RtpPort = trunk["RtpPort"]
            except KeyError:
                pass
            try:
                new_trunk.RegType = trunk["RegType"]
            except:
                pass
            try:
                new_trunk.Login = trunk["Login"]
            except:
                pass
            try:
                new_trunk.Password = trunk["Password"]
            except:
                pass
            try:
                new_trunk.Expires = trunk["Expires"]
            except:
                new_trunk.Expires = 90
            try:
                new_trunk.QParam = trunk["QParam"]
            except:
                new_trunk.QParam = 1
            try:
                new_trunk.RegMode = trunk["RegMode"]
            except KeyError:
                new_trunk.RegMode = "Manual"
            try:
                new_trunk.BindPort = trunk["BindPort"]
            except:
                pass
            #Если есть два транка с одинаковыми id, выходим
            if new_trunk.TrunkId in trunks:
                logger.error("TrunkId = %d is already in use", new_trunk.TrunkId)
                return False
            #Если два транка используют одинаковые порты, то выходим:
            if {trunkId: trunk for trunkId,trunk in trunks.items() if trunk.Port == new_trunk.Port}:
                logger.error("Trunk Port = %d is already in use. TrunkId: %d", new_trunk.Port,new_trunk.TrunkId)
                return False
            trunks[new_trunk.TrunkId] = new_trunk
        return trunks

    def parse_user_info(self, json_users):
        #Создаём словарь для хранения юзеров
        users = {}
        #Перебераем всех юзеров, описанных в секции Users
        for user in json_users:
            #Создаём нового пользователя
            new_user = testClass.UserClass()
            #Обработка обязательных свойств
            new_user.Status = "New"
            new_user.UserId = user["UserId"]
            new_user.Number = user["Number"]
            new_user.Login = user["Login"]
            new_user.Password = user["Password"]
            new_user.SipDomain = user["SipDomain"]
            new_user.SipGroup = user["SipGroup"]
            new_user.Port = user["Port"]
            #Обработка опциональных свойств
            try:
                new_user.RegOneTime = user["OneTime"]
            except KeyError:
                pass
            try:
                new_user.UserIP = user["UserIP"]
            except KeyError:
                pass
            try:
                new_user.FakePort = user["FakePort"]
            except KeyError:
                pass
            try:
                new_user.RtpPort = user["RtpPort"]
            except KeyError:
                pass
            try:
                new_user.Expires = user["Expires"]
            except KeyError:
                pass
            try:
                new_user.QParam = user["QParam"]
            except KeyError:
                pass
            try:
                new_user.SipTransport = user["SipTransport"]
            except KeyError:
                pass
            try:
                new_user.RegMode = user["RegMode"]
            except KeyError:
                pass
            try:
                new_user.BindPort = user["BindPort"]
            except KeyError:
                pass
            #Если есть два юзера с одинаковыми id, выходим
            if new_user.UserId in users:
                logger.error("UserId = %d is already in use", new_user.UserId)
                return False
            #Если два транка используют одинаковые порты, то выходим:
            if {UserId: user for UserId,user in users.items() if user.Port == new_user.Port}:
                logger.error("User Port = %d is already in use. UserID: %d", new_user.Port, new_user.UserId)
                return False
            users[new_user.UserId] = new_user
        return users

    def parse_test_info(self, json_tests):
        #Создаём список для тестов
        tests = []
        for count,test in enumerate(json_tests):
            new_test = testClass.TestClass()
            new_test.Status = "New"
            new_test.TestId = count
            #Обработка опциональных свойств
            try:
                new_test.Name = test["Name"]
            except KeyError:
                pass
            try:
                new_test.Description = test["Description"]
            except KeyError:
                pass
            #Обработка тестовой процедуры (обязательное свойство)
            new_test.TestProcedure = test["TestProcedure"]
            tests.append(new_test)
        return tests

    def parse_user_agent(self, test, ua_desc):
        #Пытаемся найти UserAgent в описании теста
        for ua in ua_desc:
            #Создаём нового UserAgent
            new_ua = testClass.UserAgentClass()
            #Устанавливаем статус UserAgent
            new_ua.Status = "New"
            #Обработка обязательных свойств
            new_ua.Name = ua["Name"]
            new_ua.Type = ua["Type"]
            #В зависимости от типа UA забираем свойство UserId(User) или TrunkID(Trunk)
            if new_ua.Type == "User":
               new_ua.UserId = ua["UserId"]
            else:
                new_ua.TrunkId = ua["TrunkId"]
            #Обработка опциональных свойств
            try:
                new_ua.WriteStat = ua["WriteStat"]
            except:
                pass
            try:
                new_ua.Cyclic = ua["Cyclic"]
            except:
                pass
            try:
                new_ua.BackGround = ua["BackGround"]
            except:
                pass
            #Обработка команд для UA (обязательное свойство)
            for command in ua["Commands"]:
                #Поскольку на данном этапе юзеры не залинкованы к процессам
                #Просто передаём объекту JSON описания команд
                new_ua.RawJsonCommands.append(command)
            #Делим агентов
            if new_ua.BackGround:
                test.BackGroundUA.append(new_ua)
            else:
                test.UserAgent.append(new_ua)
        return True

    def parse_test_var(self, test_desc):
        #Парсим пользовательские переменные
        test_var = {}
        #Забираем переменные, описанные юзером
        if "UserVar" in test_desc:
            test_var = test_desc["UserVar"][0]
        try:
            for user in test_desc["Users"]:
                #Добавляем описание основных параметров юзера
                var_prefix = "%%" + str(user["UserId"])
                test_var[str(var_prefix + "." + "SipDomain" + "%%")] = str(user["SipDomain"])
                test_var[str(var_prefix + "." + "SipGroup" + "%%")] = str(user["SipGroup"])
                test_var[str(var_prefix + "." + "Number" + "%%")] = str(user["Number"])
                test_var[str(var_prefix + "." + "Port" + "%%")] = str(user["Port"])
        except KeyError:
            pass
        try:
            for trunk in test_desc["Trunks"]:
               #Добавляем описание основных параметров транков
               var_prefix = "%%Tr." + str(trunk["TrunkId"])
               try:
                   test_var[str(var_prefix + "." + "SipDomain" + "%%")] = str(trunk["SipDomain"])
                   test_var[str(var_prefix + "." + "SipGroup" + "%%")] = str(trunk["SipGroup"])
                   test_var[str(var_prefix + "." + "Port" + "%%")] = str(trunk["Port"])
                   test_var[str(var_prefix + "." + "TrunkId" + "%%")] = str(trunk["TrunkId"])
                   test_var[str(var_prefix + "." + "TrunkName" + "%%")] = str(trunk["TrunkName"])
                   test_var[str(var_prefix + "." + "Login" + "%%")] = str(trunk["Login"])
                   test_var[str(var_prefix + "." + "Password" + "%%")] = str(trunk["Password"])
               except KeyError:
                pass
               try:
                   test_var[str(var_prefix + "." + "RemotePort" + "%%")] = str(trunk["RemotePort"])
               except KeyError:
                pass
        except:
            pass

        return test_var

    def parse_sys_conf(self, sys_json, py_sipp_path):
        if not "%%SIPP_PATH%%" in sys_json:
            logger.error("No %%SIPP_PATH variable in system config")
            return False
        if not "%%SRC_PATH%%" in sys_json:
            logger.error("No %%SRC_PATH variable in system config")
            return False
        if not "%%TEMP_PATH%%" in sys_json:
            logger.error("No %%TEMP_PATH variable in system config")
            return False
        if not "%%LOG_PATH%%" in sys_json:
            logger.error("No %%LOG_PATH variable in system config")
            return False
        if not "%%REG_XML%%" in sys_json:
            sys_json["%%REG_XML%%"] = py_sipp_path + "/xml/reg_user.xml"
        if not "%%IP%%" in sys_json:
            logger.error("No %%IP variable in system config")
            return False
        if not "%%SERV_IP%%" in sys_json:
            logger.error("No %%SERV_IP variable in system config")
            return False
        if not "%%EXTER_IP%%" in sys_json:
            logger.error("No %%EXTER_IP variable in system config")
            return False
        if not "%%EXTER_PORT%%" in sys_json:
            logger.error("No %%EXTER_PORT variable in system config")
            return False
        if not "%%DEV_USER%%" in sys_json:
            logger.error("No %%DEV_USER variable in system config")
            return False
        if not "%%DEV_PASS%%" in sys_json:
            logger.error("No %%DEV_PASS variable in system config")
            return False
        if not "%%DEV_DOM%%" in sys_json:
            logger.error("No %%DEV_DOM variable in system config")
            return False
        if not "%%SF_XML%%" in sys_json:
            sys_json["%%SF_XML%%"] = py_sipp_path + "/xml/send_sf.xml"
        return sys_json
