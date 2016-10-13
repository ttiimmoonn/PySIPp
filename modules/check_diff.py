import modules.fs_worker as fs_worker
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
		print("[DEBUG] Closing statistic files.")
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
				print("[ERROR] Can't find statistic file for User with id: \"", user_id, "\". Try set WriteStat attr in json description for that UA")
				self.close_stat_files()
				self.Status = "Failed"
				return False
			except ValueError:
				print("[ERROR] User ID must have  integer value. {Bad Value: ",user_id,"}")
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
						print("[ERROR] User ID must have float value. {Bad Value: ",find_timestamp,"}")
						return False
			stat_file.seek(0,0)
			if not find_timestamp:
				print("[ERROR] Can't find method", method, "in statistic file for user with id", user_id)
				self.close_stat_files()
				self.Status = "Failed"
				return False

		for idx, timestamp in enumerate(self.timestamps):
			if idx == len(self.timestamps) - 1:
				break
			msg_diff = self.timestamps[idx + 1] - timestamp
			if msg_diff < diff + 0.5 and msg_diff > diff - 0.5:
				print("--> [DEBUG] Require timer is",round(diff,1))
				print("--> [DEBUG] Current timer is",round(msg_diff,1))
				print("--> [DEBUG] Diff between UA", idx + 1, "and", idx, "success")
			else:
				print("[ERROR] Diff for method:",method,"not equal", diff, "Current diff = ", round(msg_diff,1))
				self.Status = "Failed"

		if self.Status == "Failed":
			return False
		else:
			self.Status == "Complite"
			return True






