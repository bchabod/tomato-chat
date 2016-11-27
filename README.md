# :tomato: Chat server

This is the 3rd assignment for CS4032 (Distributed Systems). The goal was to develop a centralized, multithreaded chat server responding to a simple protocol.

My information:

|Name             |Student ID|Status|
|-----------------|:--------:|:--------:|
|Benoit Chabod    |16336617  |Erasmus  |

## :tomato: Usage

Once again, this application has been tested on SCSS OpenNebula with two nodes.

 * A Debian node hosted the server
 * Netcat clients were used on boot2docker nodes

You need Python 2.X to run this application. If you don't have it, use apt-get, brew, etc. It can be installed easily on a boot2docker node using:

```bash
tce-load -w -i python.tcz
```

### :tomato: Running server

Just clone the repository anywhere, and run this:

```bash
./start.sh PORT
```
The compile.sh script does nothing and was just needed for the automated grading tools.
Please use CTRL-C to kill the server properly, or send him a **KILL_SERVICE** message.

### :tomato: Running a client

Sending TCP packets to the server is very easy using netcat:

```bash
nc IP PORT
```

Here are valid requests for the server:

```
JOIN_CHATROOM: test\nCLIENT_IP: 0\nPORT: 0\nCLIENT_NAME: John
LEAVE_CHATROOM: 0\nJOIN_ID: 0\nCLIENT_NAME: John
CHAT: 0\nJOIN_ID: 0\nCLIENT_NAME: John\nMESSAGE: Wassup\n\n
DISCONNECT: 0\nPORT: 0\nCLIENT_NAME: John
```
Please see the subject for more details on the chat protocol.

## :tomato: Implementation

I've chosen to keep my thread pool architecture from the 2nd assignment, and build the chat server on it.
Essentially, each thread is given a client to treat and manipulates rooms data structures shared inside the pool. Regarding the broadcast, I've chosen to let each thread pass the messages to his own client, using some kind of stack to push messages. They are removed when each active thread (at the moment of the push operation) has read it. See code for more details.
