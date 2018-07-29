import re
import logging
from modules.sip_tools import RESP_EXP, REQ_EXP, CSEQ_EXP, MSG_TYPES, MSG_FORMAT

logger = logging.getLogger('tester')


class TraceParseExp(Exception):
    pass


class SipCall:
    def __init__(self, sip_msg):
        logger.debug("Find new call: %s", sip_msg.CallID)
        self.Messages = []
        self.Transactions = []
        self.CallID = sip_msg.CallID
        self.append_message(sip_msg)

    def _get_transaction_for_msg(self, sip_msg):
        for tr in self.Transactions:
            if tr.Branch == sip_msg.Branch:
                return tr

    def append_message(self, sip_msg):
        self.Messages.append(sip_msg)
        # Append message to transaction
        tr = self._get_transaction_for_msg(sip_msg)
        if not tr and sip_msg.MsgType == MSG_TYPES.RESPONSE:
            raise TraceParseExp("No transaction for sip response.")
        elif not tr:
            self.Transactions.append(SipTransaction(sip_msg))
        else:
            tr.append_message(sip_msg)

    @staticmethod
    def _filter_transaction_by_msg(tr, **kwargs):
        for msg in tr.Messages:
            if msg.MsgType == kwargs.get("MsgType") and msg.RespCode == kwargs.get("Code"):
                return True
        return False

    def _find_transactions_by_msg_params(self, **kwargs):
        tr_list = [x for x in self.Transactions if kwargs.get("Method") in x.Methods]
        tr_list = list(filter(lambda x: self._filter_transaction_by_msg(x, **kwargs), tr_list))
        return tr_list

    def get_msg_retransmission(self, **kwargs):
        tr_list = self._find_transactions_by_msg_params(**kwargs)
        r_list = zip([x.Branch for x in tr_list], list(map(lambda x: x.get_msg_retransmission(**kwargs), tr_list)))
        return list(r_list)

    def get_first_message_in_tr(self, **kwargs):
        tr_list = self._find_transactions_by_msg_params(**kwargs)
        t_list = zip([x.Branch for x in tr_list], list(map(lambda x: x.get_first_msg(**kwargs), tr_list)))
        return list(t_list)

    def get_first_message_in_call(self, **kwargs):
        for msg in self.Messages:
            if msg.Method != kwargs.get("Method"):
                continue
            elif msg.MsgType == kwargs.get("MsgType") and msg.RespCode == kwargs.get("Code"):
                result = [(msg.Branch, msg)]
                return result


class SipTransaction:
    def __init__(self, sip_msg):
        logger.debug("Find new transaction %s", sip_msg.Branch)
        self.Messages = []
        self.Methods = []
        self.Methods.append(sip_msg.Method)
        self.Branch = sip_msg.Branch
        self.append_message(sip_msg)

    def append_message(self, sip_msg):
        logger.debug("Add message: %s to transaction: %s", sip_msg.get_msg_info(),
                     self.Branch.replace("branch=", ""))
        if sip_msg.Method not in self.Methods:
            self.Methods.append(sip_msg.Method)
        self.Messages.append(sip_msg)

    def get_msg_retransmission(self, **kwargs):
        # Filtering msg by params
        msg_list = [x for x in self. Messages if x.RespCode == kwargs.get("Code") and
                    x.MsgType == kwargs.get("MsgType")]
        # Group msg by hash
        hash_list = set(x.MsgHash for x in msg_list)
        msg_list = [[x for x in msg_list if x.MsgHash == h] for h in hash_list]
        # Find retransmissions
        msg_list = [x for x in msg_list if len(x) > 1]
        # Sorting messages by timestamp
        _ = list(map(lambda x: x.sort(key=lambda o: o.Timestamp), msg_list))
        return msg_list

    def get_first_msg(self, **kwargs):
        for msg in self.Messages:
            if msg.MsgType == kwargs.get("MsgType") and msg.RespCode == kwargs.get("Code"):
                return msg


class SipMessage:
    def __init__(self, **kwargs):
        if None in kwargs.values():
            raise TraceParseExp("Bad arguments for SipMessage class.")
        self.URI = None
        self.RespDesc = None
        self.RespCode = None
        self.Branch = kwargs.get("Branch")
        self.Date = kwargs.get("Date")
        self.Time = kwargs.get("Time")
        self.CallID = kwargs.get("CallID")
        self.Timestamp = kwargs.get("Timestamp")
        self.MsgHash = kwargs.get("MsgHash")
        self.Direction = kwargs.get("Direction")
        self.CSeq, self.Method = re.search(CSEQ_EXP, kwargs.get("CSeq")).groups()

        self.MsgType, start_line = self._get_message_type(kwargs.get("StartLine"))
        if self.MsgType == MSG_TYPES.REQUEST:
            _, self.URI, _, _ = start_line.groups()
        elif self.MsgType == MSG_TYPES.RESPONSE:
            self.RespCode, self.RespDesc = start_line.groups()
            self.RespCode = int(self.RespCode)

    def _get_message_type(self, start_line):
        result = self._is_request(start_line)
        if result:
            return MSG_TYPES.REQUEST, result
        result = self._is_response(start_line)
        if result:
            return MSG_TYPES.RESPONSE, result
        raise TraceParseExp("Unknown type of message. Start line: %s", str(start_line))

    def get_msg_info(self):
        return "{}, method: {}, code: {}".format(self.MsgType, self.Method, self.RespCode)

    @staticmethod
    def _is_request(start_line):
        return re.match(REQ_EXP, start_line)

    @staticmethod
    def _is_response(start_line):
        return re.match(RESP_EXP, start_line)


class ShortTraceParser:
    def __init__(self, trace_fd):
        self.Calls = []
        self.trace_fd = trace_fd

    def find_call(self, call_id):
        for call in self.calls:
            if call.call_id == call_id:
                return call
        return False

    @staticmethod
    def _get_msg_dict(msg_desc):
        return {k: v for k, v in zip(MSG_FORMAT, msg_desc)}

    def _get_call_for_msg(self, msg):
        for call in self.Calls:
            if call.CallID == msg.CallID:
                return call

    def parse(self):
        for line in self.trace_fd:
            line = line.rstrip()
            sip_msg = SipMessage(**self._get_msg_dict(line.split('\t')))
            sip_call = self._get_call_for_msg(sip_msg)
            if not sip_call and sip_msg.MsgType == MSG_TYPES.REQUEST:
                self.Calls.append(SipCall(sip_msg))
            elif sip_call:
                sip_call.append_message(sip_msg)
