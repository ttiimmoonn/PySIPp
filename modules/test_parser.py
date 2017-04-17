import modules.test_class as testClass
import sys
import logging
import re
logger = logging.getLogger("tester")
def parse_user_info (json_users):
    #Создаём массив для хранения юзеров
    users = {}
    #Перебераем всех юзеров, описанных в секции Users
    for user in json_users:
        #Создаём нового пользователя
        new_user = testClass.UserClass()
        #Проверяем наличие обязательных параметров
        try:
            new_user.Status = "New"
            new_user.UserId = user["UserId"]
            new_user.Number = user["Number"]
            new_user.Login = user["Login"]
            new_user.Password = user["Password"]
            new_user.SipDomain = user["SipDomain"]
            new_user.SipGroup = user["SipGroup"]
            new_user.Port = user["Port"]
        except KeyError:
            logger.error("Wrong user description. Detail: User has no attribute: %s",sys.exc_info()[1])
            return False
        #Выставляем опциональные параметры
        try:
            new_user.UserIP = user["UserIP"]
        except KeyError:
            new_user.UserIP = None
        try:
            new_user.FakePort = user["FakePort"]
        except KeyError:
            new_user.FakePort = None
        try:
            new_user.RtpPort = user["RtpPort"]
        except KeyError:
            new_user.RtpPort = None
        try:
            new_user.Expires = user["Expires"]
        except KeyError:
            new_user.Expires = 3600
        try:
            new_user.QParam = user["QParam"]
        except KeyError:
            new_user.QParam = 1
        try:
            new_user.SipTransport = user["SipTransport"]
        except KeyError:
            new_user.SipTransport = "UDP"
        #Если есть два юзера с одинаковыми id, выходим
        if new_user.UserId in users:
            logger.error("UserId = %d is already in use",int(new_user.UserId))
            return False
        else:
            users[new_user.UserId] = new_user
    return users
def parse_test_info (json_tests):
    #Создаём массив для тестов
    tests = []
    for count,test in enumerate(json_tests):
        new_test = testClass.TestClass()
        new_test.Status = "New"
        new_test.TestId = count
        #Устанавливаем опциональные свойства
        try:
            new_test.Name = test["Name"]
        except KeyError:
            new_test.Name = "Unnamed test"
        try:
            new_test.Description = test["Description"]
        except KeyError:
            new_test.Description = "No description"
        try:
            new_test.TestProcedure = test["TestProcedure"]
        except:
            logger.error("Wrong Test description. Detail: UA has no attribute: %s { Test: %s }", sys.exc_info()[1], new_test.Name)
            return False
        #Делаем проверку тестовой процедуры:
        for item in test["TestProcedure"]:
            if "Sleep" in item:
                try:
                    int(item["Sleep"])
                except:
                    logger.error("Sleep command must have a int value.")
                    return False
            if "ServiceFeature" in item:
                for sf in item["ServiceFeature"]:
                    try:
                        int(sf["userId"])
                    except:
                        logger.error("UserId in ServiceFeature command must have a int value. { Bad UserID: %s}",sf["userId"])
                        return False
            if "CheckRetransmission" in item:
                for section in item["CheckRetransmission"]:
                    try:
                        if not section["Timer"] in ["A","B","E","F","G","H"]:
                            logger.error("Unknown timer name: \"%s\" in CheckRetransmission section. Allowed timers: %s",section["Timer"],", ".join(["A","B","E","F","G","H"]))
                            return False

                        if re.search("^[0-9]{1,2}$|^([0-9]{1,2},)+[0-9]{1,2}$",section["UA"]) == None:
                            logger.error("Wrong format for UA option in CheckRetransmission section. Use: id1,id2,id3 or id")
                            return False

                        msg_info = section["Msg"][0]
                        if not msg_info["MsgType"].lower() in ["request", "response"]:
                            logger.error("Unknown MsgType: \"%s\" in CheckRetransmission section. Allowed: %s",msg_info["MsgType"], ", ".join( ["request", "response"]))
                            return False

                        if not "Method" in msg_info:
                            logger.error("Wrong CheckRetransmission description. Detail: CheckRetransmission has no attribute: \"Method\"")
                            return False

                        if msg_info["MsgType"].lower() == "request":
                            if msg_info["Code"] != "None":
                                logger.error("For request msg Code must be None. CheckRetransmission section")
                                return False
                        else:
                            try:
                                int(msg_info["Code"])
                            except ValueError:
                                logger.error("Code must be int for response msg. CheckRetransmission section")
                                return False
                    except KeyError:
                        logger.error("Wrong CheckRetransmission description. Detail: CheckRetransmission has no attribute: %s",sys.exc_info()[1])
                        return False
                    
            if "CheckDifference" in item:
                for section in item["CheckDifference"]:
                    try:
                        if not section["Mode"] in ["between_ua","inner_ua"]:
                            logger.error("Unknown Mode: \"%s\" in CheckDifference section. Allowed Modes: %s",section["Mode"],", ".join(["between_ua","inner_ua"]))
                            return False

                        if re.search("^[0-9]{1,2}$|^([0-9]{1,2},)+[0-9]{1,2}$",section["UA"]) == None:
                            logger.error("Wrong format for UA option in CheckDifference section. Use: id1,id2,id3 or id")
                            return False

                        msg_info = section["Msg"][0]
                        if not msg_info["MsgType"].lower() in ["request", "response"]:
                            logger.error("Unknown MsgType: \"%s\" in CheckDifference section. Allowed: %s",msg_info["MsgType"], ", ".join( ["request", "response"]))
                            return False

                        if not "Method" in msg_info:
                            logger.error("Wrong CheckDifference description. Detail: CheckDifference has no attribute: \"Method\"")
                            return False

                        if not section["Difference"].isdigit()  and re.search("^\%\%[a-zA-Z_\-0-9]+\%\%$",section["Difference"]) == None:
                            logger.error("Diffenrence must be int or var: %%VAR%%.  CheckDifference section.")
                            return False

                        if msg_info["MsgType"].lower() == "request":
                            if msg_info["Code"] != "None":
                                logger.error("For request msg Code must be None. CheckDifference section")
                                return False
                        else:
                            try:
                                int(msg_info["Code"])
                            except ValueError:
                                logger.error("Code must be int for response msg. CheckDifference section")
                                return False
                    except KeyError:
                        logger.error("Wrong CheckDifference description. Detail: CheckDifference has no attribute: %s",sys.exc_info()[1])
                        return False
        tests.append(new_test)
    return tests
def parse_user_agent (test,ua_desc):
        #Пытаемся найти UserAgent в описании теста
        try:
            for ua in ua_desc:
                #Создаём нового UserAgent
                new_ua = testClass.UserAgentClass()
                #Устанавливаем статус UserAgent
                new_ua.Status = "New"
                #Пытаемся забрать обязательные параметры
                try:
                    new_ua.Name = ua["Name"]
                    new_ua.Type = ua["Type"]
                except KeyError:
                    logger.error("Wrong UA description. Detail: UA has no attribute: %s { Test: %s }",sys.exc_info()[1],test.Name)
                    return False
                #В зависимости от типа UA, пытаемся забрать:
                #Для User: UserId
                #Для Trunk: Port
                if new_ua.Type == "User":
                    try:
                        new_ua.UserId = ua["UserId"]
                    except KeyError:
                        logger.error("Wrong UA description. Detail: UA has no attribute: %s { Test: %s }",sys.exc_info()[1],test.Name)
                        return False
                elif new_ua.Type == "Trunk":
                    try:
                        new_ua.Port = ua["Port"]
                    except KeyError:
                        logger.error("Wrong UA description. Detail: UA has no attribute: %s { Test: %s }",sys.exc_info()[1],test.Name)
                        return False
                else:
                    #Если кто-то передал некорректный тип юзера, выходим
                    logger.error("Wrong UA description. Detail: Unknown type of User Agent. Use \"User\" or \"Trunk\" { Test: %s }",test.Name)
                    return False
                #Парсим параметр WriteStat
                try:
                    new_ua.WriteStat = ua["WriteStat"]
                except:
                    new_ua.WriteStat = False
                #Парсим параметр cyclic
                try:
                    new_ua.Cyclic = ua["Cyclic"]
                except:
                    new_ua.Cyclic = False
                #Начинаем парсинг команд для UA
                try:
                    for command in ua["Commands"]:
                        #Поскольку на данном этапе юзеры не залинкованы к процессам
                        #Просто передаём объекту JSON описания команд
                        new_ua.RawJsonCommands.append(command)
                except KeyError:
                        logger.error("Wrong UA description. Detail: UA has no attribute: %s { Test: %s }",sys.exc_info()[1],test.Name)
                        return False
                try:
                    new_ua.BackGround = ua["BackGround"]
                except:
                    new_ua.BackGround = False
                #Делим агентов
                if new_ua.BackGround:
                    test.BackGroundUA.append(new_ua)
                else:
                    test.UserAgent.append(new_ua)
        except KeyError:
            #Если в тесте нет UA, то выходим
            logger.error("Wrong UA description. Detail: UA has no attribute: %s { Test: %s }",sys.exc_info()[1],test.Name)
            return False
        return test

def parse_test_var (test_desc):
    #Парсим пользовательские переменные
    test_var = {}
    try:
       #Забираем переменные, описанные юзером
       if "UserVar" in test_desc:
           test_var = test_desc["UserVar"][0]
       #
       for user in test_desc["Users"]:
            userId = "%%" + str(user["UserId"])
            #Добавляем описание основных параметров юзера
            test_var[str(userId + "." + "SipDomain" + "%%")] = str(user["SipDomain"])
            test_var[str(userId + "." + "SipGroup" + "%%")] = str(user["SipGroup"])
            test_var[str(userId + "." + "Number" + "%%")] = str(user["Number"])
    except KeyError:
        pass
    return test_var
def parse_sys_conf (sys_json):
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
