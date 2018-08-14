from modules.trace_parser import ShortTraceParser, TraceParseExp
from modules.sip_tools import MSG_TYPES
import logging
logger = logging.getLogger("tester")


class ShowSipFlow:
    @staticmethod
    def get_red_string(string):
        return str("\033[1;31m%s\033[1;m" % str(string))

    def print_flow(self, ua):
        if ua.UserObject:
            logger.info("Flow for user with number: %s", str(ua.UserObject.Number))
        elif ua.TrunkObject:
            logger.info("Flow for trunk %s, with port: %s", str(ua.TrunkObject.TrunkName), str(ua.TrunkObject.Port))
        for call in ua.ShortTrParser.Calls:
            logger.info("Call Flow for Call-ID: %s \n", call.CallID)
            print_string = list()
            print_string.append(" ".ljust(26, " ") + "SIPp")
            print_string.append(" ".ljust(27, " ") + "┯")
            print("\n".join(print_string))
            for count, msg in enumerate(call.Messages):
                direction = "│ ◀────RECV───── " if msg.Direction == "R" else "│ ─────SEND────▶ "
                if msg.MsgType == MSG_TYPES.REQUEST:
                    start_line = ": ".join((msg.Method, msg.URI))
                else:
                    start_line = " ".join((str(msg.RespCode), msg.RespDesc))
                print_string = " ".join((msg.Date, msg.Time, direction, start_line))
                try:
                    print_string += "\n"
                    msg_diff = round(float(call.Messages[count + 1].Timestamp) - float(msg.Timestamp), 1)

                    print_string += self.get_red_string("           Diff: %s" % str(msg_diff).ljust(10, " "))
                    print_string += "│"
                except IndexError:
                    pass
                print(print_string)

    def show_sip_flow_for_test(self, test):
        ua_with_traces = [x for x in test.CompleteUA if x.TimeStampFile]
        for ua in ua_with_traces:
            if ua.ShortTrParser:
                continue
            ua.ShortTrParser = ShortTraceParser()
            try:
                ua.ShortTrParser.parse(ua.TimeStampFile)
            except TraceParseExp:
                logger.error("Show sip flow failed. Parse trace file: %s failed", ua.TimeStampFile)
                return False
        _ = list(map(self.print_flow, ua_with_traces))



