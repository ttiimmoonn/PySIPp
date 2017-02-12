import logging
import re
from collections import OrderedDict

logger = logging.getLogger("tester")

class call():
	def __init__(self):
		self.call_id = None
		self.messages = []
		self.transactions = []

	def find_transaction(self, msg):
		for tr in self.transactions:
			if tr.branch == msg.branch and tr.cseq == msg.cseq:
				return tr
		return False

	def put_msg_to_transaction(self, msg):
		tr = self.find_transaction(msg)
		if tr:
			tr.add_msg(msg)
		else:
			new_tr = transaction()
			self.transactions.append(new_tr)
			new_tr.messages.append(msg)
			new_tr.fill_tr_info(msg)

	def add_msg(self,**kwargs):
		new_msg = message()
		if not new_msg.fill_msg_info(**kwargs):
			return False
		else:
			self.put_msg_to_transaction(new_msg)
			self.messages.append(new_msg)
			return True

	def show_tr_msg(self):
		for tr in self.transactions:
			tr.show_tr_msg()

	def get_retrans_time_seq(self,**kwargs):
		result_seq = []
		for tr in self.transactions:
			#Если в транзакции нет искомого метода,
			#уходим на следующую итерацию
			if not kwargs["method"] in tr.methods:
				continue
			#Пытаемся задектировать перепосылки в tr
			retrans_msg = tr.find_retrans(**kwargs)
			if not tr.retrans_flag:
				#Ecли ничего не нашли, то продолжаем поиск
				continue
			for msg in retrans_msg:
				result_seq.append(msg.timestamp)
		#Сбрасываем flag
		tr.retrans_flag = False
		return result_seq

	def get_retrans_duration(self,**kwargs):
		retrans_msg = self.get_retrans_time_seq(**kwargs)
		if not retrans_msg:
			return False
		return float(retrans_msg[len(retrans_msg) -1 ]) - float(retrans_msg[0])

	def get_first_msg_timestamp(self,**kwargs):
		for tr in self.transactions:
			if not kwargs["method"] in tr.methods:
				continue
			for msg in tr.messages:
				if kwargs["msg_type"] == msg.msg_type and msg.method == kwargs["method"] and msg.resp_code == kwargs["resp_code"]:
					return msg.timestamp
		return False

class transaction ():
	def __init__(self):
		self.branch = None
		self.messages = []
		self.methods = []
		self.cseq = None
		self.retrans_flag = False

	def fill_tr_info(self,msg):
		self.branch = msg.branch
		self.cseq = msg.cseq
		if not msg.method in self.methods:
			self.methods.append(msg.method)

	def add_msg(self,msg):
		self.messages.append(msg)
		if not msg.method in self.methods:
			self.methods.append(msg.method)

	def find_retrans(self,**kwargs):
		find_hash = []
		for msg in self.messages:
			if msg.msg_type == kwargs["msg_type"] and msg.method == kwargs["method"] and msg.resp_code == kwargs["resp_code"]:
				find_hash.append(msg.msg_hash)
		#если длина исходного массива равна длине множества
		#уникальных hash, то значит в транзакции не было перепосылок
		if len(find_hash) == len(set(find_hash)):
			return False
		else:
			self.retrans_flag = True
		retrans_hash = self.find_msg_hash(**kwargs)
		if not retrans_hash:
			return False
		return self.get_msg_by_hash(retrans_hash)


	def find_msg_hash(self,**kwargs):
		for msg in self.messages:
			if msg.msg_type == kwargs["msg_type"] and msg.method == kwargs["method"] and msg.resp_code == kwargs["resp_code"]:
				return msg.msg_hash
		return False

	def get_msg_by_hash(self,msg_hash):
		msg_seq = []
		for msg in self.messages:
			if msg.msg_hash == msg_hash:
				msg_seq.append(msg)
		return msg_seq


	def show_tr_msg(self):
		logger.debug("Trasaction %s, methods: %s. ",self.branch, " ".join(self.methods))
		for msg in self.messages:
			msg.show_msg_info()

class message ():
	def __init__(self):
		self.branch = None
		self.date = None
		self.time = None
		self.method = None
		self.uri = None
		self.cseq = None
		self.msg_type = None
		self.direction = None
		self.timestamp = None
		self.resp_code = None
		self.resp_desc = None
		self.hash = None


		self.req_r  = r'([A-Z]*)\s(sip:.*)\sSIP\/2.0'
		self.res_r  = r'SIP\/2\.0\s([0-9]{3})\s(.*)'
		self.cseq_r = r'([\d]*)\s([A-Z]*)'

	def show_msg_info(self):
		print()
		logger.info("Msg msg_type: %s",str(self.msg_type))
		logger.info("Msg dir: %s",str(self.direction))
		logger.info("Msg date: %s",str(self.date))
		logger.info("Msg time: %s",str(self.time))
		logger.info("Msg uri: %s",str(self.uri))
		logger.info("Msg method: %s",str(self.method))
		logger.info("Msg cseq: %s",str(self.cseq))
		logger.info("Msg timestamp: %s",str(self.timestamp))
		logger.info("Response code: %s",str(self.resp_code))
		logger.info("Response desc: %s",str(self.resp_desc))
		# logger.debug("diff_msg_time: %f",self.diff_msg_time)
		# logger.debug("diff_msg_time_in_tr: %f",self.diff_msg_time_in_tr)
		logger.info("msg_hash: %s",self.msg_hash)
		print()


	def is_request(self, start_line):
		if re.search(self.req_r, start_line):
			return True
	def is_response(self, start_line):
		if re.search(self.res_r, start_line):
			return True

	def fill_msg_info(self,**kwargs):
		try:
			self.date = kwargs["date"]
			self.time = kwargs["time"]
			self.timestamp = kwargs["timestamp"]
			self.direction = kwargs["direction"]
			self.branch = kwargs["branch"]
			self.msg_hash = kwargs["msg_hash"]
		except KeyError:
			logger.error("Req call param not found.")
			return False
		if self.is_request(kwargs["start_line"]):
			msg_search = re.search(self.req_r, kwargs["start_line"])
			self.msg_type = "request"
			self.uri = msg_search.group(2)
		elif self.is_response(kwargs["start_line"]):
			msg_search = re.search(self.res_r, kwargs["start_line"])
			self.msg_type = "response"
			self.resp_code = msg_search.group(1)
			self.resp_desc = msg_search.group(2)
		else:
			logger.error("Unknown type of message. Can't parse start_line: %s",str(kwargs["start_line"]))
			return False

		msg_search = re.search(self.cseq_r, kwargs["cseq"])
		if msg_search:
			self.cseq   = msg_search.group(1)
			self.method = msg_search.group(2)
		else:
			logger.error("Unknown cseq header format. Can't parse cseq from: %s",str(kwargs["cseq"]))
			return False
		return True

class short_trace_parser():
	def __init__(self, trace_fd):
		self.Status = None
		self.calls = []
		self.trace_fd = trace_fd

	def find_call(self, call_id):
		for call in self.calls:
			if call.call_id == call_id:
				return call
		return False

	def get_call_dict(self,*args):
		try:
			date, time, timestamp, direction,call_id,cseq, start_line, branch, msg_hash = args
		except:
			logger.error("Can't split short_msg line: \n%s", " ".join(args))
			self.Status = "Failed"
			return False
		return {"date" : date, "time" : time, "timestamp" : timestamp,
				"direction": direction, "call_id" : call_id, "cseq" : cseq,
				"start_line" : start_line , "branch" : branch, "msg_hash" : msg_hash}

	def parse_trace_msg(self):
		#Начинаем читать shorttrace log построчно
		self.Status = "Start"
		for line in self.trace_fd:
			line = line.rstrip('\n')
			call_dict = self.get_call_dict(*line.split("\t"))
			if call_dict:
				#Пытаемся найти вызов по call_id
				parse_call = self.find_call(call_dict["call_id"])
				if parse_call:
					#Если нашли, то добавляем сообщение в существующий вызов
					if not parse_call.add_msg(**call_dict):
						self.Status = "Failed"
						break

				else:
					#Если не нашли, то создаём новый вызов и добаляем туда сообщение
					new_call = call()
					self.calls.append(new_call)
					logger.debug("--| Found new call Call-ID: %s.",call_dict["call_id"])
					new_call.call_id = call_dict["call_id"]
					if not new_call.add_msg(**call_dict):
						self.Status = "Failed"
						break
			else:
				self.Status = "Failed"
				break