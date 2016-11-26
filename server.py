import socket, time, threading, sys, signal, errno
from threading import Thread

if (len(sys.argv) < 2):
	print "Server usage: python server.py PORT"
	sys.exit(0)

MIN_THREADS = 4 # Minimum number of workers at start and at any point
MAX_THREADS = 32 # Maximum number of workers
TOLERANCE = 4 # Minimum difference before resizing the pool, to prevent constant resizing (inertia)

PORT = int(sys.argv[1])

class Pool():
    def __init__(self):
        self.lockClients = threading.Lock()
        self.clients = []
        self.workers = []
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
            # At most 4 queued clients
            self.server.listen(4)
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

    def constructReply(self, data):
        reply = "HELO {0}\nIP:{1}\nPort:{2}\nStudentID:{3}\n".format(data, socket.gethostbyname(socket.gethostname()), PORT, 16336617)
        return reply

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

            # Serve client
            while not (self.pool.killRequested or self.useless):
                try:
                    data = self.conn.recv(2048)
                    print "Thread {0} received data {1}".format(self.id, data.rstrip())
                    if data == "KILL_SERVICE\n":
                        self.pool.kill()
                    elif data.startswith("HELO "):
                        while not (self.pool.killRequested or self.useless):
                            try:
                                self.conn.send(self.constructReply(data[5:].rstrip()))
                                break
                            except socket.error as e:
                                if e.errno == errno.ECONNRESET:
                                    break
                    elif data == "":
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
