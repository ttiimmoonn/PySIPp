import os,sys
from datetime import datetime
def create_log_dir(log_path):
    #Создаём дикерторию
    try:
        os.makedirs(log_path)
    except FileExistsError:
        if not clear_log_dir(log_path):
            return False
    except PermissionError:
        print("[ERROR] Сan't create the log folder. Detail:")
        print("--->",sys.exc_info()[1])
        return False
    return True

def clear_log_dir (log_path):
    for file in os.listdir(log_path):
        try:
            file = log_path + "/" + file
            if file != "" and os.path.isfile(file):
                os.remove(file)
        except PermissionError:
            print("[ERROR] Сan't clear the log folder. Detail:")
            print("--->",sys.exc_info()[1])
            return False
    return True
    
def open_log_file (ua_name,log_path):
    #Создаём дикерторию
    try:
        fileName = str(log_path) + "/" + str(ua_name) + "_" + str(datetime.strftime(datetime.now(), "%Y_%m_%d_%H_%M_%S")) + ".log"
        fd = open(fileName,"wb")
    except (PermissionError,FileNotFoundError):
        print("[ERROR] Сan't open the log file. Detail:")
        print("--->",sys.exc_info()[1])
        return False
    return fd
    