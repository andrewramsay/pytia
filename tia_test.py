from socket import *
import sys
import pytia

# TODO tidy this up...

finished = False
def receiver():
    global finished
    dsd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
    dsd.connect(('localhost', dport))
    print 'Receiving data...'
    while not finished:
        msg = dsd.recv(1000)
        if len(msg) < 1:
            break
        print 'MSG:', msg
    print 'Finished receiving data'
    dsd.close()

if __name__ == "__main__":
    c = pytia.TiAClient('localhost', 9000)
    c.connect()
    if not c.cmd_check_protocol_version():
        print 'Protocol version check failed!'
        sys.exit(-1)
    status, dport = c.cmd_get_data_connection_tcp()
    if not c.start_streaming_data_tcp('localhost', dport):
        print 'Failed to start streaming data'
        sys.exit(-1)

    for i in range(10):
        d = c.get_data()
        print ''
        print '%d signals in packet' % (len(d))

        for i in range(len(d)):
            print 'Signal %d:' % (i+1), d[i]

    c.stop_streaming_data()
    c.disconnect()

