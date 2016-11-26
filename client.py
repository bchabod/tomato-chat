import socket, sys, time

if (len(sys.argv) < 4):
	print "Client usage: python client.py H|K IP PORT"
	sys.exit(0)

HOST = sys.argv[2]
PORT = int(sys.argv[3])

serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Try to connect to server
try:
	serverSocket.connect((HOST, PORT))
except IOError as e:
	print "Server unreachable"
	sys.exit(0)

# Send appropriate message
if (sys.argv[1]=="H"):
	serverSocket.send("HELO IMPRESSIVE_TEST\n")
	data = serverSocket.recv(2048)
	print "Client received data:", data
	time.sleep(5)
else:
	serverSocket.send("KILL_SERVICE\n")

#Close socket
serverSocket.close()
