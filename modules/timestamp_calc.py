import modules.fs_worker as fs_worker

def get_seq_statistics(stat_file):
	fd = fs_worker.get_fd(stat_file)
	if not fd:
		return False
	lines = []
	for line in fd:
		sip_line = []
		line = line.split()
		timestamp = line[2]
		sip_message = " ".join(line[7:])
		sip_direction = str(line[3])
		sip_line.append(timestamp)
		sip_line.append(sip_direction)
		sip_line.append(sip_message)
		lines.append(sip_line)

	diffs=[]
	for index in range(len(lines)-1):
		diff = float(lines[index + 1][0]) - float(lines[index][0])
		diffs.append(diff)



	for index in range(len(lines)):
		if lines[index][1] == "R":
			message_str = "\033[32m<--- RECV"
		elif lines[index][1] == "S":
			message_str = "\033[34m---> SEND"
		message_str += " " + str(lines[index][2])
		message_str += "\033[1;m"
		print(message_str)
		if index < (len(lines) - 1):
			diff = "\033[1;31m"+ "     Diff: +" + str(round(diffs[index],3)) +"\033[1;m"
			print(diff)

