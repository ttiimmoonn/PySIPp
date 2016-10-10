import modules.fs_worker as fs_worker
import re 

class sip_flow():
	def __init__(self,stat_file):
		#Подключаем файл со статистикой
		self.Fd=fs_worker.get_fd(stat_file)
		self.Calls={}
		#разделяем звонки
		self.separate_calls()
		#сортируем сообщения по времени
		self.sort_call_messages()

	def separate_calls(self):
		#Example
		#2016-08-08      16:21:24.073266 1470648084.073266       S       BG:sip-t:05398bf15cd4b7ea:05398bf1647de1b5      CSeq:1 INVITE   SIP/2.0 100 Trying
		for line in self.Fd:
			#На данном этапе необходимо разделить все вызовы по call_id
			stat_line = line.split()
			if stat_line[4] in self.Calls:
				#Если уже создан массив под данный call_id,
				#просто добавляем сообщение в массив
				self.Calls[stat_line[4]].append(stat_line)
			else:
				#Если массива нет, то создаём его и добавляем сообщение.
				self.Calls[stat_line[4]]=[]
				self.Calls[stat_line[4]].append(stat_line)

	def sort_call_messages(self):
		#Далее нужно отсортировать массивы вызовов, по времени
		for call in self.Calls:
			#Сортируем сообщения в списках по timestamp
			self.Calls[call].sort(key=self.call_sort_key)
	
	def call_sort_key(self,sorting_list):
		return float(sorting_list[2])

	def print_flow(self):
		for call in self.Calls:
			for indx,msg in enumerate(self.Calls[call]):
				if indx < len(self.Calls[call]) - 1:
					diff = float(self.Calls[call][indx + 1][2]) - float(self.Calls[call][indx][2])
				if msg[3] == "R":
					message_str = str(msg[1]+" ") + "│ ◀────RECV───── "
				elif msg[3] == "S":
					message_str = str(msg[1]+" ") + "│ ─────SEND────▶ "
				message_str += " ".join(msg[7:]).strip()
				message_str = re.sub(" sip:(.*)@([\w.:;/=\s]*)","", message_str)
				message_str = re.sub(" SIP/2.0","", message_str).strip()
				print(message_str)
				if indx < len(self.Calls[call]) - 1:
					print("\033[1;31m"+ "Diff: + " +  "%0.3f" % (float(round(diff,3))) + "\033[1;m   │")
			print()
			print()




def get_seq_statistics(stat_file):
	new_flow = sip_flow(stat_file)
	new_flow.print_flow()