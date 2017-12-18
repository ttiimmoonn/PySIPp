import modules.fs_worker as fs_worker
import re 
import logging
logger = logging.getLogger("tester")
class sip_flow():
	def __init__(self,trace_obj):
		self.trace_obj = trace_obj

	def str_to_red(self,string):
		return str("\033[1;31m" + string +  "\033[1;m")

	def print_flow(self):
		for ua in tuple(self.trace_obj.users_with_traces.values()) + tuple(self.trace_obj.trunks_with_traces.values()):
			if ua.UserObject != None:
				logger.info("Flow for user with number: %s",str(ua.UserObject.Number))
			elif ua.TrunkObject != None:
				logger.info("Flow for trunk with port: %s",str(ua.TrunkObject.Port))
			for call in ua.ShortTrParser.calls:
				logger.info("Call Flow for Call-ID: %s \n",call.call_id)
				print_string = ""
				print_string += " ".ljust(26," ") + "SIPp" + "\n"
				print_string += " ".ljust(27," ") + "┯"
				print(print_string)
				for count,msg in enumerate(call.messages):
					print_string = ""
					print_string += msg.date + " "
					print_string += msg.time + " "
					if msg.direction == "R": print_string += "│ ◀────RECV───── "
					if msg.direction == "S": print_string += "│ ─────SEND────▶ "
					if msg.msg_type  == "request":print_string += msg.method + ": " + msg.uri
					if msg.msg_type  == "response":print_string += str(msg.resp_code) + " " + msg.resp_desc
					try:
						print_string += "\n"
						print_string += self.str_to_red("           Diff:"+ str(round(call.messages[count+1].diff_msg_time,1))).ljust(39," ")
						print_string += "│"
					except IndexError:
						pass
					print(print_string)





