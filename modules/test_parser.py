import modules.test_class as testClass
import sys
import logging
import re
logger = logging.getLogger("tester")

class Parser:

    def output_validate_errors(self, errors):
        for e in errors:
            #Если обязательное свойство отсутствует
            if "is a required property" in str(e.message):
                try:        
                    logger.error("In item [%s] of section [%s]: value %s" % (e.path.pop(), e.path.popleft(), e.message))
                except (IndexError, TypeError):
                    if not "CheckRetransmission" and "CheckDifference" in str(e.message):
                        logger.error("Missing property: %s" % e.message)
                    elif "Code" in str(e.message):
                        logger.error("Missing property in CheckRetransmission or CheckDifference: %s" % (e.message))
                    elif not "CheckDifference":
                        logger.error("%s" % e.message)
                    if not "CheckRetransmission" and "CheckDifference" and "Sleep" and "Print" and "Stop" \
                    and "ServiceFeature" and "ManualReg" and "DropManualReg" and "SendSSHCommand" in str(e.message):
                        logger.error("%s" % e.message)
            #Если задаваемое свойство не соответствует шаблону       
            elif "does not match any of the regexes" in str(e.message):
                logger.error("In item %s of section [%s]: value %s" % (re.findall(r"\d",str(e.path)), e.path.popleft(), e.message)) 
            #Если ошибка присутствует во вложенных секциях 
            elif "is not valid under any of the given schemas" in str(e.message):
                self.output_validate_errors(sorted(e.context, key=lambda e: e.path))
            #Действия во всех остальных случаях
            else:
                try:
                    logger.error("In item %s of section [%s]: %s value %s" % (re.findall(r"\d",str(e.path)), e.path.popleft(), e.path.pop(), e.message))
                except (IndexError, TypeError):
                    if "Sleep" in str(e.schema_path):
                        logger.error("In section Sleep: value %s %s" % (e.message))
                    if "ServiceFeature" in str(e.schema_path):
                        logger.error("In section ServiceFeature: value %s" % (e.message))
                    if "Code" in str(e.schema_path):
                        logger.error("In section CheckRetransmission or CheckDifference value Code: %s" % (e.message))
                    if "AutoTest" in str(e.schema_path):
                        logger.error("AutoTest: value %s" % e.message)
                    if "TestName" in str(e.schema_path):
                        logger.error("TestName: value %s" % e.message)

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

    def parse_sys_conf(self, sys_json):
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
            logger.error("No %%REG_XML variable in system config")
            return False
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
            logger.error("No %%SF_XML variable in system config")
            return False
        return sys_json
