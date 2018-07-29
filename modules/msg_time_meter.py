from modules.trace_parser import ShortTraceParser
from modules.trace_parser import TraceParseExp
from modules.trace_parser import MSG_TYPES
from modules.sip_tools import SIP_TIMERS, T1
from collections import OrderedDict
from pprint import pformat
from itertools import zip_longest as lzip
import modules.fs_worker as fs
import logging
import math

logger = logging.getLogger("tester")
logger.setLevel(logging.DEBUG)


class TimeDiffMeasureExp(Exception):
    pass


class TimeDiffMeasure:
    def __init__(self):
        self.UserWithTraces = dict()
        self.TrunkWithTraces = dict()

    def _parse_short_message_log(self, ua):
        if ua.UserObject:
            log_postfix = "UserObject with Number: %s" % str(ua.UserObject.Number)
        elif ua.TrunkObject:
            log_postfix = "TrunkObject with Port: %s" % str(ua.TrunkObject.Port)
        else:
            raise TimeDiffMeasureExp("Type of UA is not determined.")
        # If ua without trace file, then return
        if not ua.TimeStampFile:
            logger.debug("%s without trace file.", log_postfix)
            return
        try:
            with open(ua.TimeStampFile, 'r', encoding='utf-8') as f:
                logger.debug("Try to parse short_trace file for %s", log_postfix)
                ua.ShortTrParser = ShortTraceParser(f)
                ua.ShortTrParser.parse()
        except(FileNotFoundError, PermissionError) as e:
            raise TimeDiffMeasureExp("The trace file %s hasn't been open. Exception: %s" % (ua.TimeStampFile, e))
        except TraceParseExp as error:
            raise TimeDiffMeasureExp("Parse failed. Reason: %s" % error)

        if ua.UserObject:
            self.UserWithTraces[ua.UserId] = ua
        elif ua.TrunkObject:
            self.TrunkWithTraces[ua.TrunkId] = ua

    def _get_ua_object(self, ua_info):
        ua_type, ua_id = ua_info.split(":")
        ua_id = int(ua_id)
        try:
            if ua_type == "user":
                return self.UserWithTraces[ua_id]
            elif ua_type == "trunk":
                return self.TrunkWithTraces[ua_id]
            else:
                raise TimeDiffMeasureExp("Wrong ua description: %s" % ua_info)
        except KeyError:
            raise TimeDiffMeasureExp("UA %s without trace file." % ua_info)

    def _get_diff_for_time_seq(self, time_seq):
        logger.debug("Try to get time difference for next sequence:")
        self._pprint_list(time_seq, lvl=logging.DEBUG)
        # Raise exception if len of seq < 2
        if len(time_seq) < 2:
            raise TimeDiffMeasureExp("Timestamp sequence has wrong length: %d. Min length is 2" % len(time_seq))
        if None in time_seq:
            raise TimeDiffMeasureExp("Timestamp sequence has wrong item: None")
        # Convert to float
        seq = list(map(float, time_seq))
        # Calculating difference
        diffs = [seq[i+1] - seq[i] for i in range(len(seq) - 1)]
        logger.debug("Resulting difference list:")
        self._pprint_list(diffs, lvl=logging.DEBUG)
        return diffs

    @staticmethod
    def _pprint_list(some_list, lvl=logging.INFO):
        if lvl == logging.DEBUG:
            _ = list(map(logger.debug, pformat(some_list).split('\n')))
        else:
            _ = list(map(logger.info, pformat(some_list).split('\n')))

    def _get_time_seq_for_transaction(self, tr_list):
        """Get time sequence for message retransmission"""
        # Convert list of message obj to list of timestamps
        result = [(branch, [[m.Timestamp for m in m_list] for m_list in r_list]) for branch, r_list in tr_list]
        # Calculating difference between timestamps for calls with retransmissions
        result = [(branch, [self._get_diff_for_time_seq(t_list) for t_list in r_list])
                  for branch, r_list in result if r_list]
        return result

    def _get_time_dur_for_transaction(self, tr_list):
        """Get duration of message retransmission"""
        # Convert list of message obj to list of timestamps
        result = [(branch, [[m.Timestamp for m in m_list] for m_list in r_list]) for branch, r_list in tr_list]
        # Calculating difference between first and last timestamps.
        result = [(branch, [self._get_diff_for_time_seq([t_list[0], t_list[-1]])[0]
                            for t_list in r_list]) for branch, r_list in result if r_list]
        return result

    def _get_retransmission_seq_for_ua(self, ua_info, **kwargs):
        ua = self._get_ua_object(ua_info)
        # Get retransmissions for calls
        call_list = [(call.CallID, call.get_msg_retransmission(**kwargs)) for call in ua.ShortTrParser.Calls]
        # Get diff between retransmission messages
        call_list = [(call_id, self._get_time_seq_for_transaction(tr_list)) for call_id, tr_list in call_list]
        result = (ua_info, call_list)
        return result

    def _get_retransmission_dur_for_ua(self, ua_info, **kwargs):
        ua = self._get_ua_object(ua_info)
        # Get retransmissions for calls
        call_list = [(call.CallID, call.get_msg_retransmission(**kwargs)) for call in ua.ShortTrParser.Calls]
        # Get diff between retransmission messages
        call_list = [(call_id, self._get_time_dur_for_transaction(tr_list)) for call_id, tr_list in call_list]
        result = (ua_info, call_list)
        return result

    def _get_time_for_first_msg_in_call(self, ua_info, **kwargs):
        ua = self._get_ua_object(ua_info)
        call_list = [(call.CallID, call.get_first_message_in_call(**kwargs)) for call in ua.ShortTrParser.Calls]
        call_list = [(call_id, [(br, msg.Timestamp) for br, msg in tr_list])
                     for call_id, tr_list in call_list if tr_list]
        call_list = [(call_id, {t for _, t in tr_list}) for call_id, tr_list in call_list]
        result = (ua_info, call_list)
        return result

    @staticmethod
    def _convert_msg_description(msg):
        msg["MsgType"] = MSG_TYPES.REQUEST if msg["MsgType"] == "request" else MSG_TYPES.RESPONSE
        msg["Method"] = str(msg.get("Method")).upper()

    @staticmethod
    def _compare_seq(seq_a, seq_b, max_error=0.1):
        logger.info("Start of comparing of two sequences.")
        logger.info("├ First sequence: %s", list(map(lambda x: round(x, 1), seq_a)))
        logger.info("├ Second sequence: %s", list(map(lambda x: round(x, 1), seq_b)))
        logger.info("├ Max error: %s", str(max_error))

        if len(seq_a) != len(seq_b):
            raise TimeDiffMeasureExp("Can't compare sequences with different length")

        for a, b in zip(seq_a, seq_b):
            if math.fabs(float(a)-float(b)) > max_error:
                logger.error("Comparison has been completed with result: fail")
                return False
        logger.info("Comparison has been completed with result: success")
        return True

    @staticmethod
    def _compare_value(val1, val2, max_error=0.1):
        logger.info("Start of comparing of two values.")
        logger.info("├ First value: %s", val1)
        logger.info("├ Second value: %s", val2)
        logger.info("├ Max error: %s", str(max_error))
        if math.fabs(float(val1)-float(val2)) > max_error:
            logger.error("Comparison has been completed with result: fail")
            return False
        else:
            logger.info("Comparison has been completed with result: success")
            return True

    @staticmethod
    def _compare_seq_item_with_val(seq, val, max_error=0.1):
        logger.info("Start of comparing of sequence items with value.")
        logger.info("├ Sequence: %s", list(map(lambda x: round(x, 1), seq)))
        logger.info("├ Require value: %s", val)
        logger.info("├ Max error: %s", str(max_error))

        if True in list(map(lambda x: math.fabs(float(x)-float(val)) > max_error, seq)):
            logger.error("Comparison has been completed with result: fail")
            return False
        logger.info("Comparison has been completed with result: success")
        return True

    def _compare_time_sequence_for_ua(self, req_seq, ua_seq):
        """This function compare time sequences for all calls from ua_seq with req_seq"""
        ua_name, ua_calls_seq = ua_seq
        logger.info("Start comparison of time sequences for: %s", ua_name)
        for call_id, tr_list in ua_calls_seq:
            if not tr_list:
                raise TimeDiffMeasureExp("The call: %s without time sequence." % call_id)
            for branch, timer_seq in tr_list:
                logger.info("The call for comparison: %s, %s", call_id, branch.replace("branch=", ""))
                result = list(map(lambda x: self._compare_seq(x, req_seq), timer_seq))
                if False in result:
                    return False
        return True

    def _compare_time_value_for_ua(self, req_val, ua_seq, add=0):
        """This function compare time differences for all calls from ua_seq with required value"""
        # Retransmission duration it is time difference between first and last SIP messages from sipp trace file
        # Usually (if T1 = 0.5) this time is equal 31.5s, and retransmission timeout is equal 64*T1 = 32s.
        # For compensation of this difference use add arg. Use only CheckRetransmission method!
        ua_name, ua_time_seq = ua_seq
        logger.info("Start comparison of values for: %s", ua_name)
        for call_id, tr_list in ua_time_seq:
            if not tr_list:
                raise TimeDiffMeasureExp("The call: %s without time sequence." % call_id)
            for branch, timer_seq in tr_list:
                logger.info("The call for comparison: %s, %s", call_id, branch.replace("branch=", ""))
                result = list(map(lambda x: self._compare_value(x + add, req_val), timer_seq))
                if False in result:
                    return False
        return True

    def _parse_trace_file_for_ua(self, ua):
        try:
            if not ua.ShortTrParser:
                self._parse_short_message_log(ua)
        except TraceParseExp as error:
            raise TimeDiffMeasureExp("Parse trace file failed. Error: %s" % error)
        logger.debug("Parsing of trace files completed.")

    def check_timer(self, t_obj, ua_list):
        self._convert_msg_description(t_obj.Msg)
        logger.info("Start checking of time difference for timer:")
        logger.info("├ Timer: %s", t_obj.Timer)
        logger.info("├ CompareUA: %s", t_obj.UA)
        logger.info("├ Message: type %s, method %s, code %s", *t_obj.Msg.values())
        timer = SIP_TIMERS.get(t_obj.Timer)
        _ = list(map(self._parse_trace_file_for_ua, ua_list))
        if not timer:
            raise TimeDiffMeasureExp("Timer %s not supported" % t_obj.Timer)
        if type(timer) == list:
            list_for_compare = list(map(lambda x: self._get_retransmission_seq_for_ua(x, **t_obj.Msg), t_obj.UA))
            result = list(map(lambda x: self._compare_time_sequence_for_ua(timer, x), list_for_compare))
        else:
            list_for_compare = list(map(lambda x: self._get_retransmission_dur_for_ua(x, **t_obj.Msg), t_obj.UA))
            result = list(map(lambda x: self._compare_time_value_for_ua(timer, x, add=T1), list_for_compare))
        if False in result:
            return False
        else:
            return True

    def _check_difference_for_call(self, compare_list, val):
        call_id, t_list = compare_list
        logger.debug("Comparing between next calls:")
        self._pprint_list(call_id, logging.DEBUG)
        t_list = [list(map(float, t)) for t in t_list]
        t_list = list(map(self._get_diff_for_time_seq, t_list))
        result = list(map(lambda x: self._compare_seq_item_with_val(x, val), t_list))
        return result

    def _check_time_difference_between_ua(self, d_obj):
        if d_obj.CompareMode == "between_calls":
            for msg in d_obj.Msg:
                logger.debug("Start comparing for msg: type %s, method %s, code %s", *msg.values())
                # Get list of UA which contains next tuple:
                # (ua_info, [(call_id1,{timestamp1}), (call_id2,{timestamp2})])
                # example: ('user:0', [('BA:1ebf0', {'1530871260.402419'}), ('BA:2eb0', {'1530871270.403639'})],
                #          ('user:1', [('BA:1ebf1', {'1530871261.402419'}), ('BA:2eb1', {'1530871271.403639'})],
                #          ('user:2', [('BA:1ebf2', {'1530871262.402419'}), ('BA:2eb2', {'1530871272.403639'})])
                list_for_compare = list(map(lambda x: self._get_time_for_first_msg_in_call(x, **msg), d_obj.UA))
                # Aggregating elements for each ua and splitting it to ua_list and call_list
                user_list, call_list = zip(*list_for_compare)
                logger.debug("Comparing between next UA: %s", ", ".join(user_list))
                # Aggregating elements for each call.
                # (First call from ua1 to first call from ua2,..,uaN)
                # (Second call from ua1 to second call from ua2,..,uaN)
                # example: [(('BA:1ebf0, {'1530871260.402419'}),
                #            ('BA:1ebf1', {'1530871261.402419'}),
                #            ('BA:1ebf2', {'1530871262.402419'})),
                #           (('BA:2eb0', {'1530871270.403639'}),
                #            ('BA:2eb1', {'1530871271.403639'}),
                #            ('BA:2eb2', {'1530871272.403639'}))]
                call_list = list(zip(*call_list))
                # Splitting call_id and timestamps for each_call
                # example:
                # [(('BA:1ebf0', 'BA:1ebf1', 'BA:1ebf2'), <zipped timestamps>),
                #  (('BA:2eb0', 'BA:2eb1', 'BA:2eb2'), <zipped timestamps>)]
                call_list = [(call_id, zip(*timestamp)) for call_id, timestamp in
                             list(map(lambda x: zip(*x), call_list))]
                # check difference
                result = list(map(lambda x: self._check_difference_for_call(x, d_obj.Difference), call_list))
                if False in result:
                    return False
        elif d_obj.CompareMode == "between_msg":
            if len(d_obj.Msg) != len(d_obj.UA):
                raise TimeDiffMeasureExp("Count of Msg must be equal count of UA for between_msg compare mode")
            args_for_compare = list(zip(d_obj.Msg, d_obj.UA))
        else:
            raise TimeDiffMeasureExp("Mode %s not supported" % str(d_obj.CompareMode))
        return True

    def _check_time_difference_inner_ua(self, d_obj):
        return self

    def check_time_difference(self, d_obj, ua_list):
        logger.info("Check Diff Params:")
        logger.info("├ Mode: %s", d_obj.Mode)
        logger.info("├ CompareMode: %s", d_obj.CompareMode)
        logger.info("├ CompareUA: %s", d_obj.UA)
        logger.info("├ CompareCalls: %s", d_obj.Calls)
        logger.info("├ Require diff: %s", str(d_obj.Difference))
        logger.info("├ Messages:")
        _ = list(map(self._convert_msg_description, d_obj.Msg))
        for count, msg in enumerate(d_obj.Msg):
            logger.info("├ Message %d: type %s, method %s, code %s", count, *msg.values())
        pass
        _ = list(map(self._parse_trace_file_for_ua, ua_list))
        logger.debug("Trying to check time differences in %s mode.", d_obj.Mode)
        if d_obj.Mode == "between_ua":
            result = self._check_time_difference_between_ua(d_obj)
        elif d_obj.Mode == "inner_ua":
            result = self._check_time_difference_inner_ua(d_obj)
        else:
            raise TimeDiffMeasureExp("Unknown mode: %s" % d_obj.Mode)
        return result








class DiffCalcExeption(Exception):
    pass

class DifferCalc:
    def __init__(self, test):
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
        _ = list(map(self.parse_short_trace_msg, test.CompleteUA + test.WaitBackGroundUA))

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
        logger.info("Sequence for compare: %s", list(map(lambda x: round(x, 1), sequence)))
        logger.info("Require value: %s", str(req_value))
        logger.info("Max error: %s", str(max_error))
        if False in list(map(lambda x: math.fabs(x - req_value) <= max_error, sequence)):
            logger.error("Comparison is complete. Result: fail")
            self.Status = "Failed"
        else:
            logger.info("Comparison is complete. Result: success")

    def seq_compare(self, seq_a, seq_b, max_error=0.05):
        logger.info("Comparison start.")
        logger.info("====================================")
        logger.info("First sequence for compare: %s", list(map(lambda x: round(x, 1), seq_a)))
        logger.info("Second sequence for compare: %s", list(map(lambda x: round(x, 1), seq_b)))
        logger.info("Max error: %s", str(max_error))

        if len(seq_a) != len(seq_b):
            raise DiffCalcExeption("Can't compare sequence with different length")

        for a, b in zip(seq_a, seq_b):
            if math.fabs(float(a)-float(b)) > max_error:
                logger.error("Comparison is complete. Result: fail")
                return False
        logger.info("Comparison is complete. Result: success")
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
        logger.debug("Try to parse short_trace file for %s", log_postfix)
        ua.ShortTrParser = tr_parser.short_trace_parser(stat_file)
        ua.ShortTrParser.parse_trace_msg()
        logger.debug("Сlose short_trace file for %s", log_postfix)
        stat_file.close()
        if ua.ShortTrParser.Status == "Failed":
            logger.error("Parse complete for %s. Result: %s.", log_postfix, ua.ShortTrParser.Status)
            self.Status = "Failed"
        else:
            logger.debug("Parse complete for %s. Result: %s.", log_postfix, ua.ShortTrParser.Status)
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
        msg_info = id
        msg_info["msg_type"] = kwargs.get("MsgType")
        msg_info["method"] = kwargs.get("Method")
        msg_info["resp_code"] = kwargs.get("Code")
        result = OrderedDict()
        logger.info("Try to search first timestamp for message: %s", kwargs)
        for ua_info in args:
            ua = self._get_ua_obj(ua_info)
            if not ua:
                raise DiffCalcExeption("UA object %s without trace file." % ua_info)
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

    def get_retrans_sequence(self, *args, **kwargs):
        msg_info = {}
        msg_info["msg_type"] = kwargs.get("MsgType")
        msg_info["method"] = kwargs.get("Method")
        msg_info["resp_code"] = kwargs.get("Code")
        result = OrderedDict()
        logger.info("Try to search message retarnsmission: %s.", msg_info)
        for ua_info in args:
            ua = self._get_ua_obj(ua_info)
            if not ua:
                raise DiffCalcExeption("UA object %s without trace file." % ua_info)
            # Get timestamp sequence for messages
            call_seq = OrderedDict()
            for call in ua.ShortTrParser.calls:
                call_seq[call.call_id] = (call.get_retrans_time_seq(**msg_info))
                if call_seq[call.call_id]:
                    logger.info("Retransmission for %s is found. call: %s.", ua_info, call.call_id)
                else:
                    raise DiffCalcExeption("Retransmission for %s isn't found. call: %s." % (ua_info, call.call_id))
            # Calculating timestamp difference
            for call, seq in call_seq.items():
                call_seq[call] = self.get_diff(seq)
            result[ua_info] = call_seq
        return result

    def get_retrans_duration(self, *args, **kwargs):
        msg_info = {}
        msg_info["msg_type"] = kwargs.get("MsgType")
        msg_info["method"] = kwargs.get("Method")
        msg_info["resp_code"] = kwargs.get("Code")

        result = OrderedDict()
        logger.info("Trying to get msg retransmission duration. %s", msg_info)
        for ua_info in args:
            ua = self._get_ua_obj(ua_info)
            if not ua:
                raise DiffCalcExeption("UA object %s without trace file." % ua_info)

            ua_msg_timestamp = {}
            ua_msg_timestamp = OrderedDict(ua_msg_timestamp)
            for call in ua.ShortTrParser.calls:
                ua_msg_timestamp[call.call_id] = call.get_retrans_duration(**msg_info)
                if ua_msg_timestamp[call.call_id]:
                    logger.info("Msg retransmission duration for %s found. call: %s", ua_info, call.call_id)
                else:
                    raise DiffCalcExeption("Msg retransmission duration for %s isn't found. call: %s" % (ua_info, call.call_id))
            result[ua_info] = ua_msg_timestamp
        return result

    def get_diff(self, seq):
        logger.info("Try to get difference for timestamp sequence:")
        self._pprint_list(seq)
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

    def compare_msg_diff(self, compare_obj):
        logger.info("====================================")
        logger.info("Compare params:")
        logger.info("--| Mode: %s", compare_obj.Mode)
        logger.info("--| CompareMode: %s", compare_obj.CompareMode)
        logger.info("--| CompareUA: %s", compare_obj.UA)
        logger.info("--| CompareCalls: %s", compare_obj.Calls)
        logger.info("--| Require diff: %s", str(compare_obj.Difference))
        logger.info("--| Messages:")
        for msg in compare_obj.Msg:
            logger.info("--| %s", msg.__dict__)
        logger.info("====================================")
        if compare_obj.Mode == "inner_ua":
            self.compare_diff_inner_ua(compare_obj)
        if compare_obj.Mode == "between_ua":
            self.compare_diff_between_ua(compare_obj)

    def compare_timer_seq(self, compare_obj):
        req_seq = []
        if compare_obj.Timer in ["A"]:
            req_seq = self.seq_inv_retrans
            get_timer_seq_func = self.get_retrans_sequence
        elif compare_obj.Timer in ["B", "F", "H"]:
            req_seq.append(self.tr_timeout - 0.5)
            get_timer_seq_func= self.get_retrans_duration
        elif compare_obj.Timer in ["E", "G"]:
            req_seq = self.seq_non_inv_retrans
            get_timer_seq_func= self.get_retrans_sequence
        else:
            raise DiffCalcExeption("Unknown sip timer: %s." % str(compare_obj.Timer))

        logger.info("====================================")
        logger.info("Compare params:")
        logger.info("--| Timer: %s", compare_obj.Timer)
        logger.info("--| CompareUA: %s", compare_obj.UA)
        logger.info("--| Messages:")
        for msg in compare_obj.Msg:
            logger.info("--| %s", msg.__dict__)
        logger.info("====================================")

        for msg in compare_obj.Msg:
            timer_seq = get_timer_seq_func(*compare_obj.UA, **msg.__dict__)
            # Get timestamp for calls
            for ua_seq in timer_seq.values():
                if False in list(map(lambda x: self.seq_compare(x, req_seq), ua_seq.values())):
                    self.Status = "Failed"
                    return  False
        return True


