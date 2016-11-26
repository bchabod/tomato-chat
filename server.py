import socket, time, threading, sys, signal, errno
from threading import Thread

if (len(sys.argv) < 2):
    print "Server usage: python server.py PORT"
    sys.exit(0)

MIN_THREADS = 5 # Minimum number of workers at start and at any point
MAX_THREADS = 32 # Maximum number of workers
TOLERANCE = 4 # Minimum difference before resizing the pool, to prevent constant resizing (inertia)

J_MSG = "JOIN_CHATROOM: "
L_MSG = "LEAVE_CHATROOM: "
IP_MSG = "CLIENT_IP: "
P_MSG = "PORT: "
JID_MSG = "JOIN_ID: "
NAME_MSG = "CLIENT_NAME: "
DIS_MSG = "DISCONNECT: "
CHAT_MSG = "CHAT: "
MSG = "MESSAGE: "

PORT = int(sys.argv[1])

class Room():
    def __init__(self):
        # This will contain [CLIENT_NAME, MESSAGE, set(ID)]
        self.messages = []
        self.clients = []

class ChatState():
    def __init__(self):
        self.idCounter = 0
        self.refCounter = 0
        # Associating a name with a ref
        self.roomRefs = {}
        # Associating a ref with a Room object
        self.rooms = {}

class Pool():
    def __init__(self):
        self.lockClients = threading.Lock()
        self.lockState = threading.Lock()
        self.clients = []
        self.workers = []
        self.state = ChatState()
        self.threadCounter = 0
        self.killRequested = False
        for counter in range(MIN_THREADS):
            self.workers.append(Worker(self, self.threadCounter))
            self.workers[counter].start()
            self.threadCounter += 1

    def killWorker(self, worker):
        if (len(self.workers) - self.killedSoFar)  <= MIN_THREADS:
            return False
        if self.killedSoFar >= self.maxKill:
            return False
        if worker.conn is None:
            worker.useless = True # This thread will eventually die now
            self.killedSoFar += 1
            return True
        return False

    def assignClient(self, conn):
        conn.setblocking(0)
        self.lockClients.acquire()
        self.clients.append(conn)

        # Maybe our workers pool needs to be resized, and we need the lock to do so
        difference = len(self.clients) - len(self.workers)
        if abs(difference) > TOLERANCE:
            if difference > 0:
                # Spawn workers
                for counter in range(difference):
                    if len(self.workers) >= MAX_THREADS:
                        break
                    self.workers.append(Worker(self, self.threadCounter))
                    self.workers[-1].start()
                    self.threadCounter += 1
            else:
                # Kill workers
                self.maxKill = abs(difference)
                self.killedSoFar = 0
                self.workers = [w for w in self.workers if not self.killWorker(w)]

        self.lockClients.release()

    def kill(self):
        self.killRequested = True

class Server(Thread):
    def __init__(self, pool):
        Thread.__init__(self)
        self.daemon = True # This thread may die while waiting for a client
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("0.0.0.0", PORT))
        self.pool = pool

    def run(self):
        while True:
            # At most 5 queued clients
            self.server.listen(5)
            (conn, (ip,port)) = self.server.accept()
            # If the server is already overloaded, reject this client
            if len(self.pool.clients) > MAX_THREADS:
                print "Burnout! Server rejected client"
                conn.close()
            else:
                print "Server received client connection and added it to queue"
                self.pool.assignClient(conn)

class Worker(Thread):
    def __init__(self, pool, id):
        Thread.__init__(self)
        self.pool = pool
        self.conn = None
        self.id = id
        self.useless = False
        self.myRooms = []

    def constructReply(self, data):
        reply = "HELO {0}\nIP:{1}\nPort:{2}\nStudentID:{3}\n".format(data, socket.gethostbyname(socket.gethostname()), PORT, 16336617)
        return reply

    def constructJoinReply(self, roomName, roomRef, clientId):
        reply = ("JOINED_CHATROOM: {0}\n"
                "SERVER_IP: {1}\n"
                "PORT: {2}\n"
                "ROOM_REF: {3}\n"
                "JOIN_ID: {4}\n"
               ).format(roomName, socket.gethostbyname(socket.gethostname()), PORT, roomRef, clientId)
        return reply

    def constructLeaveReply(self, roomRef, clientId):
        reply = ("LEFT_CHATROOM: {0}\n"
                "JOIN_ID: {1}\n"
               ).format(roomRef, clientId)
        return reply

    def constructMessage(self, roomRef, clientName, message):
        reply = ("CHAT: {0}\n"
                "CLIENT_NAME: {1}\n"
                "MESSAGE: {2}\n\n"
               ).format(roomRef, clientName, message)
        return reply

    def sendClient(self, content):
        while not (self.pool.killRequested or self.useless):
            try:
                self.conn.send(content)
                print "Thread {0} sent this to client: {1}".format(self.id, content)
                break
            except socket.error as e:
                if e.errno == errno.ECONNRESET:
                    break

    def handleResponse(self, data):
        # Thread pool protocol
        if data == "KILL_SERVICE\n":
            self.pool.kill()
            return True
        elif data.startswith("HELO "):
            self.sendClient(self.constructReply(data[5:].rstrip()))
            return False

        # Chat protocol
        elif data.startswith(J_MSG):
            roomName = data.splitlines()[0][len(J_MSG):]
            clientName = data.splitlines()[3][len(NAME_MSG):]

            # Get client ID, room ref, broadcast and append client to users
            self.pool.lockState.acquire()
            clientId = self.associatedId
            if roomName in self.pool.state.roomRefs:
                roomRef = self.pool.state.roomRefs[roomName]
            else:
                roomRef = self.pool.state.refCounter
                self.pool.state.roomRefs[roomName] = roomRef
                self.pool.state.rooms[roomRef] = Room()
                self.pool.state.refCounter += 1
            room = self.pool.state.rooms[roomRef]
            room.clients.append(clientId)
            if (len(room.clients) > 0):
                joinMessage = "{0} has joined the chatroom".format(clientName)
                room.messages.append([clientName, joinMessage, set(room.clients)])
            self.pool.lockState.release()

            self.myRooms.append((roomRef, clientId))
            self.sendClient(self.constructJoinReply(roomName, roomRef, clientId))
            return False

        elif data.startswith(L_MSG):
            roomRef = int(data.splitlines()[0][len(L_MSG):])
            clientId = int(data.splitlines()[1][len(JID_MSG):])
            clientName = data.splitlines()[2][len(NAME_MSG):]

            # Discard any messages left for us, and leave chatroom
            if (roomRef, clientId) in self.myRooms:
                self.pool.lockState.acquire()
                room = self.pool.state.rooms[roomRef]
                for index in range(len(room.messages)):
                    if clientId in room.messages[index][2]:
                        room.messages[index][2].remove(clientId)
                room.messages[:] = [m for m in room.messages if m[2]]
                room.clients.remove(clientId)
                leaveMessage = "{0} has left the chatroom".format(clientName)
                if (len(room.clients) > 0):
                    room.messages.append([clientName, leaveMessage, set(room.clients)])
                self.pool.lockState.release()

            self.sendClient(self.constructLeaveReply(roomRef, clientId))
            if (roomRef, clientId) in self.myRooms:
                self.sendClient(self.constructMessage(roomRef, clientName, leaveMessage))
                self.myRooms.remove((roomRef, clientId))

            return False

        elif data.startswith(CHAT_MSG):
            roomRef = int(data.splitlines()[0][len(CHAT_MSG):])
            clientId = int(data.splitlines()[1][len(JID_MSG):])
            clientName = data.splitlines()[2][len(NAME_MSG):]
            message = data.splitlines()[3][len(MSG):]

            # Append message so that all threads can read it (including this one)
            self.pool.lockState.acquire()
            room = self.pool.state.rooms[roomRef]
            if (len(room.clients) > 0):
                room.messages.append([clientName, message, set(room.clients)])
            self.pool.lockState.release()
            return False

        elif data.startswith(DIS_MSG):
            clientName = data.splitlines()[2][len(NAME_MSG):]

            # Discard any messages left for us, and leave all chatrooms
            for t in self.myRooms:
                roomRef = t[0]
                clientId = t[1]
                self.pool.lockState.acquire()
                room = self.pool.state.rooms[roomRef]
                for index in range(len(room.messages)):
                    if clientId in room.messages[index][2]:
                        room.messages[index][2].remove(clientId)
                room.messages[:] = [m for m in room.messages if m[2]]
                room.clients.remove(clientId)
                discMessage = "{0} was disconnected".format(clientName)
                if (len(room.clients) > 0):
                    room.messages.append([clientName, discMessage, set(room.clients)])
                self.sendClient(self.constructMessage(roomRef, clientName, discMessage))
                self.pool.lockState.release()

            self.myRooms = []
            return True

    def readMessages(self):
        self.pool.lockState.acquire()
        for t in self.myRooms:
            roomRef = t[0]
            clientId = t[1]
            room = self.pool.state.rooms[roomRef]
            for index in range(len(room.messages)):
                    if clientId in room.messages[index][2]:
                        room.messages[index][2].remove(clientId)
                        self.sendClient(self.constructMessage(roomRef, room.messages[index][0], room.messages[index][1]))
            room.messages[:] = [m for m in room.messages if m[2]]
        self.pool.lockState.release()

    def run(self):
        while not (self.pool.killRequested or self.useless):
            # Try to get a client
            self.pool.lockClients.acquire()
            if (len(self.pool.clients) > 0 and not (self.pool.killRequested or self.useless)):
                self.conn = self.pool.clients.pop(0)
            self.pool.lockClients.release()

            # If we didn't get a client, try again
            if self.conn is None:
                continue

            print "Thread {0} fetched a client".format(self.id)

            self.pool.lockState.acquire()
            self.associatedId = self.pool.state.idCounter
            self.pool.state.idCounter += 1
            self.pool.lockState.release()

            # Serve client
            while not (self.pool.killRequested or self.useless):
                self.readMessages()
                try:
                    data = self.conn.recv(2048).replace("\\n", '\n')
                    print "Thread {0} received data {1}".format(self.id, data.rstrip())
                    if data == "":
                        break
                    if self.handleResponse(data):
                        break
                except socket.error as e2:
                    if e2.errno == errno.ECONNRESET:
                        break

            print "Thread {0} closing client socket".format(self.id)
            self.conn.close()
            self.conn = None

        print "Thread {0} dying".format(self.id)

print "--- Preparing thread pool..."
workerPool = Pool()

print "--- Creating CTRL-C signal handler..."
def signalHandler(signal, frame):
    print "Server received CTRL-C, nuking all threads"
    workerPool.kill()
signal.signal(signal.SIGINT, signalHandler)

print "--- TCP server starting..."
serverThread = Server(workerPool)
serverThread.start()
print "--- Server is ready!"

while True:
    if workerPool.killRequested:
        for worker in workerPool.workers:
            worker.join()
        break
