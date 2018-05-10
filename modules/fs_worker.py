import os,sys
from datetime import datetime
import logging
logger = logging.getLogger("tester")


class fs_working:
    def create_log_dir(self, log_path):
        # Создаём дикерторию
        try:
            os.makedirs(log_path)
        except FileExistsError:
            if not self.clear_log_dir(log_path):
                return False
        except PermissionError:
            logger.error("Сan't create log folder. Detail: %s",sys.exc_info()[1])
            return False
        return True

    @staticmethod
    def clear_log_dir(log_path):
        for file in os.listdir(log_path):
            try:
                file = log_path + "/" + file
                # Удаляем всё кроме основного лог файла.
                if file != "" and os.path.isfile(file) and file != log_path + "/test.log":
                    os.remove(file)
            except PermissionError:
                logger.error("Сan't clear log folder. Detail: %s",sys.exc_info()[1])
                return False
        return True

    @staticmethod
    def open_log_file(ua_name, log_path):
        # Создаём дикерторию
        try:
            fileName = str(log_path) + "/" + str(ua_name) + "_" + str(datetime.strftime(datetime.now(), "%Y_%m_%d_%H_%M_%S")) + ".log"
            fd = open(fileName,"wb")
        except (PermissionError,FileNotFoundError):
            logger.error("Сan't open file. Detail: %s",sys.exc_info()[1])
            return False
        return fd

    @staticmethod
    def get_fd(file_path):
        try:
            fd = open(file_path,"r")
        except:
            logger.error("Сan't open file. Detail: %s",sys.exc_info()[1])
            return False
        return fd    