import re
from enum import Enum
# Trace sip message
REQ_EXP = re.compile(r'([\w]+)\s(sip:([^@]+)@([^\s]+))\sSIP/2\.0')
RESP_EXP = re.compile(r'SIP/2\.0\s([\d]{3})\s([\w]+)')
CSEQ_EXP = re.compile(r'([\d]+)\s([A-Z]+)')
MSG_FORMAT = ["Date", "Time", "Timestamp", "Direction", "CallID", "CSeq", "StartLine", "Branch", "MsgHash"]
MSG_TYPES = Enum('MsgType', 'REQUEST RESPONSE')


# Timers
def init_invite_timer_seq():
    timer = T1
    timer_seq = list()
    while sum(timer_seq) + T1 < 64 * T1:
        timer_seq.append(timer)
        timer *= 2
    return timer_seq


def init_non_invite_timer_seq():
    timer = T1
    timer_seq = list()
    while sum(timer_seq) + T1 < 64 * T1:
        timer_seq.append(min(timer, T2))
        timer *= 2
    return timer_seq

T1 = 0.5
T2 = 4

SIP_TIMERS = {"B": 64*T1, "F": 64*T1, "H": 64*T1,
              "A": init_invite_timer_seq(),
              "E": init_non_invite_timer_seq(),
              "G": init_non_invite_timer_seq()}
