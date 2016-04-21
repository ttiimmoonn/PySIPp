import modules.test_class as testClass
import sys
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
            new_user.Port = user["Port"]
        except KeyError:
            print("[ERROR] Wrong user description. Detail:")
            print("---> User has no attribute:",sys.exc_info()[1])
            return False
        #Выставляем опциональные параметры
        try:
            new_user.Expires = user["Expires"]
        except KeyError:
            new_user.Expires = 3600
        try:
            new_user.QParam = user["QParam"]
        except KeyError:
            new_user.QParam = 1
        #Если есть два юзера с одинаковыми id, выходим
        if new_user.UserId in users:
            print("[ERROR] UserId =", new_user.UserId," is already in use")
            return False
        else:
            users[new_user.UserId] = new_user
    return users
def parse_test_info (json_tests):
    #Создаём массив для тестов
    tests = []
    for test in json_tests:
        new_test = testClass.TestClass()

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
            print("[ERROR] Wrong Test description. Detail:")
            print("---> UA has no attribute:",sys.exc_info()[1],"{ Test:",new_test.Name,"}")
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
                    print("[ERROR] Wrong UA description. Detail:")
                    print("---> UA has no attribute:",sys.exc_info()[1],"{ Test:",new_test.Name,"}")
                    return False
                #В зависимости от типа UA, пытаемся забрать:
                #Для User: UserId
                #Для Trunk: Port
                if new_ua.Type == "User":
                    try:
                        new_ua.UserId = ua["UserId"]
                    except KeyError:
                        print("[ERROR] Wrong UA description. Detail:")
                        print("---> UA has no attribute:",sys.exc_info()[1],"{ Test:",new_test.Name,"}")
                        return False
                elif new_ua.Type == "Trunk":
                    try:
                        new_ua.Port = ua["Port"]
                    except KeyError:
                        print("[ERROR] Wrong UA description. Detail:")
                        print("---> UA has no attribute:",sys.exc_info()[1],"{ Test:",new_test.Name,"}")
                        return False
                else:
                    #Если кто-то передал некорректный тип юзера, выходим
                    print("[ERROR] Wrong UA description. Detail:")
                    print("--> Unknown type of User Agent. Use \"User\" or \"Trunk\"","{ Test:",new_test.Name,"}")
                    return False
                #Начинаем парсинг команд для UA
                try:
                    for command in ua["Commands"]:
                        #Поскольку на данном этапе юзеры не залинкованы к процессам
                        #Просто передаём объекту JSON описания команд
                        new_ua.RawJsonCommands.append(command)
                except KeyError:
                        print("[ERROR] Wrong UA description. Detail:")
                        print("---> UA has no attribute:",sys.exc_info()[1])
                        return False
                test.UserAgent.append(new_ua)
        except KeyError:
            #Если в тесте нет UA, то выходим
            print("[ERROR] Wrong test description. Detail:")
            print("---> Test has no attribute:",sys.exc_info()[1])
            return False
        return test

def parse_test_var (test_desc):
    #Парсим пользовательские переменные
    test_var = {}
    try:
       #Забираем переменные описанные юзером
       if "UserVar" in test_desc:
           test_var = test_desc["UserVar"][0]
       # Создаём связку Id <--> Number, чтобы было удобно ссылаться на юзеров
       # В переменных
       # %%1 -> юзер с Id = 1 и т.д
       for user in test_desc["Users"]:
            userId = "%%" + str(user["UserId"])
            test_var[str(userId)] = str(user["Number"])
    except KeyError:
        pass
    return test_var
def parse_sys_conf (sys_json):
    if not "%%SIPP_PATH" in sys_json:
        print("[ERROR] No %%SIPP_PATH variable in the system config")
        return False
    if not "%%SRC_PATH" in sys_json:
        print("[ERROR] No %%SRC_PATH variable in the system config")
        return False
    if not "%%TEMP_PATH" in sys_json:
        print("[ERROR] No %%TEMP_PATH variable in the system config")
        return False
    if not "%%LOG_PATH" in sys_json:
        print("[ERROR] No %%LOG_PATH variable in the system config")
        return False
    if not "%%REG_XML" in sys_json:
        print("[ERROR] No %%REG_XML variable in the system config")
        return False
    if not "%%IP" in sys_json:
        print("[ERROR] No %%IP variable in the system config")
        return False
    if not "%%SERV_IP" in sys_json:
        print("[ERROR] No %%SERV_IP variable in the system config")
        return False
    if not "%%EXTER_IP" in sys_json:
        print("[ERROR] No %%EXTER_IP variable in the system config")
        return False
    if not "%%EXTER_PORT" in sys_json:
        print("[ERROR] No %%EXTER_PORT variable in the system config")
        return False
    if not "%%DEV_USER" in sys_json:
        print("[ERROR] No %%DEV_USER variable in the system config")
        return False
    if not "%%DEV_PASS" in sys_json:
        print("[ERROR] No %%DEV_PASS variable in the system config")
        return False
    if not "%%DEV_DOM" in sys_json:
        print("[ERROR] No %%DEV_DOM variable in the system config")
        return False
    return sys_json