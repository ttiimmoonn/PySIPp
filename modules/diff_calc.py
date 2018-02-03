import modules.trace_parser as tr_parser
import modules.fs_worker as fs
from collections import OrderedDict
import logging
import math
logger = logging.getLogger("tester")

class diff_timestamp():
    def __init__(self,test):
        self.Status = None
        self.ua_with_traces = {}
        self.users_with_traces = {}
        self.trunks_with_traces = {}
        self.t1 = 0.5
        self.t2 = 4.0
        self.tr_timeout = 64 * self.t1
        self.seq_inv_retrans = []
        self.seq_non_inv_retrans = []
        #Получаем временные последовательности для таймеров. 
        self.get_inv_retrans_seq()
        self.get_non_inv_retrans_seq()
        #Парсим short_msg log
        test.CompliteUA = list(map(self.parse_short_trace_msg, test.CompliteUA))


    def _get_ua_obj(self,ua_type,ua_id):
        if ua_type == "user":
            try:
                return self.users_with_traces[int(ua_id)]
            except KeyError:
                return False
        elif ua_type == "trunk":
            try:
                return self.trunks_with_traces[int(ua_id)]
            except KeyError:
                return False
        else:
            logger.error("Unknown type of ua object: %s", str(ua_pr.type))
            return False


    def value_compare(self, sequence, req_value, max_diff=0.05):
        logger.info("--| COM SEQ: %s",' '.join(map(str,[round(x,1)for x in sequence])))
        logger.info("--| REQ VAL: %s",req_value)
        logger.info("--| Max diff: %s",str(max_diff))
        for value in sequence:
            if math.fabs(float(value) - float(req_value)) > max_diff:
                logger.warning("--| Compare complite. Result: fail")
                self.Status = "Failed"
                return False
        logger.info("--| Compare complite. Result: succ")
        return True

    def seq_compare(self,seq_a,seq_b,max_diff=0.05):
        logger.info("--| SEQ A: %s",' '.join(map(str,[round(x,1)for x in seq_a])))
        logger.info("--| SEQ B: %s",' '.join(map(str,[round(x,1)for x in seq_b])))
        logger.info("--| Max diff: %s",str(max_diff))
        try:
            if len(seq_a) != len(seq_b):
                logger.warning("--| Can't compare sequence with different length. len seq_a: %d,len seq_b: %d",len(seq_a),len(seq_b))
                self.Status = "Failed"
                return False

            for a,b in zip(seq_a,seq_b):
                if math.fabs(float(a)-float(b)) > max_diff:
                    logger.warning("--| Compare complite. Result: fail")
                    self.Status = "Failed"
                    return False
        except:
            logger.warning("--| Exception in seq_compare function.")
            self.Status = "Failed"
            return False
        logger.info("--| Compare complite. Result: succ")
        return True

    def parse_short_trace_msg(self,ua):
        # Парсим только те UA, которые имеют TimeStampFile
        if ua.TimeStampFile:
            if ua.UserObject:
                log_postfix = "UserObject with Number: " + str(ua.UserObject.Number)
            elif ua.TrunkObject:
                log_postfix = "TrunkObject with Port: " + str(ua.TrunkObject.Port)
            fs_work = fs.fs_working()
            # Получаем файловый дескриптор на файл с short_trace
            stat_file = fs_work.get_fd(ua.TimeStampFile)
            # Если удалось получить дескриптор с short_trace, обрабатываем его
            if stat_file:
                logger.info("Try to parse short_trace file for %s",log_postfix)
                ua.ShortTrParser = tr_parser.short_trace_parser(stat_file)
                ua.ShortTrParser.parse_trace_msg()
                logger.debug("Сlose short_trace file for %s",log_postfix)
                stat_file.close()
                if ua.ShortTrParser.Status == "Failed":
                    logger.error("Parse complite for %s. Result: %s.",log_postfix,ua.ShortTrParser.Status)
                    self.Status = "Failed"
                else:
                    logger.info("Parse complite for %s. Result: %s.",log_postfix,ua.ShortTrParser.Status)
                    if ua.UserObject:
                    	self.users_with_traces[ua.UserId] = ua
                    elif ua.TrunkObject:
                    	self.trunks_with_traces[ua.TrunkId] = ua
            else:
                logger.error("Parse complite for %s. Result: Failed (trace file not found).",log_postfix)
                self.Status = "Failed"
        return ua

    def get_inv_retrans_seq(self):
        diff = self.t1
        while diff < self.tr_timeout:
            self.seq_inv_retrans.append(diff)
            diff = diff *2
    def get_non_inv_retrans_seq(self):
        diff = self.t1
        while diff < self.tr_timeout:
            if diff < self.t2:
                self.seq_non_inv_retrans.append(diff)
                diff = diff * 2
            else:
                self.seq_non_inv_retrans.append(self.t2)
                diff += 4

    def get_first_msg_timestamp(self,*args,**kwargs):
        #args - ua_id для которых выполняется функция.
        #kwargs - параметры искомого сообщения
        #для ответов  - {"msg_type":"response", "method": "INVITE", "resp_code": "200"}
        #для запросов - {"msg_type":"request", "method": "BYE", "resp_code": None}
        result = {}
        result = OrderedDict(result)
        logger.info("Try to found first msg timestamp")
        logger.info("--| MSG param: type_of_msg - %s; method - %s; resp_code - %s", kwargs["msg_type"], kwargs["method"], kwargs["resp_code"])
        for ua_type,ua_id in args:
            ua = self._get_ua_obj(ua_type,ua_id)
            if not ua:
                logger.error("--| Timestamp not found. User with id: %s without traces", ua_id)
                self.Status = "Failed"
                return False
            logger.info("--| Search first msg timestamp for user: %s",str(ua.UserObject.Number))
            ua_msg_timestamp = {}
            ua_msg_timestamp = OrderedDict(ua_msg_timestamp)
            for call in ua.ShortTrParser.calls:
                ua_msg_timestamp[call.call_id] = call.get_first_msg_timestamp(**kwargs)
                if ua_msg_timestamp[call.call_id]:
                    logger.info("--| Msg timestamp for call: %s found.", call.call_id)
                else:
                    logger.info("--| Msg timestamp for call: %s not found.", call.call_id)
            result[str(ua_type) + ":" + str(ua_id)] = ua_msg_timestamp
        return result

    def get_diff(self,seq):
        msg_diff = []
        for count,timestp in enumerate(seq):
            try:
                msg_diff.append(float(seq[count+1])-float(timestp))
            except IndexError:
                break
        return msg_diff

    def get_retrans_diff(self,*args,**kwargs):
        result = {}
        result = OrderedDict(result)
        logger.info("Try to find msg retarnsmission.")
        logger.info("--| MSG param: type_of_msg - %s; method - %s; resp_code - %s", kwargs["msg_type"], kwargs["method"], kwargs["resp_code"])
        for ua_type,ua_id in args:
            ua = self._get_ua_obj(ua_type,ua_id)
            if not ua:
                logger.error("--| Retrans not detected. User with id: %s without traces", ua_id)
                self.Status = "Failed"
                return False
            logger.info("--| Search retrans for user: %s", str(ua.UserObject.Number))
            #Получаем последовательность временных меток для нужного сообщения
            call_seq = self.get_retrans_time_seq(ua,**kwargs)
            #Словарь для хранения результатов по всем вызовам
            result_seq = {}
            result_seq = OrderedDict(result_seq)
            #Начинаем расчёт diff для всех вызовов
            for call in call_seq:
                if call_seq[call]:
                    result_seq[call] = self.get_diff(call_seq[call])
                else:
                    result_seq[call] = False
                call_diff = []
            result[str(ua_type) + ":" + str(ua_id)] = result_seq
        return result

    def get_retrans_time_seq(self,ua,**kwargs):
        result_seq = {}
        #Делаем словарь упорядоченным, чтобы вызовы шли по порядку.
        result_seq = OrderedDict(result_seq)
        #Запрашиваем последовательности timestamp для всех вызовов
        for call in ua.ShortTrParser.calls:
            result_seq[call.call_id] = (call.get_retrans_time_seq(**kwargs))
            if result_seq[call.call_id]:
                logger.info("--| Retrans for call: %s detected.",call.call_id)
            else:
                logger.info("--| Retrans for call: %s not detected.",call.call_id)
        return result_seq

    def get_retrans_duration(self, *args,**kwargs):
        result = {}
        result = OrderedDict(result)
        logger.info("Trying to find msg retarnsmission duration.")
        for ua_type,ua_id in args:
            ua = self._get_ua_obj(ua_type,ua_id)
            if not ua:
                logger.error("--| Msg retrans duration not found. User with id: %s without traces", ua_id)
                self.Status = "Failed"
                return False
            logger.info("--| Searching msg retarnsmission duration for user %s",str(ua.UserObject.Number))
            ua_msg_timestamp = {}
            ua_msg_timestamp = OrderedDict(ua_msg_timestamp)
            for call in ua.ShortTrParser.calls:
                ua_msg_timestamp[call.call_id] = call.get_retrans_duration(**kwargs)
                if ua_msg_timestamp[call.call_id]:
                    logger.info("--| Msg retrans duration for call: %s found.", call.call_id)
                else:
                    logger.info("--| Msg retrans duration for call: %s not found.", call.call_id)
            result[str(ua_type) + ":" + str(ua_id)] = ua_msg_timestamp
        return result

    def compare_timer_seq(self,timer_name,*args,**kwargs):
        req_seq = []
        ua_seq_info = {}
        if timer_name in ["A"]:
            req_seq = self.seq_inv_retrans
            ua_seq_info = self.get_retrans_diff(*args,**kwargs)
        elif timer_name in ["B", "F", "H"]:
            req_seq.append(self.tr_timeout - 0.5)
            ua_seq_info = self.get_retrans_duration(*args,**kwargs)
        elif timer_name in ["E", "G"]:
            req_seq = self.seq_non_inv_retrans
            ua_seq_info = self.get_retrans_diff(*args,**kwargs)
        else:
            logger.error("Unknown timer name: %s",str(timer_name))
            self.Status = "Failed"
        if self.Status != "Failed":
            for ua_type,ua_id in args:
                complex_id = str(ua_type) + ":" + str(ua_id)
                for call in ua_seq_info[complex_id]:
                    if ua_seq_info[complex_id][call]:
                        logger.info("--| Try to compare (call-id: %s):",call)
                        self.seq_compare(ua_seq_info[complex_id][call],req_seq)
                    else:
                        logger.error("--| Campare failed. No retrans in call: %s",str(call))
                        self.Status = "Failed"

    def compare_msg_diff(self,diffrence,mode,call_mask,*args,**kwargs):
        timestamps = []
        msg_diff = []
        #Пока делим на 1000, так как таймера на ссв в основном в ms
        diffrence = float(diffrence)/1000
        ua_msg_timestamp = self.get_first_msg_timestamp(*args, **kwargs)
        if self.Status == "Failed":
            return
        # TODO: нужно придумать как будет обрабатываться inner_ua
        if mode == "inner_ua":
            self.Status = "Failed"
            logger.error("Mode %s not supported now", mode)
            return
        if mode == "between_ua":
            try:
                for ua_calls in ua_msg_timestamp.values():
                    # TODO: тут мы просто надеемся, что сравнение будет идти между 
                    count_of_call = len(call_mask) if call_mask else len(ua_calls)
                    ua_calls = list(ua_calls.values())
                    if not ua_calls:
                        self.Status = "Failed"
                        logger.error("Timestamp list is empty.")
                        return
                    if call_mask:
                        timestamps += [ua_calls[i-1] for i in call_mask]
                    else:
                        timestamps += ua_calls

                logger.info("Try to compare msg diff sequence with: %f. Mode: %s" , float(diffrence), str(mode))
                msg_diff = [self.get_diff(timestamps[i::count_of_call]) for i in range(count_of_call)]
                _ = list(self.value_compare(cur_d,diffrence,max_diff=0.5) for cur_d in msg_diff)
            except:
                logger.error("Exeption in compare_msg_diff function. Mode: %s", str(mode))
                self.Status = "Failed"
                return False
