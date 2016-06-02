import modules.cmd_builder as builder
import paramiko
import paramiko.ssh_exception as parm_excpt 

def get_ssh_connection(host,port,user,secret):
    #Raises:    
    #BadHostKeyException – if the server’s host key could not be verified
    #AuthenticationException – if authentication failed
    #SSHException – if there was any other error connecting or establishing an SSH session
    #socket.error – if a socket error occurred while connecting
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=host, username=user, password=secret, port=port, timeout=10)
        #stdin, stdout, stderr = client.exec_command('/domain/list')
        #data = stdout.read() + stderr.read()
        #data.decode('utf-8')
        #client.close()
        return client
    except:
        print("[ERROR] Can't connenct to the CoCon interface.")
        print("--> Try to check the connection settings.")
        return False
    
def cocon_configure(CoconCommands,test_var):
    CoconIP =   test_var["%%SERV_IP%%"]
    CoconPort = 8023
    CoconUser = test_var["%%DEV_USER%%"]
    CoconPass = test_var["%%DEV_PASS%%"]
    #Подключиаемся к CoCoN
    CoconCommands = CoconCommands[0]
    for CoconCmdName in CoconCommands:
        #Пропускаем команду через словарь
        CoconCommand = builder.replace_key_value(CoconCommands[CoconCmdName], test_var)
        print("---> Command:",CoconCommand)
        if CoconCommand:
                ssh_connect = get_ssh_connection(CoconIP,CoconPort,CoconUser,CoconPass)
                if ssh_connect:
                    stdin, stdout, stderr = ssh_connect.exec_command(CoconCommand)
                    data = stdout.read() + stderr.read()
                    ssh_connect.close()
                    #print(data.decode("utf-8", "strict"))
                else:
                     #Если не удалось подключиться к CoCoN выходим...
                      return False
        else:
            return False
    return True

