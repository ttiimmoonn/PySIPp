import modules.trace_parser as tr_parser
import modules.fs_worker as fs_worker
from collections import OrderedDict
import logging
logger = logging.getLogger("tester")

class diff_timestamp():
	def __init__(self,test):	
		self.Status = None
		self.ua_with_traces = {}
		for ua in test.CompliteUA:
			if ua.ShortTrParser:
				self.ua_with_traces[ua.UserId] = ua
				continue
			if ua.TimeStampFile:
				stat_file = fs_worker.get_fd(ua.TimeStampFile)
			else:
				continue
			if stat_file:
				logger.info("Parse short_msg_file for UA %s",str(ua.UserObject.Number))
				ua.ShortTrParser = tr_parser.short_trace_parser(stat_file)
				ua.ShortTrParser.parse_trace_msg()
				logger.debug("Сlose short_msg_file for UA %s",str(ua.UserObject.Number))
				stat_file.close()
				if ua.ShortTrParser.Status == "Failed":
					logger.error("Parse complite for UA %s. Result: fail.",str(ua.UserObject.Number))
					self.Status = "Failed"
					break
				else:
					logger.info("Parse complite for UA %s. Result: succ.",str(ua.UserObject.Number))
					self.ua_with_traces[ua.UserId] = ua
			else:
				logger.error("Parse complite for UA %s. Result: fail.",str(ua.UserObject.Number))
				self.Status = "Failed"



	def get_first_msg_timestamp(self,*args,**kwargs):
		#args - ua_id для которых выполняется функция.
		#kwargs - параметры искомого сообщения
		#для ответов  - {"msg_type":"response", "method": "INVITE", "resp_code": "200"}
		#для запросов - {"msg_type":"request", "method": "BYE", "resp_code": None}
		result = {}
		result = OrderedDict(result)
		logger.info("Trying to found first msg timestamp")
		logger.info("--| MSG param: type_of_msg - %s; method - %s; resp_code - %s", kwargs["msg_type"], kwargs["method"], kwargs["resp_code"])
		for ua_id in args:
			logger.info("--| Searching first msg timestamp for user with UserId %s",ua_id)
			try:
				ua = self.ua_with_traces[ua_id]				
			except KeyError:
				logger.error("--| Timestamp not found. User with id: %s without traces", ua_id)
				self.Status = "Failed"
				return False
			ua_msg_timestamp = {}
			ua_msg_timestamp = OrderedDict(ua_msg_timestamp)
			for call in ua.ShortTrParser.calls:
				ua_msg_timestamp[call.call_id] = call.get_first_msg_timestamp(**kwargs)
				if ua_msg_timestamp[call.call_id]:
					logger.info("--| Timestamp for msg found. Call: %s", call.call_id)
				else:
					logger.info("--| Timestamp for msg not found. Call: %s", call.call_id)
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
		logger.info("Trying to find msg retarnsmission.")
		logger.info("--| MSG param: type_of_msg - %s; method - %s; resp_code - %s", kwargs["msg_type"], kwargs["method"], kwargs["resp_code"])
		for ua_id in args:
			logger.info("--| Searching retrans for user with id: %s",str(ua_id))
			try:
				ua = self.ua_with_traces[ua_id]				
			except KeyError:
				logger.error("--| Retrans not detected. User with id: %s without traces", ua_id)
				self.Status = "Failed"
				return False		
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
				logger.info("--| Retrans detected. Call: %s",call.call_id)
			else:
				logger.info("--| Retrans not detected. Call: %s",call.call_id)
		return result_seq

	def get_retrans_duration(self, *args,**kwargs):
		result = {}
		result = OrderedDict(result)
		logger.info("Trying to find msg retarnsmission duration.")
		for ua_id in args:
			logger.info("--| Searching msg retarnsmission duration for user with UserId %s",ua_id)
			try:
				ua = self.ua_with_traces[ua_id]				
			except KeyError:
				logger.error("--| Msg retrans duration not found. User with id: %s without traces", ua_id)
				self.Status = "Failed"
				return False
			ua_msg_timestamp = {}
			ua_msg_timestamp = OrderedDict(ua_msg_timestamp)
			for call in ua.ShortTrParser.calls:
				ua_msg_timestamp[call.call_id] = call.get_retrans_duration(**kwargs)
				if ua_msg_timestamp[call.call_id]:
					logger.info("--| Msg retrans duration found. Call: %s", call.call_id)
				else:
					logger.info("--| Msg retrans duration not found. Call: %s", call.call_id)
			result[ua_id] = ua_msg_timestamp
		return result

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