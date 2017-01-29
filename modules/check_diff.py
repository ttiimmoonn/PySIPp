#import modules.fs_worker as fs_worker
import logging
import math
import re
from collections import OrderedDict

logging.basicConfig(format = u'%(asctime)-8s %(levelname)-8s %(message)-8s', filemode='w', level = logging.DEBUG)
logger = logging.getLogger("tester")

fd = open("/tmp/test.log",'r')
# for line in fd:
# 	line = line.split("\t")
# 	t1,t2,t3,t4,t5,t6,t7,t8,t9 = line
# 	print(t4)

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
		last_cseq = None

		for tr in self.transactions:
			#Если в транзакции нет искомого метода,
			#уходим на следующую итерацию
			if not kwargs["method"] in tr.methods:
				continue
			for msg in tr.messages:
				if msg.msg_type != kwargs["msg_type"]:
					continue
				if kwargs["msg_type"] == "request":
					if not last_cseq: last_cseq = msg.cseq
					if (msg.cseq == last_cseq) and (msg.method == kwargs["method"]):
						result_seq.append(msg.timestamp)
						continue
				if kwargs["msg_type"] == "response":
					if not last_cseq: last_cseq = msg.cseq
					if (msg.cseq == last_cseq) and (msg.resp_code == kwargs["resp_code"]) and (msg.method == kwargs["method"]):
						result_seq.append(msg.timestamp)
						continue 
			if result_seq: break
		if result_seq:
			return result_seq
		else:
			return False

	def get_first_msg_timestamp(self,**kwargs):
		for tr in self.transactions:
			if not kwargs["method"] in tr.methods:
				continue
			for msg in tr.messages:
				if kwargs["msg_type"] == "request" and msg.method == kwargs["method"]:
					return msg.timestamp
				if kwargs["msg_type"] == "response" and msg.method == kwargs["method"] and msg.resp_code == kwargs["resp_code"]:
					return msg.timestamp
		return False

class transaction ():
	def __init__(self):
		self.branch = None
		self.messages = []
		self.methods = []
		self.cseq = None

	def fill_tr_info(self,msg):
		self.branch = msg.branch
		self.cseq = msg.cseq
		if not msg.method in self.methods:
			self.methods.append(msg.method)


	def add_msg(self,msg):
		self.messages.append(msg)
		if not msg.method in self.methods:
			self.methods.append(msg.method)

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


		self.req_r  = r'([A-Z]*)\s(sip:.*)\sSIP\/2.0'
		self.res_r  = r'SIP\/2\.0\s([0-9]{3})\s(.*)'
		self.cseq_r = r'([\d]*)\s([A-Z]*)'

	def show_msg_info(self):
		print()
		logger.debug("Msg msg_type: %s",str(self.msg_type))
		logger.debug("Msg dir: %s",str(self.direction))
		logger.debug("Msg date: %s",str(self.date))
		logger.debug("Msg time: %s",str(self.time))
		logger.debug("Msg uri: %s",str(self.uri))
		logger.debug("Msg method: %s",str(self.method))
		logger.debug("Msg cseq: %s",str(self.cseq))
		logger.debug("Msg timestamp: %s",str(self.timestamp))
		logger.debug("Response code: %s",str(self.resp_code))
		logger.debug("Response desc: %s",str(self.resp_desc))
		logger.debug("diff_msg_time: %f",self.diff_msg_time)
		logger.debug("diff_msg_time_in_tr: %f",self.diff_msg_time_in_tr)
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
		self.Status = True
		self.calls = []
		self.trace_fd = trace_fd

	def find_call(self, call_id):
		for call in self.calls:
			if call.call_id == call_id:
				return call
		return False

	def get_call_dict(self,*args):
		try:
			date, time, timestamp, direction,call_id,cseq, start_line, branch = args
		except:
			logger.error("Can't split short_msg line: \n%s", " ".join(args))
			self.status = False
			return False
		return {"date" : date, "time" : time, "timestamp" : timestamp,
				"direction": direction, "call_id" : call_id, "cseq" : cseq,
				"start_line" : start_line , "branch" : branch}

	def parse_trace_msg(self):
		for line in self.trace_fd:
			call_dict = self.get_call_dict(*line.split("\t"))
			if call_dict:
				#Пытаемся найти вызов по call_id
				parse_call = self.find_call(call_dict["call_id"])
				if parse_call:
					#Если нашли, то добавляем сообщение в существующий вызов
					if not parse_call.add_msg(**call_dict):
						self.Status = False
						break

				else:
					#Если не нашли, то создаём новый вызов и добаляем туда сообщение
					new_call = call()
					self.calls.append(new_call)
					logger.debug("Create new call obj. Call-ID: %s",call_dict["call_id"])
					new_call.call_id = call_dict["call_id"]
					if not new_call.add_msg(**call_dict):
						self.Status = False
						break
			else:
				self.Status = False
				break
	def get_first_msg_timestamp(self, **kwargs):
		result = {}
		result = OrderedDict(result)
		for call in self.calls:
			result[call.call_id] = call.get_first_msg_timestamp(**kwargs)
		return result

	def get_retrans_diff(self, **kwargs):
		#Получаем последовательность временных меток для нужного сообщения
		call_seq = self.get_retrans_time_seq(**kwargs)
		#Массив для хранения diff в пределах одного вызова
		call_diff = []
		#Словарь для хранения результатов по всем вызовам
		result_seq = {}
		result_seq = OrderedDict(result_seq)
		#Начинаем расчёт diff для всех вызовов
		for call in call_seq:
			new_seq = call_seq[call]
			if new_seq:
				#Начинаем считать diff только для последовательностей, длина которых больше 1.
				if len(new_seq) > 1:
					#Расчёт diff
					for i in range(0, len(new_seq) - 1):
						call_diff.append(float(new_seq[i+1])-float(new_seq[i]))
				#Если в call_diff есть значения, то записываем их result
				if call_diff:
					result_seq[call] = call_diff
				#Иначе говорим False
				else:
					result_seq[call] = False
			else:
				result_seq[call] = False
			#Очищаем call_diff для последующей итерации
			call_diff = []
		return result_seq


	def get_retrans_time_seq(self,**kwargs):
		result_seq = {}
		#Делаем словарь упорядоченным, чтобы вызовы шли по порядку.
		result_seq = OrderedDict(result_seq)
		#Запрашиваем последовательности timestamp для всех вызовов
		for call in self.calls:
			result_seq[call.call_id] = (call.get_retrans_time_seq(**kwargs))
		return result_seq



class timestamp_check():
	def __init__(self,test):
		self.ua_timestamp_obj = {}
		self.Status = True

		for ua in test.CompliteUA:
			stat_file = fs_worker.get_fd(ua.TimeStampFile)
			if stat_file:
				self.ua_timestamp_obj[ua.UserId] = short_trace_parser(stat_file)
				self.ua_timestamp_obj[ua.UserId].parse_trace_msg()




new_obj = short_trace_parser(fd)
new_obj.parse_trace_msg()
request = {"msg_type":"request", "method": "PRACK"}
print(new_obj.get_retrans_diff(**request))
print()
print(new_obj.get_first_msg_timestamp(**request))
exit(1)

class diff_time():
	def __init__(self,test, mode="stat"):
		self.diff_array = {}
		self.Status = None
		self.timestamps = []
		self.find_timestamps = {}
		for ua in test.CompliteUA:
			if ua.StatFile or ua.TimeStampFile:
				if mode == "stat":
					stat_file = fs_worker.get_fd(ua.StatFile)
				elif mode == "timestamp":
					stat_file = fs_worker.get_fd(ua.TimeStampFile)
			else:
				continue
			if stat_file:
				self.diff_array[int(ua.UserId)] = stat_file
			else:
				self.Status = "Failed"
	
	def close_stat_files(self):
		logger.info("Closing statistic files.")
		for file_indx in self.diff_array:
			try:
				self.diff_array[file_indx].close()
			except:
				pass

	def parse_stat(self,msg_type,method,code,*args):
		self.find_timestamps = {}
		for user_id in args[0]:
			try:
				stat_file = self.diff_array[int(user_id)]
			except KeyError:
				logger.info("Can't find statistic file for User with id: %d. Try set WriteStat attr in json description for that UA",int(user_id))
				self.close_stat_files()
				self.Status = "Failed"
				return False
			except ValueError:
				logger.info("User ID must have integer value. {Bad Value: ",user_id,"}")
				self.close_stat_files()
				self.Status = "Failed"
				return False
			timestamps = []
			for line in stat_file:
				line = line.split()
				if msg_type == "Request":
					if not re.search(method+r"\ssip:.*\sSIP\/2.0"," ".join(map(str,line[7:]))):
						continue
				elif msg_type == "Response":
					if not re.search(r"SIP\/2\.0\s" + code," ".join(map(str,line[7:]))):
						continue
					else:
						if line[6] != method:
							continue
				try:
					timestamps.append(float(line[2]))
				except ValueError:
					self.close_stat_files()
					self.Status = "Failed"
					logger.info("User ID must have float value. {Bad Value: ",find_timestamp,"}")
					return False
			self.find_timestamps[int(user_id)] = timestamps
			stat_file.seek(0,0)
			if len(timestamps) == 0:
				logger.error("Can't find msg %s in statistic file for user with id %d",method,int(user_id))
				self.close_stat_files()
				self.Status = "Failed"
				return False
			return True

	def ckeck_timer(self,**kwargs):
		code = None
		try:
			msg_type = kwargs["MsgType"]
			if msg_type == "Response":
				code = kwargs["Code"]
			method = kwargs["Method"]
			timer_name = kwargs["Timer"]
			ua_args = kwargs["UA"].split(",")
		except KeyError:
			self.Status = "Failed"
			return False
		if not self.parse_stat(msg_type, method,code, ua_args):
			self.Status = "Failed"
			return False
		for user_id in ua_args[0]:
			user_id = int(user_id)
			logger.debug("Trying to check msg diff for user: %d, timer: %s", user_id, str(timer_name))
			if timer_name == "A":
				timer_seq_diff = (0.5, 1, 2, 4, 8, 16)
				if self.check_on_seq(user_id, timer_seq_diff):
					self.Status = "Success"
				else:
					self.Status = "Failed"
					break
			elif timer_name in ("E", "G"):
				timer_seq_diff = (0.5, 1, 2, 4, 4, 4, 4, 4, 4, 4)
				if self.check_on_seq(user_id, timer_seq_diff):
					self.Status = "Success"
				else:
					self.Status = "Failed"
					break
			elif timer_name in ("B", "F", "H"):
				self.check_on_trans(user_id)
			else:
				logger.error("Timer %s not supported.", str(timer_name))
				self.Status = "Failed"
				return False

	def check_on_trans(self,user_id,req_diff=32):
		try:
			ua_seq = self.find_timestamps[user_id]
		except KeyError:
			logger.error("Can't find UA: %d in timestamp dict.", user_id)
			return False
		ua_diff = float(ua_seq[len(ua_seq) - 1] - ua_seq[0] + 0.5)
		logger.debug("UA diff eq: %s", str(ua_diff))
		logger.debug("Req diff eq: %s", str(req_diff))
		if math.fabs(ua_diff - req_diff) <= 0.05:
			logger.info("Check complite. Result: success")
			return True
		else:
			logger.info("Check complite. Result: false")
			return False

	def check_on_seq(self,user_id,timer_seq_diff):
		try:
			ua_seq = self.find_timestamps[user_id]
		except KeyError:
			logger.error("Can't find UA: %d in timestamp dict.", user_id)
			return False
		logger.debug("UA timestamps seq: %s", ", ".join(map(str,ua_seq)))
		ua_seq_diff = []
		for i in range(1, len(ua_seq)):
			ua_seq_diff.append(float(ua_seq[i] - ua_seq[i-1]))
		logger.debug("UA diff seq: %s", ", ".join(map(str,ua_seq_diff)))
		logger.debug("Req diff seq: %s", ", ".join(map(str,timer_seq_diff)))
		if len(timer_seq_diff) != len(ua_seq_diff):
			logger.error("Len of timer_seq_diff not eq len of ua_seq_diff.")
			return False

		for timer_diff,ua_seq_diff in zip(timer_seq_diff,ua_seq_diff):
			if math.fabs(float(timer_diff) - float(ua_seq_diff)) >= 0.05:
				self.Status = "Failed"
				logger.error("UA diff seq not equal req_diff_seq. UA id: %d",user_id)
				return False
		if self.Status != "Failed":
			logger.info("Check complite. Result: success")
			return True
		else:
			logger.info("Check complite. Result: failed")
			return False

	def check_diff(self, method, diff, *args):
		#Фича делается для форкига, там таймер в ms
		#поэтому делим на 1000
		diff = diff/1000
		diff = float(diff)
		#Очищаем массив с timestamp
		self.timestamps=[]
		#Ставим статус New
		self.Status = "New"
		for user_id in args:
			find_timestamp = False
			try:
				stat_file = self.diff_array[int(user_id)]
			except KeyError:
				logger.info("Can't find statistic file for User with id: %d. Try set WriteStat attr in json description for that UA",int(user_id))
				self.close_stat_files()
				self.Status = "Failed"
				return False
			except ValueError:
				logger.info("User ID must have integer value. {Bad Value: ",user_id,"}")
				self.close_stat_files()
				self.Status = "Failed"
				return False
			#Example  CANCEL 2016-10-10 09:57:47.231259 1476068267.231259
			for line in stat_file:
				line = line.split()
				if line[0] != method:
					continue
				else:
					find_timestamp = line[3]
					try:
						self.timestamps.append(float(find_timestamp))
					except ValueError:
						self.close_stat_files()
						self.Status = "Failed"
						logger.info("User ID must have float value. {Bad Value: ",find_timestamp,"}")
						return False
			stat_file.seek(0,0)
			if not find_timestamp:
				logger.error("Can't find method %s in statistic file for user with id %d",method,int(user_id))
				self.close_stat_files()
				self.Status = "Failed"
				return False

		for idx, timestamp in enumerate(self.timestamps):
			if idx == len(self.timestamps) - 1:
				break
			msg_diff = self.timestamps[idx + 1] - timestamp
			if msg_diff < diff + 0.5 and msg_diff > diff - 0.5:
				logger.info("--> Require timer is %.1f",round(diff,1))
				logger.info("--> Current timer is %.1f",round(msg_diff,1))
				logger.info("--> Diff between UA %d and %d success",idx + 1,idx)
			else:
				logger.error("Diff for method: %s not equal %.1f. Current diff = %.1f",method,diff,round(msg_diff,1))
				self.Status = "Failed"

		if self.Status == "Failed":
			return False
		else:
			self.Status == "Complite"
			return True






