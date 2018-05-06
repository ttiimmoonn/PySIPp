import modules.trace_parser as tr_parser
import modules.fs_worker as fs
from collections import OrderedDict
import logging
import math
from itertools import zip_longest

logger = logging.getLogger("tester")


class DiffCalcExeption(Exception):
    pass


class DifferCalc:
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
        # Получаем временные последовательности для таймеров.
        self.get_inv_retrans_seq()
        self.get_non_inv_retrans_seq()
        # Парсим short_msg log
        _ = list(map(self.parse_short_trace_msg, test.CompliteUA))

    def _get_ua_obj(self, ua_info):
        ua_type, ua_id = ua_info.split(":")
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

    def value_compare(self, sequence, req_value, max_error=0.05):
        req_value = float(req_value)
        max_error = float(max_error)
        sequence = list(map(float, sequence))
        logger.info("Comparison start.")
        logger.info("====================================")
        logger.info("Sequence for compare: %s", list(map(lambda x: round(x, 1),sequence)))
        logger.info("Require value: %s", str(req_value))
        logger.info("Max error: %s", str(max_error))
        if False in list(map(lambda x: math.fabs(x - req_value) <= max_error, sequence)):
            logger.error("Comparison is complete. Result: fail")
            self.Status = "Failed"
        else:
            logger.info("Comparison is complete. Result: success")

    def seq_compare(self, seq_a, seq_b, max_diff=0.05):
        logger.info("--| SEQ A: %s", ' '.join(map(str, [round(x, 1)for x in seq_a])))
        logger.info("--| SEQ B: %s", ' '.join(map(str, [round(x, 1)for x in seq_b])))
        logger.info("--| Max diff: %s",str(max_diff))
        try:
            if len(seq_a) != len(seq_b):
                logger.warning("--| Can't compare sequence with different length. len seq_a: %d,len seq_b: %d",len(seq_a),len(seq_b))
                self.Status = "Failed"
                return False

            for a,b in zip(seq_a, seq_b):
                if math.fabs(float(a)-float(b)) > max_diff:
                    logger.warning("--| Compare complete. Result: fail")
                    self.Status = "Failed"
                    return False
        except:
            logger.warning("--| Exception in seq_compare function.")
            self.Status = "Failed"
            return False
        logger.info("--| Compare complete. Result: succ")
        return True

    def parse_short_trace_msg(self, ua):
        if ua.UserObject:
            log_postfix = "UserObject with Number: %s" % str(ua.UserObject.Number)
        elif ua.TrunkObject:
            log_postfix = "TrunkObject with Port: %s" % str(ua.TrunkObject.Port)
        else:
            logger.error("Wrong ua object.")
            self.Status = "Failed"
            return
        # Парсим только те UA, которые имеют TimeStampFile
        if not ua.TimeStampFile:
            logger.debug("Parse complete for %s. Result: Failed (trace file not found).", log_postfix)
            return

        fs_work = fs.fs_working()
        # Получаем файловый дескриптор на файл с short_trace
        stat_file = fs_work.get_fd(ua.TimeStampFile)
        # Если удалось получить дескриптор с short_trace, обрабатываем его
        if not stat_file:
            return
        logger.debug("Try to parse short_trace file for %s",log_postfix)
        ua.ShortTrParser = tr_parser.short_trace_parser(stat_file)
        ua.ShortTrParser.parse_trace_msg()
        logger.debug("Сlose short_trace file for %s",log_postfix)
        stat_file.close()
        if ua.ShortTrParser.Status == "Failed":
            logger.error("Parse complete for %s. Result: %s.",log_postfix,ua.ShortTrParser.Status)
            self.Status = "Failed"
        else:
            logger.debug("Parse complete for %s. Result: %s.",log_postfix,ua.ShortTrParser.Status)
            if ua.UserObject:
                self.users_with_traces[ua.UserId] = ua
            elif ua.TrunkObject:
                self.trunks_with_traces[ua.TrunkId] = ua

    def get_inv_retrans_seq(self):
        diff = self.t1
        while diff < self.tr_timeout:
            self.seq_inv_retrans.append(diff)
            diff *= 2

    def get_non_inv_retrans_seq(self):
        diff = self.t1
        while diff < self.tr_timeout:
            if diff < self.t2:
                self.seq_non_inv_retrans.append(diff)
                diff *= 2
            else:
                self.seq_non_inv_retrans.append(self.t2)
                diff += 4

    def get_first_msg_timestamp(self, *args, **kwargs):
        # args - ua_id для которых выполняется функция.
        # kwargs - параметры искомого сообщения
        # для ответов  - {"msg_type":"response", "method": "INVITE", "resp_code": "200"}
        # для запросов - {"msg_type":"request", "method": "BYE", "resp_code": None}
        msg_info = {}
        msg_info["msg_type"] = kwargs.get("MsgType")
        msg_info["method"] = kwargs.get("Method")
        msg_info["resp_code"] = kwargs.get("Code")
        result = OrderedDict()
        logger.info("Try to search first timestamp for message: %s", kwargs)
        for ua_info in args:
            ua = self._get_ua_obj(ua_info)
            if not ua:
                raise DiffCalcExeption("UA object %s without trace file." % (ua_info))
            ua_msg_timestamp = OrderedDict()
            for call in ua.ShortTrParser.calls:
                timestamp = call.get_first_msg_timestamp(**msg_info)
                if not timestamp:
                    ua_msg_timestamp[call.call_id] = None
                else:
                    ua_msg_timestamp[call.call_id] = timestamp
                    logger.info("Found timestamp: %s for %s in call: %s", timestamp, ua_info, call.call_id)
            result[ua_info] = ua_msg_timestamp
        return result

    def get_retrans_diff(self, *args, **kwargs):
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
            # Получаем последовательность временных меток для нужного сообщения
            call_seq = self.get_retrans_time_seq(ua,**kwargs)
            # Словарь для хранения результатов по всем вызовам
            result_seq = {}
            result_seq = OrderedDict(result_seq)
            # Начинаем расчёт diff для всех вызовов
            for call in call_seq:
                if call_seq[call]:
                    result_seq[call] = self.get_diff(call_seq[call])
                else:
                    result_seq[call] = False
                call_diff = []
            result[str(ua_type) + ":" + str(ua_id)] = result_seq
        return result

    @staticmethod
    def get_retrans_time_seq(ua, **kwargs):
        result_seq = {}
        # Делаем словарь упорядоченным, чтобы вызовы шли по порядку.
        result_seq = OrderedDict(result_seq)
        # Запрашиваем последовательности timestamp для всех вызовов
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

    def compare_timer_seq(self, timer_name, *args, **kwargs):
        req_seq = []
        ua_seq_info = {}
        if timer_name in ["A"]:
            req_seq = self.seq_inv_retrans
            ua_seq_info = self.get_retrans_diff(*args, **kwargs)
        elif timer_name in ["B", "F", "H"]:
            req_seq.append(self.tr_timeout - 0.5)
            ua_seq_info = self.get_retrans_duration(*args, **kwargs)
        elif timer_name in ["E", "G"]:
            req_seq = self.seq_non_inv_retrans
            ua_seq_info = self.get_retrans_diff(*args, **kwargs)
        else:
            logger.error("Unknown timer name: %s", str(timer_name))
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

    @staticmethod
    def get_diff(seq):
        logger.info("Try to get difference for timestamp sequence: %s", seq)
        # Raise exception if len of seq < 2
        if len(seq) < 2:
            raise DiffCalcExeption("Timestamp sequence has wrong length: %d" % len(seq))
        if None in seq:
            raise DiffCalcExeption("Timestamp sequence has wrong item: None")
        # Convert to float
        seq = list(map(float, seq))
        # Calculating difference
        diffs = [seq[i+1] - seq[i] for i in range(len(seq) - 1)]
        logger.info("Differences: %s", list(map(lambda x: round(x, 1), diffs)))
        return diffs


    @staticmethod
    def _pprint_list(timestamp_list):
        from pprint import pprint, pformat
        _ = list(map(logger.info, pformat(timestamp_list).split('\n')))

    def get_timestamp_sequence(self, diff_desc, search_result):
        logger.info("Try to get timestamp sequence.")
        # Get calls from ua
        search_result = list(search_result.values())
        # Get timestamp from all calls
        timestamp_list = list(map(lambda x: list(x.values()), search_result))
        logger.info("Initial seq:")
        self._pprint_list(timestamp_list)
        if diff_desc.Calls:
            logger.info("Try to apply call filter: %s", ",".join(list(map(str, diff_desc.Calls))))
            # Make timestamp filtering by call mask
            try:
                timestamp_list = list(map(lambda x: [x[i] for i in diff_desc.Calls], timestamp_list))
                logger.info("Filtered seq:")
                self._pprint_list(timestamp_list)
            except IndexError as error:
                raise DiffCalcExeption("Call mask can not be applied. %s" % error)

        if diff_desc.Mode == "between_ua":
            # For between_ua mode make zip of timestamps
            timestamp_list = list(zip_longest(*timestamp_list, fillvalue=False))
            logger.info("Zipped seq:")
            self._pprint_list(timestamp_list)
        logger.info("Final seq:")
        self._pprint_list(timestamp_list)
        return timestamp_list

    def compare_diff_between_ua(self, diff_desc):
        """This function compare time difference between varied UA"""
        if diff_desc.CompareMode == "perUa":
            # Each ua_id corresponds to message.
            # So, in this mode we can compare time difference between varied messages
            # for example between INVITE and BYE requests

            # Link ua_id to request.
            # Warn! Count of request must be equal count of ua
            if len(diff_desc.UA) != len(diff_desc.Msg):
                raise DiffCalcExeption("Count of messages must be equal count of ua for %s mode" % diff_desc.CompareMode)
            search_result = {}
            for ua, msg in zip_longest(diff_desc.UA, diff_desc.Msg, fillvalue=False):
                search_result.update(self.get_first_msg_timestamp(ua, **msg.__dict__))
            timestamp_list = self.get_timestamp_sequence(diff_desc, search_result)
            # Get all msg difference for several calls
            msg_diff = list(map(self.get_diff, timestamp_list))
            # Make compare
            _ = list(map(lambda x: self.value_compare(x, diff_desc.Difference, max_error=0.5), msg_diff))
        elif diff_desc.CompareMode == "perMsg":
            # Each message corresponds to ua_id.
            # So, in this mode we can compare time difference for one message between varied UA
            # for example between INVITE requests for UA with id 1,2

            for msg in diff_desc.Msg:
                search_result = self.get_first_msg_timestamp(*diff_desc.UA, **msg.__dict__)
                timestamp_list = self.get_timestamp_sequence(diff_desc, search_result)
                # Get all msg difference for several calls
                msg_diff = list(map(self.get_diff, timestamp_list))
                # Make compare
                _ = list(map(lambda x: self.value_compare(x, diff_desc.Difference, max_error=0.5), msg_diff))
        else:
            self.Status = "Failed"
            logger.error("Unknown compare mode %s.", diff_desc.CompareMode)
            return False

    def compare_diff_inner_ua(self, diff_desc):
        """This function compare time difference inner UA"""
        if diff_desc.CompareMode == "perMsg":
            # get timestamp sequence for each message.
            for msg in diff_desc.Msg:
                search_result = self.get_first_msg_timestamp(*diff_desc.UA, **msg.__dict__)
                timestamp_list = self.get_timestamp_sequence(diff_desc, search_result)
                msg_diff = list(map(self.get_diff, timestamp_list))
                _ = list(map(lambda x: self.value_compare(x, diff_desc.Difference, max_error=0.5), msg_diff))
        elif diff_desc.CompareMode == "perUa":
            result = []
            for msg in diff_desc.Msg:
                search_result = self.get_first_msg_timestamp(*diff_desc.UA, **msg.__dict__)
                timestamp_list = self.get_timestamp_sequence(diff_desc, search_result)
                result.append(timestamp_list)
            # Zip by messages
            result = list(zip_longest(*result, fillvalue=False))
            # Zip by call
            result = list(map(lambda x: list(zip_longest(*x, fillvalue=False)), result))
            for call in result:
                msg_diff = list(map(self.get_diff, call))
                _ = list(map(lambda x: self.value_compare(x, diff_desc.Difference, max_error=0.5), msg_diff))

    def compare_msg_diff(self, diff_desc):
        logger.info("====================================")
        logger.info("Compare params:")
        logger.info("--| Mode: %s", diff_desc.Mode)
        logger.info("--| CompareMode: %s", diff_desc.CompareMode)
        logger.info("--| CompareUA: %s", diff_desc.UA)
        logger.info("--| CompareCalls: %s", diff_desc.Calls)
        logger.info("--| Require diff: %s", str(diff_desc.Difference))
        logger.info("--| Messages:")
        for msg in diff_desc.Msg:
            logger.info("--| %s", msg.__dict__)
        logger.info("====================================")
        if diff_desc.Mode == "inner_ua":
            self.compare_diff_inner_ua(diff_desc)
        if diff_desc.Mode == "between_ua":
            self.compare_diff_between_ua(diff_desc)
