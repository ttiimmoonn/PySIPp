import pjsua as pj
import logging
import threading
import time

logging.basicConfig(format = u'%(asctime)-8s %(levelname)-8s [%(module)s -> %(funcName)s:%(lineno)d] %(message)-8s', level = logging.INFO)

logger = logging.getLogger("tester")

class AccountCallback(pj.AccountCallback):
    def __init__(self, account,user):
        pj.AccountCallback.__init__(self, account)
        self.RegSem = None
        # dict for incoming calls
        self.IncCalls = {}
        # dict for outgoing calls
        self.OutCalls = {}
        # py_sipp user obj
        self.User = user

    def check_registration(self):
        # Waiting for complite registration.
        # Acquire Semaphore if reg_status < 200
        if self.account.info().reg_status < 200:
            self.RegSem = threading.Semaphore(0)
            logger.debug("Reg Semaphore acquire")
            self.RegSem.acquire()
        if self.account.info().reg_status == 200:
            logger.debug("Check registration for user: %s success",self.account.info().uri)
            return True
        else:
            logger.debug("Check registration for user: %s failed",self.account.info().uri)
            return False
    
    def on_reg_state(self):
        if not self.account:
            logger.warning("Reg state is changed but account not created now!")
            return False
        else:
            logger.debug("Reg state is changed.")

        if self.account.info().reg_status == 200:
            logger.info("User %s successfully registred.",self.account.info().uri)
            self.User.SetStatusCode(0)
        else:
            logger.error("Registration for user: %s failed. Code: %d. Reason: %s",self.account.info().uri,self.account.info().reg_status,self.account.info().reg_reason)
            self.User.SetStatusCode(2)
        if self.RegSem:
            if self.account.info().reg_status >= 200:
                logger.debug("Release Semaphore")
                self.RegSem.release()

class LibPjsua():
    def __init__(self):
        self.log_enabled = False
        self.lib = pj.Lib()
        self.lib.init(log_cfg = pj.LogConfig(level=4, callback=self._pjsip_logger))
        self.lib.create_transport(pj.TransportType.UDP, pj.TransportConfig(5091))
        self.lib.start()

    def _pjsip_logger(self,level, str, len):
        if self.log_enabled:
            print(str.decode("utf-8").rstrip("\r\n"))

    def CreateAccount(self,user):
        acc_callback = AccountCallback(None,user)
        acc_config = pj.AccountConfig(user.SipDomain,str(user.Number),str(user.Password),registrar=user.Registrar,proxy=user.Proxy,reg_expires=90)
        acc = self.lib.create_account(acc_config,cb=acc_callback)
        return acc, acc_callback

    def Destroy(self):
        self.lib.destroy()