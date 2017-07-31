import modules.test_class as testClass
from jsonschema import Draft4Validator
from os import listdir
import json
import sys
import logging
import re
logger = logging.getLogger("tester")

class Validator:

    def __init__(self):
    	#Словарь для хранения содержимого схем
        self.schemas_data = {}
        #Директория, в которой хранятся схемы
        self.schemas_directory = "/schema/"
        #Кортеж глобальных секций
        self.global_sections = ("Users","UserVar","PreConf","PostConf")
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

    def validate_sections(self, section, section_schema):
        errors = sorted(Draft4Validator(section_schema).iter_errors(section), key=lambda e: e.path)
        if errors:
            for e in errors:
                print("%s %s" % (e.path, e.message))
            sys.exit(1)

    def validate_difference(self, diff):
        try:
            diff["Difference"]
        except KeyError:
            pass
        else:
            if type(diff["Difference"]) == str: 
                if re.search("^\%\%[a-zA-Z-0-9_]+\%\%$",diff["Difference"]) == None:
                    logger.error("Validation error in CheckDifference: \033[1;31mDifference must be number or var (var pattern = ^%%[a-zA-Z-0-9_]+%%$)\033[1;m")
                    sys.exit(1)
            elif type(diff["Difference"]) != float and type(diff["Difference"]) != int:
                logger.error("Validation error in CheckDifference: \033[1;31mDifference must be number or var (var pattern = ^%%[a-zA-Z-0-9_]+%%$)\033[1;m")
                sys.exit(1)
            elif diff["Difference"] < 0:
                logger.error("Validation error in CheckDifference: \033[1;31mDifference must be greater or equal than zero\033[1;m")
                sys.exit(1)

    def validate_msg_code(self, msg):
        try:
            msg["Code"]
        except KeyError:
            logger.error("Validation error in section Msg: \033[1;31mCode is required property\033[1;m")
            sys.exit(1) 
        if msg["MsgType"] == "request" and msg["Code"] != None:
            logger.error("Validation error in section Msg: \033[1;31mCode must be null then MsgType=request\033[1;m")
            sys.exit(1)
        if msg["MsgType"] == "response":
            if type(msg["Code"]) != int:
                logger.error("Validation error in section Msg: \033[1;31mCode must be integer then MsgType=response\033[1;m")
                sys.exit(1)
            elif msg["Code"] < 100 or msg["Code"] > 699:
                logger.error("Validation error in section Msg: \033[1;31mCode should match the range of 100 and 699\033[1;m")
                sys.exit(1)
    
    def validate_startua_type(self, items):
        if items["Type"] == "User":
            try:
                items["UserId"]
            except KeyError:
                logger.error("Validation error in StartUA: \033[1;31mUserId is required property then Type=User\033[1;m")
                sys.exit(1)
        if items["Type"] == "Trunk":
            try:
                items["Port"]
            except KeyError:
                logger.error("Validation error in StartUA: \033[1;31mPort is required property then Type=Trunk\033[1;m")
                sys.exit(1)

    def validation_tests(self, json_file):
        #Валидация глобальных свойств
        if not "TestName" in json_file:
            logger.error("Validation error in global section: \033[1;31mTestName is required property\033[1;m")
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
        	if section == "Users" and not "Users" in json_file:
        		logger.error("Validation error in global section: \033[1;31mUsers is required property\033[1;m")
        		sys.exit(1)
        	if section in json_file:
        		self.validate_sections(json_file[section], self.schemas_data[section])
        if not "Tests" in json_file:
            logger.error("Validation error in global section: \033[1;31mTests is required property\033[1;m")
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
                    logger.error("Validation error in section Tests: \033[1;31mTestProcedure is required property\033[1;m")
                    sys.exit(1)
                else:
                	#Валидация тестовых процедур
                    for procedure in test["TestProcedure"]:
                        if "CheckRetransmission" in procedure:
                            self.validate_sections(procedure["CheckRetransmission"], self.schemas_data["CheckRetransmission"])
                            if not "Msg" in procedure["CheckRetransmission"][0]:
                                logger.error("Validation error in section CheckRetransmission: \033[1;31mMsg is required property\033[1;m")
                                sys.exit(1)
                            else:
                                self.validate_sections(procedure["CheckRetransmission"][0]["Msg"], self.schemas_data["Msg"])
                                self.validate_msg_code(procedure["CheckRetransmission"][0]["Msg"][0])
                        if "CheckDifference" in procedure:
                            self.validate_sections(procedure["CheckDifference"], self.schemas_data["CheckDifference"])
                            self.validate_difference(procedure["CheckDifference"][0])
                            if not "Msg" in procedure["CheckDifference"][0]:
                                logger.error("Validation error in section CheckDifference: \033[1;31mMsg is required property\033[1;m")
                                sys.exit(1)
                            else:
                                self.validate_sections(procedure["CheckDifference"][0]["Msg"], self.schemas_data["Msg"])
                                self.validate_msg_code(procedure["CheckDifference"][0]["Msg"][0])
                        if "StartUA" in procedure:
                            self.validate_sections(procedure, self.schemas_data["StartUA"])
                            for items in procedure["StartUA"]:
                                self.validate_startua_type(items)
                                if not "Commands" in items:
                                    logger.error("Validation error in section StartUA: Commands is required property")
                                    sys.exit(1)
                                else:
                                    self.validate_sections(items["Commands"], self.schemas_data["Commands"])
                        for section in self.simple_procedure_sections:
                            if section in procedure:
                                self.validate_sections(procedure, self.schemas_data[section])
        return True

class Parser:

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
                new_user.Mode = user["Mode"]
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
            else:
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
            #В зависимости от типа UA забираем свойство UserId(User) или Port(Trunk)
            if new_ua.Type == "User":
               new_ua.UserId = ua["UserId"]
            else:
                new_ua.Port = ua["Port"]
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
        try:
           #Забираем переменные, описанные юзером
           if "UserVar" in test_desc:
               test_var = test_desc["UserVar"][0]
           for user in test_desc["Users"]:
               userId = "%%" + str(user["UserId"])
               #Добавляем описание основных параметров юзера
               test_var[str(userId + "." + "SipDomain" + "%%")] = str(user["SipDomain"])
               test_var[str(userId + "." + "SipGroup" + "%%")] = str(user["SipGroup"])
               test_var[str(userId + "." + "Number" + "%%")] = str(user["Number"])
               test_var[str(userId + "." + "Port" + "%%")] = str(user["Port"])
        except KeyError:
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
