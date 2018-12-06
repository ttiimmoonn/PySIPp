import logging
import time
import subprocess
from subprocess import Popen, PIPE
from multiprocessing import Process, Queue
logger = logging.getLogger("logger")

class Apps():
    def __init__(self, shouldStart):
        self.shouldStart = shouldStart
        self.activeProcesses = {}
        self.deactivatedProcesses = []

        """очередь, куда прилетают законченные по таймеру процессы"""
        ProcessQueue = Queue()
        self.QueEndTimeout = ProcessQueue

    def startProcess(self, nameApps):
        try:
            program = []
            program.append(self.shouldStart[nameApps]["path"]).append(self.shouldStart[nameApps]["keys"].split(" "))
            runningProcess = subprocess.Popen(program, stdout=subprocess.PIPE)

            if self.shouldStart[nameApps]["mode"] == "background_timer":
                timer = Process(target=control_timer, args=(self.shouldStart[nameApps]["time-out"], nameApps, self.QueEndTimeout,))
                self.activeProcesses[nameApps] = ({"objProc": runningProcess, "time-out": timer})
            elif self.shouldStart[nameApps]["mode"] == "background":
                self.activeProcesses[nameApps] = ({"objProc": runningProcess})
            else:
                timer = Process(target=control_timer, args=(self.shouldStart[nameApps]["time-out"], nameApps, self.QueEndTimeout,))
                self.activeProcesses[nameApps] = ({"objProc": runningProcess, "time-out": timer})

        except Exception as ex:
            logger.error("Can't start the process...")
            logger.debug(ex)
            return False

    def stopProcess(self, nameApps):
        try:
            self.activeProcesses[nameApps].terminate()
            return True
        except Exception as ex:
            logger.error("Can't start the process...")
            logger.debug(ex)
            return False


def control_timer(timer, nameApps, QueEndTimeout):
    try:
        for sec in list(range(timer)):
            time.sleep(1)
        QueEndTimeout.pull({"name": nameApps})
        return True
    except Exception as ex:
        logger.error("Error timer process...")
        logger.debug(ex)
        return False
