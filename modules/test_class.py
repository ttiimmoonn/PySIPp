import threading
import modules.process_contr as proc
import modules.fs_worker as fs

class TestClass:
    def __init__(self):
        self.TestId = None
        self.UserAgent = []
        self.CompliteUA = []
        self.BackGroundUA = []
        self.BackGroundThreads = []
        self.WaitBackGroundUA = []
        self.ThreadEvent = threading.Event()
        self.Name = None
        self.Description = None
        self.TestProcedure = None
        self.Status = None
        self.LogPath = None
    
    def ReplaceUaToComplite(self):
        self.CompliteUA += self.UserAgent
        self.UserAgent = []

    def ReplaceBgUaToWait(self):
        self.WaitBackGroundUA += self.BackGroundUA
        self.BackGroundUA = []

    def CompliteBgUA(self):
        self.CompliteUA += self.WaitBackGroundUA
        self.WaitBackGroundUA = []

class UserAgentClass:
    def __init__(self):
        self.Commands = []
        self.RawJsonCommands=[]
        self.Process = []
        self.Status = None
        self.Cyclic = None
        self.StatusCode = None
        self.Name = None
        self.Type = None
        self.WriteStat = None
        self.TimeStampFile = None
        self.UserId = None
        self.Port = None
        self.LogFd = None
        self.UserObject = None
        self.BackGround = None
        self.UALock = threading.Lock()
        self.ShortTrParser = None
    
    def GetServiceFetureUA(self,command,code,user_obj,user_id):
        #Добавляем новый тип UA
        self.Type = "ServiceFeatureUA"
        self.Commands.append(command)
        self.Name = "SF_CODE_" + code
        self.UserObject = user_obj
        self.UserId = user_id
        return self

    def ReadStatusCode(self):
        if not self.UALock.acquire():
            #не удалось заблокировать ресурс
            return False
        else:
            try:
                #Возвращаем статус код
                return self.StatusCode
            finally:
                self.UALock.release() 
    def SetStatusCode(self,statusCode):
        if not self.UALock.acquire():
            #не удалось заблокировать ресурс
            return False
        else:
            try:
                #Возвращаем статус код
                self.StatusCode = statusCode
            finally:
                self.UALock.release()         
        
class UserClass:
    def __init__(self):
        self.Timer = None
        self.Status = "New"
        self.StatusCode = None
        self.Number = None
        self.Login = None
        self.Password = None
        self.SipDomain = None
        self.Expires = 3600
        self.QParam = 1
        self.Port = None
        self.RtpPort = None
        self.RegCommand = None
        self.UnRegCommand = None
        self.RegProcess = None
        self.UnRegProcess = None
        self.RegLogFile = None
        self.SipGroup = None
        self.SipTransport = None
        self.UserIP = None
        #Для тестирования регистраций с левого ip:port
        self.FakePort = None
        self.UserLock = threading.Lock()
    
    def SetRegistrationTimer(self):
        self.Timer = threading.Timer((int(self.Expires) * 2 / 3), proc.RegisterUser, args=(self,) , kwargs=None)
        self.Timer.start()

    def CleanRegistrationTimer(self):
        try:
            self.Timer.cancel()
        except AttributeError:
            pass

    def ReadStatusCode(self):
        if not self.UserLock.acquire():
            #не удалось заблокировать ресурс
            return False
        else:
            try:
                #Возвращаем статус код
                return self.StatusCode
            finally:
                self.UserLock.release() 
    def SetStatusCode(self,statusCode):
        if not self.UserLock.acquire():
            #не удалось заблокировать ресурс
            return False
        else:
            try:
                #Возвращаем статус код
                self.StatusCode = statusCode
            finally:
                self.UserLock.release() 
