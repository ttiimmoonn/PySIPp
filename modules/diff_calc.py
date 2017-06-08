import modules.trace_parser as tr_parser
import modules.fs_worker as fs_worker
from collections import OrderedDict
import logging
import math
logger = logging.getLogger("tester")



class diff_timestamp():
	def __init__(self,test):
		self.Status = None
		self.ua_with_traces = {}
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
		if ua.TimeStampFile:
			stat_file = fs_worker.get_fd(ua.TimeStampFile)
			if stat_file:
				logger.info("Parse short_msg_file for UA %s",str(ua.UserObject.Number))
				ua.ShortTrParser = tr_parser.short_trace_parser(stat_file)
				ua.ShortTrParser.parse_trace_msg()
				logger.debug("Сlose short_msg_file for UA %s",str(ua.UserObject.Number))
				stat_file.close()
				if ua.ShortTrParser.Status == "Failed":
					logger.error("Parse complite for UA %s. Result: fail.",str(ua.UserObject.Number))
					self.Status = "Failed"
				else:
					logger.info("Parse complite for UA %s. Result: succ.",str(ua.UserObject.Number))
					self.ua_with_traces[ua.UserId] = ua
			else:
				logger.error("Parse complite for UA %s. Result: fail.",str(ua.UserObject.Number))
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
		for ua_id in args:
			try:
				ua = self.ua_with_traces[ua_id]
			except KeyError:
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
			result[ua_id] = ua_msg_timestamp
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
		for ua_id in args:
			try:
				ua = self.ua_with_traces[ua_id]
			except KeyError:
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
			result[ua_id] = result_seq
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
		for ua_id in args:
			try:
				ua = self.ua_with_traces[ua_id]
			except KeyError:
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
			result[ua_id] = ua_msg_timestamp
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
			for ua_id in args:
				for call in ua_seq_info[ua_id]:
					if ua_seq_info[ua_id][call]:
						logger.info("--| Try to compare (call-id: %s):",call)
						self.seq_compare(ua_seq_info[ua_id][call],req_seq)
					else:
						logger.error("--| Campare failed. No retrans in call: %s",str(call))
						self.Status = "Failed"

	def compare_msg_diff(self,diffrence,mode,*args,**kwargs):
		#Пока делим на 1000, так как таймера на ссв в основном в ms
		diffrence = float(diffrence)/1000
		ua_msg_timestamp = self.get_first_msg_timestamp(*args, **kwargs)
		if self.Status != "Failed":
			if mode == "between_ua":
				timestamps = []
				msg_diff = []
				try:
					for ua_calls in ua_msg_timestamp.values():
						count_of_call = len(ua_calls)
						for timestamp in ua_calls.values():
							timestamps.append(timestamp)
					logger.info("Try to compare msg diff sequence with: %f. Mode: %s" , float(diffrence), str(mode))
					for i in range(count_of_call):
						msg_diff = self.get_diff(timestamps[i::count_of_call])
						self.value_compare(msg_diff,diffrence,max_diff=0.5)
				except:
					logger.error("Exeption in compare_msg_diff function. Mode: %s", str(mode))
					self.Status = "Failed"
					return False
			elif mode == "inner_ua":
				for ua_calls in ua_msg_timestamp.values():
					timestamps = []
					msg_diff = []
					for timestamp in ua_calls.values():
						timestamps.append(timestamp)
					msg_diff = self.get_diff(timestamps)
					logger.info("Try to compare msg diff sequence with: %f. Mode: %s" , float(diffrence), str(mode))
					self.value_compare(msg_diff,diffrence,max_diff=0.5)
