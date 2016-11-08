import modules.fs_worker as fs_worker
import logging
logger = logging.getLogger("tester")
class diff_time():
	def __init__(self,test):
		self.diff_array = {}
		self.Status = None
		self.timestamps = []
		for ua in test.CompliteUA:
			if ua.StatFile:
				stat_file = fs_worker.get_fd(ua.StatFile)
			else:
				continue
			if stat_file:
				self.diff_array[int(ua.UserId)] = stat_file
			else:
				return False
	
	def close_stat_files(self):
		logger.info("Closing statistic files.")
		for file_indx in self.diff_array:
			try:
				self.diff_array[file_indx].close()
			except:
				pass

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
				logger.info("Can't find statistic file for User with id: \"", user_id, "\". Try set WriteStat attr in json description for that UA")
				self.close_stat_files()
				self.Status = "Failed"
				return False
			except ValueError:
				logger.info("User ID must have  integer value. {Bad Value: ",user_id,"}")
				self.close_stat_files()
				self.Status = "Failed"
				return False
			#Example  CANCEL 2016-10-10 09:57:47.231259 1476068267.231259
			for line in stat_file:
				print
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
				logger.error("Can't find method %s in statistic file for user with id %d",method,user_id)
				self.close_stat_files()
				self.Status = "Failed"
				return False

		for idx, timestamp in enumerate(self.timestamps):
			if idx == len(self.timestamps) - 1:
				break
			msg_diff = self.timestamps[idx + 1] - timestamp
			if msg_diff < diff + 0.5 and msg_diff > diff - 0.5:
				logger.info("--> Require timer is %f",round(diff,1))
				logger.info("--> Current timer is %f",round(msg_diff,1))
				logger.info("--> Diff between UA %d and %d success",idx + 1,idx)
			else:
				logger.error("Diff for method: %s not equal %f. Current diff = %f",method,diff,round(msg_diff,1))
				self.Status = "Failed"

		if self.Status == "Failed":
			return False
		else:
			self.Status == "Complite"
			return True






