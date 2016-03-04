from socket import *
import sys, time
import pytia

# TODO tidy this up...

if __name__ == "__main__":
    c = pytia.TiAClient('localhost', 9000)
    c.connect()
    if not c.cmd_check_protocol_version():
        print('Protocol version check failed!')
        sys.exit(-1)
    status, dport = c.cmd_get_data_connection_tcp()
    if not c.start_streaming_data_tcp('localhost', dport):
        print('Failed to start streaming data')
        sys.exit(-1)

    time.sleep(0.1)
    for i in range(10):
        packets = c.get_data()
        print('')
        print('Retrieved %d packets' % (len(packets)))
        if len(packets) > 0:
            print('%d signals in packet' % (len(packets[0])))

            for i in range(len(packets[0])):
                print('Signal %d:' % (i+1), packets[0][i])

        print('')

    c.stop_streaming_data()
    c.disconnect()

