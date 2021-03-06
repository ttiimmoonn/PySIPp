from modules.trace_parser import ShortTraceParser
from modules.trace_parser import TraceParseExp
from modules.trace_parser import MSG_TYPES
from modules.sip_tools import SIP_TIMERS, T1
from pprint import pformat
from itertools import zip_longest as zpl
import logging
import math

logger = logging.getLogger("tester")
logger.setLevel(logging.INFO)


class TimeDiffMeterExp(Exception):
    pass


class TimeDiffMeter:
    def __init__(self):
        self.UserWithTraces = dict()
        self.TrunkWithTraces = dict()

    def _parse_short_message_log(self, ua):
        if ua.UserObject:
            log_postfix = "UserObject with Number: %s" % str(ua.UserObject.Number)
        elif ua.TrunkObject:
            log_postfix = "TrunkObject with Port: %s" % str(ua.TrunkObject.Port)
        else:
            logger.error("Type of UA is not determined.")
            raise TimeDiffMeterExp("ParseError")
        # If ua without trace file, then return
        if not ua.TimeStampFile:
            logger.debug("%s without trace file.", log_postfix)
            return
        # Parse sip trace file if ShortTrParser not set.
        if not ua.ShortTrParser:
            ua.ShortTrParser = ShortTraceParser()
            try:
                ua.ShortTrParser.parse(ua.TimeStampFile)
            except TraceParseExp as error:
                logger.error("Parse failed. Reason: %s", error)
                raise TimeDiffMeterExp("ParseError")
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
                logger.error("Wrong ua description: %s", ua_info)
                raise TimeDiffMeterExp("CompareError")
        except KeyError:
            logger.error("UA %s without trace file.", ua_info)
            raise TimeDiffMeterExp("CompareError")

    def _get_diff_for_time_seq(self, time_seq):
        logger.debug("Try to get time difference for next sequence:")
        self._pprint_list(time_seq, lvl=logging.DEBUG)
        # Raise exception if len of seq < 2
        if len(time_seq) < 2:
            logger.error("Timestamp sequence has wrong length: %d. Min length is 2", len(time_seq))
            raise TimeDiffMeterExp("CompareError")
        if None in time_seq:
            logger.error("Timestamp sequence has wrong item: None")
            raise TimeDiffMeterExp("CompareError")
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
        elif lvl == logging.INFO:
            _ = list(map(logger.info, pformat(some_list).split('\n')))
        elif lvl == logging.ERROR:
            _ = list(map(logger.error, pformat(some_list).split('\n')))

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
        logger.info("Search retransmissions in: \"%s\", msg: (type: %s, method: %s, code: %s)",
                    ua_info, *kwargs.values())
        ua = self._get_ua_object(ua_info)
        # Get retransmissions for calls
        call_list = [(call.CallID, call.get_msg_retransmission(**kwargs)) for call in ua.ShortTrParser.Calls]
        # Get diff between retransmission messages
        call_list = [(call_id, self._get_time_seq_for_transaction(tr_list)) for call_id, tr_list in call_list]
        result = (ua_info, call_list)
        return result

    def _get_retransmission_dur_for_ua(self, ua_info, **kwargs):
        logger.info("Search retransmissions in: \"%s\", msg: (type: %s, method: %s, code: %s)",
                    ua_info, *kwargs.values())
        ua = self._get_ua_object(ua_info)
        # Get retransmissions for calls
        call_list = [(call.CallID, call.get_msg_retransmission(**kwargs)) for call in ua.ShortTrParser.Calls]
        # Get diff between retransmission messages
        call_list = [(call_id, self._get_time_dur_for_transaction(tr_list)) for call_id, tr_list in call_list]
        result = (ua_info, call_list)
        return result

    def _get_time_for_first_msg_in_call(self, ua_info, **kwargs):
        logger.info("Search in: \"%s\", msg: (type: %s, method: %s, code: %s)", ua_info, *kwargs.values())
        ua = self._get_ua_object(ua_info)
        call_list = [(call.CallID, call.get_first_message_in_call(**kwargs)) for call in ua.ShortTrParser.Calls]
        call_list = [(call_id, msg.Timestamp if msg else None) for call_id, msg in call_list]
        result = (ua_info, call_list)
        return result

    @staticmethod
    def _convert_msg_description(msg):
        msg["MsgType"] = MSG_TYPES.REQUEST if msg["MsgType"] == "request" else MSG_TYPES.RESPONSE
        msg["Method"] = str(msg.get("Method")).upper()

    @staticmethod
    def _compare_seq(seq_a, seq_b, max_error=0.1):
        logger.info("Start comparison for two sequences.")
        logger.info("├ First sequence: %s", list(map(lambda x: round(x, 1), seq_a)))
        logger.info("├ Second sequence: %s", list(map(lambda x: round(x, 1), seq_b)))
        logger.info("├ Max error: %s", str(max_error))

        if len(seq_a) != len(seq_b):
            logger.error("Can't compare sequences with different length")
            raise TimeDiffMeterExp("CompareError")

        for a, b in zip(seq_a, seq_b):
            if math.fabs(float(a)-float(b)) > max_error:
                logger.error("Comparison has been completed with result: fail")
                return False
        logger.info("Comparison has been completed with result: success")
        return True

    @staticmethod
    def _compare_value(val1, val2, max_error=0.1):
        logger.info("Start comparison of two values.")
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
        logger.info("Start comparison of sequence items with value.")
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
                logger.error("The call: %s without time sequence.", call_id)
                raise TimeDiffMeterExp("CompareError")
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
                logger.error("The call: %s without time sequence.", call_id)
                raise TimeDiffMeterExp("CompareError")
            for branch, timer_seq in tr_list:
                logger.info("The call for comparison: %s, %s", call_id, branch.replace("branch=", ""))
                result = list(map(lambda x: self._compare_value(x + add, req_val), timer_seq))
                if False in result:
                    return False
        return True

    def _parse_trace_file_for_ua(self, ua):
        try:
            self._parse_short_message_log(ua)
        except TraceParseExp as error:
            logger.error("Parse trace file failed. Error: %s", error)
            raise TimeDiffMeterExp("ParseError")
        logger.debug("Parsing of trace files completed.")

    def check_timer(self, t_obj, ua_list):
        self._convert_msg_description(t_obj.Msg)
        logger.info("Start checking of time difference for timer:")
        logger.info("├ Timer: %s", t_obj.Timer)
        logger.info("├ CompareUA: %s", t_obj.UA)
        logger.info("├ Calls: %s", t_obj.Calls)
        logger.info("├ Message: type %s, method %s, code %s", *t_obj.Msg.values())
        timer = SIP_TIMERS.get(t_obj.Timer)
        _ = list(map(self._parse_trace_file_for_ua, ua_list))
        if not timer:
            logger.error("Timer %s not supported", t_obj.Timer)
            raise TimeDiffMeterExp("CompareError")
        if type(timer) is list:
            list_for_compare = list(map(lambda x: self._get_retransmission_seq_for_ua(x, **t_obj.Msg), t_obj.UA))
            list_for_compare = [(ua_info, self._filter_call_list(call_list, t_obj.Calls))
                                for ua_info, call_list in list_for_compare]
            result = list(map(lambda x: self._compare_time_sequence_for_ua(timer, x), list_for_compare))
        else:
            list_for_compare = list(map(lambda x: self._get_retransmission_dur_for_ua(x, **t_obj.Msg), t_obj.UA))
            list_for_compare = [(ua_info, self._filter_call_list(call_list, t_obj.Calls))
                                for ua_info, call_list in list_for_compare]
            result = list(map(lambda x: self._compare_time_value_for_ua(timer, x, add=T1), list_for_compare))
        if False in result:
            return False
        else:
            return True

    def _check_difference_for_call_list(self, call_list, val, max_error=0.1):
        call_id, t_list = call_list
        logger.info("Start comparison for calls:")
        self._pprint_list(call_id, logging.INFO)
        try:
            t_list = list(map(float, t_list))
        except TypeError:
            logger.error("Can't convert items in list [%s] to float", ", ".join(list(map(str, t_list))))
            raise TimeDiffMeterExp("CompareError")
        t_list = self._get_diff_for_time_seq(t_list)
        if type(val) is list:
            return self._compare_seq(t_list, val, max_error=max_error)
        else:
            return self._compare_seq_item_with_val(t_list, val, max_error=max_error)

    @staticmethod
    def _filter_call_list(call_list, call_filter):
        if call_filter:
            try:
                return [call_list[i] for i in call_filter]
            except IndexError:
                logger.error("Filtering by call list failed. Call filter: [%s]", ", ".join(list(map(str, call_filter))))
                raise TimeDiffMeterExp("CompareError")
        else:
            return call_list

    def _check_calls_list_len(self, calls_list):
        check_len = set(list(map(len, calls_list)))
        if len(check_len) != 1:
            logger.error("Can't compare list of timestamps with different lengths:")
            _ = list(map(lambda x: self._pprint_list(x, logging.ERROR), calls_list))
            raise TimeDiffMeterExp("CompareError")

    def _start_comparison_between_ua(self, calls_list, d_obj):
        self._check_calls_list_len(calls_list)
        # Aggregating elements for each call.
        # (First call from ua1 to first call from ua2,..,uaN)
        # (Second call from ua1 to second call from ua2,..,uaN)
        # example: [(('BA:1ebf0, '1530871260.402419'),
        #            ('BA:1ebf1', '1530871261.402419'),
        #            ('BA:1ebf2', '1530871262.402419')),
        #           (('BA:2eb0', '1530871270.403639'),
        #            ('BA:2eb1', '1530871271.403639'),
        #            ('BA:2eb2', '1530871272.403639'))]
        calls_list = list(zpl(*calls_list, fillvalue=(None, None)))
        # Splitting call_id and timestamps for each_call
        # example:
        # [(('BA:1ebf0', 'BA:1ebf1', 'BA:1ebf2'), <zipped timestamps>),
        #  (('BA:2eb0', 'BA:2eb1', 'BA:2eb2'), <zipped timestamps>)]
        calls_list = [(call_id, timestamp) for call_id, timestamp in
                      list(map(lambda x: list(zpl(*x)), calls_list))]
        result = list(map(lambda x: self._check_difference_for_call_list(x, d_obj.Difference, d_obj.MaxError),
                          calls_list))
        return result

    @staticmethod
    def _check_list_for_compare(list_for_compare, msg):
        ua, call_list = list_for_compare
        check_list = [timestamp for _, timestamp in call_list]
        if None in check_list:
            logger.error("List of timestamps [%s] for UA: \"%s\" doesn't contain timestamp for msg: \
(type: %s, method: %s, code: %s) in required calls", ", ".join(list(map(str, check_list))), ua, *msg.values())
            raise TimeDiffMeterExp("CompareError")

    def _check_time_difference_between_ua(self, d_obj):
        if len(d_obj.UA) <= 1:
            logger.error("Count of UA must be greater than 1 for between_ua mode")
            raise TimeDiffMeterExp("CompareError")
        result = list()
        if d_obj.SearchMode == "between_calls":
            for msg in d_obj.Msg:
                # Get list of UA which contains next tuple:
                # (ua_info, [(call_id1,{timestamp1}), (call_id2,{timestamp2})])
                # example: ('user:0', [('BA:1ebf0', {'1530871260.402419'}), ('BA:2eb0', {'1530871270.403639'})],
                #          ('user:1', [('BA:1ebf1', {'1530871261.402419'}), ('BA:2eb1', {'1530871271.403639'})],
                #          ('user:2', [('BA:1ebf2', {'1530871262.402419'}), ('BA:2eb2', {'1530871272.403639'})])
                list_for_compare = [(ua, self._filter_call_list(calls_list, d_obj.Calls)) for ua, calls_list in
                                    list(map(lambda x: self._get_time_for_first_msg_in_call(x, **msg), d_obj.UA))]
                # Check timestamps in list_for_compare
                _ = list(map(lambda x: self._check_list_for_compare(x, msg), list_for_compare))
                # Aggregating elements for each ua and splitting it to ua_list and call_list
                user_list, call_list = zpl(*list_for_compare)
                logger.debug("Comparing between next UA: %s", ", ".join(user_list))
                result = self._start_comparison_between_ua(call_list, d_obj)
        elif d_obj.SearchMode == "inside_call":
            if len(d_obj.Msg) != len(d_obj.UA):
                logger.error("Count of Msg must be equal count of UA for inside_call compare mode")
                raise TimeDiffMeterExp("CompareError")
            args_for_compare = list(zpl(d_obj.Msg, d_obj.UA))
            list_for_compare = list()
            logger.info("Start message search:")
            for arg in args_for_compare:
                msg, ua = arg
                list_for_compare.extend((ua, self._filter_call_list(call_list, d_obj.Calls)) for ua, call_list in
                                        [self._get_time_for_first_msg_in_call(ua, **msg)])
                # Check timestamps for last iteration
                self._check_list_for_compare(list_for_compare[-1], msg)
            _, call_list = zpl(*list_for_compare)
            result = self._start_comparison_between_ua(call_list, d_obj)
        else:
            logger.error("Mode %s not supported", str(d_obj.CompareMode))
            raise TimeDiffMeterExp("CompareError")
        if not result or False in result:
            return False
        else:
            return True

    def _start_comparison_inside_ua(self, ua_list, d_obj):
        ua, calls_list = ua_list
        self._check_calls_list_len(calls_list)
        call_id, t_list = zpl(*calls_list)
        call_id = set(call_id)
        print(self._check_difference_for_call_list((call_id, t_list), d_obj.Difference, d_obj.MaxError))
        return self._check_difference_for_call_list((call_id, t_list), d_obj.Difference, d_obj.MaxError)

    def _check_time_difference_inside_ua(self, d_obj):
        result = list()
        if d_obj.SearchMode == "between_calls":
            for msg in d_obj.Msg:
                list_for_compare = [(ua, self._filter_call_list(calls_list, d_obj.Calls)) for ua, calls_list in
                                    list(map(lambda x: self._get_time_for_first_msg_in_call(x, **msg), d_obj.UA))]
                _ = list(map(lambda x: self._check_list_for_compare(x, msg), list_for_compare))
                result.extend(list(map(lambda x: self._start_comparison_inside_ua(x, d_obj), list_for_compare)))
                if False in result:
                    break
        elif d_obj.SearchMode == "inside_call":
            if len(d_obj.Msg) <= 1:
                logger.error("Count of messages must be greater than 1 for inside_call search mode.")
                raise TimeDiffMeterExp("CompareError")
            for ua in d_obj.UA:
                list_for_compare = [(ua, self._filter_call_list(calls_list, d_obj.Calls)) for ua, calls_list in
                                    list(map(lambda x: self._get_time_for_first_msg_in_call(ua, **x), d_obj.Msg))]
                _ = list(map(lambda x: self._check_list_for_compare(*x), zpl(list_for_compare, d_obj.Msg)))

                list_for_compare = list(zpl(*[calls_list for _, calls_list in list_for_compare]))
                result.extend([self._start_comparison_inside_ua(x, d_obj) for x in
                              [(ua, calls_list) for calls_list in list_for_compare]])
                print(result)
                if False in result:
                    break
        else:
            logger.error("Mode %s not supported", str(d_obj.CompareMode))
            raise TimeDiffMeterExp("CompareError")

        if not result or False in result:
            return False
        else:
            return True

    def check_time_difference(self, d_obj, ua_list):
        logger.info("Check Diff Params:")
        logger.info("├ CompareMode: %s", d_obj.CompareMode)
        logger.info("├ SearchMode: %s", d_obj.SearchMode)
        logger.info("├ CompareUA: %s", d_obj.UA)
        logger.info("├ Calls: %s", d_obj.Calls)
        logger.info("├ Require diff: %s", str(d_obj.Difference))
        logger.info("├ Messages:")
        _ = list(map(self._convert_msg_description, d_obj.Msg))
        for count, msg in enumerate(d_obj.Msg):
            logger.info("├ Message %d: type %s, method %s, code %s", count, *msg.values())
        pass
        _ = list(map(self._parse_trace_file_for_ua, ua_list))
        logger.debug("Trying to check time differences in %s mode.", d_obj.CompareMode)
        if d_obj.CompareMode == "between_ua":
            result = self._check_time_difference_between_ua(d_obj)
        elif d_obj.CompareMode == "inside_ua":
            result = self._check_time_difference_inside_ua(d_obj)
        else:
            logger.error("Unknown mode: %s", d_obj.CompareMode)
            raise TimeDiffMeterExp("CompareError")
        return result


